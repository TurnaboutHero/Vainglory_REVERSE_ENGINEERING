"""Batch-profile unknown windows from a numeric diff report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .dump_stride_report import build_dump_stride_report
from .dump_window_profile import build_dump_window_profile


def build_unknown_window_batch_report(
    numeric_diff_path: str,
    dump_path: str,
    *,
    max_windows: int = 10,
    window_length: int = 4096,
) -> Dict[str, object]:
    diff = json.loads(Path(numeric_diff_path).read_text(encoding="utf-8"))
    dump = Path(dump_path)
    selected = [row for row in diff["top_windows"] if row.get("classification") == "unknown"][:max_windows]
    windows = []
    for row in selected:
        start = int(row["window_start"])
        profile = build_dump_window_profile(str(dump), start, length=window_length)
        stride = build_dump_stride_report(str(dump), start, length=window_length, strides=[4, 8, 16, 32])
        windows.append(
            {
                "window_start": start,
                "delta_count": row["delta_count"],
                "after_samples": row.get("after_samples", [])[:12],
                "after_contexts": row.get("after_contexts", [])[:6],
                "printable_ratio": profile["printable_ratio"],
                "top_bytes": profile["top_bytes"][:8],
                "top_pairs": profile["top_pairs"][:8],
                "top_stride": stride["stride_summaries"][0],
                "sample_strings": profile["strings"][:16],
            }
        )
    return {
        "numeric_diff_path": str(Path(numeric_diff_path).resolve()),
        "dump_path": str(dump.resolve()),
        "window_count": len(windows),
        "windows": windows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-profile unknown windows from a numeric diff report.")
    parser.add_argument("--numeric-diff", required=True, help="Path to numeric diff JSON")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--max-windows", type=int, default=10, help="Maximum unknown windows to profile")
    parser.add_argument("--window-length", type=int, default=4096, help="Window length")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_unknown_window_batch_report(
        args.numeric_diff,
        args.dump,
        max_windows=args.max_windows,
        window_length=args.window_length,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Unknown window batch report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
