"""Standalone project used by the procedural asset checks."""
import json
import struct
import zlib
from pathlib import Path
import tempfile
import unittest

from mcforge import assets
from mcforge.workbench import init_project


def png_info(data: bytes) -> tuple[int, int, int]:
    assert data.startswith(b"\x89PNG\r\n\x1a\n"), "PNG signature"
    width, height = struct.unpack(">II", data[16:24])
    return width, height, data[25]


def png_raw(data: bytes) -> bytes:
    offset, chunks = 8, []
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        tag = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        if tag == b"IDAT":
            chunks.append(chunk)
        offset += 12 + length
    return zlib.decompress(b"".join(chunks))


class AssetTests(unittest.TestCase):
    def setUp(self):
        base = Path(__file__).resolve().parents[1] / "local/test-temp"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mod = self.root / "mod"
        init_project(self.mod, "garden", "dev.example.garden", "Garden")

    def test_default_assets_create_block_item_models_lang_and_loot(self):
        result = assets.generate_assets(self.mod)
        self.assertEqual([row["id"] for row in result["generated"]], ["example_block", "example_item"])
        self.assertEqual(len(result["generated"]), 2)
        base = self.mod / "src/main/resources/assets/garden"
        blockstate = json.loads((base / "blockstates/example_block.json").read_text())
        self.assertEqual(blockstate["variants"][""]["model"], "garden:block/example_block")
        block_model = json.loads((base / "models/block/example_block.json").read_text())
        self.assertEqual(block_model["textures"]["all"], "garden:block/example_block")
        item_model = json.loads((base / "models/item/example_item.json").read_text())
        self.assertEqual(item_model["textures"]["layer0"], "garden:item/example_item")
        self.assertTrue((self.mod / "src/main/resources/data/garden/loot_table/blocks/example_block.json").is_file())
        lang = json.loads((base / "lang/en_us.json").read_text())
        self.assertEqual(lang["block.garden.example_block"], "Example Block")
        self.assertEqual(lang["item.garden.example_item"], "Example Item")
        self.assertEqual(lang["itemGroup.garden"], "Example Mod Tab")
        manifest = json.loads((self.mod / "mcforge-assets.json").read_text())
        self.assertEqual(manifest["toolkit_version"], __import__("mcforge").__version__)
        self.assertIn("block:example_block", manifest["assets"])

    def test_block_and_item_pngs_are_valid_deterministic_and_shaped(self):
        block = assets.texture_bytes("example_block", "block", "stone", 16)
        item = assets.texture_bytes("example_item", "item", "gem", 16)
        self.assertEqual(png_info(block), (16, 16, 6))
        self.assertEqual(png_info(item), (16, 16, 6))
        self.assertEqual(block, assets.texture_bytes("example_block", "block", "stone", 16))
        self.assertNotEqual(block, assets.texture_bytes("different_block", "block", "stone", 16))
        raw = png_raw(block)
        for row in range(16):
            start = row * (16 * 4 + 1) + 1
            self.assertTrue(all(raw[start + column * 4 + 3] == 255 for column in range(16)))
        self.assertIn(b"\x00\x00\x00\x00", png_raw(item))

    def test_existing_files_are_skipped_unless_force(self):
        texture = self.mod / "src/main/resources/assets/garden/textures/block/example_block.png"
        texture.parent.mkdir(parents=True)
        texture.write_bytes(b"sentinel")
        result = assets.generate_assets(self.mod)
        self.assertEqual(texture.read_bytes(), b"sentinel")
        self.assertIn("src/main/resources/assets/garden/textures/block/example_block.png", result["skipped"])
        assets.generate_assets(self.mod, force=True)
        self.assertNotEqual(texture.read_bytes(), b"sentinel")
        self.assertEqual(png_info(texture.read_bytes()), (16, 16, 6))

    def test_language_file_is_merged_without_losing_existing_keys(self):
        lang_path = self.mod / "src/main/resources/assets/garden/lang/en_us.json"
        lang_path.write_text(json.dumps({"custom.key": "Keep"}), encoding="utf-8")
        assets.generate_assets(self.mod)
        lang = json.loads(lang_path.read_text())
        self.assertEqual(lang["custom.key"], "Keep")
        self.assertIn("block.garden.example_block", lang)

    def test_invalid_ids_kinds_and_sizes_are_rejected(self):
        for spec in (("../evil", "block"), ("Bad Id", "block"), ("ok", "structure")):
            with self.subTest(spec=spec):
                with self.assertRaises(ValueError):
                    assets.generate_assets(self.mod, [spec])
        with self.assertRaises(ValueError):
            assets.generate_assets(self.mod, size=15)
        with self.assertRaises(ValueError):
            assets.generate_assets(self.mod, style="neon")

    def test_auto_style_uses_id_words(self):
        self.assertEqual(assets.resolve_style("auto", "oak_plank"), "wood")
        self.assertEqual(assets.resolve_style("auto", "ruby_gem"), "gem")
        self.assertEqual(assets.resolve_style("auto", "iron_ingot"), "metal")
        self.assertEqual(assets.resolve_style("auto", "moss_leaf"), "organic")
        self.assertEqual(assets.resolve_style("auto", "void_rune"), "arcane")
        self.assertEqual(assets.resolve_style("auto", "plain_block"), "stone")
        self.assertEqual(assets.resolve_style("gem", "oak_plank"), "gem")


if __name__ == "__main__":
    unittest.main()
