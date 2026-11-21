#!/usr/bin/env python3
"""Rebuild the local FAISS index from SQLite source records."""

import json
import sys

from workmate.vector_store import get_vector_store_stats, rebuild_vector_index


def main():
    try:
        result = rebuild_vector_index()
        result["stats"] = get_vector_store_stats()
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "vector_rebuild_failed"}))
        print(f"[workmate] {type(exc).__name__}: vector rebuild failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
