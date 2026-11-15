"""Reject public-source hygiene defects before they reach a commit or release.

The scan covers files tracked by Git: ignored local reports, build outputs and
caches are not part of the public tree. Binary files are checked by path only.
"""

from __future__ import annotations

import hashlib
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

# Public text stays family-friendly: none of the blocked vocabulary in any tracked
# file. The words are stored as SHA-256 prefixes of lowercase whole words, so
# this file contains none of the words it rejects.
BLOCKED_WORD_HASHES = frozenset({
    "0033728f0fbc83a0", "01b3c1269215e1a0", "0508a634445d4016", "0add1fe38f967689", "0f28c4960d96647e", "102626eace2d1293",
    "12a667c9be6ff8f6", "22082517effcaaaa", "25390976ce87338a", "2a6060b5e21aacf2", "38136d6e343860f6", "3a7a3762ef7b56d0",
    "3f319f095c6630cd", "4140197ec7959b1c", "4ae1915834846378", "4bb60e47e119588e", "594810adcbee20bd", "6556c1a58444e10f",
    "6577be77529947bf", "6672b930d5d08ec0", "6b247754a7cbff78", "6ccffa4977d4246e", "6cd1442aa2721a94", "796e43a5a8cdb73b",
    "7e03b174115e2c78", "7e85c676fd97d370", "7f5a9ba14cb89dc2", "7fdc3e8038e87ff5", "83ebccea9fff4079", "8c5c04391361cbf4",
    "94a2b576a9f577e9", "98d44e13f455d916", "9a4eac2dfadaf64a", "9c5ba01ca08e6b8a", "9ddcab3ac3610db0", "a02d538d50989a60",
    "a368606514955567", "acf45488978d9ff4", "b29d65697289995a", "ba79229c14881e61", "c6603565c5159fbe", "cd2eb0837c9b4c96",
    "d516dbecbf6a8cb4", "d84f691fc4981d9d", "d92f4cf1e2d7e812", "e1b73076698c35dc", "e25e2951d83772d4", "e683679358a5aea3",
    "e99d55248f67be76", "ebec03d80c0d3bff", "eff26b18165ece9c", "f6952d6eef555ddd", "ff5ae7e8d206066d",
})
WORD = re.compile(r"[a-z]+")


def blocked_words(text: str, blocked=BLOCKED_WORD_HASHES) -> int:
    """Number of distinct whole words in text whose hash is on the blocked list."""
    return sum(1 for word in set(WORD.findall(text.lower()))
               if hashlib.sha256(word.encode()).hexdigest()[:16] in blocked)


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


def scan(paths: list[Path], root: Path = ROOT, blocked=BLOCKED_WORD_HASHES) -> list[str]:
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
        count = blocked_words(text, blocked)
        if count:
            problems.append(f"{relative}: {count} word(s) not allowed in public text (blocked vocabulary)")
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
