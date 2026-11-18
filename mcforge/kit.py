"""`kit PROJECT NAME`: copy a proven Java kit for GeckoLib mobs into the project (NeoForge 1.21.1).

Kits are source the project owns afterwards; nothing is rewritten unless --force is given.

    bonemath  kit/BoneMath.java          same-frame bone transforms, model <-> world, chain segments
    trace     kit/DevTrace.java          MCFORGE-TRACE lines for devlog
    springs   kit/SpringBones.java       data-driven secondary motion (adds bonemath and trace)
    layer     kit/SharedBoneLayer.java   a second geometry that follows the main bones
    geomob    a GeckoLib mob skeleton: entity, model, renderer, registration, spawn egg (adds all of the above)

`kit PROJECT geomob --mob NAME` names the mob. The generated classes read `gen/<Name>Rig.java` and
`gen/<Name>Clips.java`; placeholders are written when they do not exist and the asset pipeline
(`pipeline PROJECT`) regenerates them with the real springs and clip timings.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .workbench import ROOT, guard_output, read_json

COMMON = {"bonemath": ["BoneMath.java"], "trace": ["DevTrace.java"],
          "springs": ["BoneMath.java", "DevTrace.java", "SpringBones.java"], "layer": ["SharedBoneLayer.java"],
          "geomob": ["BoneMath.java", "DevTrace.java", "SpringBones.java", "SharedBoneLayer.java"]}
KITS = tuple(COMMON)
NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")
GECKOLIB_DEPENDENCY = '''
[[dependencies.${mod_id}]]
    modId="geckolib"
    type="required"
    versionRange="[4.5,)"
    ordering="AFTER"
    side="BOTH"
'''


def pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def template_files() -> list[str]:
    """Every template the kits copy (relative to the toolkit root); packaging ships exactly these."""
    names = sorted({name for files in COMMON.values() for name in files})
    return [f"templates/kit/common/{name}" for name in names] + [
        f"templates/kit/geomob/{name}.java" for name in ("Entity", "Model", "Renderer", "Content", "Client", "Rig", "Clips")]


def _fill(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(f"@{key}@", value)
    return text


def add_kit(project: Path, kit: str, mob: str | None = None, *, force: bool = False, hitbox: tuple[float, float] = (0.7, 1.9)) -> dict:
    project = Path(project).resolve()
    guard_output(project)
    if kit not in COMMON:
        raise ValueError(f"Unknown kit {kit!r}: use one of {', '.join(KITS)}")
    lock = read_json(project / "mcforge-project.json")
    if lock.get("family", "neoforge-mdg") != "neoforge-mdg" or lock.get("minecraft") != "1.21.1":
        raise ValueError("kit targets NeoForge 1.21.1 with GeckoLib 4.9 (the classes are compiled and client-run on that "
                         "version); on other targets read the templates under templates/kit and adapt them")
    package, mod_id = lock["package"], lock["mod_id"]
    java = project.joinpath("src/main/java", *package.split("."))
    values = {"PACKAGE": package, "MODID": mod_id}
    plan: list[tuple[Path, str, bool]] = []   # target, text, placeholder (never overwritten)
    for name in COMMON[kit]:
        plan.append((java / "kit" / name, _fill((ROOT / "templates/kit/common" / name).read_text(encoding="utf-8"), values), False))
    notes = []
    if kit == "geomob":
        if not mob or not NAME.fullmatch(mob):
            raise ValueError("kit geomob needs --mob NAME (lowercase id such as cave_stalker)")
        width, height = hitbox
        values |= {"NAME": mob, "PASCAL": pascal(mob), "WIDTH": f"{width:g}", "HEIGHT": f"{height:g}", "EYE": f"{height * 0.85:.2f}",
                   "EGG_A": "5B6C7A", "EGG_B": "D9C27E"}
        source = ROOT / "templates/kit/geomob"
        cls = values["PASCAL"]
        for name, folder in (("Entity", mob), ("Content", mob), ("Model", f"{mob}/client"), ("Renderer", f"{mob}/client"),
                             ("Client", f"{mob}/client")):
            plan.append((java / folder / f"{cls}{name}.java", _fill((source / f"{name}.java").read_text(encoding="utf-8"), values), False))
        for name in ("Rig", "Clips"):
            plan.append((java / "gen" / f"{cls}{name}.java", _fill((source / f"{name}.java").read_text(encoding="utf-8"), values), True))
    created, kept = [], []
    for target, text, placeholder in plan:
        guard_output(target)
        if target.exists() and (placeholder or not force):
            kept.append(str(target.relative_to(project).as_posix()))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
        created.append(str(target.relative_to(project).as_posix()))
    if kit == "geomob":
        assets = project / "src/main/resources/assets" / mod_id
        egg = assets / "models/item" / f"{mob}_spawn_egg.json"
        if not egg.exists():
            egg.parent.mkdir(parents=True, exist_ok=True)
            egg.write_text(json.dumps({"parent": "minecraft:item/template_spawn_egg"}, indent=2) + "\n", encoding="utf-8", newline="\n")
            created.append(egg.relative_to(project).as_posix())
        lang_path = assets / "lang/en_us.json"
        lang = json.loads(lang_path.read_text(encoding="utf-8-sig")) if lang_path.is_file() else {}
        title = " ".join(part.capitalize() for part in mob.split("_"))
        before = dict(lang)
        lang.setdefault(f"entity.{mod_id}.{mob}", title)
        lang.setdefault(f"item.{mod_id}.{mob}_spawn_egg", f"{title} Spawn Egg")
        if lang != before:
            lang_path.parent.mkdir(parents=True, exist_ok=True)
            lang_path.write_text(json.dumps(lang, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        loot = project / "src/main/resources/data" / mod_id / "loot_table/entities" / f"{mob}.json"
        if not loot.exists():
            loot.parent.mkdir(parents=True, exist_ok=True)
            loot.write_text(json.dumps({"type": "minecraft:entity", "pools": []}, indent=2) + "\n", encoding="utf-8", newline="\n")
            created.append(loot.relative_to(project).as_posix())
        toml = project / "src/main/templates/META-INF/neoforge.mods.toml"
        if toml.is_file():
            text = toml.read_text(encoding="utf-8")
            if 'modId="geckolib"' not in text.replace(" ", ""):
                toml.write_text(text.rstrip("\n") + "\n" + GECKOLIB_DEPENDENCY, encoding="utf-8", newline="\n")
                notes.append("declared geckolib as a required dependency in neoforge.mods.toml")
        if "geckolib" not in (project / "build.gradle").read_text(encoding="utf-8"):
            notes.append("GeckoLib is not on the classpath yet: libs --add geckolib --project PROJECT "
                         "(pin the build the target pack ships: inventory --instance PATH)")
        geo = assets / "geo/entity" / f"{mob}.geo.json"
        if not geo.is_file():
            notes.append(f"no geometry yet: pipeline PROJECT --mob {mob}, then run its build_assets.py all "
                         "(writes the geo, texture, animations and the real gen/ classes)")
        lock.setdefault("kits", {})[f"geomob:{mob}"] = {"hitbox": [width, height]}
    else:
        lock.setdefault("kits", {})[kit] = {}
    (project / "mcforge-project.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {"project": str(project), "kit": kit, "mob": mob, "created": created, "kept": kept, "notes": notes,
            "next": "devshots PROJECT --subject %s:%s, then verify PROJECT --client" % (mod_id, mob) if kit == "geomob"
                    else "call the kit from GeoModel.setCustomAnimations (guide entities); verify PROJECT"}
