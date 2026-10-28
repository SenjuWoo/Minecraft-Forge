"""Optional Windows JDK21 provisioning from Adoptium's official API.

Only explicit setup-java downloads a JDK. The resolved release and SHA-256 are
recorded locally; no global PATH, registry or launcher files are modified.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import tempfile
import urllib.parse
import urllib.request
import zipfile

from .workbench import ROOT, check_java, guard_output
from . import __version__

API = "https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse"


def request(url: str):
    if urllib.parse.urlparse(url).scheme != "https":
        raise ValueError("Provisioning requires HTTPS")
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"Minecraft-Forge/{__version__}"}), timeout=60)


def java_plan() -> dict:
    with request(API) as response:
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
    if url.scheme != "https" or url.hostname != "github.com" or not url.path.startswith("/adoptium/temurin21-binaries/releases/download/"):
        raise ValueError("JDK download is not an official Temurin21 release")
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("Invalid JDK checksum")
    if not 0 < package["size"] <= 350 * 1024 * 1024:
        raise ValueError("JDK package exceeds download budget")
    return {"release": asset["release_name"], "url": package["link"], "sha256": checksum,
            "size_bytes": package["size"], "source": API, "destination": str(ROOT / "local/tools/jdk21")}


def extract_jdk(archive: Path, stage: Path):
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


def setup_java(plan_only: bool = False) -> dict:
    if os.name != "nt" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise ValueError("Bundled provisioning supports Windows x64; use an official JDK21 for your platform and set MCFORGE_JAVA_HOME")
    plan = java_plan()
    if plan_only:
        return plan
    target = Path(plan["destination"])
    guard_output(target)
    if target.exists():
        raise ValueError("Local JDK destination already exists; inspect it before replacing anything")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".jdk-", dir=target.parent) as scratch:
        base = Path(scratch)
        archive = base / "jdk.zip"
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
        home = roots[0]
        info = check_java(home)
        if info["major"] != 21 or not info["jdk"] or info.get("exit_code") != 0:
            raise ValueError("Downloaded JDK failed runtime check")
        (home / "MCFORGE-PROVENANCE.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        home.rename(target)
    return {"installed": str(target), "provenance": plan}
