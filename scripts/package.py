"""Build the portable toolkit from an explicit product allowlist.

No installed mods, local reports, Gradle caches or ownership ledgers enter it.
Every entry is hashed in the package manifest; archives use stable timestamps.
"""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mcforge import __version__
from mcforge.workbench import testing_templates, verify_vendor


def main():
    verify_vendor()
    files = [ROOT / name for name in ("Minecraft-Forge.ps1", "README.md", "AGENTS.md", "LICENSE", "THIRD-PARTY.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md")]
    files.extend(testing_templates())
    for directory, patterns in {"mcforge": ("*.py",), "docs": ("*.md",), "skills": ("*.md",), "vendor": ("*.json", "*.zip", "*.txt"), "tests": ("*.py",), "scripts": ("*.py",)}.items():
        for pattern in patterns:
            files.extend((ROOT / directory).rglob(pattern))
    payload = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in sorted(set(files))}
    if "skills/minecraft-forge/SKILL.md" not in payload:
        raise ValueError("Agent skill missing from toolkit source")
    payload["PACKAGE-MANIFEST.json"] = (json.dumps({"version": __version__, "files": {key: hashlib.sha256(data).hexdigest() for key, data in payload.items()}}, indent=2) + "\n").encode()
    output = ROOT / "dist" / f"Minecraft-Forge-{__version__}.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="utf-8")
    print(json.dumps({"archive": str(output), "sha256": checksum, "files": len(payload), "size_bytes": output.stat().st_size}))


if __name__ == "__main__":
    main()
