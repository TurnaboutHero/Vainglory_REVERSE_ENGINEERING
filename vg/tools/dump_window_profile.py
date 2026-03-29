"""Profile a fixed byte window inside a dump file."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .dump_string_cluster_report import extract_strings_with_offsets


def build_dump_window_profile(dump_path: str, start: int, length: int = 4096) -> Dict[str, object]:
    path = Path(dump_path)
    data = path.read_bytes()
    chunk = data[start : start + length]
    printable_ratio = sum(32 <= b < 127 for b in chunk) / len(chunk) if chunk else 0.0
    top_bytes = [{"byte": byte, "count": count} for byte, count in Counter(chunk).most_common(16)]
    top_pairs = [
        {"pair_hex": pair.hex(), "count": count}
        for pair, count in Counter(chunk[i : i + 2] for i in range(0, max(0, len(chunk) - 1), 2)).most_common(12)
    ]
    top_eights = [
        {"chunk_hex": eight.hex(), "count": count}
        for eight, count in Counter(chunk[i : i + 8] for i in range(0, max(0, len(chunk) - 7), 8)).most_common(12)
    ]

    strings = []
    for row in extract_strings_with_offsets(data):
        offset = int(row["offset"])
        if start <= offset < start + length:
            strings.append(
                {
                    "offset": offset,
                    "encoding": row["encoding"],
                    "value": str(row["value"])[:160],
                }
            )
            if len(strings) >= 80:
                break

    return {
        "dump_path": str(path.resolve()),
        "window_start": start,
        "window_end": start + length,
        "length": len(chunk),
        "printable_ratio": printable_ratio,
        "top_bytes": top_bytes,
        "top_pairs": top_pairs,
        "top_eights": top_eights,
        "strings": strings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile a fixed byte window inside a dump file.")
    parser.add_argument("--dump", required=True, help="Dump path")
    parser.add_argument("--start", required=True, type=int, help="Window start offset")
    parser.add_argument("--length", type=int, default=4096, help="Window length")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_window_profile(args.dump, args.start, length=args.length)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump window profile saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
