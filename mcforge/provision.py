"""Optional JDK provisioning from Adoptium's official API.

Only explicit setup-java downloads a JDK (17, 21 or 25) into this toolkit's
local/tools folder. The resolved release and SHA-256 are recorded locally; no
global PATH, registry or launcher files are modified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import tarfile
import tempfile
import urllib.parse
import urllib.request
import zipfile

from .workbench import ROOT, check_java, guard_output
from . import __version__

MAJORS = (8, 17, 21, 25)


def _platform() -> tuple[str, str]:
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "mac"}.get(platform.system())
    machine = {"amd64": "x64", "x86_64": "x64", "arm64": "aarch64", "aarch64": "aarch64"}.get(platform.machine().lower())
    if not system or not machine:
        raise ValueError("JDK provisioning supports Windows, Linux and macOS on x64/aarch64; "
                         "install an official JDK for your platform and set MCFORGE_JAVA_HOME")
    return system, machine


def api_url(major: int = 21) -> str:
    try:
        system, machine = _platform()
    except ValueError:
        system, machine = "windows", "x64"
    return f"https://api.adoptium.net/v3/assets/latest/{major}/hotspot?architecture={machine}&image_type=jdk&os={system}&vendor=eclipse"


API = api_url(21)


def request(url: str):
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError("Provisioning requires HTTPS")
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__}"}), timeout=60)


def java_plan(major: int = 21) -> dict:
    if major not in MAJORS:
        raise ValueError("setup-java provisions JDK 8, 17, 21 or 25")
    source = API if major == 21 else api_url(major)
    with request(source) as response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("JDK metadata exceeds limit")
    assets = json.loads(data)
    if len(assets) != 1:
        raise ValueError("JDK API did not resolve exactly one release")
    asset = assets[0]
    package = asset["binary"]["package"]
    url = urllib.parse.urlparse(package["link"])
    checksum = package["checksum"]
    if url.scheme != "https" or url.hostname != "github.com" or not url.path.startswith(f"/adoptium/temurin{major}-binaries/releases/download/"):
        raise ValueError(f"JDK download is not an official Temurin{major} release")
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("Invalid JDK checksum")
    if not 0 < package["size"] <= 350 * 1024 * 1024:
        raise ValueError("JDK package exceeds download budget")
    return {"release": asset["release_name"], "url": package["link"], "sha256": checksum,
            "size_bytes": package["size"], "source": source, "destination": str(ROOT / f"local/tools/jdk{major}")}


def extract_jdk(archive: Path, stage: Path):
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            entries = source.infolist()
            if len(entries) > 30000 or sum(e.file_size for e in entries) > 1024 * 1024 * 1024:
                raise ValueError("JDK archive exceeds extraction budget")
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or ":" in entry.filename:
                    raise ValueError("Unsafe JDK archive path")
                if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Linked JDK archive entry")
            source.extractall(stage)
        return
    with tarfile.open(archive, "r:gz") as source:
        entries = source.getmembers()
        if len(entries) > 30000 or sum(e.size for e in entries) > 1024 * 1024 * 1024:
            raise ValueError("JDK archive exceeds extraction budget")
        for entry in entries:
            path = PurePosixPath(entry.name)
            if path.is_absolute() or ".." in path.parts or "\\" in entry.name or ":" in entry.name:
                raise ValueError("Unsafe JDK archive path")
        # The data filter refuses links and devices that would leave the stage.
        source.extractall(stage, filter="data")


def setup_java(plan_only: bool = False, major: int = 21) -> dict:
    _platform()
    plan = java_plan(major)
    if plan_only:
        return plan
    target = Path(plan["destination"])
    guard_output(target)
    if target.exists():
        raise ValueError("Local JDK destination already exists; inspect it before replacing anything")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".jdk-", dir=target.parent) as scratch:
        base = Path(scratch)
        archive = base / "jdk.archive"
        hasher = hashlib.sha256()
        size = 0
        with request(plan["url"]) as response, archive.open("xb") as output:
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > plan["size_bytes"]:
                    raise ValueError("JDK download exceeds published size")
                hasher.update(block)
                output.write(block)
        if size != plan["size_bytes"] or hasher.hexdigest() != plan["sha256"]:
            raise ValueError("JDK size/checksum mismatch")
        stage = base / "unpacked"
        extract_jdk(archive, stage)
        roots = [p for p in stage.iterdir() if p.is_dir()]
        if len(roots) != 1:
            raise ValueError("Unexpected JDK archive layout")
        # macOS archives nest the runtime under Contents/Home.
        home = roots[0] / "Contents/Home" if (roots[0] / "Contents/Home/bin").is_dir() else roots[0]
        info = check_java(home)
        if info["major"] != major or not info["jdk"] or info.get("exit_code") != 0:
            raise ValueError("Downloaded JDK failed runtime check")
        (home / "MCFORGE-PROVENANCE.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        home.rename(target)
    return {"installed": str(target), "provenance": plan}
