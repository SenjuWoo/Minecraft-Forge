"""Offline coverage for the 1.0 multi-loader toolkit: targets, scaffolds, content, packs, launchers, libraries."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from mcforge import __main__ as cli
from mcforge import content, javagen, launchers, libs, packs, pixelart, preview, project, resources, shapes, targets
from mcforge.scaffold import init_project
from mcforge.verification import _steps
from mcforge.workbench import add_load_tests

ROOT = Path(__file__).resolve().parents[1]
ALL_TARGETS = ("neoforge-1.21.1", "neoforge-26.3", "fabric-1.20.1", "fabric-1.21.1", "fabric-26.3", "forge-1.20.1", "forge-26.3")


class Temp(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / "local" / "test-temp"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def make(self, target_id, mod_id="probe"):
        path = self.root / target_id
        init_project(path, mod_id, "dev.example." + mod_id, "Probe Mod", target_id=target_id)
        return path

    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = cli.main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()


class TargetTests(Temp):
    def test_registry_lists_every_bundled_target_with_verified_templates(self):
        rows = targets.list_targets()
        self.assertEqual(sorted(row["id"] for row in rows), sorted(ALL_TARGETS))
        self.assertEqual([row["id"] for row in rows if row["default"]], ["neoforge-1.21.1"])
        for row in rows:
            targets.select_target(target_id=row["id"])  # hash check passes

    def test_selection_by_loader_and_version(self):
        self.assertEqual(targets.select_target()["id"], "neoforge-1.21.1")
        self.assertEqual(targets.select_target("fabric")["id"], "fabric-1.21.1")
        self.assertEqual(targets.select_target("forge", "26.3")["id"], "forge-26.3")
        with self.assertRaisesRegex(ValueError, "--fetch"):
            targets.select_target("forge", "1.19.2")
        with self.assertRaisesRegex(ValueError, "Unknown loader"):
            targets.select_target("rift")
        with self.assertRaisesRegex(ValueError, "Unknown target"):
            targets.select_target(target_id="neoforge-9.9")

    def test_every_target_scaffolds_with_pinned_reproducible_build_inputs(self):
        expected_java = {"neoforge-1.21.1": 21, "neoforge-26.3": 25, "fabric-1.20.1": 17, "fabric-1.21.1": 21, "fabric-26.3": 25,
                         "forge-1.20.1": 17, "forge-26.3": 25}
        for target_id in ALL_TARGETS:
            with self.subTest(target=target_id):
                path = self.make(target_id)
                lock = json.loads((path / "mcforge-project.json").read_text())
                info = project.inspect_project(path)
                self.assertEqual(info["errors"], [])
                self.assertEqual(info["lock_status"], "locked")
                self.assertEqual(lock["target_id"], target_id)
                self.assertEqual(lock["java_major"], expected_java[target_id])
                self.assertIn("distributionSha256Sum=", (path / "gradle/wrapper/gradle-wrapper.properties").read_text())
                self.assertNotIn("foojay", (path / "settings.gradle").read_text())
                self.assertIn("org.gradle.daemon=false", (path / "gradle.properties").read_text())
                java = list((path / "src/main/java/dev/example/probe").glob("*.java"))
                self.assertTrue(java, "template sources must move into the chosen package")
                self.assertFalse((path / "src/main/java/com").exists())
                self.assertFalse((path / ".github").exists())

    def test_family_specific_pins_and_gradle_jdk(self):
        fabric = project.inspect_project(self.make("fabric-1.20.1"))
        self.assertEqual(fabric["family"], "fabric-loom")
        self.assertEqual(fabric["target"]["loom"], "1.19.4")
        self.assertEqual(fabric["gradle_java_major"], 25)
        forge = project.inspect_project(self.make("forge-1.20.1"))
        self.assertEqual((forge["family"], forge["target"]["forge_version"], forge["target"]["forgegradle"]), ("forge-fg", "47.4.28", "6.0.54"))
        self.assertEqual(forge["gradle_java_major"], 17)
        modern = project.inspect_project(self.make("forge-26.3"))
        self.assertEqual(modern["target"]["forgegradle"], "7.0.40")
        self.assertNotIn("parchment_mappings", project.inspect_project(self.make("neoforge-26.3"))["target"])

    def test_forge_version_change_is_drift(self):
        path = self.make("forge-1.20.1")
        properties = path / "gradle.properties"
        properties.write_text(properties.read_text().replace("forge_version=47.4.28", "forge_version=47.4.29"))
        info = project.inspect_project(path)
        self.assertEqual(info["lock_status"], "drift")
        self.assertEqual(info["drift"][0]["field"], "forge_version")

    def test_fabric_project_gets_official_test_wiring_and_own_license(self):
        path = self.make("fabric-1.21.1")
        build = (path / "build.gradle").read_text()
        self.assertIn("configureTests", build)
        self.assertIn('modId = "probe_tests"', build)
        self.assertTrue((path / "src/gametest/java/dev/example/probe/testing/LoadSmokeTest.java").is_file())
        metadata = json.loads((path / "src/main/resources/fabric.mod.json").read_text())
        self.assertEqual(metadata["license"], "All-Rights-Reserved")
        self.assertNotIn("contact", metadata)
        self.assertEqual(metadata["entrypoints"]["main"], ["dev.example.probe.ExampleMod"])
        modern = (self.make("fabric-26.3") / "src/gametest/java/dev/example/probe/testing/LoadSmokeTest.java").read_text()
        self.assertIn("net.fabricmc.fabric.api.gametest.v1.GameTest", modern)

    def test_loader_version_must_match_its_minecraft_line(self):
        with self.assertRaisesRegex(ValueError, "does not belong"):
            init_project(self.root / "bad", "probe", "dev.example.probe", "Probe", target_id="neoforge-26.3", loader_version="21.1.265")
        with self.assertRaisesRegex(ValueError, "GameTest starter"):
            init_project(self.root / "bad2", "probe", "dev.example.probe", "Probe", target_id="fabric-1.21.1", with_tests=True)

    def test_verification_steps_follow_the_build_system(self):
        self.assertEqual(_steps("fabric-loom", {"game_tests": "fabric"}, False), [("tests-build", ["build"])])
        self.assertEqual(_steps("forge-fg", {}, True), [("build", ["build"]), ("server-load", ["runGameTestServer"])])
        self.assertEqual(_steps("neoforge-mdg", {"target_id": "neoforge-26.3", "minecraft": "26.3"}, True)[-1], ("server-load", ["runGameTestServer"]))
        with self.assertRaisesRegex(ValueError, "tests PROJECT"):
            _steps("neoforge-mdg", {"target_id": "neoforge-1.21.1", "minecraft": "1.21.1"}, True)
        with self.assertRaisesRegex(ValueError, "tests PROJECT"):
            _steps("neoforge-mdg", {"target_id": "neoforge-1.21.4", "minecraft": "1.21.4"}, True)
        self.assertEqual(_steps("neoforge-mdg", {"minecraft": "1.21.5"}, True)[-1][0], "server-load")

    def test_load_tests_command_adds_one_smoke_test(self):
        path = self.make("neoforge-1.21.1")
        result = add_load_tests(path)
        self.assertEqual(result["status"], "added")
        lock = json.loads((path / "mcforge-project.json").read_text())
        self.assertTrue(lock["with_tests"])
        self.assertFalse(lock["starter"])
        testing = path / "src/gameTest/java/dev/example/probe/testing"
        self.assertEqual(sorted(p.name for p in testing.iterdir()), ["LoadSmokeTest.java", "TestMod.java"])
        self.assertEqual(add_load_tests(path)["status"], "already_configured")
        with self.assertRaisesRegex(ValueError, "before Minecraft 1.21.5"):
            add_load_tests(self.make("forge-26.3"))


class ContentTests(Temp):
    KINDS = [("block", "ruby_block", {}), ("item", "ruby", {}), ("food", "honey_bun", {}), ("sword", "bone_sword", {}),
             ("toolset", "ruby", {}), ("armor", "ruby", {}), ("furniture", "oak_chair", {}), ("furniture", "brass_lamp", {"shape": "lamp"}),
             ("mob", "cave_boar", {}), ("mob", "bone_golem", {"shape": "biped", "hostile": True})]

    def test_every_kind_on_every_kit_target_writes_java_and_assets(self):
        for target_id in ("neoforge-1.21.1", "fabric-1.21.1", "fabric-1.20.1", "forge-1.20.1"):
            path = self.make(target_id)
            for kind, name, options in self.KINDS:
                with self.subTest(target=target_id, kind=kind, name=name):
                    result = content.add_content(path, kind, name, **options)
                    self.assertEqual(result["java"]["status"], "generated")
                    for created in result["created"]:
                        self.assertTrue((path / created).is_file())
            java = {p.name for p in path.rglob("*.java")}
            self.assertTrue({"CaveBoarContent.java", "CaveBoarEntity.java", "CaveBoarEntityModel.java", "RubyArmorContent.java",
                             "RubyTier.java", "OakChairBlock.java"} <= java, target_id)
            self.assertTrue((path / "mcforge-content.json").is_file())
        fabric = json.loads((self.root / "fabric-1.21.1/src/main/resources/fabric.mod.json").read_text())
        self.assertIn("dev.example.probe.content.CaveBoarContent", fabric["entrypoints"]["main"])
        self.assertIn("dev.example.probe.content.client.CaveBoarEntityClient", fabric["entrypoints"]["client"])

    def test_layout_follows_the_minecraft_version(self):
        old = self.make("forge-1.20.1")
        content.add_content(old, "block", "ruby_block")
        self.assertTrue((old / "src/main/resources/data/probe/loot_tables/blocks/ruby_block.json").is_file())
        self.assertTrue((old / "src/main/resources/data/minecraft/tags/blocks/mineable/pickaxe.json").is_file())
        new = self.make("neoforge-26.3")
        result = content.add_content(new, "block", "ruby_block")
        self.assertEqual(result["java"]["status"], "not_generated")
        self.assertTrue((new / "mcforge-pending/data/probe/loot_table/blocks/ruby_block.json").is_file())
        self.assertFalse((new / "src/main/resources/data/probe/loot_table").exists())
        tag = json.loads((new / "src/main/resources/data/minecraft/tags/block/mineable/pickaxe.json").read_text())
        self.assertEqual(tag["values"], [{"id": "probe:ruby_block", "required": False}])
        self.assertTrue((new / "src/main/resources/assets/probe/items/ruby_block.json").is_file())
        content.add_content(new, "armor", "ruby")
        self.assertTrue((new / "src/main/resources/assets/probe/equipment/ruby.json").is_file())
        fabric_old = self.make("fabric-1.20.1", "fab")
        content.add_content(fabric_old, "armor", "ruby")
        self.assertTrue((fabric_old / "src/main/resources/assets/minecraft/textures/models/armor/fab_ruby_layer_1.png").is_file())

    def test_existing_files_are_kept_and_tags_lang_merge(self):
        path = self.make("neoforge-1.21.1")
        content.add_content(path, "block", "ruby_block")
        texture = path / "src/main/resources/assets/probe/textures/block/ruby_block.png"
        texture.write_bytes(b"hand made")
        again = content.add_content(path, "block", "ruby_block")
        self.assertEqual(texture.read_bytes(), b"hand made")
        self.assertIn("src/main/resources/assets/probe/textures/block/ruby_block.png", again["skipped"])
        content.add_content(path, "block", "jade_block", style="gem")
        tag = json.loads((path / "src/main/resources/data/minecraft/tags/block/mineable/pickaxe.json").read_text())
        self.assertEqual(tag["values"], ["probe:ruby_block", "probe:jade_block"])
        lang = json.loads((path / "src/main/resources/assets/probe/lang/en_us.json").read_text())
        self.assertEqual(lang["block.probe.jade_block"], "Jade Block")

    def test_rejects_bad_input(self):
        path = self.make("neoforge-1.21.1")
        for kind, name, options in (("wand", "x_wand", {}), ("block", "Bad", {}), ("armor", "ruby", {"tier": "mythril"}),
                                    ("furniture", "x", {"shape": "throne"}), ("mob", "ghost", {"shape": "snake"})):
            with self.subTest(kind=kind):
                with self.assertRaises(ValueError):
                    content.add_content(path, kind, name, **options)

    def test_quickstart_dresses_registered_content_on_every_family(self):
        from mcforge.workbench import quickstart_project
        fabric = self.root / "qfab"
        quickstart_project(fabric, "qfab", "dev.example.qfab", "Q", loader="fabric", minecraft="1.21.1")
        self.assertTrue((fabric / "src/main/java/dev/example/qfab/content/ExampleBlockContent.java").is_file())
        forge = self.root / "qfrg"
        quickstart_project(forge, "qfrg", "dev.example.qfrg", "Q", loader="forge", minecraft="1.20.1")
        self.assertTrue((forge / "src/main/resources/data/qfrg/loot_tables/blocks/example_block.json").is_file())
        self.assertFalse((forge / "src/main/resources/data/qfrg/loot_table").exists())
        modern = self.root / "qneo26"
        quickstart_project(modern, "qneo", "dev.example.qneo", "Q", target_id="neoforge-26.3")
        self.assertTrue((modern / "src/main/resources/assets/qneo/items/example_item.json").is_file())

    def test_kits_cover_exactly_the_compiled_targets(self):
        self.assertEqual(set(javagen.KITS), {("neoforge-mdg", "1.21.1"), ("fabric-loom", "1.21.1"), ("fabric-loom", "1.20.1"), ("forge-fg", "1.20.1")})


class ArtTests(unittest.TestCase):
    def test_png_roundtrip_and_determinism(self):
        image = pixelart.sprite("sword", "ruby", 7)
        self.assertEqual(pixelart.read_png(pixelart.png_bytes(image)), image)
        self.assertEqual(pixelart.png_bytes(pixelart.sprite("sword", "ruby", 7)), pixelart.png_bytes(image))
        self.assertEqual(len(pixelart.sprite("axe", "metal", 1, 32)), 32)
        self.assertEqual(pixelart.resolve_style("auto", "ruby_sword"), "ruby")
        self.assertEqual(pixelart.resolve_style("auto", "oak_chair"), "wood")

    def test_blockbench_rig_roundtrip_is_exact(self):
        for archetype in shapes.RIGS:
            rig = shapes.mob_rig(archetype)
            png = pixelart.png_bytes(pixelart.blank(*rig["texture"]))
            back = shapes.bbmodel_to_rig(shapes.read_bbmodel(shapes.rig_bbmodel("x", rig, png)))
            for part, other in zip(rig["parts"], back["parts"]):
                self.assertEqual(tuple(part["pivot"]), tuple(other["pivot"]))
                for cube, copy in zip(part["cubes"], other["cubes"]):
                    self.assertEqual((tuple(cube["origin"]), tuple(cube["size"]), tuple(cube["uv"])),
                                     (tuple(copy["origin"]), tuple(copy["size"]), tuple(copy["uv"])))

    def test_blockbench_block_project_converts_and_rejects_two_axis_rotation(self):
        png = pixelart.png_bytes(pixelart.block_texture(1, "wood", 16))
        parsed = shapes.read_bbmodel(shapes.furniture_bbmodel("chair", "chair", png, 16))
        model = shapes.bbmodel_to_block_model(parsed, "probe:block/chair")
        self.assertEqual(len(model["elements"]), len(shapes.FURNITURE["chair"]["boxes"]))
        parsed["cubes"][0]["rotation"] = [22.5, 45, 0]
        with self.assertRaisesRegex(ValueError, "two axes"):
            shapes.bbmodel_to_block_model(parsed, "probe:block/chair")

    def test_furniture_shapes_turn_back_after_four_quarters(self):
        shape = shapes.furniture_shapes("chair")
        north = shape["north"]
        west = shape["west"]
        turned = [(16 - z2, y1, x1, 16 - z1, y2, x2) for x1, y1, z1, x2, y2, z2 in west]
        self.assertEqual(sorted(turned), sorted(north))

    def test_preview_draws_the_model(self):
        rig = shapes.mob_rig("quadruped")
        texture = pixelart.blank(*rig["texture"])
        for y in range(len(texture)):
            for x in range(len(texture[0]) // 4):
                pixelart.put(texture, x, y, (200, 100, 50))
        image = preview.render(preview.rig_boxes(rig, texture), size=64, direction=(0.55, 0.5, 0.67), up=(0, -1, 0))
        coloured = sum(1 for row in image for x in range(64) if row[x * 4] > 60)
        self.assertGreater(coloured, 200)


class PackTests(Temp):
    def test_pack_formats_come_from_the_game(self):
        self.assertEqual(resources.pack_mcmeta("1.20.1", "data", "x")["pack"]["pack_format"], 15)
        self.assertEqual(resources.pack_mcmeta("1.21.1", "resource", "x")["pack"]["pack_format"], 34)
        self.assertIn("min_format", resources.pack_mcmeta("26.3", "data", "x")["pack"])
        borrowed = resources.facts("26.9")
        self.assertFalse(borrowed["exact"])
        self.assertEqual(borrowed["borrowed_from"], "26.3")

    def test_three_pack_kinds(self):
        data = packs.create_pack(self.root / "dp", "data", "Grass", "1.20.1")
        self.assertIn("data/grass/functions/hello.mcfunction", data["files"])
        recipe = json.loads((self.root / "dp/data/grass/recipes/grass_from_dirt.json").read_text())
        self.assertEqual(recipe["result"]["item"], "minecraft:grass_block")
        modern = packs.create_pack(self.root / "dp2", "data", "Grass", "26.3")
        self.assertIn("data/grass/function/hello.mcfunction", modern["files"])
        recipe = json.loads((self.root / "dp2/data/grass/recipe/grass_from_dirt.json").read_text())
        self.assertEqual(recipe["ingredients"][0], "minecraft:dirt")
        resource = packs.create_pack(self.root / "rp", "resource", "Look", "1.21.1", retexture=["block/stone"], archive=True)
        self.assertTrue(zipfile.is_zipfile(resource["zip"]))
        shader = packs.create_pack(self.root / "sp", "shader", "Warm", "1.21.1")
        self.assertIn("shaders/final.fsh", shader["files"])
        with self.assertRaisesRegex(ValueError, "texture paths"):
            packs.create_pack(self.root / "rp2", "resource", "Look", "1.21.1", retexture=["../../evil"])


class LauncherTests(Temp):
    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value) if not isinstance(value, str) else value)

    def test_each_launcher_format_is_read(self):
        at = self.root / "at"
        self.write(at / "instances/Pack/instance.json", {"launcher": {"name": "AT Pack", "version": "1.21.1",
                                                                        "loaderVersion": {"type": "NeoForge", "version": "21.1.265"}}})
        prism = self.root / "prism"
        self.write(prism / "instances/P/mmc-pack.json", {"components": [{"uid": "net.minecraft", "version": "1.20.1"},
                                                                          {"uid": "org.quiltmc.quilt-loader", "version": "0.26.0"}]})
        self.write(prism / "instances/P/instance.cfg", "name=Prism Pack\n")
        curse = self.root / "curse"
        self.write(curse / "Instances/C/minecraftinstance.json", {"name": "Curse Pack", "gameVersion": "1.20.1",
                                                                   "baseModLoader": {"name": "forge-47.4.28"}})
        modrinth = self.root / "modrinth"
        self.write(modrinth / "profiles/M/profile.json", {"metadata": {"name": "MR", "game_version": "26.3", "loader": "fabric",
                                                                        "loader_version": {"id": "0.20.1"}}})
        rows = {row["launcher"]: row for name, root in (("atlauncher", at), ("prism", prism), ("curseforge", curse), ("modrinth", modrinth))
                for row in launchers.discover(name, [root])}
        self.assertEqual(rows["atlauncher"]["suggested_project"]["status"], "bundled")
        self.assertEqual(rows["prism"]["name"], "Prism Pack")
        self.assertEqual(rows["prism"]["suggested_project"]["init_options"], "--loader fabric --minecraft 1.20.1")
        self.assertIn("Quilt", rows["prism"]["suggested_project"]["note"])
        self.assertEqual(rows["curseforge"]["loader"], {"type": "Forge", "version": "47.4.28"})
        self.assertEqual(rows["modrinth"]["minecraft"], "26.3")
        unknown = launchers.suggest({"loader": {"type": "Forge", "version": "40.2.0"}, "minecraft": "1.18.2"})
        self.assertEqual(unknown["status"], "on_demand")
        self.assertTrue(unknown["init_options"].endswith("--fetch"))

    def jar(self, path, mod_id, version):
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("fabric.mod.json", json.dumps({"schemaVersion": 1, "id": mod_id, "version": version}))

    def test_deploy_plans_first_then_replaces_with_backup(self):
        mod = self.root / "mod"
        self.write(mod / "mcforge-project.json", {"mod_id": "probe", "loader": "fabric", "minecraft": "1.21.1"})
        self.jar(mod / "build/libs/probe-2.0.0.jar", "probe", "2.0.0")
        instance = self.root / "inst"
        self.write(instance / "instance.json", {"launcher": {"name": "I", "version": "1.21.1", "loaderVersion": {"type": "Fabric", "version": "0.20.1"}}})
        self.jar(instance / "mods/probe-1.0.0.jar", "probe", "1.0.0")
        self.jar(instance / "mods/other.jar", "other", "1")
        plan = launchers.deploy(mod, instance, unverified=True)
        self.assertFalse(plan["applied"])
        self.assertTrue((instance / "mods/probe-1.0.0.jar").is_file())
        done = launchers.deploy(mod, instance, unverified=True, apply=True)
        self.assertTrue(done["applied"])
        self.assertEqual(sorted(p.name for p in (instance / "mods").iterdir()), ["other.jar", "probe-2.0.0.jar"])
        self.assertTrue(list((instance / "mcforge-backups").rglob("probe-1.0.0.jar")))
        self.write(instance / "instance.json", {"launcher": {"name": "I", "version": "1.20.1", "loaderVersion": {"type": "Forge"}}})
        with self.assertRaisesRegex(ValueError, "does not match"):
            launchers.deploy(mod, instance, unverified=True)

    def test_launcher_folders_are_read_only_for_project_writes(self):
        instance = self.root / "prism-inst"
        self.write(instance / "mmc-pack.json", {"components": []})
        with self.assertRaisesRegex(ValueError, "read-only"):
            init_project(instance / "newmod", "probe", "dev.example.probe", "Probe")


class LibraryTests(Temp):
    def test_catalog_filters_offline(self):
        result = libs.list_libraries(loader="fabric", category="animation")
        slugs = [row["slug"] for row in result["libraries"]]
        self.assertIn("geckolib", slugs)
        self.assertTrue(all("fabric" in row["loaders"] or "quilt" in row["loaders"] for row in result["libraries"]))
        self.assertGreater(len(libs.catalog()["libraries"]), 40)

    def test_add_writes_one_replaceable_block_per_build_system(self):
        cases = {"fabric-1.20.1": 'modImplementation "maven.modrinth:geckolib:4.8.4"',
                 "forge-1.20.1": 'implementation fg.deobf("maven.modrinth:geckolib:4.8.4")',
                 "neoforge-1.21.1": 'implementation "maven.modrinth:geckolib:4.8.4"',
                 "fabric-26.3": 'implementation "maven.modrinth:geckolib:4.8.4"'}
        for target_id, line in cases.items():
            with self.subTest(target=target_id):
                path = self.make(target_id)
                libs.add(path, "geckolib", "4.8.4")
                libs.add(path, "geckolib", "4.8.4")
                build = (path / "build.gradle").read_text()
                self.assertIn(line, build)
                self.assertEqual(build.count("// mcforge libs: geckolib"), 1)
                self.assertEqual(project.inspect_project(path)["errors"], [])
        with self.assertRaisesRegex(ValueError, "safe"):
            libs.add(self.root / "neoforge-1.21.1", "geckolib", "1.0;evil")


class CliTests(Temp):
    def test_capabilities_are_generated_from_the_parser(self):
        code, output, _ = self.invoke(["capabilities"])
        self.assertEqual(code, 0)
        data = json.loads(output)
        self.assertTrue({"add", "bbmodel", "deploy", "libs", "pack", "plan", "preview", "targets", "tests"} <= set(data["commands"]))
        self.assertEqual(sorted(data["targets"]), sorted(ALL_TARGETS))
        for name in data["guides"]:
            self.assertTrue((ROOT / "docs" / cli.GUIDES[name]).is_file(), name)

    def test_plan_routes_packs_without_a_mod(self):
        result = json.loads(self.invoke(["plan", "a warm shader pack for iris"])[1])
        self.assertFalse(result["mod_needed"])
        result = json.loads(self.invoke(["plan", "forge 1.20.1 ruby armor and a boar mob"])[1])
        self.assertEqual((result["loader"], result["minecraft"]), ("forge", "1.20.1"))
        self.assertEqual({step.get("route") for step in result["steps"]} & {"mob", "armor set"}, {"mob", "armor set"})

    def test_plan_routes_animated_entities_and_sounds_to_their_guides(self):
        result = json.loads(self.invoke(["plan", "an animated geckolib mob with voice lines and sfx"])[1])
        routes = {step.get("route"): step for step in result["steps"]}
        self.assertEqual(routes["animated entity"]["guide"], "entities")
        self.assertEqual(routes["sounds"]["guide"], "audio")
        self.assertIn("mob", routes)
        result = json.loads(self.invoke(["plan", "a bright red ore block"])[1])
        self.assertNotIn("animated entity", {step.get("route") for step in result["steps"]})

    def test_entity_and_audio_guides_print(self):
        for topic, marker in (("entities", "[-rx, -ry, rz]"), ("audio", "libvorbis")):
            code, output, _ = self.invoke(["guide", topic])
            self.assertEqual(code, 0)
            self.assertIn(marker, output)

    def test_init_loader_flags_reach_the_scaffold(self):
        code, output, error = self.invoke(["init", str(self.root / "f"), "--mod-id", "probe", "--package", "dev.example.probe",
                                           "--name", "Probe", "--loader", "forge", "--minecraft", "26.3"])
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["lock"]["target_id"], "forge-26.3")


if __name__ == "__main__":
    unittest.main()
