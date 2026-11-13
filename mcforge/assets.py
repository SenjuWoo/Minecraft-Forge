"""Free, deterministic procedural assets for a generated NeoForge project.

The generator uses only the Python standard library: PNG bytes are written with
zlib/struct, and resource/data JSON follows the Minecraft 1.21.1 layout. It
never downloads art or calls a paid service. Existing files are skipped unless
``force`` is set; the language file is merged instead of replaced.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import re
import struct
import zlib

from . import __version__

ASSET_ID = re.compile(r"[a-z0-9_]{2,64}")
STYLES = ("auto", "stone", "wood", "gem", "metal", "organic", "arcane")
KINDS = ("block", "item")

# Coarse palettes: shadow, base, light, highlight. Deliberately low-saturation
# so generated placeholder art sits next to vanilla textures without screaming.
PALETTES = {
    "stone": ((74, 74, 80), (104, 104, 110), (134, 134, 140), (164, 164, 170)),
    "wood": ((88, 58, 36), (124, 84, 50), (158, 112, 68), (190, 144, 96)),
    "gem": ((20, 92, 112), (34, 150, 170), (72, 210, 218), (176, 248, 244)),
    "metal": ((86, 96, 112), (128, 140, 158), (178, 190, 204), (230, 238, 246)),
    "organic": ((48, 88, 40), (76, 126, 54), (112, 170, 78), (168, 214, 120)),
    "arcane": ((60, 34, 100), (96, 56, 150), (142, 88, 204), (210, 158, 248)),
}


def _clamp(value: int) -> int:
    return 0 if value < 0 else 255 if value > 255 else value


def _png(width: int, height: int, rows: list[bytearray]) -> bytes:
    """Write an RGBA PNG without Pillow or any external process."""
    raw = b"".join(b"\x00" + bytes(row) for row in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def _seed(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(":".join(parts).encode("utf-8")).digest()[:8], "big")


def resolve_style(style: str, asset_id: str) -> str:
    """Resolve ``auto`` from the asset id; an explicit style is never changed."""
    if style != "auto":
        return style
    value = asset_id.lower()
    checks = (
        ("wood", ("wood", "log", "plank", "bark", "beam")),
        ("gem", ("gem", "diamond", "ruby", "emerald", "crystal", "shard", "amethyst")),
        ("metal", ("iron", "steel", "copper", "gold", "metal", "ingot", "silver", "bronze")),
        ("organic", ("leaf", "grass", "seed", "food", "flesh", "meat", "plant", "moss", "berry")),
        ("arcane", ("rune", "arcane", "magic", "ender", "soul", "void", "spirit")),
    )
    for name, words in checks:
        if any(word in value for word in words):
            return name
    return "stone"


def _display_name(asset_id: str) -> str:
    return " ".join(part.capitalize() for part in asset_id.split("_"))


def _block_texture(seed: int, style: str, size: int) -> bytes:
    rng = random.Random(seed)
    palette = PALETTES[style]
    coarse = [[rng.random() for _ in range(4)] for _ in range(4)]
    rows: list[bytearray] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            fx = x * 3 / max(1, size - 1)
            fy = y * 3 / max(1, size - 1)
            ix, iy = min(2, int(fx)), min(2, int(fy))
            tx, ty = fx - ix, fy - iy
            top = coarse[iy][ix] * (1 - tx) + coarse[iy][ix + 1] * tx
            bottom = coarse[iy + 1][ix] * (1 - tx) + coarse[iy + 1][ix + 1] * tx
            value = top * (1 - ty) + bottom * ty + rng.uniform(-0.12, 0.12)
            if x in (0, size - 1) or y in (0, size - 1):
                value -= 0.20
            index = 0 if value < 0.34 else 1 if value < 0.55 else 2 if value < 0.78 else 3
            red, green, blue = palette[index]
            shift = rng.randint(-5, 5)
            row += bytes((_clamp(red + shift), _clamp(green + shift), _clamp(blue + shift), 255))
        rows.append(row)
    for _ in range(max(2, size // 4)):
        x, y = rng.randrange(size), rng.randrange(size)
        offset = rng.choice((-22, 22))
        pixel = rows[y][x * 4:x * 4 + 3]
        rows[y][x * 4:x * 4 + 3] = bytes(_clamp(channel + offset) for channel in pixel)
    return _png(size, size, rows)


def _inside(style: str, dx: float, dy: float, radius: float) -> bool:
    if style == "metal":
        return abs(dx) <= radius and abs(dy) <= radius * 0.55
    if style == "organic":
        return (dx / radius) ** 2 + (dy / (radius * 1.15)) ** 2 <= 1
    if style == "arcane":
        return abs(dx) + abs(dy) <= radius * 1.05 or (abs(dx) <= max(1, radius * 0.12) and abs(dy) <= radius)
    return abs(dx) + abs(dy) <= radius * 1.1


def _edge(style: str, dx: float, dy: float, radius: float) -> bool:
    if style == "metal":
        return abs(abs(dx) - radius) < 1.1 or abs(abs(dy) - radius * 0.55) < 1.1
    if style == "organic":
        return (dx / radius) ** 2 + (dy / (radius * 1.15)) ** 2 > 0.78
    return abs(dx) + abs(dy) > radius * 0.92


def _item_texture(seed: int, style: str, size: int) -> bytes:
    rng = random.Random(seed)
    palette = PALETTES[style]
    centre = (size - 1) / 2
    radius = size * 0.38
    rows: list[bytearray] = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            dx, dy = x - centre, y - centre
            if not _inside(style, dx, dy, radius):
                row += b"\x00\x00\x00\x00"
                continue
            if _edge(style, dx, dy, radius):
                index = 0
            elif dx + dy < -radius * 0.45:
                index = 3
            else:
                index = 1 + (1 if (x + y) % 5 == 0 else 0)
            red, green, blue = palette[index]
            shift = rng.randint(-4, 4)
            row += bytes((_clamp(red + shift), _clamp(green + shift), _clamp(blue + shift), 255))
        rows.append(row)
    return _png(size, size, rows)


def texture_bytes(asset_id: str, kind: str, style: str, size: int) -> bytes:
    """Return a deterministic RGBA PNG for one asset."""
    resolved = resolve_style(style, asset_id)
    seed = _seed(asset_id, kind, resolved, str(size))
    return _block_texture(seed, resolved, size) if kind == "block" else _item_texture(seed, resolved, size)


def _json(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _loot_table(mod_id: str, asset_id: str) -> dict:
    return {
        "type": "minecraft:block",
        "pools": [{
            "rolls": 1,
            "bonus_rolls": 0,
            "entries": [{"type": "minecraft:item", "name": f"{mod_id}:{asset_id}"}],
            "conditions": [{"condition": "minecraft:survives_explosion"}],
        }],
    }


def generate_assets(project: Path, specs: list[tuple[str, str]] | None = None, *,
                    style: str = "auto", size: int = 16, force: bool = False) -> dict:
    """Generate textures, models, blockstates, lang and block loot tables.

    ``specs`` is a list of ``(asset_id, kind)`` pairs. With no specs, the
    generated MDK example block and item are dressed. Existing files are
    skipped unless ``force`` is set; the language file is always merged.
    """
    project = Path(project).resolve()
    if style not in STYLES:
        raise ValueError("style must be one of: " + ", ".join(STYLES))
    if size not in (16, 32):
        raise ValueError("size must be 16 or 32 pixels")
    lock_path = project / "mcforge-project.json"
    if not lock_path.is_file():
        raise ValueError(f"Not a Minecraft Forge project (missing {lock_path.name})")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read project lock: {error}") from error
    mod_id = lock.get("mod_id") if isinstance(lock, dict) else None
    if not isinstance(mod_id, str) or not ASSET_ID.fullmatch(mod_id):
        raise ValueError("Project lock has no valid mod_id")
    specs = list(specs) if specs is not None else [("example_block", "block"), ("example_item", "item")]
    if not specs:
        raise ValueError("At least one asset is required")
    assets_root = project / "src/main/resources/assets" / mod_id
    data_root = project / "src/main/resources/data" / mod_id
    # Folder names follow the project's Minecraft version (plural loot_tables before 1.21, item definitions from 1.21.4).
    from .resources import facts
    layout = facts(str(lock.get("minecraft") or "1.21.1"))["layout"]
    lang_path = assets_root / "lang/en_us.json"
    lang: dict[str, str] = {}
    if lang_path.is_file():
        try:
            existing = json.loads(lang_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Existing language file is not valid JSON: {lang_path}") from error
        if not isinstance(existing, dict):
            raise ValueError("Existing language file must contain a JSON object")
        lang = existing
    created: list[str] = []
    skipped: list[str] = []
    generated: list[dict] = []
    for asset_id, kind in specs:
        if not isinstance(asset_id, str) or not ASSET_ID.fullmatch(asset_id):
            raise ValueError(f"Invalid asset id: {asset_id!r}; use [a-z0-9_] 2-64 characters")
        if kind not in KINDS:
            raise ValueError(f"Invalid asset kind: {kind!r}; use block or item")
        resolved = resolve_style(style, asset_id)
        texture = texture_bytes(asset_id, kind, resolved, size)
        files: list[tuple[Path, bytes]] = []
        if kind == "block":
            files.extend([
                (assets_root / "blockstates" / f"{asset_id}.json",
                 _json({"variants": {"": {"model": f"{mod_id}:block/{asset_id}"}}})),
                (assets_root / "models/block" / f"{asset_id}.json",
                 _json({"parent": "minecraft:block/cube_all", "textures": {"all": f"{mod_id}:block/{asset_id}"}})),
                (assets_root / "models/item" / f"{asset_id}.json",
                 _json({"parent": f"{mod_id}:block/{asset_id}"})),
                (assets_root / "textures/block" / f"{asset_id}.png", texture),
                (data_root / layout["loot_table"] / "blocks" / f"{asset_id}.json", _json(_loot_table(mod_id, asset_id))),
            ])
            if layout["item_definitions"]:
                files.append((assets_root / "items" / f"{asset_id}.json",
                              _json({"model": {"type": "minecraft:model", "model": f"{mod_id}:block/{asset_id}"}})))
            lang[f"block.{mod_id}.{asset_id}"] = _display_name(asset_id)
        else:
            files.extend([
                (assets_root / "models/item" / f"{asset_id}.json",
                 _json({"parent": "minecraft:item/generated", "textures": {"layer0": f"{mod_id}:item/{asset_id}"}})),
                (assets_root / "textures/item" / f"{asset_id}.png", texture),
            ])
            if layout["item_definitions"]:
                files.append((assets_root / "items" / f"{asset_id}.json",
                              _json({"model": {"type": "minecraft:model", "model": f"{mod_id}:item/{asset_id}"}})))
            lang[f"item.{mod_id}.{asset_id}"] = _display_name(asset_id)
        record = {"id": asset_id, "kind": kind, "style": resolved,
                  "texture_sha256": hashlib.sha256(texture).hexdigest(), "files": [], "skipped": []}
        for path, data in files:
            relative = path.relative_to(project).as_posix()
            if path.exists() and not force:
                skipped.append(relative)
                record["skipped"].append(relative)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            created.append(relative)
            record["files"].append(relative)
        generated.append(record)
    lang_data = _json(lang)
    if not lang_path.is_file() or lang_path.read_bytes() != lang_data:
        lang_path.parent.mkdir(parents=True, exist_ok=True)
        lang_path.write_bytes(lang_data)
        created.append(lang_path.relative_to(project).as_posix())
    manifest_path = project / "mcforge-assets.json"
    manifest: dict = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            raise ValueError(f"Existing asset manifest is not valid JSON: {manifest_path}") from error
        if not isinstance(manifest, dict):
            raise ValueError("Existing asset manifest must contain a JSON object")
    manifest["toolkit_version"] = __version__
    manifest["style"] = style
    manifest["size"] = size
    manifest.setdefault("assets", {})
    for record in generated:
        manifest["assets"][f"{record['kind']}:{record['id']}"] = {
            "style": record["style"],
            "texture_sha256": record["texture_sha256"],
            "files": record["files"] + record["skipped"],
        }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "project": str(project),
        "mod_id": mod_id,
        "style": style,
        "size": size,
        "generated": generated,
        "created": created,
        "skipped": skipped,
        "manifest": str(manifest_path),
        "next": "Replace generated placeholder art when the feature is final; then run verify PROJECT.",
    }
