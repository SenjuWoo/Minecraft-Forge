"""`packcompat`: an overlay pack that rewrites a resource pack's newer-format models for an older game.

Resource packs that support several releases sometimes ship block and item models in a model format newer than
the game reads (seen: a pack's models for blocks added after 1.21.1, loaded by a 1.21.1 pack that backports those
blocks). The older game rejects the whole file and the block renders as the missing model. This command reads the
pack, applies the overlays the target game would apply, rewrites only the models that need it and writes them into
a small separate pack that goes directly above the original in the pack list. The original pack is never changed.

Rules (each was a rejected field in 1.21.1 and is written by 26.3):
- element `rotation` as Euler `x`/`y`/`z` -> one `axis` + `angle` (the largest component; others dropped, reported)
- `angle` outside -45..45 or off the 22.5 step -> nearest allowed angle (reported)
- `shade_direction_override: "up"` -> `shade: false`; other directions dropped (reported)
- `light_emission` -> NeoForge `neoforge_data.block_light` (ignored by other loaders)
- texture objects `{"sprite": ..., ...}` (texture variables and faces) -> the sprite string
- with `--mod-jar`: a pack blockstate that uses property names the mod's own blockstate does not have (a pack
  written for a snapshot of the block) is replaced by the mod's blockstate. A mod blockstate keyed only by ""
  lists no properties, so it gives no verdict.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import zipfile

from .resources import facts, pack_mcmeta, version_key

ALLOWED_ANGLES = (-45.0, -22.5, 0.0, 22.5, 45.0)
MARKER = "mcforge-packcompat.json"
MAX_PACK_BYTES = 1024 * 1024 * 1024
MAX_ENTRY_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 200_000
MODEL = re.compile(r"assets/([a-z0-9_.-]+)/models/([a-z0-9_./-]+)\.json")
BLOCKSTATE = re.compile(r"assets/([a-z0-9_.-]+)/blockstates/([a-z0-9_./-]+)\.json")
VERIFIED = "1.21.1"


def _safe_name(name: str) -> bool:
    """Pack entry names are data: no absolute paths, drive letters, backslashes or parent steps."""
    return bool(name) and not name.startswith("/") and "\\" not in name and ":" not in name \
        and ".." not in name.split("/")


class _Source:
    """A resource pack as a ZIP or a folder; every read is bounded."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zip = None
        if self.path.is_file():
            if self.path.stat().st_size > MAX_PACK_BYTES:
                raise ValueError("Pack exceeds 1 GiB inspection limit")
            self.zip = zipfile.ZipFile(self.path)
            infos = self.zip.infolist()
            if len(infos) > MAX_ENTRIES:
                raise ValueError("Pack has too many entries")
            self.names = {info.filename: info for info in infos if not info.is_dir()}
        elif self.path.is_dir():
            self.names = {}
            for file in self.path.rglob("*"):
                if file.is_file():
                    self.names[file.relative_to(self.path).as_posix()] = file
                    if len(self.names) > MAX_ENTRIES:
                        raise ValueError("Pack has too many files")
        else:
            raise ValueError(f"Pack not found: {self.path}")

    def read(self, name: str) -> bytes:
        entry = self.names[name]
        if self.zip is not None:
            if entry.file_size > MAX_ENTRY_BYTES:
                raise ValueError(f"{name} exceeds the inspection limit")
            with self.zip.open(entry) as stream:
                return stream.read(MAX_ENTRY_BYTES + 1)[:MAX_ENTRY_BYTES]
        if entry.stat().st_size > MAX_ENTRY_BYTES:
            raise ValueError(f"{name} exceeds the inspection limit")
        return entry.read_bytes()

    def json(self, name: str):
        return json.loads(self.read(name).decode("utf-8-sig"))

    def close(self):
        if self.zip is not None:
            self.zip.close()


def _in_range(value, target: tuple[int, int]) -> bool | None:
    """Format range check: int, [min, max], {min_inclusive, max_inclusive}; a bound may be [major, minor]."""
    def key(bound):
        if isinstance(bound, list) and bound and all(isinstance(part, int) for part in bound):
            return (bound[0], bound[1] if len(bound) > 1 else 0)
        if isinstance(bound, int):
            return (bound, 0)
        return None
    if isinstance(value, dict):
        low, high = key(value.get("min_inclusive")), key(value.get("max_inclusive"))
    elif isinstance(value, list) and len(value) == 2 and all(isinstance(part, int) for part in value):
        low, high = key(value[0]), key(value[1])
    else:
        low = high = key(value)
    if low is None or high is None:
        return None
    # A plain-number upper bound covers every minor version of that format (max 97 covers 97.1).
    upper = high if isinstance(value, list) and isinstance(value[1], list) or isinstance(value, dict) and isinstance(
        value.get("max_inclusive"), list) else (high[0], 1 << 30)
    return low <= target <= upper


def active_overlays(meta: dict, target: tuple[int, int], new_schema: bool) -> tuple[list[str], list[dict]]:
    """Overlay folders the target applies, in the game's order (a later folder wins over earlier ones and over the
    root; 1.21.1 CompositePackResources). NeoForge's `neoforge:overlays` entries follow the vanilla ones."""
    active, skipped = [], []
    for section in ("overlays", "neoforge:overlays"):
        for entry in ((meta.get(section) or {}).get("entries") or []):
            if not isinstance(entry, dict):
                continue
            directory = entry.get("directory")
            if not isinstance(directory, str) or not re.fullmatch(r"[-_a-zA-Z0-9.]+", directory):
                skipped.append({"directory": directory, "why": "invalid directory name"})
                continue
            if new_schema and ("min_format" in entry or "max_format" in entry):
                applies = _in_range({"min_inclusive": entry.get("min_format"), "max_inclusive": entry.get("max_format")}, target)
            elif "formats" in entry:
                applies = _in_range(entry["formats"], target)
            else:
                skipped.append({"directory": directory, "why": "no `formats` field the target reads"})
                continue
            if applies:
                active.append(directory)
            else:
                skipped.append({"directory": directory, "why": "format range excludes the target" if applies is False
                                else "unreadable format range"})
    return active, skipped


def fix_element(element: dict, notes: list[str]) -> set[str]:
    fixes = set()
    if "shade_direction_override" in element:
        direction = element.pop("shade_direction_override")
        if direction == "up":
            element["shade"] = False
        else:
            notes.append(f"shade_direction_override {direction!r} dropped (default shading)")
        fixes.add("shade_direction_override")
    if "light_emission" in element:
        element.setdefault("neoforge_data", {}).setdefault("block_light", element.pop("light_emission"))
        fixes.add("light_emission")
    rotation = element.get("rotation")
    if isinstance(rotation, dict):
        if "axis" not in rotation:
            parts = [(axis, float(rotation.get(axis, 0) or 0)) for axis in ("x", "y", "z")]
            nonzero = [part for part in parts if part[1] != 0.0]
            for axis in ("x", "y", "z"):
                rotation.pop(axis, None)
            rotation["axis"], rotation["angle"] = max(nonzero, key=lambda part: abs(part[1])) if nonzero else ("y", 0.0)
            if len(nonzero) > 1:
                notes.append(f"Euler rotation {dict(nonzero)} reduced to {rotation['axis']}={rotation['angle']}")
            fixes.add("euler_rotation")
        try:
            angle = float(rotation.get("angle", 0))
        except (TypeError, ValueError):
            angle = 0.0
        if angle not in ALLOWED_ANGLES:
            rotation["angle"] = min(ALLOWED_ANGLES, key=lambda allowed: abs(allowed - angle))
            notes.append(f"angle {angle:g} clamped to {rotation['angle']:g}")
            fixes.add("angle_clamped")
    for face in (element.get("faces") or {}).values():
        if isinstance(face, dict) and isinstance(face.get("texture"), dict):
            face["texture"] = face["texture"].get("sprite", "#missing")
            fixes.add("texture_object")
    return fixes


def fix_model(model: dict, notes: list[str]) -> set[str]:
    fixes = set()
    textures = model.get("textures")
    if isinstance(textures, dict):
        for key, value in list(textures.items()):
            if isinstance(value, dict):
                textures[key] = value.get("sprite", "#missing")
                fixes.add("texture_object")
    for element in model.get("elements") or []:
        if isinstance(element, dict):
            fixes |= fix_element(element, notes)
    return fixes


def state_properties(blockstate: dict) -> set[str]:
    """Property names a blockstate uses (variant keys and multipart `when`, including OR/AND)."""
    names = set()
    for key in (blockstate.get("variants") or {}):
        names |= {part.split("=")[0] for part in key.split(",") if "=" in part}
    for part in blockstate.get("multipart") or []:
        stack = [part.get("when") or {}]
        while stack:
            when = stack.pop()
            if isinstance(when, list):
                stack.extend(when)
                continue
            for key, value in when.items():
                if key in ("OR", "AND"):
                    stack.extend(value if isinstance(value, list) else [value])
                else:
                    names.add(key)
    return names


def _options_entry(game_dir: Path, pack: Path, compat_name: str) -> dict:
    """The options.txt `resourcePacks` change, read-only. The list runs bottom to top: a later entry wins."""
    above = f"file/{pack.name}"
    entry = f"file/{compat_name}"
    result = {"entry": entry, "place_after": above,
              "how": f"in options.txt `resourcePacks`, put \"{entry}\" right after \"{above}\" (later entries are higher), "
                     "or enable it above the pack in the Resource Packs screen; this command never edits options.txt"}
    options = game_dir / "options.txt"
    try:
        text = options.read_text(encoding="utf-8", errors="replace") if options.is_file() else ""
    except OSError:
        text = ""
    line = re.search(r"(?m)^resourcePacks:(\[.*\])\s*$", text)
    if line:
        try:
            packs = json.loads(line[1])
        except ValueError:
            packs = None
        if isinstance(packs, list):
            result["current"] = f"resourcePacks:{line[1]}"
            if entry in packs:
                result["already_listed"] = True
                result["above_pack"] = above in packs and packs.index(entry) > packs.index(above)
            else:
                wanted = list(packs)
                wanted.insert(wanted.index(above) + 1 if above in wanted else len(wanted), entry)
                result["suggested"] = "resourcePacks:" + json.dumps(wanted, separators=(",", ":"))
    return result


def _prepare_destination(out: Path) -> None:
    """Replace a previous packcompat output; refuse a folder that holds anything else."""
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"{out} exists and is not a folder")
        if (out / MARKER).is_file():
            shutil.rmtree(out)
        elif any(out.iterdir()):
            raise ValueError(f"{out} exists and was not written by packcompat; choose an empty or new folder")
    out.mkdir(parents=True, exist_ok=True)


def build(pack: Path, minecraft: str, *, out: Path | None = None, instance: Path | None = None, apply: bool = False,
          mod_jars: list[Path] | None = None) -> dict:
    from .workbench import guard_output
    pack = Path(os.path.abspath(pack))
    if (out is None) == (instance is None):
        raise ValueError("Pass exactly one of --out DIR or --instance INSTANCE")
    if apply and instance is None:
        raise ValueError("--apply writes into an instance; use it with --instance")
    row = facts(minecraft)
    target = tuple(row["resource_pack_format"])
    raw = row.get("pack_version_raw")
    new_schema = isinstance(raw, dict) and "resource_major" in raw
    stem = pack.stem if pack.is_file() else pack.name
    compat_name = f"{stem}-compat"
    game = None
    if instance is not None:
        from .launchers import game_dir
        game = game_dir(Path(instance))
        destination = game / "resourcepacks" / compat_name
    else:
        destination = Path(os.path.abspath(out))
        try:
            guard_output(destination)
        except ValueError as error:
            raise ValueError(f"{error}. To write into a launcher instance use --instance INSTANCE --apply "
                             "(writes only resourcepacks/<pack>-compat)") from None
    if destination == pack or pack in destination.parents:
        raise ValueError("The output must not be the pack itself or inside it")

    source = _Source(pack)
    jars = []
    try:
        names = [name for name in source.names if _safe_name(name)]
        unsafe = sorted(set(source.names) - set(names))[:20]
        try:
            meta = source.json("pack.mcmeta") if "pack.mcmeta" in source.names else {}
        except ValueError:
            meta = {}
        overlays, skipped = active_overlays(meta if isinstance(meta, dict) else {}, target, new_schema)
        effective: dict[str, str] = {}
        for prefix in ["", *(folder + "/" for folder in overlays)]:
            for name in names:
                if name.startswith(prefix):
                    relative = name[len(prefix):]
                    if MODEL.fullmatch(relative) or BLOCKSTATE.fullmatch(relative):
                        effective[relative] = name
        rewritten, unreadable, outputs = [], [], {}
        for relative, name in sorted(effective.items()):
            if not MODEL.fullmatch(relative):
                continue
            try:
                model = source.json(name)
            except (ValueError, UnicodeDecodeError):
                unreadable.append(name)
                continue
            notes: list[str] = []
            try:
                fixes = fix_model(model, notes) if isinstance(model, dict) else set()
            except (TypeError, ValueError, AttributeError) as error:
                # one malformed model (a non-numeric rotation, say) is listed and skipped; the run goes on
                unreadable.append(f"{name}: {error}")
                continue
            if fixes:
                rewritten.append({"path": relative, "from": name, "fixes": sorted(fixes), "fallbacks": notes})
                outputs[relative] = model
        blockstates = []
        for jar_path in mod_jars or []:
            jars.append((Path(jar_path).name, zipfile.ZipFile(jar_path)))
        if jars:
            for relative, name in sorted(effective.items()):
                if not BLOCKSTATE.fullmatch(relative):
                    continue
                for label, jar in jars:
                    try:
                        mine = json.loads(jar.read(relative).decode("utf-8-sig"))
                    except KeyError:
                        continue
                    except (ValueError, UnicodeDecodeError):
                        break
                    try:
                        theirs = source.json(name)
                    except (ValueError, UnicodeDecodeError):
                        unreadable.append(name)
                        break
                    ours, pack_props = state_properties(mine), state_properties(theirs)
                    if ours and pack_props - ours:
                        blockstates.append({"path": relative, "mod_jar": label, "pack_properties": sorted(pack_props),
                                            "mod_properties": sorted(ours)})
                        outputs[relative] = mine
                    break
    finally:
        source.close()
        for _, jar in jars:
            jar.close()

    warnings = []
    if not row.get("exact"):
        warnings.append(f"Minecraft {minecraft} is not in the facts table; pack format borrowed from {row.get('borrowed_from')}")
    if version_key(minecraft) != version_key(VERIFIED):
        warnings.append(f"The rules were checked on {VERIFIED} (rejects these fields) against 26.3 (writes them). On "
                        f"{minecraft} some of them may already be valid or not yet in use; check the target's own models.")
    if unsafe:
        warnings.append(f"Ignored {len(unsafe)} pack entries with unsafe names, e.g. {unsafe[0]!r}")
    result = {"pack": str(pack), "minecraft": minecraft, "pack_format": list(target), "overlays_active": overlays,
              "overlays_skipped": skipped, "models_checked": sum(1 for key in effective if MODEL.fullmatch(key)),
              "rewritten": rewritten, "blockstates": blockstates, "unreadable": unreadable[:50],
              "fallbacks": sum(len(item["fallbacks"]) for item in rewritten), "out": str(destination),
              "written": False, "warnings": warnings}
    if not outputs:
        result["next"] = "Nothing to rewrite: the pack's effective models already use a format this target reads."
        return result
    if instance is not None:
        result["options_txt"] = _options_entry(game, pack, compat_name)
        if not apply:
            result["next"] = "Plan only; nothing was written. Close the game and rerun with --apply to write the overlay pack."
            return result
    _prepare_destination(destination)
    for relative, data in sorted(outputs.items()):
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    mcmeta = pack_mcmeta(minecraft, "resource", f"{stem}: models rewritten for Minecraft {minecraft} (packcompat)")
    (destination / "pack.mcmeta").write_text(json.dumps(mcmeta, indent=2) + "\n", encoding="utf-8", newline="\n")
    (destination / MARKER).write_text(json.dumps({"tool": "packcompat", "pack": pack.name, "minecraft": minecraft,
                                                  "files": sorted(outputs)}, indent=2) + "\n", encoding="utf-8", newline="\n")
    result["written"] = True
    result["files"] = len(outputs)
    if instance is None:
        result["options_txt"] = {"entry": f"file/{destination.name}", "place_after": f"file/{pack.name}",
                                 "how": "copy the folder into the instance's resourcepacks/ and enable it directly above the original pack"}
    result["next"] = "Enable the overlay directly above the original pack, then count `Unable to load model` lines in the client log before and after."
    return result
