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
from .inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_METADATA_BYTES, discover_instances, inspect_jar, inventory
from .workbench import ROOT, check_java, default_launcher, guard_output, init_project, java_candidates, run_gradle, verify_vendor

GUIDES = {"workflow": "WORKFLOW.md", "neoforge": "NEOFORGE.md", "tools": "TOOLS.md", "testing": "TESTING.md"}


def emit(value, output: Path | None = None):
    text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    if output:
        guard_output(output)
        with output.open("x", encoding="utf-8") as stream:
            stream.write(text)
        print(json.dumps({"report": str(output)}))
    else:
        print(text, end="")


def doctor(java_home: Path | None = None, project: Path | None = None) -> dict:
    from .project import inspect_project
    info = inspect_project(project) if project else None
    required_java = info["target"].get("java_major") if info else 21
    java = [check_java(path) for path in ([java_home.resolve()] if java_home else java_candidates())]
    ready = any(p["jdk"] and p["major"] == required_java and p.get("exit_code") == 0 for p in java)
    if info and (info["errors"] or info["drift"]):
        ready = False
    template = verify_vendor()
    result = {"version": __version__, "python": sys.version.split()[0], "python_executable": sys.executable,
            "target": {"minecraft": info["target"].get("minecraft") if info else "1.21.1",
                       "neoforge": info["target"].get("neo_version") if info else template["neo_version"], "java": required_java},
            "ready": ready, "java": java, "git": shutil.which("git"), "rg": shutil.which("rg"),
            "template": {"verified": True, "commit": template["commit"], "sha256": template["sha256"]},
            "gradle_cache": str(ROOT / "local/gradle"), "mcp": "not needed; no server registered",
            "missing": [] if ready else [f"JDK {required_java} with javac and a resolved project target; inspect project errors/drift or guide tools"]}
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


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description="Minecraft Forge: CLI-first NeoForge workbench; no always-on MCP")
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
    instances = commands.add_parser("instances", help="list ATLauncher instances (read-only)")
    instances.add_argument("--atlauncher", type=Path, default=default_launcher())
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
    init.add_argument("--neo-version", default="21.1.265")
    init.add_argument("--with-tests", action="store_true", help="add isolated GameTests and a working recipe data provider")
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
    setup = commands.add_parser("setup-java", help="explicitly provision a verified local Windows x64 JDK21")
    setup.add_argument("--plan", action="store_true", help="resolve official package identity without downloading it")
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
            emit(check_receipt(args.path) if args.check else verify_project(args.path, args.java_home, starter=args.starter))
        elif args.command == "instances":
            emit(discover_instances(args.atlauncher))
        elif args.command == "inventory":
            result = inventory(args.instance, args.hash)
            emit(result, args.output)
            return 1 if result["errors"] or any(jar["errors"] for jar in result["enabled"]) else 0
        elif args.command == "jar":
            result = inspect_jar(args.path, args.hash)
            emit(result)
            return 1 if result["errors"] else 0
        elif args.command == "init":
            emit(init_project(args.path, args.mod_id, args.package, args.name, args.neo_version, with_tests=args.with_tests))
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
                print(f"Source: {source['source']}", file=sys.stderr)
                return search_sources(Path(source["source"]), args.path)
            if args.path is None or args.query is None:
                raise ValueError("Use sources SOURCE_PATH QUERY or sources --project PROJECT [QUERY]")
            return search_sources(Path(args.path), args.query)
        elif args.command == "self-test":
            return subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"], cwd=ROOT)
        elif args.command == "setup-java":
            from .provision import setup_java
            emit(setup_java(args.plan))
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
