"""Cluster exact result-screen strings by virtual-address proximity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .minidump_string_locator import locate_strings_in_minidump


def _cluster_hits(hits: List[Dict[str, object]], max_gap: int) -> List[List[Dict[str, object]]]:
    if not hits:
        return []
    hits = sorted(hits, key=lambda row: int(row["virtual_address"]))
    clusters = [[hits[0]]]
    for hit in hits[1:]:
        prev = clusters[-1][-1]
        if int(hit["virtual_address"]) - int(prev["virtual_address"]) <= max_gap:
            clusters[-1].append(hit)
        else:
            clusters.append([hit])
    return clusters


def build_result_screen_va_cluster_report(
    dump_path: str,
    values: List[str],
    *,
    max_gap: int = 0x800,
) -> Dict[str, object]:
    located = locate_strings_in_minidump(dump_path, values)
    flat_hits = []
    for row in located["strings"]:
        for hit in row["hits"]:
            if hit["virtual_address"] is None:
                continue
            flat_hits.append(
                {
                    "value": row["value"],
                    "virtual_address": int(hit["virtual_address"]),
                    "file_offset": int(hit["file_offset"]),
                }
            )
    clusters = []
    for cluster in _cluster_hits(flat_hits, max_gap):
        values = [item["value"] for item in cluster]
        clusters.append(
            {
                "start_va": cluster[0]["virtual_address"],
                "end_va": cluster[-1]["virtual_address"],
                "span": cluster[-1]["virtual_address"] - cluster[0]["virtual_address"],
                "item_count": len(cluster),
                "distinct_values": sorted(set(values)),
                "items": cluster,
            }
        )
    clusters.sort(key=lambda row: (len(row["distinct_values"]), row["item_count"], -row["span"]), reverse=True)
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "max_gap": max_gap,
        "cluster_count": len(clusters),
        "clusters": clusters,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cluster exact result-screen strings by virtual-address proximity.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--value", action="append", required=True, help="Exact string to include (repeatable)")
    parser.add_argument("--max-gap", type=int, default=0x800, help="Maximum VA gap for clustering")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_va_cluster_report(args.dump, list(args.value), max_gap=args.max_gap)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen VA cluster report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
