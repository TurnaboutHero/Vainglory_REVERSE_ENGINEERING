"""Analyze fixed-stride repetition patterns inside a dump window."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List


def _stride_summary(chunk: bytes, stride: int) -> Dict[str, object]:
    if stride <= 0 or len(chunk) < stride:
        return {"stride": stride, "row_count": 0, "unique_rows": 0, "repeat_ratio": 0.0, "top_rows": []}
    rows = [chunk[i : i + stride] for i in range(0, len(chunk) - stride + 1, stride)]
    counts = Counter(rows)
    row_count = len(rows)
    unique_rows = len(counts)
    repeat_ratio = 1.0 - (unique_rows / row_count) if row_count else 0.0
    top_rows = [{"hex": row.hex(), "count": count} for row, count in counts.most_common(12)]
    return {
        "stride": stride,
        "row_count": row_count,
        "unique_rows": unique_rows,
        "repeat_ratio": repeat_ratio,
        "top_rows": top_rows,
    }


def build_dump_stride_report(dump_path: str, start: int, length: int = 4096, strides: List[int] | None = None) -> Dict[str, object]:
    if strides is None:
        strides = [4, 8, 16, 32]
    path = Path(dump_path)
    data = path.read_bytes()
    chunk = data[start : start + length]
    summaries = [_stride_summary(chunk, stride) for stride in strides]
    summaries.sort(key=lambda row: (float(row["repeat_ratio"]), int(row["row_count"])), reverse=True)
    return {
        "dump_path": str(path.resolve()),
        "window_start": start,
        "window_end": start + length,
        "length": len(chunk),
        "stride_summaries": summaries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze fixed-stride repetition inside a dump window.")
    parser.add_argument("--dump", required=True, help="Dump path")
    parser.add_argument("--start", required=True, type=int, help="Window start offset")
    parser.add_argument("--length", type=int, default=4096, help="Window length")
    parser.add_argument("--strides", nargs="*", type=int, default=[4, 8, 16, 32], help="Stride values to inspect")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_stride_report(args.dump, args.start, length=args.length, strides=list(args.strides))
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump stride report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
