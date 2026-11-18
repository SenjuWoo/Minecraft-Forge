"""`pipeline PROJECT --mob NAME`: scaffold a code-driven asset pipeline next to a mod project.

Every finished GeckoLib mob built with this toolkit generated its model, textures and animations from scripts:
rerunnable, diffable, free of z-fighting by construction, and a fix is "change the generator and rerun". Each
project used to start by copying and reshaping the previous project's scripts; this command ships that kit.

It writes `asset-pipeline/` (default: beside the project folder, so nothing in it is a build input of the mod):
`lib/` the machinery (implicit shapes, voxeliser, painter, game-lit preview renderer, animation toolkit with
grounding, events and IK, sounds wiring, NBT structures, spring tuner, release staging, plan helpers) and `mob/`
a small example creature to replace. The pipeline needs numpy and Pillow; it creates its own virtual environment
on first run. The toolkit core stays standard-library only.

`--force` refreshes `lib/` and the entry script; `mob/`, `palette.json` and `pipeline.json` are never replaced.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .workbench import ROOT, guard_output, read_json

TEMPLATE = "templates/pipeline"
OWNED = ("mob/", "palette.json")           # written once, never replaced
NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")


def template_files() -> list[str]:
    """Every pipeline template file (relative to the toolkit root); packaging ships exactly these."""
    root = ROOT / TEMPLATE
    return sorted(path.relative_to(ROOT).as_posix() for path in root.rglob("*")
                  if path.is_file() and "__pycache__" not in path.parts and path.suffix in (".py", ".json", ".md", ".txt"))


def add_pipeline(project: Path, mob: str, directory: Path | None = None, *, force: bool = False) -> dict:
    project = Path(project).resolve()
    guard_output(project)
    lock = read_json(project / "mcforge-project.json")
    if not mob or not NAME.fullmatch(mob):
        raise ValueError("--mob must be a lowercase id such as cave_stalker")
    target = Path(directory).resolve() if directory else project.parent / "asset-pipeline"
    guard_output(target)
    if target == project or project in target.parents and target.parent == project and target.name in ("src", "build", "gradle"):
        raise ValueError("Choose a pipeline folder that is not part of the Gradle project layout")
    config_path = target / "pipeline.json"
    if config_path.is_file():
        existing = read_json(config_path)
        if existing.get("mob") != mob and not force:
            raise ValueError(f"{target} already holds the pipeline of {existing.get('mob')!r}; pass --dir DIR for a second mob")
    created, kept, refreshed = [], [], []
    for relative in template_files():
        name = relative[len(TEMPLATE) + 1:]
        destination = target / (".gitignore" if name == "gitignore.txt" else name)
        owned = name.startswith(OWNED[0]) or name == OWNED[1]
        if destination.exists():
            if owned or not force:
                kept.append(destination.relative_to(target).as_posix())
                continue
            refreshed.append(destination.relative_to(target).as_posix())
        else:
            created.append(destination.relative_to(target).as_posix())
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / relative).read_bytes())
    if not config_path.is_file():
        config = {"mod_id": lock["mod_id"], "mob": mob, "package": lock["package"],
                  "project": Path(os.path.relpath(project, target)).as_posix(), "media": "../media", "toolkit": "minecraft-forge"}
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")
        created.append("pipeline.json")
    lock.setdefault("pipelines", {})[mob] = Path(os.path.relpath(target, project)).as_posix()
    (project / "mcforge-project.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    script = target / "build_assets.py"
    return {"project": str(project), "pipeline": str(target), "mob": mob, "created": created, "refreshed": refreshed, "kept": kept,
            "next": [f"python -I \"{script}\" check", f"python -I \"{script}\" all --validate",
                     f"kit PROJECT geomob --mob {mob}  (entity, model, renderer, registration)",
                     f"devshots PROJECT --subject {lock['mod_id']}:{mob}, then verify PROJECT --client and devlog PROJECT",
                     "replace the example in mob/ with your design: start with mob/look.py (the checklist), then rig, model, paint, clips"]}
