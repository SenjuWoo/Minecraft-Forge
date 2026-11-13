"""Refresh every pinned official template; maintainer action, never startup.

Requires network. Each archive is fetched from an immutable official URL, its
Gradle wrapper is matched against Gradle's published wrapper checksums, and the
result is written to vendor/targets.json (all targets) and vendor/manifest.json
(the default target, kept for older callers). No downloaded code is executed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor"
AGENT = "Minecraft-Forge (template maintenance)"
GITHUB = "https://codeload.github.com/{repo}/zip/{commit}"
FORGE = "https://maven.minecraftforge.net/net/minecraftforge/forge/{v}/forge-{v}-mdk.zip"

# One row per bundled target. `overrides` replace moving or ranged upstream pins
# with the exact versions this release was built against.
SPECS = [
    {"id": "neoforge-1.21.1", "loader": "neoforge", "family": "neoforge-mdg", "minecraft": "1.21.1",
     "repo": "NeoForgeMDKs/MDK-1.21.1-ModDevGradle", "commit": "f7002b1b6011723c7b12fde95147689491a6ddab",
     "archive": "neoforge-1.21.1-mdk.zip", "loader_version": "21.1.265", "java_major": 21, "gradle_java_major": 21},
    {"id": "neoforge-26.3", "loader": "neoforge", "family": "neoforge-mdg", "minecraft": "26.3",
     "repo": "NeoForgeMDKs/MDK-26.3-ModDevGradle", "commit": "3ed230cf177d44b4be4a69034d4a3259fd9c2b49",
     "archive": "neoforge-26.3-mdk.zip", "loader_version": "26.3.0.103", "java_major": 25, "gradle_java_major": 25},
    {"id": "fabric-1.20.1", "loader": "fabric", "family": "fabric-loom", "minecraft": "1.20.1",
     "repo": "FabricMC/fabric-example-mod", "commit": "cbac69685181b0104c2d1c94c4fb69bb51c8e685",
     "archive": "fabric-1.20.1-template.zip", "java_major": 17, "gradle_java_major": 25,
     "overrides": {"loom_version": "1.19.4"}},
    {"id": "fabric-1.21.1", "loader": "fabric", "family": "fabric-loom", "minecraft": "1.21.1",
     "repo": "FabricMC/fabric-example-mod", "commit": "4c47210589a9ff72a6075c8dd1d73315dcc3e010",
     "archive": "fabric-1.21.1-template.zip", "java_major": 21, "gradle_java_major": 25,
     "overrides": {"loom_version": "1.19.4"}},
    {"id": "fabric-26.3", "loader": "fabric", "family": "fabric-loom", "minecraft": "26.3",
     "repo": "FabricMC/fabric-example-mod", "commit": "bb432bac6559cf5f57a2d02f300fa6fa4b870d66",
     "archive": "fabric-26.3-template.zip", "java_major": 25, "gradle_java_major": 25,
     "overrides": {"loom_version": "1.19.4"}},
    {"id": "forge-1.20.1", "loader": "forge", "family": "forge-fg", "minecraft": "1.20.1",
     "forge": "1.20.1-47.4.28", "archive": "forge-1.20.1-mdk.zip", "loader_version": "47.4.28",
     "java_major": 17, "gradle_java_major": 17, "overrides": {"forgegradle": "6.0.54"}},
    {"id": "forge-26.3", "loader": "forge", "family": "forge-fg", "minecraft": "26.3",
     "forge": "26.3-66.1.8", "archive": "forge-26.3-mdk.zip", "loader_version": "66.1.8",
     "java_major": 25, "gradle_java_major": 25, "run_java_major": 8, "overrides": {"forgegradle": "7.0.40"}},
]
DEFAULT = "neoforge-1.21.1"


def fetch(url: str, limit: int = 8 * 1024 * 1024) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"Response exceeds {limit} bytes: {url}")
    return data


def wrapper_checksums() -> dict[str, str]:
    """Map every published release wrapper checksum to its Gradle version."""
    versions = [row for row in json.loads(fetch("https://services.gradle.org/versions/all"))
                if not (row.get("snapshot") or row.get("nightly") or row.get("releaseNightly") or row.get("broken")
                        or row.get("rcFor") or row.get("milestoneFor")) and row.get("wrapperChecksumUrl")
                and int(row["version"].split(".")[0]) >= 8]

    def one(row):
        try:
            return fetch(row["wrapperChecksumUrl"], 4096).decode().strip(), row["version"]
        except OSError:
            return None
    # Several releases ship byte-identical wrappers; report the newest for a stable record.
    versions.sort(key=lambda row: tuple(int(part) for part in row["version"].split(".")))
    with ThreadPoolExecutor(8) as pool:
        return dict(item for item in pool.map(one, versions) if item)


def members(raw: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        tops = {name.split("/", 1)[0] for name in names}
        strip = len(tops) == 1 and all("/" in name for name in names)
        return {(name.split("/", 1)[1] if strip else name): archive.read(name) for name in names}


def main() -> int:
    VENDOR.mkdir(exist_ok=True)
    wrappers = wrapper_checksums()
    targets = {}
    for spec in SPECS:
        url = (GITHUB.format(repo=spec["repo"], commit=spec["commit"]) if "repo" in spec
               else FORGE.format(v=spec["forge"]))
        raw = fetch(url)
        files = members(raw)
        wrapper_hash = hashlib.sha256(files["gradle/wrapper/gradle-wrapper.jar"]).hexdigest()
        if wrapper_hash not in wrappers:
            raise ValueError(f"{spec['id']}: Gradle wrapper matches no published release checksum")
        properties = files["gradle/wrapper/gradle-wrapper.properties"].decode()
        gradle = re.search(r"/gradle-([0-9][0-9.]*)-(?:bin|all)\.zip", properties)[1]
        kind = "all" if f"gradle-{gradle}-all.zip" in properties else "bin"
        dist_hash = fetch(f"https://services.gradle.org/distributions/gradle-{gradle}-{kind}.zip.sha256", 4096).decode().strip()
        licenses = sorted(name for name in files if "license" in name.lower() and "/" not in name)
        if not licenses:
            raise ValueError(f"{spec['id']}: upstream template license missing")
        (VENDOR / spec["archive"]).write_bytes(raw)
        record = {key: spec[key] for key in ("loader", "family", "minecraft", "java_major", "gradle_java_major", "archive")}
        record.update(sha256=hashlib.sha256(raw).hexdigest(), url=url, verified_date="2026-11-13",
                      gradle=gradle, gradle_distribution_sha256=dist_hash,
                      gradle_wrapper_version=wrappers[wrapper_hash], gradle_wrapper_sha256=wrapper_hash,
                      licenses=licenses, overrides=spec.get("overrides", {}))
        if "repo" in spec:
            record.update(repository=f"https://github.com/{spec['repo']}", commit=spec["commit"])
        else:
            record["repository"] = "https://maven.minecraftforge.net/net/minecraftforge/forge/"
        for optional in ("loader_version", "run_java_major"):
            if optional in spec:
                record[optional] = spec[optional]
        targets[spec["id"]] = record
        print(f"{spec['id']}: {record['sha256']} gradle {gradle} wrapper {record['gradle_wrapper_version']}", file=sys.stderr)
    (VENDOR / "targets.json").write_text(json.dumps({"schema": 1, "default": DEFAULT, "targets": targets}, indent=2) + "\n", encoding="utf-8", newline="\n")
    default = targets[DEFAULT]
    legacy = {"repository": default["repository"], "commit": default["commit"], "url": default["url"],
              "archive": default["archive"], "sha256": default["sha256"], "verified_date": "2026-10-27",
              "minecraft": default["minecraft"], "neo_version": default["loader_version"], "java_major": default["java_major"],
              "gradle": default["gradle"], "gradle_distribution_sha256": default["gradle_distribution_sha256"],
              "gradle_wrapper_version": default["gradle_wrapper_version"], "gradle_wrapper_sha256": default["gradle_wrapper_sha256"],
              "licenses": default["licenses"]}
    (VENDOR / "manifest.json").write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"targets": sorted(targets), "default": DEFAULT}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
