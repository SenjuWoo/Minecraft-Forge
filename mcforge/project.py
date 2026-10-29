"""Read the pinned Groovy MDK target without executing a build or changing files.

Inspection is offline. Only check_updates requests bounded official metadata;
its candidates are suggestions requiring validation, never automatic upgrades.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import __version__

MAX_TEXT = 2 * 1024 * 1024
NEOFORGE_METADATA = "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
MODDEV_METADATA = "https://maven.neoforged.net/releases/net/neoforged/moddev/net.neoforged.moddev.gradle.plugin/maven-metadata.xml"
GRADLE_CURRENT = "https://services.gradle.org/versions/current"


def _text(path: Path, limit: int = MAX_TEXT) -> str:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Inspection limit exceeded: {path.name}")
    return data.decode("utf-8-sig")


def _properties(path: Path) -> dict[str, str]:
    properties = {}
    for line in _text(path).splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")):
            continue
        if "=" not in line or line.endswith("\\"):
            raise ValueError(f"Unsupported property syntax in {path.name}")
        key, value = line.split("=", 1)
        key = key.strip()
        if key in properties:
            raise ValueError(f"Duplicate property {key} in {path.name}")
        properties[key] = value.strip().replace("\\:", ":").replace("\\=", "=")
    return properties


def _without_comments(text: str) -> str:
    # Keep strings/line boundaries intact so commented examples cannot become effective pins.
    output = []
    quote = None
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            output.append(char)
            if char == "\\" and index + 1 < len(text):
                index += 1
                output.append(text[index])
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            output.append(char)
        elif text.startswith("//", index):
            end = text.find("\n", index)
            index = len(text) if end == -1 else end
            continue
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end == -1:
                raise ValueError("Unterminated Groovy comment")
            output.extend("\n" for _ in range(text[index:end].count("\n")))
            index = end + 2
            continue
        else:
            output.append(char)
        index += 1
    if quote:
        raise ValueError("Unterminated Groovy string")
    return "".join(output)


def _blocks(text: str, name: str) -> list[str]:
    blocks = []
    for match in re.finditer(r"(?m)^\s*" + re.escape(name) + r"\s*\{", text):
        start = match.end()
        depth, quote, index = 1, None, start
        while index < len(text):
            char = text[index]
            if quote:
                if char == "\\":
                    index += 1
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if not depth:
                    blocks.append(text[start:index])
                    break
            index += 1
        if depth:
            raise ValueError(f"Unterminated {name} block")
    return blocks


def _one(values: list[str], label: str) -> str:
    if len(values) != 1:
        raise ValueError(f"Expected one unambiguous {label}; found {len(values)}")
    return values[0].strip()


def _resolve(expression: str, properties: dict[str, str], label: str) -> str:
    expression = expression.strip().rstrip(";").strip()
    if len(expression) >= 2 and expression[0] in "\"'" and expression[-1] == expression[0]:
        value = expression[1:-1]
        reference = re.fullmatch(r"\$\{(?:project\.)?([A-Za-z_]\w*)\}", value)
        if reference:
            value = properties.get(reference[1], "")
    elif re.fullmatch(r"\d+", expression):
        value = expression
    else:
        reference = re.fullmatch(r"(?:project\.)?([A-Za-z_]\w*)", expression)
        value = properties.get(reference[1], "") if reference else ""
    if not value or not re.fullmatch(r"\d+(?:\.\d+)*(?:[-+][A-Za-z0-9][A-Za-z0-9._+-]*)?", value):
        raise ValueError(f"Cannot resolve {label} from a literal or plain project property")
    return value


def _assignment(blocks: list[str], key: str, properties: dict[str, str]) -> str:
    values = [value for block in blocks for value in re.findall(r"(?m)^\s*" + re.escape(key) + r"\s*=\s*([^\r\n]+)", block)]
    return _resolve(_one(values, key), properties, key)


def read_target(project: Path) -> dict:
    """Read only supported literal/property forms; dynamic or duplicate pins fail explicitly."""
    project = Path(project)
    properties = _properties(project / "gradle.properties")
    build = _without_comments(_text(project / "build.gradle"))
    neo = _blocks(build, "neoForge")
    parchment = [block for section in neo for block in _blocks(section, "parchment")]
    plugins = re.findall(r"(?m)^\s*id\s+['\"]net\.neoforged\.moddev['\"]\s+version\s+([^\r\n]+)", build)
    java = re.findall(r"(?m)^\s*java\.toolchain\.languageVersion\s*=\s*JavaLanguageVersion\.of\(([^)\r\n]+)\)\s*;?\s*$", build)
    wrapper = _properties(project / "gradle/wrapper/gradle-wrapper.properties")
    url = wrapper.get("distributionUrl", "")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Gradle distribution URL must use credential-free HTTPS")
    distribution = re.search(r"/gradle-([0-9][A-Za-z0-9.+_-]*?)-(?:bin|all)\.zip$", parsed.path)
    if not distribution:
        raise ValueError("Cannot resolve Gradle version from distribution URL")
    checksum = wrapper.get("distributionSha256Sum", "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Gradle distribution SHA256 is missing or malformed")
    archive = project / "gradle/wrapper/gradle-wrapper.jar"
    if archive.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Gradle wrapper exceeds inspection limit")
    with archive.open("rb") as stream:
        wrapper_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    minecraft = properties.get("minecraft_version", "")
    if not re.fullmatch(r"\d+(?:\.\d+)+", minecraft):
        raise ValueError("Cannot resolve minecraft_version property")
    return {"minecraft": minecraft, "neo_version": _assignment(neo, "version", properties),
            "java_major": int(_resolve(_one(java, "Java toolchain"), properties, "Java toolchain")),
            "gradle": distribution[1], "moddev": _resolve(_one(plugins, "ModDevGradle plugin"), properties, "ModDevGradle plugin"),
            "parchment_minecraft": _assignment(parchment, "minecraftVersion", properties),
            "parchment_mappings": _assignment(parchment, "mappingsVersion", properties),
            "gradle_distribution_url": url, "gradle_distribution_sha256": checksum,
            "gradle_wrapper_sha256": wrapper_hash}


def inspect_project(project: Path) -> dict:
    """Compare actual target inputs with the recorded lock, preserving legacy project files."""
    project = Path(project).resolve()
    result = {"project": str(project), "target": {}, "lock_status": "unresolved", "drift": [], "warnings": [], "errors": []}
    try:
        target = result["target"] = read_target(project)
        lock = json.loads(_text(project / "mcforge-project.json"))
        if not isinstance(lock, dict):
            raise ValueError("Project lock must be a JSON object")
        expected = lock.get("target")
        if expected is not None and not isinstance(expected, dict):
            raise ValueError("Locked target must be a JSON object")
        result["lock_status"] = "locked" if expected is not None else "legacy"
        if expected is None:
            expected = {key: lock.get(key) for key in ("minecraft", "neo_version", "java_major", "gradle_wrapper_sha256")}
            result["warnings"].append("Legacy lock does not pin Gradle distribution, ModDevGradle or mappings; no files were migrated")
        for key in target:
            if key not in expected and result["lock_status"] == "legacy":
                continue
            if expected.get(key) != target[key]:
                locked = expected.get(key)
                if key == "gradle_distribution_url" and isinstance(locked, str) and urllib.parse.urlparse(locked).username:
                    locked = "<redacted credential URL>"
                result["drift"].append({"field": key, "locked": locked, "actual": target[key]})
        # Older top-level aliases may still be consumed by agents and must agree with the actual target.
        for key in ("minecraft", "neo_version", "java_major", "gradle_wrapper_sha256"):
            if key in lock and lock[key] != target[key] and not any(row["field"] == key for row in result["drift"]):
                result["drift"].append({"field": key, "locked": lock[key], "actual": target[key]})
        if result["drift"]:
            result["lock_status"] = "drift"
        if target["minecraft"] != "1.21.1" or not re.fullmatch(r"21\.1\.\d+", target["neo_version"]) or target["java_major"] != 21:
            result["errors"].append("Project target is outside the tested Minecraft1.21.1 / NeoForge21.1.x / Java21 provider")
    except (OSError, ValueError, TypeError) as error:
        result["errors"].append(str(error))
        result["lock_status"] = "unresolved"
    return result


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__} (read-only update check)"})
    with urllib.request.urlopen(request, timeout=30) as response:
        if urllib.parse.urlparse(response.geturl()).scheme != "https":
            raise ValueError("Metadata redirected away from HTTPS")
        data = response.read(MAX_TEXT + 1)
    if len(data) > MAX_TEXT:
        raise ValueError("Official metadata exceeds inspection limit")
    return data


def _versions(data: bytes) -> list[str]:
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("Unexpected DTD/entity in Maven metadata")
    root = ET.fromstring(data)
    versions = sorted({node.text.strip() for node in root.findall("./versioning/versions/version")
                       if node.text and re.fullmatch(r"\d+(?:\.\d+)+", node.text.strip())}, key=_version_key)
    if not versions:
        raise ValueError("No stable numeric versions in official metadata")
    return versions


def _version_key(version: str) -> tuple[int, ...]:
    values = tuple(int(part) for part in version.split("."))
    return values + (0,) * max(0, 8 - len(values))


def _candidate(current: str, latest: str, scope: str) -> dict:
    stable = re.fullmatch(r"\d+(?:\.\d+)+", current)
    return {"current": current, "latest": latest,
            "update_available": _version_key(latest) > _version_key(current) if stable else None,
            "scope": scope, "requires_validation": True}


def check_updates(project: Path) -> dict:
    """Report stable upstream candidates on explicit request; network failures remain unknown."""
    inspected = inspect_project(project)
    current = inspected["target"]
    result = {"project": inspected["project"], "current": current, "candidates": {}, "ports": [],
              "notes": ["Candidates are not compatibility proof; no project files or pins were changed",
                        "Gradle/plugin/mappings upgrades require a separate build and test run"],
              "errors": list(inspected["errors"]), "source_urls": {}}
    if inspected["drift"]:
        result["notes"].append("Project lock has drift; candidates describe the actual files, not the recorded lock")
    if not current or result["errors"]:
        return result
    urls = {"neo_version": NEOFORGE_METADATA, "moddev": MODDEV_METADATA,
            "parchment_mappings": f"https://maven.parchmentmc.org/org/parchmentmc/data/parchment-{current['parchment_minecraft']}/maven-metadata.xml",
            "gradle": GRADLE_CURRENT}
    result["source_urls"] = urls
    for component, url in urls.items():
        try:
            data = _fetch(url)
            if component == "gradle":
                release = json.loads(data)
                latest = release.get("version", "")
                if not re.fullmatch(r"\d+(?:\.\d+)+", latest) or release.get("snapshot") is True:
                    raise ValueError("Current Gradle release is not stable numeric metadata")
                scope = "build_tool"
            else:
                versions = _versions(data)
                if component == "neo_version":
                    prefix = ".".join(current[component].split(".")[:2]) + "."
                    matching = [version for version in versions if version.startswith(prefix)]
                    if not matching:
                        raise ValueError("No stable NeoForge versions for the project's existing branch")
                    latest, scope = matching[-1], "same_minecraft_branch"
                    lines = {}
                    for version in versions:
                        branch = ".".join(version.split(".")[:2])
                        if not version.startswith(prefix) and _version_key(version) > _version_key(latest):
                            lines[branch] = version
                    result["ports"] = [{"neo_version": version, "note": "Different loader line; select its Minecraft MDK/JDK and port separately"}
                                       for version in sorted(lines.values(), key=_version_key, reverse=True)[:5]]
                else:
                    latest = versions[-1]
                    scope = "gradle_plugin" if component == "moddev" else "same_parchment_minecraft"
            result["candidates"][component] = _candidate(current[component], latest, scope)
        except (OSError, ValueError, TypeError, AttributeError, ET.ParseError) as error:
            result["errors"].append(f"{component} metadata unavailable: {error}")
    return result
