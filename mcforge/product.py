"""The explicit portable-product allowlist shared by packaging and local install.

Only runtime code, guides, tests, templates and pinned vendor bytes are
included. Private ledgers, local reports, caches and release archives never are.
"""

from __future__ import annotations

from pathlib import Path

from .workbench import TESTING_FILES

PRODUCT_NAMES = (
    "Minecraft-Forge.ps1",
    "README.md",
    "AGENTS.md",
    "LICENSE",
    "THIRD-PARTY.md",
    "CREDITS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
)

PRODUCT_GLOBS = {
    "assets": ("*.svg", "*.png"),
    "mcforge": ("*.py",),
    "docs": ("*.md",),
    "skills": ("*.md",),
    "vendor": ("*.json", "*.zip", "*.txt"),
    "tests": ("*.py",),
    "scripts": ("*.py",),
}


def product_files(root: Path) -> list[Path]:
    """Return the exact portable payload, failing on a missing required file."""
    files = [root / name for name in PRODUCT_NAMES]
    files.extend(root / "templates/testing" / name for name in TESTING_FILES)
    for directory, patterns in PRODUCT_GLOBS.items():
        for pattern in patterns:
            files.extend((root / directory).rglob(pattern))
    unique = sorted(set(files))
    missing = [path.relative_to(root).as_posix() for path in unique if not path.is_file()]
    if missing:
        raise ValueError("Portable product is missing required files: " + ", ".join(missing))
    return unique
