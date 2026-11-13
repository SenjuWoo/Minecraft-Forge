"""Popular libraries mods build on: an offline catalog plus exact-version resolution.

The catalog (mcforge/data/libraries.json) is read offline. ``resolve`` asks
Modrinth for the newest release of one project matching the project's loader
and Minecraft version, and returns its files, hashes and declared dependencies.
``add`` writes that exact coordinate into build.gradle in a marked block. A
resolved release is a candidate, not compatibility proof: build and test it.
"""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from . import __version__

DATA = Path(__file__).resolve().parent / "data" / "libraries.json"
MODRINTH = "https://api.modrinth.com/v2"
MAVEN = "https://api.modrinth.com/maven"
SLUG = re.compile(r"[a-z0-9][a-z0-9_.-]{1,63}")


@lru_cache(maxsize=1)
def catalog() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _key(value: str):
    return tuple(int(part) for part in value.split(".") if part.isdigit())


def list_libraries(loader: str | None = None, minecraft: str | None = None, category: str | None = None,
                   query: str | None = None) -> dict:
    rows = []
    for slug, entry in sorted(catalog()["libraries"].items()):
        if loader and loader not in entry["loaders"] and not (loader == "quilt" and "fabric" in entry["loaders"]):
            continue
        if category and entry["category"] != category:
            continue
        if query and query.lower() not in (slug + " " + entry["title"] + " " + entry["purpose"]).lower():
            continue
        if minecraft and entry["minecraft"] and not (_key(entry["minecraft"]["oldest"]) <= _key(minecraft) <= _key(entry["minecraft"]["newest"])):
            continue
        rows.append({"slug": slug} | {key: entry[key] for key in ("title", "category", "purpose", "loaders", "license", "minecraft", "page")})
    return {"generated": catalog()["generated"], "count": len(rows), "libraries": rows,
            "categories": sorted({entry["category"] for entry in catalog()["libraries"].values()}),
            "note": "Catalog ranges say a release exists somewhere in that span, not for every version; resolve one with libs --resolve SLUG --project PATH"}


def _get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__} (library resolution)"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(4 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise ValueError("Modrinth has no such project") from error
        if error.code == 429:
            raise ValueError(f"Modrinth rate limit; retry after {error.headers.get('Retry-After', 'the reset')} seconds") from error
        raise
    if len(data) > 4 * 1024 * 1024:
        raise ValueError("Modrinth response exceeds 4 MiB")
    return json.loads(data)


def _project_target(project: Path) -> tuple[str, str, str]:
    lock = json.loads((Path(project) / "mcforge-project.json").read_text(encoding="utf-8-sig"))
    from .project import project_family
    family = lock.get("family") or project_family(Path(project))
    return lock.get("loader", "neoforge"), lock["minecraft"], family


def resolve(slug: str, loader: str, minecraft: str) -> dict:
    if not SLUG.fullmatch(slug):
        raise ValueError("Library slug must be a Modrinth project slug, e.g. geckolib")
    loaders = [loader] + (["fabric"] if loader == "quilt" else [])
    query = urllib.parse.urlencode({"loaders": json.dumps(loaders), "game_versions": json.dumps([minecraft]), "include_changelog": "false"})
    versions = _get(f"{MODRINTH}/project/{slug}/version?{query}")
    releases = [row for row in versions if row.get("version_type") == "release"] or versions
    if not releases:
        raise ValueError(f"{slug} publishes no {loader} file for Minecraft {minecraft}; pick another library or version")
    row = releases[0]
    primary = next((item for item in row["files"] if item.get("primary")), row["files"][0])
    dependencies = []
    for dependency in row.get("dependencies", []):
        dependencies.append({"project_id": dependency.get("project_id"), "version_id": dependency.get("version_id"),
                             "type": dependency.get("dependency_type")})
    if dependencies:
        ids = sorted({item["project_id"] for item in dependencies if item["project_id"]})
        if ids:
            names = {item["id"]: item["slug"] for item in _get(f"{MODRINTH}/projects?ids=" + urllib.parse.quote(json.dumps(ids)))}
            for item in dependencies:
                item["slug"] = names.get(item["project_id"])
    return {"slug": slug, "version": row["version_number"], "version_id": row["id"], "loader": loader, "minecraft": minecraft,
            "published": row.get("date_published"), "file": primary["filename"], "url": primary["url"],
            "sha512": primary["hashes"].get("sha512"), "sha1": primary["hashes"].get("sha1"), "size": primary.get("size"),
            # The version id is unique; one version number can name files for several loaders and Minecraft versions.
            "dependencies": dependencies, "maven": f"maven.modrinth:{slug}:{row['id']}",
            "note": "Newest matching release on Modrinth; a candidate, not compatibility proof"}


def configuration(family: str, project: Path) -> str:
    """Gradle configuration that puts a mod on the compile and run classpath for this build system."""
    build = (Path(project) / "build.gradle").read_text(encoding="utf-8-sig")
    if family == "fabric-loom":
        return "modImplementation" if "fabric-loom-remap" in build or "loom.officialMojangMappings" in build or "mappings " in build else "implementation"
    # ForgeGradle 6 (obfuscated Minecraft) must remap mod dependencies; the MDK only mentions fg.deobf in comments.
    if family == "forge-fg" and re.search(r"net\.minecraftforge\.gradle['\"]\s+version\s+['\"]6\.", build):
        return "implementation fg.deobf"
    return "implementation"


def snippet(family: str, project: Path, coordinate: str, slug: str) -> str:
    config = configuration(family, project)
    line = f'    {config}("{coordinate}")' if config.endswith("deobf") else f'    {config} "{coordinate}"'
    return (f"\n// mcforge libs: {slug} (resolved from Modrinth; rerun libs --add to change it)\n"
            # A content filter, not exclusiveContent: ForgeGradle 6 serves remapped copies of this group from its own cache.
            "repositories {\n    maven {\n        name = \"Modrinth\"\n"
            f'        url = "{MAVEN}"\n'
            '        content { includeGroup "maven.modrinth" }\n    }\n}\n'
            f"dependencies {{\n{line}\n}}\n// end mcforge libs: {slug}\n")


def add(project: Path, slug: str, version: str | None = None) -> dict:
    """Write one library into build.gradle; a previous block for the same slug is replaced."""
    project = Path(project).resolve()
    from .workbench import guard_output
    guard_output(project)
    loader, minecraft, family = _project_target(project)
    if version and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", version):
        raise ValueError("Version contains characters that are not safe in a Gradle coordinate")
    resolved = resolve(slug, loader, minecraft) if not version else {"slug": slug, "version": version,
                                                                     "maven": f"maven.modrinth:{slug}:{version}", "dependencies": []}
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.+-]*", resolved["maven"].rsplit(":", 1)[1]):
        raise ValueError("Version contains characters that are not safe in a Gradle coordinate")
    path = project / "build.gradle"
    text = path.read_text(encoding="utf-8-sig")
    pattern = re.compile(r"\n// mcforge libs: " + re.escape(slug) + r" .*?// end mcforge libs: " + re.escape(slug) + r"\n", re.S)
    text = pattern.sub("", text)
    path.write_text(text.rstrip("\n") + "\n" + snippet(family, project, resolved["maven"], slug), encoding="utf-8", newline="\n")
    required = [item.get("slug") or item["project_id"] for item in resolved["dependencies"] if item["type"] == "required"]
    return resolved | {"project": str(project), "written": str(path), "required_dependencies": required,
                       "next": ("Declare the dependency in your mod metadata (mods.toml / fabric.mod.json) with the library's mod id, "
                                + (f"add its required libraries ({', '.join(required)}), " if required else "")
                                + "then verify PROJECT")}
