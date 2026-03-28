"""Extract simple ASCII/UTF-16 strings from dump files and diff them."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set


ASCII_RE = re.compile(rb"[\x20-\x7E]{4,}")
UTF16_RE = re.compile((rb"(?:[\x20-\x7E]\x00){4,}"))


def extract_strings_from_bytes(data: bytes) -> Set[str]:
    values: Set[str] = set()
    for match in ASCII_RE.findall(data):
        try:
            values.add(match.decode("ascii"))
        except Exception:
            pass
    for match in UTF16_RE.findall(data):
        try:
            values.add(match.decode("utf-16-le"))
        except Exception:
            pass
    return values


def build_dump_string_diff(before_path: str, after_path: str) -> Dict[str, object]:
    before = Path(before_path).read_bytes()
    after = Path(after_path).read_bytes()
    before_strings = extract_strings_from_bytes(before)
    after_strings = extract_strings_from_bytes(after)
    added = sorted(after_strings - before_strings)
    removed = sorted(before_strings - after_strings)
    return {
        "before_path": str(Path(before_path).resolve()),
        "after_path": str(Path(after_path).resolve()),
        "before_strings": len(before_strings),
        "after_strings": len(after_strings),
        "added_count": len(added),
        "removed_count": len(removed),
        "added_sample": added[:200],
        "removed_sample": removed[:200],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff strings between two dump files.")
    parser.add_argument("--before", required=True, help="Before dump path")
    parser.add_argument("--after", required=True, help="After dump path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_string_diff(args.before, args.after)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump diff saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
