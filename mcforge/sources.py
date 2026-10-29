"""Locate exact-version sources prepared inside a project; never build or fetch them.

The sources JAR is preferred over the merged artifact. Invalid preferred inputs
fail explicitly instead of silently switching to another file or cached version.
"""
from __future__ import annotations

from pathlib import Path
import re
import zipfile

from .inventory import MAX_ARCHIVE_BYTES, MAX_ARCHIVE_ENTRIES, MAX_METADATA_BYTES


def resolve_sources(project: Path) -> dict:
    from .project import read_target

    project = Path(project).resolve()
    target = read_target(project)
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
