"""Pinned template creation and foreground Gradle runs. No background service.

Uses only the standard library and discovered JDKs. Generated projects and the
local Gradle cache are writable; launcher installations remain read-only.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from collections import deque
import zipfile

from . import __version__

ROOT = Path(__file__).resolve().parents[1]
TESTING_FILES = ("build.gradle", "src/gameTest/java/TestMod.java", "src/gameTest/java/SmokeTests.java",
                 "src/gameTest/java/ExampleRecipes.java", "src/gameTest/resources/META-INF/neoforge.mods.toml",
                 "src/gameTest/resources/data/@MOD_ID@/structure/empty.nbt")
JAVA_WORDS = set("abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null var record sealed permits yield _".split())


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def default_launcher() -> Path:
    return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "ATLauncher"


def java_candidates(explicit: Path | None = None) -> list[Path]:
    candidates = [explicit] if explicit else []
    candidates += [Path(os.environ[key]) for key in ("MCFORGE_JAVA_HOME", "JAVA_HOME") if os.environ.get(key)]
    executable = shutil.which("javac")
    if executable:
        candidates.append(Path(executable).resolve().parent.parent)
    # ATLauncher runtimes are input-only; some include javac and can be reused.
    runtimes = default_launcher() / "runtimes/minecraft"
    if runtimes.is_dir():
        candidates.extend(p.parent.parent for p in sorted(runtimes.glob("*/windows-x64/*/bin/javac.exe")))
    for base in (Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Eclipse Adoptium",
                 Path.home() / ".jdks", ROOT / "local/tools"):
        if base.is_dir():
            candidates.extend(sorted(base.glob("jdk*")))
    return list(dict.fromkeys(p.resolve() for p in candidates if p))


def check_java(home: Path) -> dict:
    suffix = ".exe" if os.name == "nt" else ""
    java = home / "bin" / ("java" + suffix)
    compiler = home / "bin" / ("javac" + suffix)
    result = {"home": str(home), "jdk": compiler.is_file(), "major": None}
    if not java.is_file():
        result["error"] = "java executable missing"
        return result
    try:
        completed = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=15)
        output = completed.stderr + completed.stdout
        match = re.search(r'version "(\d+)', output)
        result.update(major=int(match[1]) if match else None, version=output.splitlines()[0] if output else "", exit_code=completed.returncode)
    except (OSError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    return result


def select_java(explicit: Path | None = None, major: int = 21) -> Path:
    for path in java_candidates(explicit):
        info = check_java(path)
        if info["jdk"] and info["major"] == major and info.get("exit_code") == 0:
            return path
        if explicit:
            break
    raise ValueError(f"JDK {major} with javac is required. Set MCFORGE_JAVA_HOME or use --java-home; see guide tools. No global Java settings were changed.")


def verify_vendor() -> dict:
    manifest = read_json(ROOT / "vendor/manifest.json")
    if digest(ROOT / "vendor" / manifest["archive"]) != manifest["sha256"]:
        raise ValueError("Bundled MDK hash mismatch; restore the toolkit or run the maintainer vendor script")
    return manifest


def guard_output(path: Path):
    resolved = path.resolve()
    launcher = default_launcher().resolve()
    if resolved == launcher or launcher in resolved.parents:
        raise ValueError("ATLauncher is read-only; select an owned development directory")
    for parent in (path, *path.parents):
        if parent.is_symlink() or (parent.exists() and getattr(parent.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Output ancestry contains a symlink/junction; select a direct owned path")
        if (parent / "instance.json").exists():
            raise ValueError("Launcher instances are read-only; select an owned development directory")


def init_project(destination: Path, mod_id: str, package: str, name: str, neo_version: str = "21.1.265", *, with_tests: bool = False) -> dict:
    destination = Path(os.path.abspath(destination))
    guard_output(destination)
    if destination.exists():
        raise ValueError("Destination must not exist; existing files are never overwritten")
    if not destination.parent.is_dir():
        raise ValueError("Destination parent must already exist")
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
        raise ValueError("mod-id must match [a-z][a-z0-9_]{1,63}")
    if with_tests and len(mod_id) > 58:
        raise ValueError("--with-tests requires mod-id at most 58 characters to leave room for _tests")
    if not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", package) or any(p in JAVA_WORDS for p in package.split(".")):
        raise ValueError("package must be dotted lowercase Java identifiers, without Java keywords")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}", name):
        raise ValueError("name must be 1-80 plain letters, numbers, spaces, underscores, dots or hyphens")
    if not re.fullmatch(r"21\.1\.\d+", neo_version):
        raise ValueError("This provider supports only Minecraft 1.21.1 / NeoForge 21.1.x")
    manifest = verify_vendor()
    with tempfile.TemporaryDirectory(prefix=".mcforge-", dir=destination.parent) as scratch:
        stage = Path(scratch) / "project"
        stage.mkdir()
        with zipfile.ZipFile(ROOT / "vendor" / manifest["archive"]) as archive:
            for entry in archive.infolist():
                relative = PurePosixPath(entry.filename)
                if relative.is_absolute() or ".." in relative.parts or "\\" in entry.filename:
                    raise ValueError("Unsafe template archive path")
                parts = relative.parts[1:]
                if not parts or parts[0] == ".github" or entry.is_dir():
                    continue
                # Change only the known template namespace, never arbitrary binary bytes.
                target = stage.joinpath(*[mod_id if p == "examplemod" else p for p in parts])
                if parts[:6] == ("src", "main", "java", "com", "example", "examplemod"):
                    target = stage.joinpath("src/main/java", *package.split("."), *parts[6:])
                target.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(entry)
                if target.suffix != ".jar":
                    text = data.decode("utf-8").replace("examplemod", mod_id)
                    if target.suffix == ".java":
                        # Rewrite the namespace last so literal template words in a chosen package survive.
                        text = text.replace(f"com.example.{mod_id}", package)
                    if target.name == "gradle.properties":
                        for key, value in {"mod_id": mod_id, "mod_name": name, "mod_group_id": package, "neo_version": neo_version, "org.gradle.daemon": "false"}.items():
                            text = re.sub(r"(?m)^" + re.escape(key) + r"=.*$", lambda _: f"{key}={value}", text)
                    if target.name == "gradle-wrapper.properties":
                        text += f"\ndistributionSha256Sum={manifest['gradle_distribution_sha256']}\n"
                    # Normal builds should not silently provision a different JDK.
                    if target.name == "settings.gradle":
                        text = text.split("\nplugins {")[0] + "\n"
                    data = text.encode("utf-8")
                target.write_bytes(data)
        (stage / "gradlew").chmod(0o755)
        if with_tests:
            add_testing_starter(stage, mod_id, package)
        lock = {"toolkit_version": __version__, "minecraft": "1.21.1", "neo_version": neo_version,
                "java_major": 21, "mod_id": mod_id, "package": package, "template_commit": manifest["commit"],
                "template_sha256": manifest["sha256"], "gradle_wrapper_sha256": manifest["gradle_wrapper_sha256"]}
        if with_tests:
            lock["with_tests"] = True
        from .project import read_target
        lock["target"] = read_target(stage)
        (stage / "mcforge-project.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
        (stage / "AGENTS.md").write_text(f"# Mod authoring\n\nRead mcforge-project.json and STATE.md first. Target Minecraft 1.21.1 / NeoForge {neo_version} / Java 21.\nToolkit: {ROOT}\nRead that toolkit's AGENTS.md, then only the guide needed for this task.\nUse the pinned Gradle wrapper. Keep ATLauncher, installed mods, worlds and saves read-only.\nVerify signatures in exact generated sources; build success does not prove gameplay compatibility.\nDo not publish without explicit authorization.\n", encoding="utf-8")
        (stage / "WORKSPACE_OWNERSHIP.md").write_text("# Workspace ownership\n\nProject root and active source: this directory. One owner for all agents.\nLocal/private; no remote or publication authorized. Version: gradle.properties mod_version.\nRead-only references: ATLauncher and all installed mods/saves. Outputs: build/ and run/.\nRecovery: preserve source and read STATE.md before continuing.\n", encoding="utf-8")
        (stage / "STATE.md").write_text("# State\n\nGoal: replace the official example with the requested mod.\nDone: pinned template created; no builds or runtime checks yet.\nNext: inspect source and Gradle tasks; implement one feature and add meaningful tests.\nBuild: toolkit gradle command, project path, build. Output: build/libs/.\nRuntime: unverified.\n", encoding="utf-8")
        if with_tests:
            with (stage / "STATE.md").open("a", encoding="utf-8") as stream:
                stream.write("\nOpt-in starter: two GameTests and a recipe data provider included in src/gameTest (not yet run).\nRun: toolkit verify PROJECT --starter; verify PROJECT --check rechecks receipt freshness.\nReport: build/reports/gametest/results.xml. Receipt/logs: build/mcforge/. Final JAR excludes the test mod; generated recipe is included.\n")
        publish_project(stage, destination)
    next_step = "verify PROJECT --starter" if with_tests else "gradle PROJECT tasks; verify PROJECT"
    return {"project": str(destination), "lock": lock, "next": next_step}


def testing_templates() -> list[Path]:
    files = [ROOT / "templates/testing" / name for name in TESTING_FILES]
    for path in files:
        if not path.is_file():
            raise ValueError(f"Testing starter template missing: {path.relative_to(ROOT)}")
    return files


def publish_project(stage: Path, destination: Path):
    # Windows readers without FILE_SHARE_DELETE can briefly block an otherwise valid rename.
    for delay in (0.02, 0.05, 0.1, 0):
        try:
            stage.rename(destination)
            return
        except PermissionError as error:
            if (os.name != "nt" or getattr(error, "winerror", None) not in (5, 32)
                    or not delay or not stage.is_dir() or destination.exists()):
                raise
            time.sleep(delay)


def add_testing_starter(stage: Path, mod_id: str, package: str):
    overlay = ROOT / "templates/testing"
    files = testing_templates()
    snippet = files[0].read_text(encoding="utf-8")
    for source in files[1:]:
        relative = source.relative_to(overlay)
        target = stage / str(relative).replace("@MOD_ID@", mod_id)
        if relative.parts[:3] == ("src", "gameTest", "java"):
            target = stage.joinpath("src/gameTest/java", *package.split("."), "testing", *relative.parts[3:])
        target.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        if source.suffix != ".nbt":
            data = data.decode("utf-8").replace("@PACKAGE@", package).replace("@MOD_ID@", mod_id).encode("utf-8")
        target.write_bytes(data)
    with (stage / "build.gradle").open("a", encoding="utf-8") as stream:
        stream.write("\n" + snippet)


GRADLE_OPTIONS = ("--stacktrace", "--offline", "--info", "--all", "--rerun-tasks")


def check_gradle_context(project: Path):
    """Refuse implicit build overrides rather than claim file pins describe them."""
    overrides = [key for key, value in os.environ.items() if value and (
        key.upper().startswith("ORG_GRADLE_PROJECT_") or key.upper() in {"JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS"})]
    if overrides:
        raise ValueError("Unresolved Gradle environment overrides; unset for this process: " + ", ".join(sorted(overrides)))
    cache = ROOT / "local/gradle"
    custom = [cache / name for name in ("gradle.properties", "init.gradle", "init.gradle.kts") if (cache / name).is_file()]
    if (cache / "init.d").is_dir():
        custom += list((cache / "init.d").glob("*.gradle*"))
    if custom:
        raise ValueError("Custom shared Gradle properties/init scripts are outside target inspection; inspect: " + ", ".join(str(p) for p in custom))
    properties = project / "gradle.properties"
    if properties.is_file() and re.search(r"(?m)^\s*systemProp\.", properties.read_text(encoding="utf-8-sig")):
        raise ValueError("Project systemProp overrides are outside target inspection")


def stop_gradle(process):
    """Stop only this foreground build's process group, including its game worker."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        process.wait(timeout=10)
        return
    except (OSError, subprocess.TimeoutExpired):
        pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=10)


def run_gradle(project: Path, tasks: list[str], java_home: Path | None = None, *, options=(), log_path: Path | None = None) -> int:
    guard_output(project)
    project = project.resolve()
    lock = read_json(project / "mcforge-project.json")
    if not tasks or any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9_:]*", task) for task in tasks):
        raise ValueError("Pass Gradle task names only; select native diagnostic options separately")
    if any(option not in GRADLE_OPTIONS for option in options):
        raise ValueError("Unsupported Gradle option; only --stacktrace, --offline, --info, --all and --rerun-tasks are allowed")
    check_gradle_context(project)
    from .project import inspect_project
    info = inspect_project(project)
    if info["errors"] or info["drift"]:
        raise ValueError(f"Project target is unresolved or changed: {info['errors'] or info['drift']}; inspect doctor --project before updating its lock")
    wrapper = project / "gradle/wrapper/gradle-wrapper.jar"
    if digest(wrapper) != lock["gradle_wrapper_sha256"]:
        raise ValueError("Project wrapper changed; verify provenance before updating mcforge-project.json")
    home = select_java(java_home, info["target"]["java_major"])
    env = os.environ.copy()
    env["JAVA_HOME"] = str(home)
    env["PATH"] = str(home / "bin") + os.pathsep + env.get("PATH", "")
    env["GRADLE_USER_HOME"] = str(ROOT / "local/gradle")
    suffix = ".exe" if os.name == "nt" else ""
    command = [str(home / "bin" / ("java" + suffix)), "-classpath", str(wrapper), "org.gradle.wrapper.GradleWrapperMain",
               "--console=plain", "--no-daemon", f"-Dorg.gradle.java.installations.paths={home}",
               "-Dorg.gradle.java.installations.auto-download=false", *options, *tasks]
    log_path = Path(log_path) if log_path else project / "build/mcforge/logs" / f"gradle-{uuid.uuid4().hex}.log"
    guard_output(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Gradle log: {log_path}", file=sys.stderr)
    group = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with log_path.open("x", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=project, env=env, stdout=log, stderr=subprocess.STDOUT, **group)
        try:
            result = process.wait()
        except BaseException:
            stop_gradle(process)
            raise
    print(f"Gradle exit: {result}", file=sys.stderr)
    if result:
        with log_path.open(encoding="utf-8", errors="replace") as log:
            tail = deque(log, maxlen=20)
        print("".join(line[:500] for line in tail), end="", file=sys.stderr)
    return result
