"""Rebuild mcforge/data/minecraft_versions.json from Mojang's official files.

Maintainer action; requires network. For every release since 1.14 it reads the
version manifest (required Java) and the client JAR's own ``version.json`` and
file listing, using HTTP range requests so no JAR is downloaded in full. The
pack formats and folder names in the output are therefore read from the game,
not remembered. Nothing downloaded is executed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
AGENT = "Minecraft-Forge (version facts maintenance)"
FIRST = "1.14"


def fetch(url: str, start: int | None = None, end: int | None = None) -> bytes:
    headers = {"User-Agent": AGENT}
    if start is not None:
        headers["Range"] = f"bytes={start}-{end}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as response:
        return response.read()


class RemoteFile(io.RawIOBase):
    """Seekable read-only view of a remote file; zipfile reads only what it needs."""

    def __init__(self, url: str, size: int):
        self.url, self.size, self.position = url, size, 0
        self.cache: dict[tuple[int, int], bytes] = {}

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def read(self, count=-1):
        if count is None or count < 0:
            count = self.size - self.position
        count = min(count, self.size - self.position)
        if count <= 0:
            return b""
        for (start, end), data in self.cache.items():
            if start <= self.position and self.position + count <= end:
                chunk = data[self.position - start:self.position - start + count]
                self.position += count
                return chunk
        # Read ahead generously: the central directory and its tail are requested back to back.
        end = min(self.size, self.position + max(count, 256 * 1024))
        data = fetch(self.url, self.position, end - 1)
        self.cache[(self.position, end)] = data
        chunk = data[:count]
        self.position += count
        return chunk


def has(names: set[str], prefix: str) -> bool:
    return any(name.startswith(prefix) for name in names)


def facts(row: dict) -> tuple[str, dict]:
    meta = json.loads(fetch(row["url"]))
    client = meta["downloads"]["client"]
    with zipfile.ZipFile(RemoteFile(client["url"], client["size"])) as archive:
        names = set(archive.namelist())
        version = json.loads(archive.read("version.json"))
        # A shapeless recipe present in every release shows that version's recipe JSON shape.
        recipe_name = next(name for name in ("data/minecraft/recipe/flint_and_steel.json", "data/minecraft/recipes/flint_and_steel.json") if name in names)
        sample = json.loads(archive.read(recipe_name))
    pack = version.get("pack_version")
    if isinstance(pack, int):
        resource = data = [pack, 0]
    else:
        resource = [pack.get("resource_major", pack.get("resource")), pack.get("resource_minor", 0)]
        data = [pack.get("data_major", pack.get("data")), pack.get("data_minor", 0)]
    data_root, asset_root = "data/minecraft/", "assets/minecraft/"
    plural = has(names, data_root + "loot_tables/")
    layout = {
        "loot_table": "loot_tables" if plural else "loot_table",
        "recipe": "recipes" if has(names, data_root + "recipes/") else "recipe",
        "advancement": "advancements" if has(names, data_root + "advancements/") else "advancement",
        "structure": "structures" if has(names, data_root + "structures/") else "structure",
        "block_tags": "tags/blocks" if has(names, data_root + "tags/blocks/") else "tags/block",
        "item_tags": "tags/items" if has(names, data_root + "tags/items/") else "tags/item",
        "entity_tags": "tags/entity_types" if has(names, data_root + "tags/entity_types/") else "tags/entity_type",
        "item_definitions": has(names, asset_root + "items/"),
        "equipment": ("equipment" if has(names, asset_root + "equipment/")
                      else "models/equipment" if has(names, asset_root + "models/equipment/") else None),
        "armor_textures": ("textures/entity/equipment" if has(names, asset_root + "textures/entity/equipment/")
                           else "textures/models/armor"),
        "post_effects": ("post_effect" if has(names, asset_root + "post_effect/")
                         else "shaders/post" if has(names, asset_root + "shaders/post/") else None),
        "core_shaders": has(names, asset_root + "shaders/core/"),
        "worldgen_data": has(names, data_root + "worldgen/"),
        "enchantment_data": has(names, data_root + "enchantment/"),
        "recipe_result_key": "id" if "id" in sample["result"] else "item",
        "recipe_ingredient": "string" if isinstance(sample["ingredients"][0], str) else "object",
    }
    return row["id"], {"released": row["releaseTime"][:10], "java_major": meta.get("javaVersion", {}).get("majorVersion"),
                       "client_sha1": client["sha1"], "resource_pack_format": resource, "data_pack_format": data,
                       "pack_version_raw": pack, "layout": layout}


def main() -> int:
    manifest = json.loads(fetch(MANIFEST))
    releases = [row for row in manifest["versions"] if row["type"] == "release"]
    releases = releases[:[row["id"] for row in releases].index(FIRST) + 1]
    with ThreadPoolExecutor(6) as pool:
        versions = dict(pool.map(facts, releases))
    output = ROOT / "mcforge/data/minecraft_versions.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({"schema": 1, "source": MANIFEST, "generated": manifest["latest"],
                                  "note": "Read from each release's client JAR (version.json and file listing).",
                                  "versions": versions}, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"versions": len(versions), "newest": releases[0]["id"], "oldest": releases[-1]["id"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
