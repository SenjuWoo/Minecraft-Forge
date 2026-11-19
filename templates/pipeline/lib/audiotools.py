"""Audio post-processing: a staged sound set -> the mod, and a validator for what the mod ships.

Generators (AssetForge, ComfyUI, synthesis) write into a staging folder that is never inside the mod
(default asset-pipeline/audio/export; a running job must not change mod sources while verify runs). Then

    python -I build_assets.py audio export [STAGING]     # write the processed set into assets/<mod>/sounds/<mob>/
    python -I build_assets.py audio --validate           # check what the mod ships

The class of a staged file is its first folder (voice/, sfx/, music/; anything else counts as sfx). Each class is
processed by mob/sounds.py AUDIO (defaults below): a 35 Hz high-pass (generated takes carry sub-audible rumble that
eats the level), silence trimmed at both ends, RMS levelling (short sounds cannot be loudness-normalised), a soft
limiter under -1 dBFS, mono OGG Vorbis (stereo plays without distance attenuation; a jukebox disc too). Files land
flat in sounds/<mob>/ under their own stem; only files whose bytes changed are written.

The validator fails on a file that is silent, clips, is shorter than 50 ms or is not mono Vorbis, and on variants
of one sound (step_1, step_2 ...) that are copies (correlation above 0.98). Generators have returned the same take
for every variant of a batch; one run per variant index with its own seed avoids it.

Needs ffmpeg on PATH (decode, filters, Vorbis). Machine checks only: report the set as unheard until a person has
listened.
"""
from __future__ import annotations

import re
import shutil
import subprocess

import numpy as np

from . import paths

SR = 44100
FOLDER = paths.SOUNDS / paths.MOB
STAGING = paths.PIPE / "audio" / "export"
DEFAULTS = {
    "voice": {"highpass": 35, "trim_db": -50, "rms_db": -24.0, "gain_db": (-14.0, 15.0), "ceiling_db": -1.0},
    "sfx": {"highpass": 35, "trim_db": -50, "rms_db": -22.0, "gain_db": (-14.0, 15.0), "ceiling_db": -1.0},
    "music": {"highpass": 0, "trim_db": None, "rms_db": None, "gain_db": (0.0, 0.0), "ceiling_db": -1.0},
}
EXTENSIONS = (".ogg", ".wav", ".flac", ".mp3")
VARIANT = re.compile(r"(.+?)_v?\d+$")


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("audio: ffmpeg is not on PATH (needed to decode, filter and encode)")
    return exe


def classes() -> dict:
    from mob import sounds as MS
    custom = getattr(MS, "AUDIO", {})
    return {name: DEFAULTS.get(name, DEFAULTS["sfx"]) | dict(custom.get(name, {})) for name in set(DEFAULTS) | set(custom)}


def decode(path, highpass: float = 0) -> np.ndarray:
    args = [_ffmpeg(), "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR)]
    if highpass:
        args += ["-af", f"highpass=f={highpass}"]
    raw = subprocess.run(args + ["-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).astype(np.float64)


def encode(x: np.ndarray, quality: int = 5) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    done = subprocess.run([_ffmpeg(), "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                           "-fflags", "+bitexact", "-flags:a", "+bitexact", "-map_metadata", "-1",
                           "-c:a", "libvorbis", "-q:a", str(quality), "-f", "ogg", "-"], input=pcm, capture_output=True)
    if done.returncode:
        raise RuntimeError("ffmpeg could not encode Vorbis: " + done.stderr.decode(errors="replace")[-300:])
    return done.stdout


def trim(x: np.ndarray, db: float, keep_s: float = 0.01) -> np.ndarray:
    if not len(x):
        return x
    loud = np.flatnonzero(np.abs(x) > 10 ** (db / 20))
    if not len(loud):
        return x
    pad = int(keep_s * SR)
    return x[max(0, loud[0] - pad): loud[-1] + pad + 1]


def level(x: np.ndarray, rms_db: float | None, gain_db=(-14.0, 15.0), ceiling_db: float = -1.0) -> np.ndarray:
    """Gain to one RMS level (clamped), then a soft-knee limiter under the ceiling so raised transients never clip."""
    y = x
    if rms_db is not None and len(x):
        rms = float(np.sqrt(np.mean(x ** 2))) or 1e-9
        y = x * 10 ** (float(np.clip(rms_db - 20 * np.log10(rms), *gain_db)) / 20)
    ceiling = 10 ** (ceiling_db / 20)
    knee = 0.6 * ceiling
    a = np.abs(y)
    over = a > knee
    a[over] = knee + (ceiling - knee) * np.tanh((a[over] - knee) / (ceiling - knee))
    return np.sign(y) * a


def process(path, options: dict) -> bytes:
    x = decode(path, options.get("highpass") or 0)
    if options.get("trim_db") is not None:
        x = trim(x, options["trim_db"])
    return encode(level(x, options.get("rms_db"), tuple(options.get("gain_db", (0.0, 0.0))), options.get("ceiling_db", -1.0)))


def export(staging) -> int:
    staging = (paths.PIPE / staging).resolve() if staging else STAGING
    if not staging.is_dir():
        print(f"audio: no staging folder {staging}")
        return 2
    if FOLDER.resolve() == staging or staging in FOLDER.resolve().parents or FOLDER.resolve() in staging.parents:
        print("audio: the staging folder must be outside the mod")
        return 2
    opts = classes()
    sources = [p for p in sorted(staging.rglob("*")) if p.suffix.lower() in EXTENSIONS]
    seen, written = {}, 0
    for src in sources:
        kind = src.relative_to(staging).parts[0] if len(src.relative_to(staging).parts) > 1 else "sfx"
        if src.stem in seen:
            print(f"audio: {src.stem} is staged twice ({seen[src.stem]} and {src}); stems must be unique")
            return 1
        seen[src.stem] = src
        data = process(src, opts.get(kind, opts["sfx"]))
        out = FOLDER / f"{src.stem}.ogg"
        if not out.exists() or out.read_bytes() != data:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            written += 1
    print(f"audio export: {len(sources)} file(s) processed, {written} written into {FOLDER}")
    return 0


def channels(path) -> int | None:
    head = path.read_bytes()[:4096]
    at = head.find(b"\x01vorbis")
    return head[at + 11] if at >= 0 and len(head) > at + 11 else None


def copies(files) -> list[str]:
    groups: dict[str, list] = {}
    for f in files:
        m = VARIANT.match(f.stem)
        if m:
            groups.setdefault(m.group(1), []).append(f)
    out = []
    for stem, group in sorted(groups.items()):
        if len(group) < 2:
            continue
        xs = [decode(f) for f in group]
        worst, pair = 0.0, None
        for i in range(len(xs)):
            for j in range(i + 1, len(xs)):
                n = min(len(xs[i]), len(xs[j]))
                a, b = xs[i][:n], xs[j][:n]
                if n and a.std() > 0 and b.std() > 0:
                    c = float(np.corrcoef(a, b)[0, 1])
                    if c > worst:
                        worst, pair = c, (group[i].name, group[j].name)
        if worst > 0.98:
            out.append(f"{stem}: variants {pair[0]} and {pair[1]} are copies (correlation {worst:.3f}); regenerate one with its own seed")
    return out


def validate(args) -> int:
    files = sorted(FOLDER.glob("*.ogg")) if FOLDER.is_dir() else []
    errs = []
    for f in files:
        if channels(f) != 1:
            errs.append(f"{f.name}: not mono Vorbis (channels {channels(f)})")
            continue
        x = decode(f)
        if len(x) < 0.05 * SR:
            errs.append(f"{f.name}: {len(x) / SR:.3f} s (under 50 ms)")
        elif np.max(np.abs(x)) < 0.05:
            errs.append(f"{f.name}: silent (peak {np.max(np.abs(x)):.3f})")
        elif np.mean(np.abs(x) > 0.999) > 0.001:
            errs.append(f"{f.name}: clips")
    errs += copies(files)
    for e in errs[:60]:
        print("AUDIO ERROR:", e)
    print(f"audio validate: {len(files)} file(s), {len(errs)} error(s)")
    return 1 if errs else 0


def run(args) -> int:
    rest = list(getattr(args, "rest", None) or [])
    if rest and rest[0] == "export":
        return export(rest[1] if len(rest) > 1 else None)
    if getattr(args, "validate", False):
        return 0                             # cli runs validate() next
    print("audio: `audio export [STAGING]` writes the processed set into the mod; `audio --validate` checks it")
    return 0
