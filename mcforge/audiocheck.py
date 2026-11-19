"""One report for a project's sounds: sounds.json keys, registered SoundEvent ids, files and their format.

Reads OGG headers with the standard library (channels, sample rate, duration from
the last page's granule position). Loudness (mean/peak dB) comes from FFmpeg's
volumedetect when `ffmpeg` is on PATH; without it that column is "not measured".
Registered ids are found by scanning Java sources for SoundEvent registrations:
a heuristic, reported as such.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess

MAX_SOUND = 64 * 1024 * 1024
JAVA_PATTERNS = (
    # NeoForge/Forge holders: DeferredHolder<SoundEvent, SoundEvent> X = SOUNDS.register("id", ...) or a helper("id").
    re.compile(r"(?:DeferredHolder|RegistryObject|Supplier|Holder)\s*<\s*SoundEvent[^=;]*=\s*[\w.]+\s*\(\s*\"([a-z0-9_./-]+)\""),
    # Direct construction: SoundEvent.createVariableRangeEvent(ResourceLocation.fromNamespaceAndPath(MODID, "id")), SoundEvent.of(Identifier.of(...)).
    re.compile(r"SoundEvent\s*\.\s*(?:createVariableRangeEvent|createFixedRangeEvent|of)\s*\(\s*(?:new\s+)?(?:ResourceLocation|Identifier)"
               r"(?:\s*\.\s*(?:fromNamespaceAndPath|of|tryBuild))?\s*\(\s*[^,()]+,\s*\"([a-z0-9_./-]+)\""),
    re.compile(r"(?:SOUND_EVENTS|SOUNDS)\s*\.\s*register\s*\(\s*\"([a-z0-9_./-]+)\""),
)


def ogg_info(path: Path) -> dict:
    """Channels, sample rate and duration of an Ogg Vorbis file from its headers and last page."""
    data = path.read_bytes() if path.stat().st_size <= MAX_SOUND else None
    if data is None:
        return {"error": "file exceeds 64 MiB"}
    if not data.startswith(b"OggS"):
        return {"error": "not an Ogg file"}
    start = data.find(b"\x01vorbis")
    if start < 0 or start + 16 > len(data):
        return {"error": "no Vorbis identification header (Minecraft plays Ogg Vorbis only)"}
    channels = data[start + 11]
    rate = struct.unpack_from("<I", data, start + 12)[0]
    last = data.rfind(b"OggS")
    granule = struct.unpack_from("<q", data, last + 6)[0] if last + 14 <= len(data) else -1
    duration = round(granule / rate, 3) if rate and granule >= 0 else None
    return {"channels": channels, "sample_rate": rate, "duration": duration}


def loudness(path: Path) -> dict | None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    done = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=120)
    mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", done.stderr)
    peak = re.search(r"max_volume:\s*(-?[\d.]+) dB", done.stderr)
    if not mean or not peak:
        return {"error": "ffmpeg could not measure this file"}
    return {"mean_db": float(mean.group(1)), "peak_db": float(peak.group(1))}


def _sound_entries(entry) -> list[dict]:
    result = []
    for sound in entry.get("sounds", []) if isinstance(entry, dict) else []:
        result.append({"name": sound, "type": "file"} if isinstance(sound, str) else
                      {"name": sound.get("name", ""), "type": sound.get("type", "file"), "stream": bool(sound.get("stream"))})
    return result


def _fingerprint(path: Path, decode: bool) -> str:
    """Bytes hash; with ffmpeg, the hash of the decoded audio (a re-encoded copy has other bytes, same samples)."""
    ffmpeg = shutil.which("ffmpeg") if decode else None
    if ffmpeg:
        done = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-map", "0:a", "-ac", "1", "-f", "md5", "-"],
                              capture_output=True, text=True)
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    return "sha256=" + hashlib.sha256(path.read_bytes()).hexdigest()


def _copies(events: dict, files_on_disk: dict, mod_id: str, decode: bool) -> list[str]:
    """Variants of one event that are the same audio: the game picks among copies, so the event never varies.
    Generators have returned one take for every variant of a batch (one run per variant with its own seed fixes it)."""
    out = []
    for event, entry in events.items():
        paths = []
        for sound in _sound_entries(entry):
            namespace, _, path = sound["name"].partition(":") if ":" in sound["name"] else (mod_id, "", sound["name"])
            if sound["type"] != "event" and namespace == mod_id and path in files_on_disk:
                paths.append(path)
        if len(paths) < 2:
            continue
        seen: dict[str, str] = {}
        for path in paths:
            key = _fingerprint(files_on_disk[path], decode)
            if key in seen:
                out.append(f"{event!r}: variants {seen[key]} and {path} are the same audio; regenerate one with its own seed")
            else:
                seen[key] = path
    return out


def check_audio(project: Path, *, measure: bool = True) -> dict:
    project = Path(project).resolve()
    lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8-sig"))
    mod_id = lock["mod_id"]
    resources = [project / root for root in ("src/main/resources", "src/generated/resources") if (project / root).is_dir()]
    sounds_json = next((root / "assets" / mod_id / "sounds.json" for root in resources if (root / "assets" / mod_id / "sounds.json").is_file()), None)
    events = json.loads(sounds_json.read_text(encoding="utf-8-sig")) if sounds_json else {}
    lang = {}
    for root in resources:
        path = root / "assets" / mod_id / "lang/en_us.json"
        if path.is_file():
            lang.update(json.loads(path.read_text(encoding="utf-8-sig")))
    registered = set()
    for source in (project / "src").rglob("*.java"):
        text = source.read_text(encoding="utf-8", errors="replace")
        for pattern in JAVA_PATTERNS:
            registered.update(pattern.findall(text))
    files_on_disk = {}
    for root in resources:
        folder = root / "assets" / mod_id / "sounds"
        if folder.is_dir():
            for path in folder.rglob("*.ogg"):
                files_on_disk[path.relative_to(folder).with_suffix("").as_posix()] = path
    problems, warnings, files, used = [], [], [], set()
    if sounds_json is None:
        (problems if registered else warnings).append(f"assets/{mod_id}/sounds.json is missing")
    for event, entry in events.items():
        if event not in registered:
            warnings.append(f"sounds.json event {event!r} has no SoundEvent registration found in Java (heuristic scan)")
        subtitle = entry.get("subtitle") if isinstance(entry, dict) else None
        if subtitle and subtitle not in lang:
            warnings.append(f"subtitle key {subtitle!r} of {event!r} is missing from en_us.json")
        for sound in _sound_entries(entry):
            if sound["type"] == "event":
                continue
            namespace, _, path = sound["name"].partition(":") if ":" in sound["name"] else (mod_id, "", sound["name"])
            if namespace != mod_id:
                continue
            used.add(path)
            if path not in files_on_disk:
                problems.append(f"{event!r} plays {namespace}:{path}, but assets/{mod_id}/sounds/{path}.ogg does not exist")
    for event in sorted(registered - set(events)):
        problems.append(f"SoundEvent {mod_id}:{event} is registered but sounds.json has no entry: it will play nothing")
    for path, file in sorted(files_on_disk.items()):
        info = ogg_info(file)
        row = {"file": f"assets/{mod_id}/sounds/{path}.ogg", "referenced": path in used, **info}
        if "error" in info:
            problems.append(f"{row['file']}: {info['error']}")
        else:
            if info["channels"] != 1:
                warnings.append(f"{row['file']}: {info['channels']} channels; positional sounds must be mono (stereo plays without attenuation)")
            if info["sample_rate"] not in (44100, 48000):
                warnings.append(f"{row['file']}: {info['sample_rate']} Hz; 44100 or 48000 Hz is usual")
            if info["duration"] is not None and info["duration"] > 20:
                streamed = any(s.get("stream") for e in events.values() for s in _sound_entries(e) if s["name"].rpartition(":")[2] == path)
                if not streamed:
                    warnings.append(f"{row['file']}: {info['duration']} s; set \"stream\": true for long sounds")
            if measure:
                measured = loudness(file)
                row["loudness"] = measured if measured is not None else "not measured (ffmpeg not on PATH)"
        if path not in used:
            warnings.append(f"{row['file']} is not referenced by sounds.json")
        files.append(row)
    problems.extend(_copies(events, files_on_disk, mod_id, measure))
    levels = [row["loudness"]["mean_db"] for row in files if isinstance(row.get("loudness"), dict) and "mean_db" in row["loudness"]]
    if len(levels) > 1 and max(levels) - min(levels) > 9:
        warnings.append(f"mean loudness spans {min(levels):.1f} to {max(levels):.1f} dB; match the set (RMS plus a limiter)")
    return {"project": str(project), "sounds_json": str(sounds_json) if sounds_json else None, "events": len(events),
            "registered_ids": sorted(registered), "files": files, "problems": problems, "warnings": warnings,
            "status": "problems" if problems else "ok",
            "note": "Registered ids come from a source scan; heard-in-game is still unverified until someone listens."}
