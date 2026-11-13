"""Bundled loader targets: pinned official templates with recorded provenance.

``vendor/targets.json`` is the registry. Every bundled target is built by this
toolkit's CI. Other Minecraft versions resolve on demand from the same official
sources (``resolve_remote``); those are pinned by hash when fetched and are
labelled unverified, because no release of this toolkit built them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import urllib.request

from . import __version__
from . import workbench

LOADERS = ("neoforge", "fabric", "forge")
FAMILIES = {"neoforge": "neoforge-mdg", "fabric": "fabric-loom", "forge": "forge-fg"}
MINECRAFT = re.compile(r"\d+(?:\.\d+){1,2}")
MAX_TEMPLATE = 8 * 1024 * 1024


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _root() -> Path:
    return workbench.ROOT


def load_targets() -> dict:
    registry = _root() / "vendor/targets.json"
    if not registry.is_file():
        # A toolkit copy older than the registry carries one NeoForge template and its manifest.
        legacy = json.loads((_root() / "vendor/manifest.json").read_text(encoding="utf-8-sig"))
        target = dict(legacy, loader="neoforge", family="neoforge-mdg", loader_version=legacy["neo_version"],
                      gradle_java_major=legacy["java_major"], overrides={})
        return {"schema": 1, "default": "neoforge-1.21.1", "targets": {"neoforge-1.21.1": target}}
    data = json.loads(registry.read_text(encoding="utf-8-sig"))
    if data.get("schema") != 1 or not isinstance(data.get("targets"), dict) or data.get("default") not in data["targets"]:
        raise ValueError("vendor/targets.json is not a valid target registry; restore the toolkit")
    return data


def archive_path(target: dict) -> Path:
    name = target["archive"]
    if "/" in name or "\\" in name:
        raise ValueError("Template archive name must be a plain file name")
    return (_root() / "local/templates" if target.get("tier") == "on-demand" else _root() / "vendor") / name


def verify_template(target: dict) -> dict:
    path = archive_path(target)
    if not path.is_file() or _digest(path) != target["sha256"]:
        raise ValueError(f"Template hash mismatch for {target['id']}; restore the toolkit or refetch the template")
    return target


def list_targets() -> list[dict]:
    data = load_targets()
    rows = []
    for name, target in sorted(data["targets"].items()):
        rows.append({"id": name, "loader": target["loader"], "minecraft": target["minecraft"],
                     "loader_version": target.get("loader_version"), "java_major": target["java_major"],
                     "gradle_java_major": target["gradle_java_major"], "run_java_major": target.get("run_java_major"),
                     "gradle": target["gradle"],
                     "tier": "bundled", "default": name == data["default"]})
    return rows


def select_target(loader: str | None = None, minecraft: str | None = None, target_id: str | None = None) -> dict:
    """Return one bundled target; an unknown pair names the on-demand route instead of guessing."""
    data = load_targets()
    if target_id:
        if target_id not in data["targets"]:
            raise ValueError(f"Unknown target {target_id}; bundled: {', '.join(sorted(data['targets']))}")
        chosen = target_id
    elif loader is None and minecraft is None:
        chosen = data["default"]
    else:
        loader = (loader or data["targets"][data["default"]]["loader"]).lower()
        if loader not in LOADERS:
            raise ValueError(f"Unknown loader {loader}; use one of: {', '.join(LOADERS)} (Quilt loads Fabric mods)")
        matches = [name for name, target in data["targets"].items()
                   if target["loader"] == loader and (minecraft is None or target["minecraft"] == minecraft)]
        if not matches:
            raise ValueError(f"No bundled {loader} template for Minecraft {minecraft}; "
                             f"add --fetch to resolve the official one, or pick from: targets")
        # Without a version, prefer the default's Minecraft, then the newest bundled.
        default_mc = data["targets"][data["default"]]["minecraft"]
        matches.sort(key=lambda name: (data["targets"][name]["minecraft"] == default_mc,
                                       tuple(int(part) for part in data["targets"][name]["minecraft"].split("."))))
        chosen = matches[-1]
    return verify_template(dict(data["targets"][chosen], id=chosen, tier="bundled"))


def _fetch(url: str, limit: int = MAX_TEMPLATE) -> bytes:
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError("Template sources must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__} (template resolution)"})
    with urllib.request.urlopen(request, timeout=60) as response:
        if urllib.parse.urlparse(response.geturl()).scheme != "https":
            raise ValueError("Template source redirected away from HTTPS")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Template response exceeds the size limit")
    return data


def _stable(url: str) -> list[str]:
    versions = re.findall(r"<version>(\d+(?:\.\d+)+)</version>", _fetch(url, 1 << 21).decode("utf-8", "replace"))
    return sorted(set(versions), key=lambda value: tuple(int(part) for part in value.split(".")))


def _exact_pins(loader: str, build: str, properties: str) -> dict:
    """Replace an upstream version range or snapshot with the newest matching release."""
    if loader == "forge":
        ranged = re.search(r"id\s+['\"]net\.minecraftforge\.gradle['\"]\s+version\s+['\"]\[([0-9.]+),\s*([0-9.]+)\)['\"]", build)
        if ranged:
            key = lambda value: tuple(int(part) for part in value.split("."))
            found = [v for v in _stable("https://maven.minecraftforge.net/net/minecraftforge/gradle/net.minecraftforge.gradle.gradle.plugin/maven-metadata.xml")
                     + _stable("https://maven.minecraftforge.net/net/minecraftforge/gradle/ForgeGradle/maven-metadata.xml")
                     if key(ranged[1]) <= key(v) < key(ranged[2])]
            if not found:
                raise ValueError("No ForgeGradle release satisfies the template's version range")
            return {"forgegradle": sorted(set(found), key=key)[-1]}
    if loader == "fabric":
        snapshot = re.search(r"(?m)^loom_version\s*=\s*(\d+\.\d+)-SNAPSHOT\s*$", properties)
        if snapshot:
            releases = _stable("https://maven.fabricmc.net/net/fabricmc/fabric-loom/maven-metadata.xml")
            line = [v for v in releases if v.startswith(snapshot[1] + ".")] or releases
            return {"loom_version": line[-1]}
    return {}


def resolve_remote(loader: str, minecraft: str, loader_version: str | None = None) -> dict:
    """Fetch the official template for a version this release does not bundle.

    The archive lands in ``local/templates`` with its hash recorded. It is the
    upstream project's template at that moment: this toolkit never built it.
    """
    import io
    import zipfile
    loader = loader.lower()
    if loader not in LOADERS or not MINECRAFT.fullmatch(minecraft or ""):
        raise ValueError("--fetch needs --loader neoforge|fabric|forge and an exact --minecraft version")
    record = {"loader": loader, "family": FAMILIES[loader], "minecraft": minecraft, "tier": "on-demand", "overrides": {}}
    if loader == "forge":
        if not loader_version:
            promos = json.loads(_fetch("https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json", 1 << 20))["promos"]
            loader_version = promos.get(f"{minecraft}-recommended") or promos.get(f"{minecraft}-latest")
            if not loader_version:
                raise ValueError(f"Forge publishes no build for Minecraft {minecraft}")
        version = f"{minecraft}-{loader_version}"
        record.update(url=f"https://maven.minecraftforge.net/net/minecraftforge/forge/{version}/forge-{version}-mdk.zip",
                      repository="https://maven.minecraftforge.net/net/minecraftforge/forge/", loader_version=loader_version)
    else:
        repo = f"NeoForgeMDKs/MDK-{minecraft}-ModDevGradle" if loader == "neoforge" else "FabricMC/fabric-example-mod"
        branch = "main" if loader == "neoforge" else minecraft
        commit = json.loads(_fetch(f"https://api.github.com/repos/{repo}/commits/{branch}", 1 << 20)).get("sha", "")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"No official {loader} template for Minecraft {minecraft}")
        record.update(url=f"https://codeload.github.com/{repo}/zip/{commit}", repository=f"https://github.com/{repo}", commit=commit)
        if loader_version:
            record["loader_version"] = loader_version
    raw = _fetch(record["url"])
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        strip = len({name.split("/", 1)[0] for name in names}) == 1 and all("/" in name for name in names)
        files = {(name.split("/", 1)[1] if strip else name): name for name in names}
        for needed in ("build.gradle", "gradle/wrapper/gradle-wrapper.jar", "gradle/wrapper/gradle-wrapper.properties"):
            if needed not in files:
                raise ValueError(f"Official template has an unsupported layout (missing {needed})")
        wrapper = hashlib.sha256(archive.read(files["gradle/wrapper/gradle-wrapper.jar"])).hexdigest()
        properties = archive.read(files["gradle/wrapper/gradle-wrapper.properties"]).decode("utf-8")
        build = archive.read(files["build.gradle"]).decode("utf-8")
        props = archive.read(files["gradle.properties"]).decode("utf-8") if "gradle.properties" in files else ""
    record["overrides"] = _exact_pins(loader, build, props)
    gradle = re.search(r"/gradle-([0-9][0-9.]*)-(bin|all)\.zip", properties)
    if not gradle:
        raise ValueError("Official template has no resolvable Gradle distribution")
    java = re.search(r"JavaLanguageVersion\.of\((\d+)\)|options\.release\s*=\s*(\d+)", build)
    if not java:
        raise ValueError("Official template declares no Java version")
    major = int(java[1] or java[2])
    record.update(sha256=hashlib.sha256(raw).hexdigest(), gradle=gradle[1], java_major=major,
                  gradle_java_major=max(major, 25 if record["overrides"].get("loom_version", "1.19") >= "1.19" else 21) if loader == "fabric" else major,
                  gradle_distribution_sha256=_fetch(f"https://services.gradle.org/distributions/gradle-{gradle[1]}-{gradle[2]}.zip.sha256", 4096).decode().strip(),
                  gradle_wrapper_sha256=wrapper, archive=f"{loader}-{minecraft}-{hashlib.sha256(raw).hexdigest()[:12]}.zip",
                  id=f"{loader}-{minecraft}")
    cache = _root() / "local/templates"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / record["archive"]
    if not path.is_file():
        path.write_bytes(raw)
    return verify_template(record)
