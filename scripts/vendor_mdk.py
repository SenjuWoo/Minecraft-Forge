"""Refresh the pinned official MDK from upstream; maintainer action, never startup.

Requires network. Records provenance and verifies the Gradle wrapper against its
published checksum. Does not run downloaded code or install global tools.
"""
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "f7002b1b6011723c7b12fde95147689491a6ddab"
URL = f"https://codeload.github.com/NeoForgeMDKs/MDK-1.21.1-ModDevGradle/zip/{COMMIT}"


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Minecraft-Forge/0.1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read(8 * 1024 * 1024)


def main():
    raw = fetch(URL)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {"/".join(p.split("/")[1:]): archive.read(p)
                 for p in archive.namelist() if not p.endswith("/")}
    wrapper = files["gradle/wrapper/gradle-wrapper.jar"]
    # Upstream updated the distribution URL but retains the authentic 8.14.3 wrapper.
    wrapper_hash = fetch("https://services.gradle.org/distributions/gradle-8.14.3-wrapper.jar.sha256").decode().strip()
    if hashlib.sha256(wrapper).hexdigest() != wrapper_hash:
        raise ValueError("Official Gradle wrapper checksum mismatch")
    dist_hash = fetch("https://services.gradle.org/distributions/gradle-9.2.1-bin.zip.sha256").decode().strip()
    licenses = [key for key in files if "license" in key.lower()]
    if not licenses:
        raise ValueError("Upstream template license missing")
    vendor = ROOT / "vendor"
    vendor.mkdir(exist_ok=True)
    target = vendor / "neoforge-1.21.1-mdk.zip"
    target.write_bytes(raw)
    record = {
        "repository": "https://github.com/NeoForgeMDKs/MDK-1.21.1-ModDevGradle",
        "commit": COMMIT, "url": URL, "archive": target.name,
        "sha256": hashlib.sha256(raw).hexdigest(), "verified_date": "2026-10-27",
        "minecraft": "1.21.1", "neo_version": "21.1.265", "java_major": 21,
        "gradle": "9.2.1", "gradle_distribution_sha256": dist_hash,
        "gradle_wrapper_version": "8.14.3", "gradle_wrapper_sha256": wrapper_hash,
        "licenses": licenses,
    }
    (vendor / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
