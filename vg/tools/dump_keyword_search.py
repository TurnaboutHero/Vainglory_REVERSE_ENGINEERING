"""Search dump files for specific keywords across common encodings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def _find_all(data: bytes, needle: bytes) -> List[int]:
    offsets: List[int] = []
    start = 0
    while True:
        index = data.find(needle, start)
        if index == -1:
            break
        offsets.append(index)
        start = index + 1
    return offsets


def search_dump_keywords(dump_path: str, keywords: List[str]) -> Dict[str, object]:
    dump = Path(dump_path)
    data = dump.read_bytes()
    results = []

    for keyword in keywords:
        encodings = {
            "ascii": keyword.encode("ascii", errors="ignore") if all(ord(ch) < 128 for ch in keyword) else b"",
            "utf8": keyword.encode("utf-8"),
            "utf16le": keyword.encode("utf-16-le"),
            "utf16be": keyword.encode("utf-16-be"),
        }

        row = {
            "keyword": keyword,
            "matches": {},
        }
        for encoding_name, needle in encodings.items():
            if not needle:
                continue
            offsets = _find_all(data, needle)
            row["matches"][encoding_name] = {
                "count": len(offsets),
                "offsets": offsets[:100],
            }
        results.append(row)

    return {
        "dump_path": str(dump.resolve()),
        "size_bytes": dump.stat().st_size,
        "keywords": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Search a dump file for specific keywords.")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--keyword", action="append", required=True, help="Keyword to search (can be repeated)")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = search_dump_keywords(args.dump, list(args.keyword))
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump keyword search saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
