"""Group dump strings into offset windows and summarize cluster types."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

from .dump_player_handle_candidates import is_probable_handle


ASCII_RE = re.compile(rb"[\x20-\x7E]{4,}")
UTF16_RE = re.compile(rb"(?:[\x20-\x7E]\x00){4,}")
GLYPH_RE = re.compile(r"(?:cid\d{4,}|uni[0-9A-Fa-f]{3,})")
LOCALE_RE = re.compile(
    r"(?:koreana|schinese|english|german|spanish|french|japanese|russian|vietnamese|south[- ]korea|united-states|zh-hans|zh-hant)",
    re.IGNORECASE,
)
RUNTIME_RE = re.compile(
    r'(?:temporary|gamemode_|"handle"|entitlement_|practice|ranked)',
    re.IGNORECASE,
)
CONFIG_RE = re.compile(r'(?:\\"|imagename|skinkey|experiment|limitededition|seasonchest|availability|proto)', re.IGNORECASE)


def extract_strings_with_offsets(data: bytes) -> List[Dict[str, object]]:
    values: List[Dict[str, object]] = []
    for match in ASCII_RE.finditer(data):
        values.append(
            {
                "offset": match.start(),
                "encoding": "ascii",
                "value": match.group().decode("ascii", errors="ignore"),
            }
        )
    for match in UTF16_RE.finditer(data):
        values.append(
            {
                "offset": match.start(),
                "encoding": "utf16le",
                "value": match.group().decode("utf-16-le", errors="ignore"),
            }
        )
    values.sort(key=lambda row: int(row["offset"]))
    return values


def classify_string_value(value: str) -> str:
    lower = value.lower()
    if GLYPH_RE.search(value):
        return "glyph"
    if LOCALE_RE.search(value):
        return "locale"
    if RUNTIME_RE.search(value):
        return "runtime"
    if CONFIG_RE.search(value):
        return "config"
    if is_probable_handle(value):
        return "handle"
    return "other"


def build_dump_string_cluster_report(
    dump_path: str,
    *,
    window_size: int = 4096,
    min_strings: int = 8,
    top_n: int = 50,
) -> Dict[str, object]:
    dump = Path(dump_path)
    strings = extract_strings_with_offsets(dump.read_bytes())

    windows: Dict[int, List[Dict[str, object]]] = defaultdict(list)
    for row in strings:
        windows[int(row["offset"]) // window_size].append(row)

    clusters = []
    for window_index, rows in windows.items():
        if len(rows) < min_strings:
            continue
        class_counts = Counter(classify_string_value(str(row["value"])) for row in rows)
        sample_strings = []
        seen = set()
        for row in rows:
            value = str(row["value"])
            if value in seen:
                continue
            seen.add(value)
            sample_strings.append(value[:120])
            if len(sample_strings) >= 20:
                break
        score = (
            class_counts["runtime"] * 6
            + class_counts["handle"] * 5
            + class_counts["locale"] * 2
            - class_counts["glyph"] * 2
            - class_counts["config"]
        )
        clusters.append(
            {
                "window_index": window_index,
                "window_start": window_index * window_size,
                "window_end": (window_index + 1) * window_size,
                "string_count": len(rows),
                "class_counts": dict(class_counts),
                "score": score,
                "sample_strings": sample_strings,
            }
        )

    clusters.sort(key=lambda row: (int(row["score"]), int(row["class_counts"].get("runtime", 0)), int(row["class_counts"].get("handle", 0)), int(row["string_count"])), reverse=True)
    top_clusters = clusters[:top_n]
    summary = Counter()
    for cluster in clusters:
        for key, value in cluster["class_counts"].items():
            summary[key] += value

    return {
        "dump_path": str(dump.resolve()),
        "window_size": window_size,
        "cluster_count": len(clusters),
        "string_count": len(strings),
        "summary_class_counts": dict(summary),
        "top_clusters": top_clusters,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cluster dump strings by offset window and summarize the most interesting regions.")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--window-size", type=int, default=4096, help="Cluster window size in bytes")
    parser.add_argument("--min-strings", type=int, default=8, help="Minimum strings required per window")
    parser.add_argument("--top-n", type=int, default=50, help="Number of top clusters to emit")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_string_cluster_report(
        args.dump,
        window_size=args.window_size,
        min_strings=args.min_strings,
        top_n=args.top_n,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump cluster report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
