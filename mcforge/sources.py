"""Locate exact-version sources prepared inside a project; never build or fetch them.

The sources JAR is preferred over the merged artifact. Invalid preferred inputs
fail explicitly instead of silently switching to another file or cached version.
"""
from __future__ import annotations

from pathlib import Path
import re
import zipfile

from .inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_METADATA_BYTES


PREPARE = {"fabric-loom": "genSources", "forge-fg": "build (ForgeGradle 7) or an IDE import (ForgeGradle 6)"}


def _has_java(path: Path) -> bool:
    try:
        if not path.is_file() or path.stat().st_size > MAX_ARCHIVE_BYTES:
            return False
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            return len(entries) <= MAX_ARCHIVE_ENTRIES and any(item.filename.endswith(".java") for item in entries)
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile):
        return False


def _other_sources(project: Path, family: str, target: dict) -> dict:
    """Fabric Loom and ForgeGradle keep source JARs in their own caches; list the ones for this exact version."""
    from . import workbench
    minecraft = target["minecraft"]
    if family == "fabric-loom":
        roots = [project / ".gradle/loom-cache/minecraftMaven", workbench.ROOT / "local/gradle/caches/fabric-loom/minecraftMaven"]
        wanted = lambda name: name.endswith("-sources.jar") and f"-{minecraft}-" in name
    else:
        version = f"{minecraft}-{target['forge_version']}"
        roots = [project / ".gradle/mavenizer/repo", project / "build/fg_cache",
                 workbench.ROOT / "local/gradle/caches/forge_gradle/minecraft_user_repo",
                 workbench.ROOT / "local/gradle/caches/forge_gradle/maven_downloader"]
        wanted = lambda name: name.endswith("-sources.jar") and version in name
    found = []
    for base in roots:
        if base.is_dir():
            found += [path for path in sorted(base.rglob("*-sources.jar")) if wanted(path.name) and _has_java(path)]
    if not found:
        raise ValueError(f"No prepared sources for Minecraft {minecraft} in this project. Run: gradle \"{project}\" "
                         f"{PREPARE[family]}; then repeat")
    # Prefer the archive that holds the game itself over API-only archives.
    found.sort(key=lambda path: ("mapped" not in path.name and "minecraft" not in path.name, len(path.name)))
    return {"project": str(project), "source": str(found[0].resolve()), "sources": [str(path.resolve()) for path in found],
            "kind": family, "target": target}


def resolve_sources(project: Path) -> dict:
    from .project import project_family, read_target

    project = Path(project).resolve()
    target = read_target(project)
    family = project_family(project)
    if family != "neoforge-mdg":
        return _other_sources(project, family, target)
    version = target.get("neo_version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9][A-Za-z0-9._+-]*", version):
        raise ValueError("Project NeoForge version is unresolved; inspect the project's build pins first")
    directory = project / "build/moddev/artifacts"
    entries = list(directory.iterdir()) if directory.is_dir() else []
    for suffix, kind in (("sources.jar", "neoforge"), ("merged.jar", "merged")):
        expected = f"neoforge-{version}-{suffix}"
        matches = [path for path in entries if path.name.casefold() == expected.casefold()]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous prepared sources for NeoForge {version}: {expected}")
        if not matches:
            continue
        source = matches[0]
        try:
            if not source.is_file() or source.stat().st_size > MAX_ARCHIVE_BYTES:
                raise ValueError("Expected a source archive within the 512 MiB inspection limit")
            with zipfile.ZipFile(source) as archive:
                archive_entries = archive.infolist()
                if len(archive_entries) > MAX_ARCHIVE_ENTRIES:
                    raise ValueError("Source archive has too many entries")
                if not any(not item.is_dir() and item.filename.endswith(".java")
                           and item.file_size <= MAX_METADATA_BYTES for item in archive_entries):
                    raise ValueError("Source archive contains no inspectable Java source")
        except (OSError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile) as error:
            raise ValueError(f"Prepared source artifact is invalid: {source.name}: {error}") from error
        return {"project": str(project), "source": str(source.resolve()), "kind": kind, "target": target}
    raise ValueError(f"No prepared sources for NeoForge {version} in this project. "
                     f"Run: gradle \"{project}\" createMinecraftArtifacts. "
                     "ModDevGradle skips sources with CI=true; set CI=false only for the preparation command if needed")
