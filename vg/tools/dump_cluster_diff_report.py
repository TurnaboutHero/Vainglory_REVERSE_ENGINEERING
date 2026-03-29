"""Compare two dump files by offset-window string class composition."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

from .dump_string_cluster_report import classify_string_value, extract_strings_with_offsets


def _summarize_windows(path: str, window_size: int) -> Dict[int, Dict[str, object]]:
    strings = extract_strings_with_offsets(Path(path).read_bytes())
    windows: Dict[int, Dict[str, object]] = defaultdict(lambda: {"class_counts": Counter(), "sample_strings": []})
    for row in strings:
        window_index = int(row["offset"]) // window_size
        value = str(row["value"])
        window = windows[window_index]
        window["class_counts"][classify_string_value(value)] += 1
        if any(ch.isdigit() for ch in value) and len(window["sample_strings"]) < 20:
            window["sample_strings"].append(value[:120])
    return windows


def build_dump_cluster_diff_report(before_path: str, after_path: str, *, window_size: int = 4096, top_n: int = 50) -> Dict[str, object]:
    before = _summarize_windows(before_path, window_size)
    after = _summarize_windows(after_path, window_size)
    rows: List[Dict[str, object]] = []
    for window_index in sorted(set(before) | set(after)):
        before_counts = before.get(window_index, {"class_counts": Counter(), "sample_strings": []})["class_counts"]
        after_bucket = after.get(window_index, {"class_counts": Counter(), "sample_strings": []})
        after_counts = after_bucket["class_counts"]
        deltas = {
            "runtime": after_counts["runtime"] - before_counts["runtime"],
            "handle": after_counts["handle"] - before_counts["handle"],
            "config": after_counts["config"] - before_counts["config"],
            "locale": after_counts["locale"] - before_counts["locale"],
            "glyph": after_counts["glyph"] - before_counts["glyph"],
            "other": after_counts["other"] - before_counts["other"],
        }
        score = (
            deltas["runtime"] * 8
            + deltas["handle"] * 8
            + deltas["config"] * 2
            + deltas["locale"]
            + deltas["other"] * 0.2
            - deltas["glyph"] * 0.5
        )
        if score <= 0:
            continue
        rows.append(
            {
                "window_index": window_index,
                "window_start": window_index * window_size,
                "window_end": (window_index + 1) * window_size,
                "score": score,
                "before_class_counts": dict(before_counts),
                "after_class_counts": dict(after_counts),
                "delta_class_counts": deltas,
                "after_sample_strings": after_bucket["sample_strings"][:12],
            }
        )

    rows.sort(key=lambda row: (float(row["score"]), int(row["delta_class_counts"]["runtime"]), int(row["delta_class_counts"]["handle"]), int(row["delta_class_counts"]["other"])), reverse=True)
    return {
        "before_path": str(Path(before_path).resolve()),
        "after_path": str(Path(after_path).resolve()),
        "window_size": window_size,
        "window_count": len(rows),
        "top_windows": rows[:top_n],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two dump files by string-cluster windows.")
    parser.add_argument("--before", required=True, help="Before dump path")
    parser.add_argument("--after", required=True, help="After dump path")
    parser.add_argument("--window-size", type=int, default=4096, help="Window size in bytes")
    parser.add_argument("--top-n", type=int, default=50, help="Top changed windows to emit")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_cluster_diff_report(
        args.before,
        args.after,
        window_size=args.window_size,
        top_n=args.top_n,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump cluster diff saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
