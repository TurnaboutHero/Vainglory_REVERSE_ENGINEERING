"""Compare dump windows by changes in short numeric-like string tokens."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List

from .dump_string_cluster_report import extract_strings_with_offsets


NUMERIC_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])[0-9:/.-]{1,12}(?![A-Za-z0-9_])")
HTTP_MARKERS = ("http/1.1", "content-length", "x-cloud-trace-context", "sessiontoken", "alt-svc", "via: 1.1 google")
SHADER_MARKERS = ("subgroupballot", "spvinverse", "spvtranspose", "floatbitstouint", "uintbitstofloat", "return mat2(", "return mat3(", "return mat4(")
ISA_MARKERS = ("src0.", "src1.", "src2.", "grf<", "arf<", "r<0;1,0>", "ctrlix_", "imm32", "regfile")
CONFIG_MARKERS = ("skinkey", "imagename", "themekey", "heroKey".lower(), "obtainable", "availableonepoch")
IMPORT_MARKERS = ("api-ms-", ".dll", "kernelbase", "cryptbase", "systemfunction036")


def classify_numeric_window(contexts: List[str]) -> str:
    joined = " ".join(contexts).lower()
    if any(marker in joined for marker in HTTP_MARKERS):
        return "http_network"
    if any(marker in joined for marker in SHADER_MARKERS):
        return "shader_codegen"
    if any(marker in joined for marker in ISA_MARKERS):
        return "isa_table"
    if any(marker in joined for marker in CONFIG_MARKERS):
        return "config_blob"
    if any(marker in joined for marker in IMPORT_MARKERS):
        return "import_table"
    return "unknown"


def _numeric_windows(path: str, window_size: int) -> Dict[int, Dict[str, object]]:
    strings = extract_strings_with_offsets(Path(path).read_bytes())
    windows: Dict[int, Dict[str, object]] = defaultdict(lambda: {"count": 0, "samples": [], "contexts": []})
    for row in strings:
        value = str(row["value"])
        tokens = [token for token in NUMERIC_TOKEN_RE.findall(value) if any(ch.isdigit() for ch in token)]
        if not tokens:
            continue
        window_index = int(row["offset"]) // window_size
        windows[window_index]["count"] += len(tokens)
        if value not in windows[window_index]["contexts"] and len(windows[window_index]["contexts"]) < 20:
            windows[window_index]["contexts"].append(value[:160])
        for token in tokens:
            if token not in windows[window_index]["samples"]:
                windows[window_index]["samples"].append(token)
            if len(windows[window_index]["samples"]) >= 20:
                break
    return windows


def build_dump_numeric_token_diff(before_path: str, after_path: str, *, window_size: int = 4096, top_n: int = 50) -> Dict[str, object]:
    before = _numeric_windows(before_path, window_size)
    after = _numeric_windows(after_path, window_size)
    rows: List[Dict[str, object]] = []
    for window_index in sorted(set(before) | set(after)):
        before_count = int(before.get(window_index, {"count": 0})["count"])
        after_bucket = after.get(window_index, {"count": 0, "samples": []})
        after_count = int(after_bucket["count"])
        delta = after_count - before_count
        if delta <= 0:
            continue
        rows.append(
            {
                "window_index": window_index,
                "window_start": window_index * window_size,
                "window_end": (window_index + 1) * window_size,
                "before_count": before_count,
                "after_count": after_count,
                "delta_count": delta,
                "classification": classify_numeric_window(after_bucket["contexts"]),
                "after_samples": after_bucket["samples"][:20],
                "after_contexts": after_bucket["contexts"][:8],
            }
        )
    rows.sort(key=lambda row: (int(row["delta_count"]), int(row["after_count"])), reverse=True)
    return {
        "before_path": str(Path(before_path).resolve()),
        "after_path": str(Path(after_path).resolve()),
        "window_size": window_size,
        "window_count": len(rows),
        "top_windows": rows[:top_n],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare dump windows by numeric-like token growth.")
    parser.add_argument("--before", required=True, help="Before dump path")
    parser.add_argument("--after", required=True, help="After dump path")
    parser.add_argument("--window-size", type=int, default=4096, help="Window size in bytes")
    parser.add_argument("--top-n", type=int, default=50, help="Top changed windows to emit")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_numeric_token_diff(
        args.before,
        args.after,
        window_size=args.window_size,
        top_n=args.top_n,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump numeric token diff saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
