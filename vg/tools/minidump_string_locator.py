"""Locate exact strings in a minidump and map file offsets to virtual addresses."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .dump_keyword_search import _find_all
from .minidump_parser import map_file_offset_to_va, parse_memory_ranges


def locate_strings_in_minidump(dump_path: str, strings: List[str]) -> Dict[str, object]:
    path = Path(dump_path)
    data = path.read_bytes()
    ranges = parse_memory_ranges(data)
    rows = []
    for value in strings:
        needle = value.encode("utf-16-le")
        hits = []
        for file_offset in _find_all(data, needle):
            hits.append(
                {
                    "file_offset": file_offset,
                    "virtual_address": map_file_offset_to_va(ranges, file_offset),
                }
            )
        rows.append({"value": value, "hit_count": len(hits), "hits": hits[:100]})
    return {
        "dump_path": str(path.resolve()),
        "memory_range_count": len(ranges),
        "strings": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Locate exact UTF-16 strings in a minidump and map them to virtual addresses.")
    parser.add_argument("--dump", required=True, help="Minidump path")
    parser.add_argument("--string", action="append", required=True, help="Exact string to locate")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = locate_strings_in_minidump(args.dump, list(args.string))
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Minidump string locator saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
