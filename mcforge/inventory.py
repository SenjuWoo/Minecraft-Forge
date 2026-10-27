"""Read-only launcher and JAR metadata inspection; declarations are not compatibility proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tomllib
import zipfile
import zlib


MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 50_000
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_INSTANCE_BYTES = 16 * 1024 * 1024
MAX_CRASH_BYTES = 128 * 1024


def _bounded_read(path: Path, limit: int) -> bytes:
    with path.open("rb") as handle:
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"file exceeds {limit} byte inspection limit")
    return data


def _zip_read(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > MAX_METADATA_BYTES:
        raise ValueError(f"{name} exceeds metadata size limit")
    with archive.open(info) as handle:
        data = handle.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError(f"{name} exceeds metadata read limit")
    return data


def _manifest(data: bytes) -> dict:
    text = data.decode("utf-8", errors="replace").replace("\r\n", "\n")
    # Manifest continuation lines belong to the preceding attribute.
    text = text.replace("\n ", "")
    return dict(line.split(": ", 1) for line in text.split("\n\n", 1)[0].splitlines() if ": " in line)


def inspect_jar(path: Path, hash_file: bool = False) -> dict:
    """Inspect bounded metadata, never extract or execute an installed mod."""
    path = Path(path)
    result = {
        "path": str(path), "file": path.name, "size_bytes": None,
        "metadata": [], "mods": [], "dependencies": [], "nested_jars": [],
        "mixins": [], "foreign_fabric_only": False, "errors": [],
    }
    try:
        result["size_bytes"] = path.stat().st_size
        if result["size_bytes"] > MAX_ARCHIVE_BYTES:
            raise ValueError("archive exceeds 512 MiB inspection limit")
        if hash_file:
            with path.open("rb") as handle:
                result["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
        with zipfile.ZipFile(path) as archive:
            if len(archive.infolist()) > MAX_ARCHIVE_ENTRIES:
                raise ValueError("archive has too many entries")
            names = archive.namelist()
            expected = ["META-INF/neoforge.mods.toml", "META-INF/mods.toml", "fabric.mod.json"]
            result["metadata"] = [name for name in expected if name in names]
            manifest = {}
            if "META-INF/MANIFEST.MF" in names:
                try:
                    manifest = _manifest(_zip_read(archive, "META-INF/MANIFEST.MF"))
                except (ValueError, OSError, RuntimeError, zlib.error, zipfile.BadZipFile) as error:
                    result["errors"].append(str(error))
            preferred = next((name for name in expected[:2] if name in names), None)
            result["foreign_fabric_only"] = "fabric.mod.json" in names and preferred is None
            for name in result["metadata"]:
                if names.count(name) > 1:
                    result["errors"].append(f"duplicate archive entry: {name}")
                    continue
                try:
                    raw = _zip_read(archive, name).decode("utf-8-sig")
                    data = json.loads(raw) if name.endswith(".json") else tomllib.loads(raw)
                    if not isinstance(data, dict):
                        raise ValueError("metadata root must be an object")
                    if name.endswith(".toml"):
                        if name != preferred:
                            continue
                        for mod in data.get("mods", []):
                            if not isinstance(mod, dict) or not isinstance(mod.get("modId"), str):
                                raise ValueError("mods entries require modId")
                            version = mod.get("version")
                            if version == "${file.jarVersion}":
                                version = manifest.get("Implementation-Version", version)
                            result["mods"].append({
                                "mod_id": mod["modId"], "version": version,
                                "name": mod.get("displayName"), "side": None,
                                "description": str(mod.get("description", ""))[:1000],
                            })
                        dependencies = data.get("dependencies", {})
                        if not isinstance(dependencies, dict):
                            raise ValueError("dependencies must be a table")
                        for owner, declarations in dependencies.items():
                            if not isinstance(declarations, list):
                                raise ValueError(f"dependencies.{owner} must be an array")
                            for dependency in declarations:
                                if not isinstance(dependency, dict):
                                    raise ValueError("dependency must be a table")
                                result["dependencies"].append({
                                    "owner": owner, "mod_id": dependency.get("modId"),
                                    "type": dependency.get("type", ("required" if dependency["mandatory"] else "optional") if "mandatory" in dependency else None),
                                    "version_range": dependency.get("versionRange"),
                                    "side": dependency.get("side"), "ordering": dependency.get("ordering"),
                                })
                        result["mixins"].extend(entry.get("config") for entry in data.get("mixins", []) if isinstance(entry, dict) and entry.get("config"))
                    elif preferred is None:
                        if not isinstance(data.get("id"), str):
                            raise ValueError("Fabric metadata requires id")
                        result["mods"].append({
                            "mod_id": data["id"], "version": data.get("version"),
                            "name": data.get("name"), "side": data.get("environment", "*"),
                            "description": str(data.get("description", ""))[:1000],
                        })
                        for key in ("depends", "recommends", "suggests", "breaks", "conflicts"):
                            for dependency, constraint in data.get(key, {}).items():
                                result["dependencies"].append({"owner": data["id"], "mod_id": dependency, "type": key, "version_range": constraint, "side": None, "ordering": None})
                        result["mixins"].extend(entry if isinstance(entry, str) else entry.get("config") for entry in data.get("mixins", []) if isinstance(entry, (str, dict)))
                except (ValueError, UnicodeError, OSError, RuntimeError, TypeError, AttributeError, NotImplementedError, EOFError, zlib.error, zipfile.BadZipFile) as error:
                    result["errors"].append(f"{name}: {error}")
            jarjar = "META-INF/jarjar/metadata.json"
            if jarjar in names:
                try:
                    data = json.loads(_zip_read(archive, jarjar))
                    entries = data.get("jars", [])
                    if not isinstance(entries, list):
                        raise ValueError("jars must be an array")
                    for entry in entries:
                        if not isinstance(entry, dict):
                            raise ValueError("nested JAR descriptor must be an object")
                        result["nested_jars"].append({key: entry.get(key) for key in ("path", "identifier", "version")})
                except (ValueError, UnicodeError, OSError, RuntimeError, TypeError, AttributeError, NotImplementedError, EOFError, zlib.error, zipfile.BadZipFile) as error:
                    result["errors"].append(f"{jarjar}: {error}")
    except (OSError, ValueError, RuntimeError, NotImplementedError, EOFError, zlib.error, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
        result["errors"].append(str(error))
    return result


def _instance_summary(instance: Path) -> dict:
    result = {"path": str(instance), "name": instance.name, "minecraft": None, "loader": {}, "java_major": None, "errors": []}
    try:
        data = json.loads(_bounded_read(instance / "instance.json", MAX_INSTANCE_BYTES))
        launcher = data.get("launcher", {})
        loader = launcher.get("loaderVersion") or {}
        result.update({
            "name": launcher.get("name", instance.name),
            "minecraft": launcher.get("version") or data.get("id"),
            "loader": {"type": loader.get("type"), "version": loader.get("version")},
            "java_major": (data.get("javaVersion") or {}).get("majorVersion"),
        })
    except (OSError, ValueError, TypeError, AttributeError) as error:
        result["errors"].append(f"instance.json: {error}")
    return result


def discover_instances(atlauncher: Path) -> list[dict]:
    """List instance descriptors without reading accounts or launcher credentials."""
    directory = Path(atlauncher) / "instances"
    return [_instance_summary(path) for path in sorted(directory.iterdir()) if path.is_dir() and (path / "instance.json").is_file()]


def _crashes(instance: Path) -> list[dict]:
    directory = instance / "crash-reports"
    if not directory.is_dir():
        return []
    reports = sorted(directory.glob("*.txt"), key=lambda path: path.stat().st_mtime_ns, reverse=True)[:3]
    summaries = []
    for path in reports:
        summary = {"file": path.name, "description": None, "exception": None, "signals": []}
        try:
            with path.open("rb") as handle:
                text = handle.read(MAX_CRASH_BYTES).decode("utf-8", errors="replace")
            for line in text.splitlines():
                if line.startswith("Description: "):
                    summary["description"] = line[13:413]
                if summary["exception"] is None and re.match(r"^(?:[\w$]+\.)+[\w$]*(?:Exception|Error)(?::|$)", line):
                    summary["exception"] = line[:400]
                if "Failure message:" in line:
                    summary["signals"].append(line.strip()[:400])
                    if len(summary["signals"]) >= 5:
                        break
        except OSError as error:
            summary["error"] = str(error)
        summaries.append(summary)
    return summaries


def inventory(instance: Path, hash_files: bool = False) -> dict:
    """Inventory actual files, independently of potentially stale launcher listings."""
    instance = Path(instance)
    result = _instance_summary(instance)
    result["instance"] = result.pop("path")
    mods = instance / "mods"
    result["enabled"] = [inspect_jar(path, hash_files) for path in sorted(mods.glob("*.jar"))]
    if not mods.is_dir():
        result["errors"].append("mods directory does not exist")
    disabled = instance / "disabledmods"
    result["disabled"] = sorted(path.name for path in disabled.iterdir() if path.is_file()) if disabled.is_dir() else []
    result["disabled"].extend(sorted(path.name for path in mods.glob("*.disabled")))
    providers: dict[str, list[str]] = {}
    for jar in result["enabled"]:
        for mod_id in {mod["mod_id"] for mod in jar["mods"]}:
            providers.setdefault(mod_id, []).append(jar["file"])
    result["duplicates"] = [{"mod_id": mod_id, "files": files} for mod_id, files in sorted(providers.items()) if len(files) > 1]
    result["foreign_fabric_only"] = [jar["file"] for jar in result["enabled"] if jar["foreign_fabric_only"]]
    result["crashes"] = _crashes(instance)
    return result
