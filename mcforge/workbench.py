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


def jdk_root() -> Path:
    """Where setup-java puts JDKs: shared by every copy of the toolkit for this user (MCFORGE_JDK_ROOT overrides)."""
    if os.environ.get("MCFORGE_JDK_ROOT"):
        return Path(os.environ["MCFORGE_JDK_ROOT"])
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Minecraft-Tools" / "jdks"
    return Path.home() / ".local/share/minecraft-forge-jdks"


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
    # CI images and version managers publish one home per major.
    candidates += [Path(value) for key, value in sorted(os.environ.items()) if re.fullmatch(r"JAVA_HOME_\d+_\w+", key) and value]
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    for base in (program_files / "Eclipse Adoptium", program_files / "Microsoft", program_files / "Java",
                 program_files / "Zulu", program_files / "Amazon Corretto", program_files / "BellSoft",
                 Path.home() / ".jdks", jdk_root(), ROOT / "local/tools", Path("/usr/lib/jvm"), Path.home() / ".sdkman/candidates/java"):
        if base.is_dir():
            candidates.extend(sorted(path for path in base.iterdir() if path.is_dir() and path.name != "current"))
    mac = Path("/Library/Java/JavaVirtualMachines")
    if mac.is_dir():
        candidates.extend(sorted(path / "Contents/Home" for path in mac.iterdir()))
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
        match = re.search(r'version "(?:1\.)?(\d+)', output)
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
    raise ValueError(f"JDK {major} with javac is required. Run setup-java --major {major}, set MCFORGE_JAVA_HOME or use --java-home; see guide tools. No global Java settings were changed.")


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
        if any((parent / marker).exists() for marker in ("instance.json", "mmc-pack.json", "minecraftinstance.json", "launcher_profiles.json")):
            raise ValueError("Launcher instances are read-only; select an owned development directory")


def init_project(destination: Path, mod_id: str, package: str, name: str, neo_version: str | None = None, **options) -> dict:
    """Create a pinned project; see scaffold.init_project for the loader/version options."""
    from .scaffold import init_project as create
    return create(destination, mod_id, package, name, neo_version, **options)


def quickstart_project(destination: Path, mod_id: str, package: str, name: str, neo_version: str | None = None,
                       *, with_tests: bool = True, style: str = "auto", size: int = 16, **options) -> dict:
    """Create the pinned scaffold and dress its example content in one command."""
    from .targets import select_target
    if not options.get("fetch") and select_target(options.get("loader"), options.get("minecraft"), options.get("target_id"))["id"] != "neoforge-1.21.1":
        with_tests = False
    result = init_project(destination, mod_id, package, name, neo_version, with_tests=with_tests, **options)
    family = result["lock"]["family"]
    if family == "fabric-loom":
        # The Fabric template registers no example content: add a real block and item (Java on kit targets).
        from .content import add_content
        result["assets"] = [add_content(destination, "block", "example_block", style=style, size=size),
                            add_content(destination, "item", "example_item", style=style, size=size)]
    else:
        # The NeoForge and Forge MDKs register example_block and example_item; dress those.
        from .assets import generate_assets
        result["assets"] = generate_assets(destination, style=style, size=size)
    result["next"] = "verify PROJECT --starter" if with_tests else "verify PROJECT"
    return result


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


LOAD_TEST = "templates/testing-load/LoadSmokeTest.java"


def needs_load_test(lock: dict) -> bool:
    """NeoForge before 1.21.5 (the classic GameTest framework) refuses to start a test server with zero tests."""
    if lock.get("family", "neoforge-mdg") != "neoforge-mdg":
        return False
    version = tuple(int(part) for part in str(lock.get("minecraft", "1.21.1")).split(".") if part.isdigit())
    return version < (1, 21, 5)
STARTER_ONLY = {"SmokeTests.java", "ExampleRecipes.java"}


def add_load_tests(project: Path) -> dict:
    """Add the game-test wiring and one load smoke test to an existing NeoForge 1.21.1 project."""
    project = Path(project).resolve()
    guard_output(project)
    lock_path = project / "mcforge-project.json"
    lock = read_json(lock_path)
    if lock.get("game_tests") or lock.get("with_tests"):
        return {"project": str(project), "status": "already_configured", "next": "verify PROJECT"}
    if not needs_load_test(lock):
        raise ValueError("Only NeoForge before Minecraft 1.21.5 needs this: Fabric projects ship a smoke test, and the other "
                         "targets start their game-test server without one (verify PROJECT --load)")
    if (project / "src/gameTest").exists():
        raise ValueError("src/gameTest already exists; wire your own tests instead of overwriting them")
    if len(lock["mod_id"]) > 58:
        raise ValueError("The test mod id needs room for _tests: mod-id must be at most 58 characters")
    add_testing_starter(project, lock["mod_id"], lock["package"], load_only=True)
    lock.update(with_tests=True, starter=False)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return {"project": str(project), "status": "added", "tests": ["LoadSmokeTest.modLoads"],
            "next": "verify PROJECT (runs datagen, the game-test server and the build)"}


def add_testing_starter(stage: Path, mod_id: str, package: str, *, load_only: bool = False):
    overlay = ROOT / "templates/testing"
    files = testing_templates()
    snippet = files[0].read_text(encoding="utf-8")
    if load_only:
        files = [path for path in files if path.name not in STARTER_ONLY]
        source = ROOT / LOAD_TEST
        target = stage.joinpath("src/gameTest/java", *package.split("."), "testing", source.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source.read_text(encoding="utf-8").replace("@PACKAGE@", package).replace("@MOD_ID@", mod_id),
                          encoding="utf-8", newline="\n")
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
    home = select_java(java_home, info.get("gradle_java_major") or info["target"]["java_major"])
    # Gradle may need further toolchains (ForgeGradle 7 launches its run tool on Java 8); offer every local JDK.
    suffix = ".exe" if os.name == "nt" else ""
    installations = ",".join(dict.fromkeys(str(path) for path in [home, *java_candidates()]
                                           if (path / "bin" / ("javac" + suffix)).is_file() and "," not in str(path)))
    env = os.environ.copy()
    env["JAVA_HOME"] = str(home)
    env["PATH"] = str(home / "bin") + os.pathsep + env.get("PATH", "")
    env["GRADLE_USER_HOME"] = str(ROOT / "local/gradle")
    suffix = ".exe" if os.name == "nt" else ""
    command = [str(home / "bin" / ("java" + suffix)), "-classpath", str(wrapper), "org.gradle.wrapper.GradleWrapperMain",
               "--console=plain", "--no-daemon", f"-Dorg.gradle.java.installations.paths={installations}",
               "-Dorg.gradle.java.installations.auto-download=false", *(option for option in options if option != "--all"), *tasks,
               *(option for option in options if option == "--all")]
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
