"""Locate qword pointers to known virtual addresses inside a minidump."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List

from .minidump_parser import map_file_offset_to_va, parse_memory_ranges


def locate_pointers_in_minidump(dump_path: str, targets: List[Dict[str, object]]) -> Dict[str, object]:
    path = Path(dump_path)
    data = path.read_bytes()
    ranges = parse_memory_ranges(data)

    rows = []
    for target in targets:
        label = str(target["label"])
        va = int(target["virtual_address"])
        needle = struct.pack("<Q", va)
        hits = []
        start = 0
        while True:
            idx = data.find(needle, start)
            if idx == -1:
                break
            hits.append(
                {
                    "file_offset": idx,
                    "pointer_va": map_file_offset_to_va(ranges, idx),
                }
            )
            start = idx + 1
        rows.append(
            {
                "label": label,
                "virtual_address": va,
                "pointer_hit_count": len(hits),
                "pointer_hits": hits[:200],
            }
        )

    return {
        "dump_path": str(path.resolve()),
        "memory_range_count": len(ranges),
        "targets": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Locate qword pointers to known VAs in a minidump.")
    parser.add_argument("--dump", required=True, help="Minidump path")
    parser.add_argument("--targets-json", required=True, help="JSON file containing [{'label', 'virtual_address'}]")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    targets = json.loads(Path(args.targets_json).read_text(encoding="utf-8"))
    report = locate_pointers_in_minidump(args.dump, targets)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Minidump pointer locator saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
