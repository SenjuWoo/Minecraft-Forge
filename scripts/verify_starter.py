"""Check real datagen, GameTest results and the final opt-in starter JAR.

Run after runData, then runGameTestServer and build. Reads only the owned
project's outputs; missing or incomplete evidence fails with JSON on stderr.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import tomllib
import xml.etree.ElementTree as ET
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcforge.inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_METADATA_BYTES
from mcforge.workbench import digest, read_json


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_json(path: Path) -> dict:
    require(path.stat().st_size <= MAX_METADATA_BYTES, f"JSON exceeds inspection limit: {path}")
    data = read_json(path)
    require(isinstance(data, dict), f"JSON must be an object: {path}")
    return data


def verify(project: Path) -> dict:
    project = Path(project).resolve()
    lock = load_json(project / "mcforge-project.json")
    require(lock.get("with_tests") is True, "Project was not created with --with-tests")
    mod_id, package = lock["mod_id"], lock["package"]
    require(isinstance(mod_id, str) and re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id), "Invalid locked mod ID")
    require(isinstance(package, str) and re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", package), "Invalid locked Java package")
    recipe_id = f"{mod_id}:example_items_from_block"
    recipe_path = f"data/{mod_id}/recipe/example_items_from_block.json"
    advancement_path = f"data/{mod_id}/advancement/recipes/misc/example_items_from_block.json"
    generated = project / "src/generated/resources"
    recipe = load_json(generated / recipe_path)
    expected = {"type": "minecraft:crafting_shapeless", "category": "misc",
                "ingredients": [{"item": f"{mod_id}:example_block"}],
                "result": {"id": f"{mod_id}:example_item", "count": 9}}
    # Vanilla may omit an empty optional group during codec serialization.
    require({k: v for k, v in recipe.items() if k != "group"} == expected and recipe.get("group", "") == "",
            "Generated recipe does not match the expected one-block/nine-item recipe")
    advancement = load_json(generated / advancement_path)
    require(advancement.get("parent") == "minecraft:recipes/root", "Wrong recipe advancement parent")
    require(advancement.get("rewards") == {"recipes": [recipe_id]}, "Wrong advancement recipe reward")
    criteria = advancement.get("criteria", {})
    require(set(criteria) == {"has_example_block", "has_the_recipe"}, "Missing advancement unlock criteria")
    require(criteria["has_the_recipe"] == {"trigger": "minecraft:recipe_unlocked", "conditions": {"recipe": recipe_id}},
            "Wrong recipe-unlocked criterion")
    block = criteria["has_example_block"]
    require(block.get("trigger") == "minecraft:inventory_changed", "Wrong block unlock trigger")
    predicates = block.get("conditions", {}).get("items", [])
    require(isinstance(predicates, list) and len(predicates) == 1 and isinstance(predicates[0], dict), "Wrong block unlock predicate")
    require(predicates[0].get("items") in (f"{mod_id}:example_block", [f"{mod_id}:example_block"]), "Wrong block unlock item")
    requirements = advancement.get("requirements", [])
    require(isinstance(requirements, list) and len(requirements) == 1 and set(requirements[0]) == set(criteria),
            "Advancement must unlock from the block or the recipe criterion")

    properties = project / "gradle.properties"
    versions = re.findall(r"(?m)^\s*mod_version\s*=\s*([^\r\n]+)", properties.read_text(encoding="utf-8-sig")) if properties.is_file() else []
    require(len(versions) <= 1, "Ambiguous mod_version properties")
    if versions:
        version = versions[0].strip()
        require(version and not any(c in version for c in "/\\:"), "Invalid mod_version for artifact selection")
        artifact = project / "build/libs" / f"{mod_id}-{version}.jar"
        require(artifact.is_file(), f"Expected compiled mod JAR missing: {artifact.name}")
    else:
        jars = sorted((project / "build/libs").glob(f"{mod_id}-*.jar"))
        require(len(jars) == 1, "Expected one unambiguous compiled mod JAR")
        artifact = jars[0]
    require(artifact.stat().st_size <= MAX_ARCHIVE_BYTES, "Mod JAR exceeds inspection limit")
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        require(len(names) <= MAX_ARCHIVE_ENTRIES, "Mod JAR has too many entries")
        forbidden = (package.replace(".", "/") + "/testing/", f"data/{mod_id}/structure/empty.nbt")
        require(not any(name.startswith(forbidden[0]) or name == forbidden[1] for name in names), "Development test content leaked into the mod JAR")
        payload = {}
        for name in ("META-INF/neoforge.mods.toml", recipe_path, advancement_path):
            require(names.count(name) == 1, f"Missing or duplicate packaged entry: {name}")
            require(archive.getinfo(name).file_size <= MAX_METADATA_BYTES, f"Packaged entry exceeds inspection limit: {name}")
            with archive.open(name) as stream:
                payload[name] = stream.read(MAX_METADATA_BYTES + 1)
            require(len(payload[name]) <= MAX_METADATA_BYTES, f"Packaged entry exceeds read limit: {name}")
        metadata = tomllib.loads(payload["META-INF/neoforge.mods.toml"].decode("utf-8-sig"))
        mods = metadata.get("mods", [])
        require(isinstance(mods, list) and len(mods) == 1 and mods[0].get("modId") == mod_id, "JAR must declare only the main mod, never its test mod")
        require(json.loads(payload[recipe_path]) == recipe, "Packaged recipe differs from generated JSON")
        require(json.loads(payload[advancement_path]) == advancement, "Packaged advancement differs from generated JSON")

    report_path = project / "build/reports/gametest/results.xml"
    require(report_path.stat().st_size <= MAX_METADATA_BYTES, "GameTest report exceeds inspection limit")
    raw = report_path.read_bytes()
    require(b"<!DOCTYPE" not in raw.upper() and b"<!ENTITY" not in raw.upper(), "Unexpected DTD/entity in GameTest report")
    report = ET.fromstring(raw)
    require(not any(node.tag.rsplit("}", 1)[-1] in {"failure", "error", "skipped"} for node in report.iter()),
            "GameTest report contains failed, errored or skipped results")
    cases = [node for node in report.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
    require(len(cases) >= 2, "GameTest report must contain at least two actual testcase elements")
    names = [node.get("name", "") for node in cases]
    for required in ("registeredBlockCanBePlaced", "generatedRecipeCraftsOnlyTheExpectedInput"):
        require(any(name.lower().endswith(required.lower()) for name in names), f"Required GameTest missing: {required}")
    return {"project": str(project), "tests": len(cases), "test_names": names, "artifact": str(artifact),
            "sha256": digest(artifact), "recipe": recipe_path, "tests_excluded": True}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(verify(args.project), indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError, zipfile.BadZipFile, zlib.error, RuntimeError) as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
