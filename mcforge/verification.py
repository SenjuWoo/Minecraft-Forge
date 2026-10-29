"""Run project checks and bind their evidence to the current inputs and outputs.

Receipts and logs stay under the owned project's build/mcforge directory. A
previous passing XML file never substitutes for a new test run.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import uuid
import xml.etree.ElementTree as ET

from . import __version__
from .inventory import MAX_ARCHIVE_BYTES, MAX_METADATA_BYTES, inspect_jar
from .workbench import check_gradle_context, check_java, digest, guard_output, read_json, run_gradle, select_java


def _now():
    return datetime.now(timezone.utc).isoformat()


def _plain(path: Path, project: Path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Verification does not follow links: {path}")
        if part == project:
            break


def _relative(project: Path, name: str) -> Path:
    parts = PurePosixPath(name)
    if parts.is_absolute() or ".." in parts.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe evidence path")
    path = project.joinpath(*parts.parts)
    _plain(path, project)
    return path


def _hashes(project: Path, roots: list[str]) -> dict:
    files = []
    for name in roots:
        path = _relative(project, name)
        if path.is_dir():
            for base, directories, entries in os.walk(path, followlinks=False):
                directories[:] = sorted(d for d in directories if d not in {".cache", "__pycache__"})
                for child in directories + sorted(entries):
                    candidate = Path(base) / child
                    _plain(candidate, project)
                    if candidate.is_file():
                        files.append(candidate)
        elif path.is_file():
            files.append(path)
    files = sorted(set(files))
    if len(files) > 10000 or sum(p.stat().st_size for p in files) > MAX_ARCHIVE_BYTES:
        raise ValueError("Verification inputs exceed the 10000-file/512 MiB budget")
    return {p.relative_to(project).as_posix(): digest(p) for p in files}


def _inputs(project: Path) -> dict:
    from .project import _without_comments
    files = []
    ledgers = {"STATE.md", "PLAN.md", "VALIDATION.md", "WORKSPACE_OWNERSHIP.md"}
    for base, directories, entries in os.walk(project, followlinks=False):
        relative = Path(base).relative_to(project)
        directories[:] = sorted(name for name in directories
                                if name != "__pycache__"
                                and not (relative in {Path("."), Path("buildSrc"), Path("build-logic")}
                                         and name in {".git", ".gradle", "build"})
                                and not (relative == Path(".") and name in {"run", "run-data", "run-gametest"})
                                and not (relative == Path("src") and name == "generated"))
        for name in directories + sorted(entries):
            path = Path(base) / name
            _plain(path, project)
            if not path.is_file() or (relative == Path(".") and name in ledgers):
                continue
            files.append(path.relative_to(project).as_posix())
            if len(files) > 10000:
                raise ValueError("Verification inputs exceed the 10000-file/512 MiB budget")
            if path.suffix not in {".gradle", ".kts"}:
                continue
            if path.stat().st_size > MAX_METADATA_BYTES:
                raise ValueError("Build script exceeds inspection limit")
            text = _without_comments(path.read_text(encoding="utf-8-sig"))
            if (re.search(r"\bincludeBuild\s*(?:\(|['\"])", text)
                    or (name.startswith("settings.gradle") and re.search(r"\binclude\s*(?:\(|['\"])", text))
                    or re.search(r"\bapply\s*(?:\(\s*)?from\s*[:=]", text)):
                raise ValueError("Verification supports one project without external included/applied build scripts")
            # Arbitrary Groovy cannot be evaluated safely; literal filesystem inputs must remain local.
            for match in re.finditer(r"(['\"])((?:\\.|(?!\1)[^\\])*)\1", text, re.DOTALL):
                value = match[2].replace("\\", "/")
                if (".." in value.split("/") or value.startswith("/") or re.match(r"[A-Za-z]:/", value)
                        or (value.startswith("file:/") and not value.startswith("file://${project.projectDir}/"))):
                    raise ValueError("Verification requires project-local file inputs; external paths are unsupported")
    return _hashes(project, files)


def _generated(project: Path) -> dict:
    return _hashes(project, ["src/generated"])


def _project_info(project: Path) -> dict:
    from .project import inspect_project
    check_gradle_context(project)
    info = inspect_project(project)
    if info.get("errors") or info.get("drift") or info.get("lock_status") in {"drift", "unresolved"}:
        raise ValueError(f"Project inspection failed: {info.get('errors') or info.get('drift')}")
    target = info["target"]
    if target.get("minecraft") != "1.21.1" or target.get("java_major") != 21:
        raise ValueError("Verification currently supports only Minecraft 1.21.1 / Java 21")
    return info


def _identity(project: Path):
    lock_path = _relative(project, "mcforge-project.json")
    if lock_path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Project lock exceeds inspection limit")
    lock = read_json(lock_path)
    mod_id, package = lock["mod_id"], lock["package"]
    if not isinstance(mod_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", mod_id):
        raise ValueError("Invalid locked mod ID")
    if not isinstance(package, str) or not re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", package):
        raise ValueError("Invalid locked Java package")
    props = _relative(project, "gradle.properties").read_text(encoding="utf-8-sig")
    versions = re.findall(r"(?m)^\s*mod_version\s*=\s*([^\r\n]+)", props)
    ids = re.findall(r"(?m)^\s*mod_id\s*=\s*([^\r\n]+)", props)
    if len(versions) != 1 or len(ids) != 1 or ids[0].strip() != mod_id:
        raise ValueError("Project identity/properties are missing, ambiguous or differ from the lock")
    version = versions[0].strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+\-]*", version):
        raise ValueError("Unsupported mod_version for artifact selection")
    return lock, version


def _test_result(project: Path) -> dict:
    path = _relative(project, "build/reports/gametest/results.xml")
    if not path.is_file() or path.stat().st_size > MAX_METADATA_BYTES:
        raise ValueError("Fresh GameTest XML report missing or exceeds inspection limit")
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unexpected DTD/entity in GameTest report")
    try:
        report = ET.fromstring(raw)
    except ET.ParseError as error:
        raise ValueError(f"GameTest report is not valid XML: {error}") from error
    tags = [node.tag.rsplit("}", 1)[-1] for node in report.iter()]
    if any(tag in {"failure", "error", "skipped"} for tag in tags):
        raise ValueError("GameTest report contains failed, errored or skipped results")
    cases = [node for node in report.iter() if node.tag.rsplit("}", 1)[-1] == "testcase"]
    if not cases:
        raise ValueError("GameTest report contains zero actual test cases")
    return {"status": "passed", "count": len(cases), "names": [node.get("name", "") for node in cases]}


def _artifact(project: Path, lock: dict, version: str) -> Path:
    artifact = _relative(project, f"build/libs/{lock['mod_id']}-{version}.jar")
    result = inspect_jar(artifact)
    if result["errors"] or len(result["mods"]) != 1:
        raise ValueError(f"Compiled mod JAR invalid: {result['errors'] or 'expected one main mod'}")
    mod = result["mods"][0]
    if mod["mod_id"] != lock["mod_id"] or mod["version"] != version:
        raise ValueError("Compiled mod identity/version differs from the current project")
    if lock.get("with_tests"):
        import zipfile
        with zipfile.ZipFile(artifact) as archive:
            prefix = lock["package"].replace(".", "/") + "/testing/"
            structure = f"data/{lock['mod_id']}/structure/empty.nbt"
            if any(name.startswith(prefix) or name == structure for name in archive.namelist()):
                raise ValueError("Development test content leaked into the mod JAR")
    return artifact


def _atomic(path: Path, value: dict):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _save(project: Path, run_dir: Path, receipt: dict):
    _atomic(run_dir / "receipt.json", receipt)
    _atomic(project / "build/mcforge/verification.json", receipt)


def _summary(project: Path, receipt: dict) -> dict:
    return {key: receipt[key] for key in ("status", "run_id", "project", "target", "tests", "artifact", "warnings") if key in receipt} | {
        "receipt": str(project / "build/mcforge/verification.json"),
        "logs": [step["log"] for step in receipt.get("commands", [])]}


def verify_project(project: Path, java_home: Path | None = None, *, starter: bool = False) -> dict:
    project = Path(os.path.abspath(project))
    guard_output(project)
    if not project.is_dir():
        raise ValueError("Project directory does not exist")
    base = project / "build/mcforge"
    _plain(base, project)
    base.mkdir(parents=True, exist_ok=True)
    lock_path = base / "verification.lock"
    try:
        lease = lock_path.open("x", encoding="utf-8")
    except FileExistsError as error:
        raise ValueError("Verification is already locked; inspect the owning run before removing its lock") from error
    run_id = uuid.uuid4().hex
    run_dir = base / "verification" / run_id
    receipt = {"schema": 1, "toolkit_version": __version__, "run_id": run_id, "project": str(project),
               "status": "running", "started_at": _now(), "commands": [], "warnings": []}
    try:
        lease.write(json.dumps({"pid": os.getpid(), "run_id": run_id}) + "\n")
        lease.flush()
        _plain(run_dir, project)
        run_dir.mkdir(parents=True)
        _save(project, run_dir, receipt)
        inputs = _inputs(project)
        info = _project_info(project)
        lock, version = _identity(project)
        if starter and not lock.get("with_tests"):
            raise ValueError("Starter assertions require a project created with --with-tests")
        home = select_java(java_home, info["target"]["java_major"])
        receipt.update(inputs=inputs, target=info["target"], java=check_java(home), warnings=info.get("warnings", []))
        receipt["tests"] = {"status": "pending"} if lock.get("with_tests") else {"status": "not_configured", "count": 0}
        if not lock.get("with_tests"):
            receipt["warnings"].append("No configured GameTests; successful build is not behavioral coverage")
        steps = [("datagen", ["runData"]), ("tests-build", ["runGameTestServer", "build"])] if lock.get("with_tests") else [("datagen", ["runData"]), ("build", ["build"])]
        for name, tasks in steps:
            if name == "tests-build":
                report = _relative(project, "build/reports/gametest/results.xml")
                if report.exists():
                    if not report.is_file():
                        raise ValueError("GameTest report path is not a regular file")
                    report.replace(run_dir / "previous-gametest.xml")
            log = run_dir / f"{name}.log"
            step = {"tasks": tasks, "started_at": _now(), "log": str(log)}
            receipt["commands"].append(step)
            _save(project, run_dir, receipt)
            code = run_gradle(project, tasks, home, log_path=log)
            step.update(exit_code=code, finished_at=_now())
            if code != 0:
                raise ValueError(f"Gradle {' '.join(tasks)} exited {code}; see {log}")
            if _inputs(project) != inputs:
                raise ValueError("Project inputs changed during verification; rerun with stable sources")
            if name == "datagen":
                receipt["generated"] = _generated(project)
            elif _generated(project) != receipt["generated"]:
                raise ValueError("Generated data changed after datagen; verification evidence is inconsistent")
        if lock.get("with_tests"):
            receipt["tests"] = _test_result(project)
        artifact = _artifact(project, lock, version)
        if starter:
            from scripts.verify_starter import verify
            receipt["starter"] = verify(project)
        if _inputs(project) != inputs or _generated(project) != receipt["generated"]:
            raise ValueError("Project inputs/generated data changed while collecting verification evidence")
        outputs = [artifact.relative_to(project).as_posix()]
        if lock.get("with_tests"):
            outputs.append("build/reports/gametest/results.xml")
        outputs += [Path(step["log"]).relative_to(project).as_posix() for step in receipt["commands"]]
        receipt.update(outputs=_hashes(project, outputs), artifact={"path": str(artifact), "sha256": digest(artifact)}, status="passed", finished_at=_now())
        _save(project, run_dir, receipt)
        return _summary(project, receipt)
    except BaseException as error:
        receipt.update(status="interrupted" if isinstance(error, KeyboardInterrupt) else "failed", error=str(error), finished_at=_now())
        if run_dir.is_dir():
            _save(project, run_dir, receipt)
        raise
    finally:
        lease.close()
        if lock_path.is_file() and read_json(lock_path).get("run_id") == run_id:
            lock_path.unlink()


def check_receipt(project: Path) -> dict:
    project = Path(os.path.abspath(project))
    guard_output(project)
    path = _relative(project, "build/mcforge/verification.json")
    if not path.is_file() or path.stat().st_size > 8 * MAX_METADATA_BYTES:
        raise ValueError("Verification receipt missing or exceeds inspection limit; run verify first")
    receipt = read_json(path)
    if receipt.get("schema") != 1 or receipt.get("status") != "passed" or receipt.get("project") != str(project):
        raise ValueError("No successful verification receipt for this project")
    if _inputs(project) != receipt["inputs"] or _generated(project) != receipt["generated"]:
        raise ValueError("Verification receipt is stale: project inputs or generated data changed")
    if _project_info(project)["target"] != receipt["target"]:
        raise ValueError("Verification receipt is stale: target changed")
    outputs = receipt["outputs"]
    if not isinstance(outputs, dict) or not outputs or _hashes(project, list(outputs)) != outputs:
        raise ValueError("Verification receipt is stale: artifact, test report or logs changed")
    return _summary(project, receipt)
