"""Create a clean WorkMate release archive without local runtime data."""

from __future__ import annotations

import os
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist" / "WorkMateAI-R3-FAISS-Updated.zip"
SKIP_DIRS = {
    ".git", ".venv", "venv", "runs", "dist", "__pycache__",
    ".pytest_cache", "vector_store", "model_cache",
}


def main() -> None:
    if OUTPUT.exists():
        raise SystemExit(f"Refusing to overwrite existing archive: {OUTPUT}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for current, directories, files in os.walk(ROOT):
            directories[:] = sorted(name for name in directories if name not in SKIP_DIRS)
            for name in sorted(files):
                path = Path(current) / name
                relative = path.relative_to(ROOT)
                if name == ".env" or path.suffix.lower() in {".pyc", ".sqlite3"}:
                    continue
                archive.write(path, relative.as_posix())
                entries += 1

    with zipfile.ZipFile(OUTPUT) as archive:
        names = archive.namelist()
        forbidden = [
            name for name in names
            if any(part in SKIP_DIRS for part in Path(name).parts)
            or Path(name).name == ".env"
            or Path(name).suffix.lower() in {".pyc", ".sqlite3"}
        ]
        if forbidden:
            OUTPUT.unlink(missing_ok=True)
            raise SystemExit(f"Excluded files found in archive: {forbidden[:5]}")
        required = {
            "workmate/vector_store.py",
            "tests/test_vector_store.py",
            "docs/VECTOR_DATABASE_EVALUATION.md",
        }
        missing = required.difference(names)
        if missing:
            OUTPUT.unlink(missing_ok=True)
            raise SystemExit(f"Required release files missing: {sorted(missing)}")
    print(f"Created {OUTPUT} ({entries} files)")
    print("Verified no .env, SQLite databases, Python caches, runs, or model/index caches")


if __name__ == "__main__":
    main()
