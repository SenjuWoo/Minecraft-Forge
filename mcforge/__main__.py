"""Run with Python 3.11+ or the PowerShell entrypoint. JSON goes to stdout.

Network access is explicit. Debug tracebacks are opt-in; Gradle writes durable
logs and exits with its own status. Nothing registers an MCP or service.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib

from . import __version__
from .assets import STYLES
from .content import KINDS as CONTENT_KINDS
from .pixelart import PALETTES
from .inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_METADATA_BYTES, discover_instances, inspect_jar, inventory
from .workbench import ROOT, check_java, default_launcher, guard_output, init_project, java_candidates, quickstart_project, run_gradle, verify_vendor

GUIDES = {"workflow": "WORKFLOW.md", "neoforge": "NEOFORGE.md", "fabric": "FABRIC.md", "forge": "FORGE.md", "content": "CONTENT.md",
          "assets": "ASSETS.md", "libraries": "LIBRARIES.md", "launchers": "LAUNCHERS.md", "packs": "PACKS.md",
          "tools": "TOOLS.md", "testing": "TESTING.md"}
OPTIONAL_TOOLS = ("blockbench", "magick", "ffmpeg", "krita", "gimp", "aseprite", "audacity", "blender", "rg")


def emit(value, output: Path | None = None):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if output:
        guard_output(output)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(text)
        print(json.dumps({"report": str(output)}))
    else:
        print(text, end="")


def parse_asset_specs(values: list[str]) -> list[tuple[str, str]] | None:
    """Parse repeated ``ID:KIND`` arguments; no specs means the example pair."""
    if not values:
        return None
    specs = []
    for value in values:
        if value.count(":") != 1:
            raise ValueError("--id must be ID:KIND, e.g. ruby_block:block or ruby:item")
        asset_id, kind = value.split(":", 1)
        specs.append((asset_id, kind))
    return specs


def doctor(java_home: Path | None = None, project: Path | None = None) -> dict:
    from .project import inspect_project
    info = inspect_project(project) if project else None
    required_java = (info.get("gradle_java_major") or info["target"].get("java_major")) if info else 21
    java = [check_java(path) for path in ([java_home.resolve()] if java_home else java_candidates())]
    ready = any(p["jdk"] and p["major"] == required_java and p.get("exit_code") == 0 for p in java)
    if info and (info["errors"] or info["drift"]):
        ready = False
    template = verify_vendor()
    majors = {entry["major"] for entry in java if entry["jdk"] and entry.get("exit_code") == 0}
    from .targets import list_targets
    # Loom compiles with --release, so Fabric needs only the JDK that runs Gradle.
    targets = [dict(row, java_ready=row["gradle_java_major"] in majors and (row["loader"] == "fabric" or row["java_major"] in majors),
                    run_tasks_ready=row.get("run_java_major") in majors | {None})
               for row in list_targets()]
    result = {"version": __version__, "python": sys.version.split()[0], "python_executable": sys.executable,
            "target": {"minecraft": info["target"].get("minecraft") if info else "1.21.1",
                       "neoforge": info["target"].get("neo_version") if info else template["neo_version"], "java": required_java},
            "ready": ready, "java": java, "targets": targets, "git": shutil.which("git"), "rg": shutil.which("rg"),
            "optional_tools": {name: shutil.which(name) for name in OPTIONAL_TOOLS},
            "template": {"verified": True, "commit": template["commit"], "sha256": template["sha256"]},
            "gradle_cache": str(ROOT / "local/gradle"), "mcp": "not needed; no server registered",
            "missing": [] if ready else [f"JDK {required_java} with javac and a resolved project target; run setup-java --major {required_java}, inspect project errors/drift or guide tools"]}
    if info:
        result["target"]["loader"] = info.get("loader", "neoforge")
    if info:
        result["project"] = info
    return result


def search_mods(query: str, minecraft: str) -> dict:
    parameters = urllib.parse.urlencode({"query": query, "limit": 10,
        "facets": json.dumps([["categories:neoforge"], [f"versions:{minecraft}"], ["project_type:mod"]])})
    url = "https://api.modrinth.com/v2/search?" + parameters
    request = urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__} (local CLI mod-authoring workbench)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError("API response exceeds 2 MiB")
        data = json.loads(raw)
        return {"source": url, "hits": [{key: hit.get(key) for key in ("project_id", "slug", "title", "description", "author", "categories")} for hit in data["hits"]],
                "next": "Inspect the project's exact version, loader, license, dependencies and file hash before adding it; search hits are not compatibility proof."}
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise ValueError(f"Modrinth rate limit; retry after {error.headers.get('Retry-After', 'the server reset')} (no automatic retry)") from error
        raise


def search_sources(path: Path, query: str) -> int:
    if path.is_dir():
        command = shutil.which("rg")
        if not command:
            raise ValueError("ripgrep is required for directory source search; install it with your package manager, or supply a source JAR")
        process = subprocess.Popen([command, "-n", "-F", "--glob", "*.java", "--max-count", "5", "--max-filesize", "2M", "--", query, str(path)], stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
        try:
            for number, line in enumerate(process.stdout, 1):
                print(line.rstrip()[:1000])
                if number == 50:
                    process.terminate()
                    process.wait()
                    return 0
            return process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            process.stdout.close()
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Source archive exceeds 512 MiB limit")
    matches = []
    with zipfile.ZipFile(path) as archive:
        if len(archive.infolist()) > MAX_ARCHIVE_ENTRIES:
            raise ValueError("Source archive has too many entries")
        inspected = 0
        for info in archive.infolist():
            if not info.filename.endswith(".java") or info.file_size > MAX_METADATA_BYTES:
                continue
            inspected += info.file_size
            if inspected > 256 * 1024 * 1024:
                raise ValueError("Source scan exceeds 256 MiB budget; select a narrower source archive")
            with archive.open(info) as stream:
                data = stream.read(MAX_METADATA_BYTES + 1)
            if len(data) > MAX_METADATA_BYTES:
                raise ValueError("Source entry exceeds inspection limit")
            for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
                if query in line:
                    matches.append({"file": info.filename, "line": number, "text": line[:500]})
                    if len(matches) >= 50:
                        break
            if len(matches) >= 50:
                break
    emit({"archive": str(path), "query": query, "matches": matches, "limit": 50})
    return 0 if matches else 1


def preview_file(project: Path, source: Path, output: Path | None, size: int) -> dict:
    from . import preview, shapes
    from .pixelart import png_bytes, read_png, scale
    project = project.resolve()
    lock = json.loads((project / "mcforge-project.json").read_text(encoding="utf-8-sig"))
    output = output or project / "build/mcforge/previews" / (source.stem + ".png")
    guard_output(output)
    if source.suffix == ".png":
        image = read_png(source.read_bytes())
        factor = max(1, size // max(len(image), len(image[0]) // 4))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(png_bytes(scale(image, factor)))
        return {"preview": str(output), "texture": [len(image[0]) // 4, len(image)], "zoom": factor}
    if source.suffix == ".bbmodel":
        parsed = shapes.read_bbmodel(json.loads(source.read_text(encoding="utf-8-sig")))
        if not parsed["textures"]:
            raise ValueError("The Blockbench project embeds no texture to render with")
        texture = read_png(parsed["textures"][0]["png"])
        if parsed["format"] == "java_block":
            model = shapes.bbmodel_to_block_model(parsed, "preview:texture")
            image = preview.render(preview.block_boxes(model, {"preview:texture": texture}), size=size)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(png_bytes(image))
            return {"preview": str(output), "format": parsed["format"], "elements": len(model["elements"])}
        return preview.preview_rig(shapes.bbmodel_to_rig(parsed), texture, output, size) | {"format": parsed["format"]}
    return preview.preview_block_model(project, lock["mod_id"], source, output, size)


def capabilities() -> dict:
    """Generated from the argument parser, so it always matches this version."""
    cli = parser()
    sub = next(action for action in cli._actions if isinstance(action, argparse._SubParsersAction))
    helps = {choice.dest: choice.help for choice in sub._choices_actions}
    commands = {}
    for name, command in sub.choices.items():
        options = []
        for action in command._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            options.append({"name": action.option_strings[0] if action.option_strings else action.dest, "help": action.help,
                            "choices": list(action.choices) if action.choices else None, "required": bool(action.required)})
        commands[name] = {"help": helps.get(name), "arguments": options}
    from .targets import list_targets
    return {"version": __version__, "commands": commands, "guides": sorted(GUIDES), "targets": [row["id"] for row in list_targets()],
            "content_kinds": list(CONTENT_KINDS), "mcp": "none; every command is a foreground CLI call"}


def target_options(command):
    command.add_argument("--loader", choices=("neoforge", "fabric", "forge"), help="mod loader; default neoforge")
    command.add_argument("--minecraft", help="Minecraft version, e.g. 1.20.1, 1.21.1 or 26.3; default 1.21.1")
    command.add_argument("--loader-version", help="exact loader build; default is the pinned one")
    command.add_argument("--neo-version", help="alias of --loader-version for NeoForge")
    command.add_argument("--target", dest="target_id", help="bundled target id from: targets")
    command.add_argument("--fetch", action="store_true", help="resolve the official template for a version that is not bundled (network)")


def target_arguments(args) -> tuple[str | None, dict]:
    """Keep the historical call shape when no loader option is given."""
    options = {key: value for key, value in (("loader", args.loader), ("minecraft", args.minecraft),
               ("target_id", args.target_id), ("fetch", args.fetch)) if value}
    version = args.loader_version or args.neo_version
    return (version if options or version else "21.1.265"), options


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Minecraft Forge: CLI workbench for NeoForge, Fabric and Forge mods; no always-on MCP")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--debug", action="store_true", help="debug tracebacks on stderr")
    commands = cli.add_subparsers(dest="command", required=True)
    check = commands.add_parser("doctor", help="check runtimes and verify bundled template")
    check.add_argument("--java-home", type=Path)
    check.add_argument("--project", type=Path, help="inspect actual project pins and target-lock drift offline")
    updates = commands.add_parser("updates", help="read compatible upstream version candidates without changing project pins")
    updates.add_argument("path", type=Path)
    verify = commands.add_parser("verify", help="build fresh evidence or recheck a previous verification receipt")
    verify.add_argument("path", type=Path)
    verify.add_argument("--java-home", type=Path)
    verify_mode = verify.add_mutually_exclusive_group()
    verify_mode.add_argument("--check", action="store_true", help="rehash prior evidence without rebuilding")
    verify_mode.add_argument("--starter", action="store_true", help="also assert the bundled example recipe and test identities")
    verify.add_argument("--load", action="store_true", help="also boot the headless game-test server: proves the mod and its data load")
    instances = commands.add_parser("instances", help="list launcher instances read-only: ATLauncher, Prism/MultiMC, CurseForge, Modrinth, official")
    instances.add_argument("--atlauncher", type=Path, help="ATLauncher folder; lists only that launcher")
    instances.add_argument("--launcher", default="all", choices=("all", "atlauncher", "prism", "curseforge", "modrinth", "vanilla"))
    instances.add_argument("--root", type=Path, action="append", help="launcher folder to read instead of the default locations; repeatable")
    ship = commands.add_parser("deploy", help="plan (or with --apply perform) copying the verified mod JAR into one instance")
    ship.add_argument("path", type=Path, help="project directory")
    ship.add_argument("--instance", type=Path, required=True, help="instance folder from: instances")
    ship.add_argument("--apply", action="store_true", help="write into the instance; without it only the plan is printed")
    ship.add_argument("--allow-mismatch", action="store_true", help="deploy although loader or Minecraft version differ")
    ship.add_argument("--unverified", action="store_true", help="use the newest built JAR without a fresh verification receipt")
    scan = commands.add_parser("inventory", help="inspect installed JARs and bounded crash summaries (read-only)")
    scan.add_argument("--instance", type=Path, required=True)
    scan.add_argument("--hash", action="store_true", help="hash JAR bytes for an exact local pack snapshot")
    scan.add_argument("--output", type=Path, help="create a new report; never overwrite a file")
    jar = commands.add_parser("jar", help="inspect mod IDs, versions, sides and dependency declarations")
    jar.add_argument("path", type=Path)
    jar.add_argument("--hash", action="store_true")
    init = commands.add_parser("init", help="create an owned mod project from the pinned official MDK")
    init.add_argument("path", type=Path)
    init.add_argument("--mod-id", required=True)
    init.add_argument("--package", required=True)
    init.add_argument("--name", required=True)
    target_options(init)
    init.add_argument("--with-tests", action="store_true", help="add isolated GameTests and a working recipe data provider (neoforge-1.21.1)")
    asset = commands.add_parser("asset", help="generate free procedural textures, models, blockstates, lang and loot tables")
    asset.add_argument("path", type=Path)
    asset.add_argument("--id", action="append", dest="ids", default=[], metavar="ID:KIND", help="asset id and kind, e.g. ruby_block:block; repeatable")
    asset.add_argument("--style", choices=STYLES, default="auto")
    asset.add_argument("--size", type=int, choices=(16, 32), default=16)
    asset.add_argument("--force", action="store_true", help="overwrite existing generated files")
    add = commands.add_parser("add", help="add one piece of content: textures, models, data and (where a kit exists) Java")
    add.add_argument("path", type=Path)
    add.add_argument("kind", choices=CONTENT_KINDS)
    add.add_argument("name", help="lowercase id, e.g. ruby_block, ruby (toolset/armor), cave_boar, oak_chair")
    add.add_argument("--style", default="auto", help="palette: auto, " + ", ".join(sorted(PALETTES)))
    add.add_argument("--size", type=int, choices=(16, 32), default=16)
    add.add_argument("--tier", default="iron", help="tool/armor numbers start from vanilla: wood, stone, iron, diamond, netherite")
    add.add_argument("--repair", help="repair item id, e.g. minecraft:iron_ingot or mymod:ruby")
    add.add_argument("--shape", help="furniture: chair, table, stool, bench, shelf, cabinet, lamp, pedestal; mob: quadruped, biped, blob; item: ingot, gemstone, orb")
    add.add_argument("--hostile", action="store_true", help="mob attacks players")
    add.add_argument("--force", action="store_true", help="overwrite files this command generates")
    look = commands.add_parser("preview", help="render a block model, texture or Blockbench project to PNG without the game")
    look.add_argument("path", type=Path, help="project directory")
    look.add_argument("file", type=Path, help="block model .json, texture .png or .bbmodel")
    look.add_argument("--output", type=Path, help="PNG to write; default PROJECT/build/mcforge/previews/NAME.png")
    look.add_argument("--size", type=int, default=256, choices=(128, 256, 384, 512))
    bench = commands.add_parser("bbmodel", help="import a Blockbench project as a block model or an entity model class")
    bench.add_argument("path", type=Path, help="project directory")
    bench.add_argument("file", type=Path, help=".bbmodel file")
    bench_kind = bench.add_mutually_exclusive_group(required=True)
    bench_kind.add_argument("--block", metavar="ID")
    bench_kind.add_argument("--entity", metavar="ID")
    bench.add_argument("--force", action="store_true", help="replace a model class that was edited by hand")
    quick = commands.add_parser("quickstart", help="create a pinned project and generate starter assets in one command")
    quick.add_argument("path", type=Path)
    quick.add_argument("--mod-id", required=True)
    quick.add_argument("--package", required=True)
    quick.add_argument("--name", required=True)
    target_options(quick)
    quick.add_argument("--no-tests", action="store_true", help="skip the optional GameTest/datagen starter")
    quick.add_argument("--style", choices=STYLES, default="auto")
    quick.add_argument("--size", type=int, choices=(16, 32), default=16)
    install = commands.add_parser("install", help="install or update this toolkit in a versionless local root")
    install.add_argument("--root", type=Path)
    install.add_argument("--force", action="store_true", help="replace an existing install; keeps a timestamped backup")
    gradle = commands.add_parser("gradle", help="run foreground Gradle tasks with discovered JDK21 and local cache")
    gradle.add_argument("path", type=Path)
    gradle.add_argument("tasks", nargs="+")
    gradle.add_argument("--java-home", type=Path)
    for option in ("--stacktrace", "--offline", "--info", "--all", "--rerun-tasks"):
        gradle.add_argument(option, action="append_const", const=option, dest="gradle_options", default=[])
    gradle.add_argument("--log", type=Path, help="write to a new log file; default is a unique file in PROJECT/build/mcforge/logs")
    guide = commands.add_parser("guide", help="load just one focused agent reference")
    guide.add_argument("topic", choices=GUIDES)
    search = commands.add_parser("search", help="query Modrinth, filtered to NeoForge and an exact Minecraft version")
    search.add_argument("query")
    search.add_argument("--minecraft", default="1.21.1")
    sources = commands.add_parser("sources", help="literal search of local Java source directory or sources JAR")
    sources.add_argument("path", nargs="?", help="source path, or query when --project is used")
    sources.add_argument("query", nargs="?")
    sources.add_argument("--project", type=Path, help="resolve exact prepared project sources; omit query to print their location")
    setup = commands.add_parser("setup-java", help="explicitly provision a verified local JDK (8, 17, 21 or 25)")
    setup.add_argument("--plan", action="store_true", help="resolve official package identity without downloading it")
    setup.add_argument("--major", type=int, choices=(8, 17, 21, 25), default=21, help="17: Forge 1.20.1; 21: NeoForge 1.21.x; 25: 26.x and Fabric Loom; 8: ForgeGradle 7 run tasks")
    tests = commands.add_parser("tests", help="add game-test wiring and a load smoke test to a NeoForge project before Minecraft 1.21.5")
    tests.add_argument("path", type=Path)
    libs = commands.add_parser("libs", help="catalog of popular libraries; resolve or add an exact release (network)")
    libs.add_argument("--loader", choices=("neoforge", "fabric", "forge", "quilt"))
    libs.add_argument("--minecraft")
    libs.add_argument("--category")
    libs.add_argument("--query")
    libs_mode = libs.add_mutually_exclusive_group()
    libs_mode.add_argument("--resolve", metavar="SLUG", help="newest Modrinth release for the project's loader and version")
    libs_mode.add_argument("--add", metavar="SLUG", help="write the resolved release into build.gradle")
    libs.add_argument("--project", type=Path, help="project for --resolve/--add")
    libs.add_argument("--version", dest="library_version", help="exact release for --add instead of the newest")
    pack = commands.add_parser("pack", help="create a resource, data or shader pack (no compiled mod)")
    pack.add_argument("path", type=Path)
    pack.add_argument("--kind", required=True, choices=("resource", "data", "shader"))
    pack.add_argument("--name", required=True)
    pack.add_argument("--minecraft", default="1.21.1")
    pack.add_argument("--retexture", action="append", default=[], metavar="TEXTURE", help="vanilla texture path, e.g. block/stone; repeatable")
    pack.add_argument("--style", default="auto")
    pack.add_argument("--size", type=int, choices=(16, 32), default=16)
    pack.add_argument("--zip", action="store_true", help="also write PATH.zip")
    route = commands.add_parser("plan", help="route a plain-language request to commands, guides and pitfalls; writes nothing")
    route.add_argument("request")
    commands.add_parser("capabilities", help="list every command and option of this version as JSON")
    commands.add_parser("targets", help="list the bundled loader/Minecraft targets and their pins")
    commands.add_parser("self-test", help="run bundled offline diagnostics")
    return cli


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING)
    try:
        if args.command == "doctor":
            result = doctor(args.java_home, args.project)
            emit(result)
            return 0 if result["ready"] else 1
        if args.command == "updates":
            from .project import check_updates
            result = check_updates(args.path)
            emit(result)
            return 1 if result["errors"] else 0
        elif args.command == "verify":
            from .verification import check_receipt, verify_project
            if args.check and args.java_home:
                raise ValueError("--java-home selects a new run; it cannot be combined with --check")
            if args.check and args.load:
                raise ValueError("--load starts a new run; it cannot be combined with --check")
            if args.check:
                emit(check_receipt(args.path))
            else:
                emit(verify_project(args.path, args.java_home, starter=args.starter, **({"load": True} if args.load else {})))
        elif args.command == "instances":
            from .launchers import discover
            if args.atlauncher:
                emit(discover("atlauncher", [args.atlauncher]))
            else:
                emit(discover(args.launcher, args.root))
        elif args.command == "deploy":
            from .launchers import deploy
            emit(deploy(args.path, args.instance, apply=args.apply, allow_mismatch=args.allow_mismatch, unverified=args.unverified))
        elif args.command == "inventory":
            result = inventory(args.instance, args.hash)
            emit(result, args.output)
            return 1 if result["errors"] or any(jar["errors"] for jar in result["enabled"]) else 0
        elif args.command == "jar":
            result = inspect_jar(args.path, args.hash)
            emit(result)
            return 1 if result["errors"] else 0
        elif args.command == "init":
            version, options = target_arguments(args)
            emit(init_project(args.path, args.mod_id, args.package, args.name, version, with_tests=args.with_tests, **options))
        elif args.command == "asset":
            from .assets import generate_assets
            emit(generate_assets(args.path, parse_asset_specs(args.ids), style=args.style, size=args.size, force=args.force))
        elif args.command == "add":
            from .content import add_content
            emit(add_content(args.path, args.kind, args.name, style=args.style, size=args.size, tier=args.tier,
                             repair=args.repair, shape=args.shape, hostile=args.hostile, force=args.force))
        elif args.command == "preview":
            emit(preview_file(args.path, args.file, args.output, args.size))
        elif args.command == "bbmodel":
            from .content import import_bbmodel
            emit(import_bbmodel(args.path, args.file, block=args.block, entity=args.entity, force=args.force))
        elif args.command == "quickstart":
            version, options = target_arguments(args)
            emit(quickstart_project(args.path, args.mod_id, args.package, args.name, version,
                                    with_tests=not args.no_tests, style=args.style, size=args.size, **options))
        elif args.command == "install":
            from .install import install_toolkit
            emit(install_toolkit(args.root, args.force))
        elif args.command == "gradle":
            return run_gradle(args.path, args.tasks, args.java_home, options=args.gradle_options, log_path=args.log)
        elif args.command == "guide":
            print((ROOT / "docs" / GUIDES[args.topic]).read_text(encoding="utf-8"))
        elif args.command == "search":
            emit(search_mods(args.query, args.minecraft))
        elif args.command == "sources":
            if args.project:
                from .sources import resolve_sources
                if args.query is not None:
                    raise ValueError("Use sources --project PROJECT [QUERY], or sources SOURCE_PATH QUERY")
                source = resolve_sources(args.project)
                if args.path is None:
                    emit(source)
                    return 0
                codes = []
                for archive in source.get("sources", [source["source"]]):
                    print(f"Source: {archive}", file=sys.stderr)
                    codes.append(search_sources(Path(archive), args.path))
                return 0 if 0 in codes else max(codes)
            if args.path is None or args.query is None:
                raise ValueError("Use sources SOURCE_PATH QUERY or sources --project PROJECT [QUERY]")
            return search_sources(Path(args.path), args.query)
        elif args.command == "self-test":
            return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], cwd=ROOT)
        elif args.command == "setup-java":
            from .provision import setup_java
            emit(setup_java(args.plan, args.major) if args.major != 21 else setup_java(args.plan))
        elif args.command == "tests":
            from .workbench import add_load_tests
            emit(add_load_tests(args.path))
        elif args.command == "libs":
            from . import libs
            if args.resolve or args.add:
                if not args.project:
                    raise ValueError("--resolve and --add need --project PATH")
                if args.add:
                    emit(libs.add(args.project, args.add, args.library_version))
                else:
                    loader, minecraft, _ = libs._project_target(args.project)
                    emit(libs.resolve(args.resolve, loader, minecraft))
            else:
                emit(libs.list_libraries(args.loader, args.minecraft, args.category, args.query))
        elif args.command == "pack":
            from .packs import create_pack
            emit(create_pack(args.path, args.kind, args.name, args.minecraft, retexture=args.retexture, style=args.style,
                             size=args.size, archive=args.zip))
        elif args.command == "plan":
            from .plan import plan
            emit(plan(args.request))
        elif args.command == "capabilities":
            emit(capabilities())
        elif args.command == "targets":
            from .targets import list_targets
            emit(list_targets())
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, TypeError, AttributeError, EOFError, zlib.error, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        if args.debug:
            logging.exception("Command failed")
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
