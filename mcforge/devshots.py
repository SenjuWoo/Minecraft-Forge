"""Scaffold the development-only client screenshot run (NeoForge 1.21.1 test mod).

`devshots PROJECT` writes `DevShots.java` into the test source set and a `devShots`
client run into build.gradle. `verify PROJECT --client` then runs it after the
build and records the screenshots and log in the receipt (client_load tier).
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from .workbench import ROOT, guard_output, read_json

TEMPLATE = "templates/devshots/DevShots.java"
BEGIN, END = "// mcforge devshots (toolkit: devshots PROJECT; verify PROJECT --client)", "// end mcforge devshots"
SUBJECT = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+")


def default_subject(project: Path, mod_id: str) -> str:
    manifest = project / "mcforge-content.json"
    if manifest.is_file():
        for key in sorted(read_json(manifest).get("content", {})):
            if key.startswith("mob:"):
                return f"{mod_id}:{key[4:]}"
    return "minecraft:pig"


def gradle_block(subject: str) -> str:
    return f"""{BEGIN}
neoForge {{
    runs {{
        devShots {{
            client()
            gameDirectory = project.file('run-devshots')
            sourceSet = sourceSets.gameTest
            loadedMods = [neoForge.mods[project.mod_id], neoForge.mods["${{project.mod_id}}_tests"]]
            systemProperty 'mcforge.devshots', 'true'
            systemProperty 'mcforge.devshots.subject', '{subject}'
            programArguments.addAll('--width', '1280', '--height', '800')
        }}
    }}
}}
{END}
"""


def add_devshots(project: Path, subject: str | None = None, *, force: bool = False) -> dict:
    project = Path(project).resolve()
    guard_output(project)
    lock_path = project / "mcforge-project.json"
    lock = read_json(lock_path)
    if lock.get("family", "neoforge-mdg") != "neoforge-mdg" or lock.get("minecraft") != "1.21.1":
        raise ValueError("devshots targets NeoForge 1.21.1 projects (the driver's client API is checked on that version); "
                         "on other targets follow guide testing, \"Client screenshot automation\"")
    if not lock.get("with_tests") or not (project / "src/gameTest").is_dir():
        raise ValueError("The screenshot driver lives in the test mod: run tests PROJECT (or init --with-tests) first")
    subject = subject or default_subject(project, lock["mod_id"])
    if not SUBJECT.fullmatch(subject):
        raise ValueError("--subject must be an entity id such as minecraft:pig or mymod:cave_boar")
    target = project.joinpath("src/gameTest/java", *lock["package"].split("."), "testing", "DevShots.java")
    if target.exists() and not force:
        raise ValueError(f"{target.name} exists; pass --force to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text((ROOT / TEMPLATE).read_text(encoding="utf-8").replace("@PACKAGE@", lock["package"]),
                      encoding="utf-8", newline="\n")
    build = project / "build.gradle"
    text = build.read_text(encoding="utf-8")
    block = gradle_block(subject)
    if BEGIN in text and END in text:
        start, end = text.index(BEGIN), text.index(END) + len(END)
        text = text[:start] + block.rstrip("\n") + text[end:]
    else:
        text = text.rstrip("\n") + "\n\n" + block
    build.write_text(text, encoding="utf-8", newline="\n")
    lock["devshots"] = {"subject": subject}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {"project": str(project), "driver": str(target), "subject": subject, "run": "runDevShots",
            "screenshots": str(project / "run-devshots" / "screenshots"),
            "next": "verify PROJECT --client (builds, runs the client, records the screenshots); "
                    "a display is required, so this does not run on headless CI"}
