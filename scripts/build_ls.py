#!/usr/bin/env python3
"""Build the local fallback manifest used by /ls.

GitHub Pages compiles ls/site-files.json from Jekyll's site file collection on
every deployment. This script produces the equivalent fallback for local static
servers and can be run from anywhere inside the repository:

    python3 scripts/build_ls.py
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ls" / "site-files-fallback.json"
IGNORED_PARTS = {
    ".git",
    ".agents",
    ".codex",
    "node_modules",
    "__pycache__",
    "output",
    "tmp",
}
IGNORED_FILES = {
    Path("ls/site-files.json"),
    Path("ls/site-files-fallback.json"),
}


def repository_paths() -> list[Path]:
    """Return tracked and non-ignored untracked files, with an rglob fallback."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        relative_paths = [
            Path(raw.decode("utf-8"))
            for raw in result.stdout.split(b"\0")
            if raw
        ]
    except (FileNotFoundError, subprocess.CalledProcessError, UnicodeDecodeError):
        relative_paths = [
            path.relative_to(ROOT)
            for path in ROOT.rglob("*")
            if path.is_file()
        ]

    return sorted(
        (
            path
            for path in relative_paths
            if path not in IGNORED_FILES
            and not any(part in IGNORED_PARTS or part.startswith(".") for part in path.parts)
            and (ROOT / path).is_file()
        ),
        key=lambda path: path.as_posix().casefold(),
    )


def main() -> None:
    files = [
        {
            "path": f"/{path.as_posix()}",
            "size": (ROOT / path).stat().st_size,
        }
        for path in repository_paths()
    ]
    OUTPUT.write_text(
        json.dumps(files, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(files)} files to {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
