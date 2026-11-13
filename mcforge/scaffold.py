"""Create an owned mod project from a pinned official template.

One code path serves every loader family. Only the template's known example
namespace is renamed; binary files are copied untouched. The resulting pins are
read back from the staged files and written to the project lock.
"""
from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import zipfile

from . import __version__
from . import workbench
from .workbench import JAVA_WORDS, add_testing_starter, digest, guard_output, publish_project, verify_vendor

VERSION_KEY = {"neoforge-mdg": "neo_version", "forge-fg": "forge_version", "fabric-loom": "loader_version"}
GUIDE = {"neoforge-mdg": "neoforge", "forge-fg": "forge", "fabric-loom": "fabric"}
# Fabric's official test wiring: a `gametest` source set and a headless server run that `build` depends on.
FABRIC_TESTS_GRADLE = """
// Game tests (toolkit: verify PROJECT). `build` runs them on a headless server; test code stays out of the mod JAR.
fabricApi {
	configureTests {
		createSourceSet = true
		modId = "@MOD_ID@_tests"
		enableClientGameTests = false
	}
}
loom.runs.named("gameTest") {
	vmArg "-Dfabric-api.gametest.report-file=${layout.buildDirectory.get().asFile}/reports/gametest/results.xml"
}
"""
FABRIC_TEST_MOD = """{
	"schemaVersion": 1,
	"id": "@MOD_ID@_tests",
	"version": "1.0.0",
	"name": "@NAME@ tests",
	"environment": "*",
	"entrypoints": {
		"fabric-gametest": [
			"@PACKAGE@.testing.LoadSmokeTest"
		]
	},
	"depends": {
		"@MOD_ID@": "*"
	}
}
"""
# Minecraft 1.21.5 replaced the structure-template tests with registered test instances.
FABRIC_TEST_CLASSIC = """package @PACKAGE@.testing;

import net.fabricmc.fabric.api.gametest.v1.FabricGameTest;
import net.minecraft.gametest.framework.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;

/** Passes once the server has loaded this mod, its registries and its data pack. Add real assertions beside it. */
public class LoadSmokeTest implements FabricGameTest {
	@GameTest(template = EMPTY_STRUCTURE)
	public void modLoads(GameTestHelper helper) {
		helper.succeed();
	}
}
"""
FABRIC_TEST_MODERN = """package @PACKAGE@.testing;

import net.fabricmc.fabric.api.gametest.v1.GameTest;
import net.minecraft.gametest.framework.GameTestHelper;

/** Passes once the server has loaded this mod, its registries and its data pack. Add real assertions beside it. */
public class LoadSmokeTest {
	@GameTest
	public void modLoads(GameTestHelper helper) {
		helper.succeed();
	}
}
"""


def add_fabric_tests(stage: Path, mod_id: str, package: str, name: str, minecraft: str):
    fill = lambda value: value.replace("@MOD_ID@", mod_id).replace("@PACKAGE@", package).replace("@NAME@", name)
    with (stage / "build.gradle").open("a", encoding="utf-8") as stream:
        stream.write(fill(FABRIC_TESTS_GRADLE))
    version = tuple(int(part) for part in minecraft.split("."))
    source = FABRIC_TEST_MODERN if version >= (1, 21, 5) else FABRIC_TEST_CLASSIC
    target = stage.joinpath("src/gametest/java", *package.split("."), "testing/LoadSmokeTest.java")
    target.parent.mkdir(parents=True)
    target.write_text(fill(source), encoding="utf-8", newline="\n")
    resources = stage / "src/gametest/resources"
    resources.mkdir(parents=True)
    (resources / "fabric.mod.json").write_text(fill(FABRIC_TEST_MOD), encoding="utf-8", newline="\n")



def _drop_foojay(text: str) -> str:
    """Remove the JDK auto-provisioning settings plugin; builds use the selected local JDK."""
    match = re.search(r"(?m)^plugins\s*\{[^{}]*foojay[^{}]*\}\s*\n?", text)
    return text[:match.start()] + text[match.end():] if match else text


def _set_property(text: str, key: str, value: str, *, add: bool = False) -> str:
    pattern = r"(?m)^" + re.escape(key) + r"\s*=.*$"
    if re.search(pattern, text):
        return re.sub(pattern, lambda _: f"{key}={value}", text)
    return text.rstrip("\n") + f"\n{key}={value}\n" if add else text


def stage_template(target: dict, stage: Path, mod_id: str, package: str, name: str, loader_version: str | None):
    """Extract the pinned template, renaming only its known example namespace."""
    from .targets import archive_path
    family = target["family"]
    token, namespace = ("modid", "com.example") if family == "fabric-loom" else ("examplemod", "com.example.examplemod")
    namespace_parts = tuple(namespace.split("."))
    overrides = target.get("overrides", {})
    with zipfile.ZipFile(archive_path(target)) as archive:
        entries = [entry for entry in archive.infolist() if not entry.is_dir()]
        strip = len({entry.filename.split("/", 1)[0] for entry in entries}) == 1 and all("/" in entry.filename for entry in entries)
        for entry in entries:
            relative = PurePosixPath(entry.filename)
            if relative.is_absolute() or ".." in relative.parts or "\\" in entry.filename:
                raise ValueError("Unsafe template archive path")
            parts = relative.parts[1:] if strip else relative.parts
            if not parts or parts[0] == ".github" or (family == "fabric-loom" and parts == ("LICENSE",)):
                continue
            # Change only the known template namespace, never arbitrary binary bytes.
            if len(parts) > 3 and parts[0] == "src" and parts[2] == "java" and parts[3:3 + len(namespace_parts)] == namespace_parts:
                path = stage.joinpath(*parts[:3], *package.split("."), *parts[3 + len(namespace_parts):])
            else:
                path = stage.joinpath(*[mod_id + part[len(token):] if part == token or part.startswith(token + ".") else part
                                        for part in parts])
            path.parent.mkdir(parents=True, exist_ok=True)
            data = archive.read(entry)
            if path.suffix not in {".jar", ".png"}:
                text = data.decode("utf-8").replace(token, mod_id)
                # Rewrite the namespace last so literal template words in a chosen package survive.
                if family == "fabric-loom":
                    if path.suffix in {".java", ".json"}:
                        text = text.replace(namespace, package)
                elif path.suffix == ".java" or path.name == "build.gradle":
                    text = text.replace(f"com.example.{mod_id}", package)
                if path.name in {"mods.toml", "neoforge.mods.toml", "fabric.mod.json"}:
                    text = text.replace("Example Mod", name)
                if path.name == "fabric.mod.json":
                    # The template's CC0 notice covers the template, not the mod written from it.
                    text = text.replace('"license": "CC0-1.0"', '"license": "All-Rights-Reserved"')
                    text = re.sub(r'(?s)[ \t]*"contact": \{.*?\},\r?\n', "", text, count=1)
                if path.name == "gradle.properties":
                    values = {"mod_id": mod_id, "mod_name": name, "mod_group_id": package}
                    if family == "fabric-loom":
                        values = {"group": package}
                        if "loom_version" in overrides:
                            values["loom_version"] = overrides["loom_version"]
                    if loader_version:
                        values[VERSION_KEY[family]] = loader_version
                    for key, value in values.items():
                        text = _set_property(text, key, value)
                    text = _set_property(text, "org.gradle.daemon", "false", add=True)
                if path.name == "gradle-wrapper.properties":
                    text = text.rstrip("\n") + f"\ndistributionSha256Sum={target['gradle_distribution_sha256']}\n"
                if path.name == "settings.gradle":
                    # Normal builds should not silently provision a different JDK.
                    text = _drop_foojay(text)
                if path.name == "build.gradle" and family == "forge-fg":
                    if "forgegradle" in overrides:
                        text = re.sub(r"(id\s+['\"]net\.minecraftforge\.gradle['\"]\s+version\s+)['\"][^'\"]+['\"]",
                                      lambda match: f"{match[1]}'{overrides['forgegradle']}'", text, count=1)
                    if loader_version and "forge_version" not in text:
                        text = re.sub(r"(net\.minecraftforge:forge:[0-9.]+-)[0-9.]+", lambda match: match[1] + loader_version, text, count=1)
                data = text.encode("utf-8")
            path.write_bytes(data)
    if family == "fabric-loom":
        add_fabric_tests(stage, mod_id, package, name, target["minecraft"])
    if (stage / "gradlew").is_file():
        (stage / "gradlew").chmod(0o755)


def loader_version_ok(target: dict, version: str) -> bool:
    if target["family"] == "neoforge-mdg":
        minecraft = target["minecraft"].split(".")
        # NeoForge drops the leading "1." of classic versions: 1.21.1 -> 21.1.x, 26.3 -> 26.3.x.
        prefix = ".".join((minecraft[1:] + ["0"])[:2]) if minecraft[0] == "1" else ".".join(minecraft[:2])
        return bool(re.fullmatch(re.escape(prefix) + r"\.\d+(?:\.\d+)?", version))
    return bool(re.fullmatch(r"\d+(?:\.\d+){1,3}", version))


def init_project(destination: Path, mod_id: str, package: str, name: str, neo_version: str | None = None, *,
                 with_tests: bool = False, loader: str | None = None, minecraft: str | None = None,
                 loader_version: str | None = None, target_id: str | None = None, fetch: bool = False) -> dict:
    destination = Path(os.path.abspath(destination))
    guard_output(destination)
    if destination.exists():
        raise ValueError("Destination must not exist; existing files are never overwritten")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must already exist")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
        raise ValueError("mod-id must match [a-z][a-z0-9_]{1,63}")
    if (with_tests or loader == "fabric" or str(target_id).startswith("fabric")) and len(mod_id) > 58:
        raise ValueError("--with-tests requires mod-id at most 58 characters to leave room for _tests")
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", package) or any(p in JAVA_WORDS for p in package.split(".")):
        raise ValueError("package must be dotted lowercase Java identifiers, without Java keywords")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}", name):
        raise ValueError("name must be 1-80 plain letters, numbers, spaces, underscores, dots or hyphens")
    from .targets import resolve_remote, select_target
    if fetch:
        target = resolve_remote(loader or "neoforge", minecraft or "", loader_version or neo_version)
    else:
        target = select_target(loader, minecraft, target_id)
    family = target["family"]
    version = loader_version or neo_version or target.get("loader_version")
    if version and not loader_version_ok(target, version):
        if target["id"] == "neoforge-1.21.1":
            raise ValueError("This provider supports only Minecraft 1.21.1 / NeoForge 21.1.x")
        raise ValueError(f"Loader version {version} does not belong to {target['loader']} for Minecraft {target['minecraft']}")
    if with_tests and target["id"] != "neoforge-1.21.1":
        raise ValueError("The GameTest starter targets neoforge-1.21.1; other targets use verify PROJECT --load")
    if target["id"] == "neoforge-1.21.1":
        verify_vendor()
    with tempfile.TemporaryDirectory(prefix=".mcforge-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "project"
        stage.mkdir()
        stage_template(target, stage, mod_id, package, name, version)
        if digest(stage / "gradle/wrapper/gradle-wrapper.jar") != target["gradle_wrapper_sha256"]:
            raise ValueError("Template wrapper differs from its recorded hash")
        if with_tests:
            add_testing_starter(stage, mod_id, package)
        from .project import read_target
        actual = read_target(stage)
        lock = {"toolkit_version": __version__, "minecraft": actual["minecraft"]}
        if family == "neoforge-mdg":
            lock["neo_version"] = actual["neo_version"]
        lock.update({"java_major": actual["java_major"], "mod_id": mod_id, "package": package,
                     "template_commit": target.get("commit"), "template_sha256": target["sha256"],
                     "gradle_wrapper_sha256": target["gradle_wrapper_sha256"],
                     "loader": target["loader"], "family": family, "target_id": target["id"], "template_tier": target["tier"]})
        if with_tests:
            lock["with_tests"] = True
        if family == "fabric-loom":
            lock["game_tests"] = "fabric"
        lock["target"] = actual
        loader_line = {"neoforge-mdg": "NeoForge", "forge-fg": "Forge", "fabric-loom": "Fabric loader"}[family] + f" {actual[VERSION_KEY[family]]}"
        (stage / "mcforge-project.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        (stage / "AGENTS.md").write_text(f"# Mod authoring\n\nRead mcforge-project.json and STATE.md first. Target Minecraft {actual['minecraft']} / {loader_line} / Java {actual['java_major']}.\nToolkit: {workbench.ROOT}\nRead that toolkit's AGENTS.md, then only the guide needed for this task (start with: guide {GUIDE[family]}).\nUse the pinned Gradle wrapper. Keep ATLauncher, installed mods, worlds and saves read-only.\nVerify signatures in exact generated sources; build success does not prove gameplay compatibility.\nDo not publish without explicit authorization.\n", encoding="utf-8")
        (stage / "WORKSPACE_OWNERSHIP.md").write_text("# Workspace ownership\n\nProject root and active source: this directory. One owner for all agents.\nLocal/private; no remote or publication authorized. Version: the project's Gradle version property.\nRead-only references: launcher instances and all installed mods/saves. Outputs: build/ and run/.\nRecovery: preserve source and read STATE.md before continuing.\n", encoding="utf-8")
        (stage / "STATE.md").write_text("# State\n\nGoal: replace the official example with the requested mod.\nDone: pinned template created; no builds or runtime checks yet.\nNext: inspect source and Gradle tasks; implement one feature and add meaningful tests.\nBuild: toolkit gradle command, project path, build. Output: build/libs/.\nRuntime: unverified.\n", encoding="utf-8")
        if target["tier"] != "bundled":
            with (stage / "STATE.md").open("a", encoding="utf-8") as stream:
                stream.write(f"\nTemplate: fetched on demand from {target['url']} (sha256 {target['sha256']}); no toolkit release built this target.\n")
        if with_tests:
            with (stage / "STATE.md").open("a", encoding="utf-8") as stream:
                stream.write("\nOpt-in starter: two GameTests and a recipe data provider included in src/gameTest (not yet run).\nRun: toolkit verify PROJECT --starter; verify PROJECT --check rechecks receipt freshness.\nReport: build/reports/gametest/results.xml. Receipt/logs: build/mcforge/. Final JAR excludes the test mod; generated recipe is included.\n")
        publish_project(stage, destination)
    next_step = "verify PROJECT --starter" if with_tests else "gradle PROJECT tasks; verify PROJECT"
    return {"project": str(destination), "lock": lock, "next": next_step}
