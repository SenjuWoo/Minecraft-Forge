"""Reject public-source hygiene defects before they reach a commit or release.

The scan covers files tracked by Git: ignored local reports, build outputs and
caches are not part of the public tree. Binary files are checked by path only.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each pattern is a defect with a concrete public consequence: a stale account
# link, an unexpanded manifest placeholder, a machine-local path or a
# credential-shaped string. Literal fragments are assembled so this file does
# not match its own scan.
FORBIDDEN_TEXT = {
    "stale legacy account link": re.compile("Shugoki" + "Fable"),
    "unexpanded manifest version": re.compile(r"0\.0" + "NONE"),
    "machine-local Windows path": re.compile(r"[A-Za-z]:\\Users\\", re.IGNORECASE),
    "machine-local backup path": re.compile(r"[A-Za-z]:\\Backup\\", re.IGNORECASE),
    "credential-shaped GitHub token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})\b"
    ),
}

# Built mods, compiled classes, logs, environment files and stray archives are
# never source. The vendored MDK ZIP is the one allowed archive: package.py
# pins and verifies its bytes against vendor/manifest.json.
FORBIDDEN_SUFFIXES = {".jar", ".class", ".log", ".env", ".zip"}
FORBIDDEN_PARTS = {"local", "dist", "build", ".gradle", "__pycache__"}


def tracked_files(root: Path = ROOT) -> list[Path]:
    """Return tracked files, or raise if Git cannot list them."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [root / name for name in result.stdout.split("\0") if name]


def scan(paths: list[Path], root: Path = ROOT) -> list[str]:
    """Return human-readable problems for the supplied files."""
    problems: list[str] = []
    for path in paths:
        relative = path.relative_to(root)
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            problems.append(f"{relative}: local or build output must not be tracked")
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            vendored = relative.parts[0] == "vendor" and path.suffix.lower() == ".zip"
            if not vendored:
                problems.append(f"{relative}: disallowed tracked file type")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in FORBIDDEN_TEXT.items():
            if pattern.search(text):
                problems.append(f"{relative}: {label}")
    return problems


def main() -> int:
    try:
        files = tracked_files()
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"hygiene: cannot list tracked files: {error}", file=sys.stderr)
        return 2
    problems = scan(files)
    if problems:
        print("Release hygiene failed:", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"Release hygiene passed ({len(files)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
