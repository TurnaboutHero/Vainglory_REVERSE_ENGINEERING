"""Extract printable neighborhoods around keyword hits inside dump files."""

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


def _printable_ascii(chunk: bytes) -> str:
    return "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)


def build_dump_neighborhood_report(dump_path: str, keyword: str, radius: int = 128) -> Dict[str, object]:
    dump = Path(dump_path)
    data = dump.read_bytes()
    encodings = {
        "ascii": keyword.encode("ascii", errors="ignore") if all(ord(ch) < 128 for ch in keyword) else b"",
        "utf8": keyword.encode("utf-8"),
        "utf16le": keyword.encode("utf-16-le"),
        "utf16be": keyword.encode("utf-16-be"),
    }

    hits = []
    for encoding_name, needle in encodings.items():
        if not needle:
            continue
        for offset in _find_all(data, needle)[:100]:
            start = max(0, offset - radius)
            end = min(len(data), offset + len(needle) + radius)
            chunk = data[start:end]
            hits.append(
                {
                    "encoding": encoding_name,
                    "offset": offset,
                    "context_start": start,
                    "context_end": end,
                    "context_hex_prefix": chunk[:64].hex(),
                    "context_ascii": _printable_ascii(chunk),
                }
            )

    return {
        "dump_path": str(dump.resolve()),
        "keyword": keyword,
        "radius": radius,
        "hit_count": len(hits),
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract neighborhoods around keyword hits in a dump file.")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--keyword", required=True, help="Keyword to inspect")
    parser.add_argument("--radius", type=int, default=128, help="Bytes before/after hit to include")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_neighborhood_report(args.dump, args.keyword, radius=args.radius)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump neighborhood report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
