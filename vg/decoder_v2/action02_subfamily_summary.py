"""Classify action 0x02 value buckets into tentative subfamilies."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .action02_sharing_profile import build_action02_sharing_profile
from .action02_value_context_profile import build_action02_value_context_profile


def _label_subfamily(shared_cluster_rate: float, top_patterns: List[Dict[str, object]]) -> str:
    pattern_names = {item["pattern"] for item in top_patterns}
    has_reward_triplet = {"0x06@3.0", "0x08@0.6", "0x03@1.0"}.issubset(pattern_names)
    if shared_cluster_rate >= 0.02 and has_reward_triplet:
        return "shared_reward_candidate"
    if shared_cluster_rate <= 0.005 and has_reward_triplet:
        return "solo_reward_candidate"
    if has_reward_triplet:
        return "mixed_reward_candidate"
    return "unclassified"


def build_action02_subfamily_summary(truth_path: str) -> Dict[str, object]:
    """Join sharing and context profiles into tentative 0x02 subfamily labels."""
    sharing = build_action02_sharing_profile(truth_path)
    context = build_action02_value_context_profile(truth_path)
    context_map = {row["value"]: row for row in context["rows"]}

    rows = []
    for share_row in sharing["rows"]:
        value = share_row["value"]
        context_row = context_map.get(value, {"top_same_frame_patterns": []})
        top_patterns = context_row.get("top_same_frame_patterns", [])
        rows.append(
            {
                "value": value,
                "match_count": share_row["match_count"],
                "event_count": share_row["event_count"],
                "shared_cluster_rate": share_row["shared_cluster_rate"],
                "subfamily_label": _label_subfamily(share_row["shared_cluster_rate"], top_patterns),
                "top_same_frame_patterns": top_patterns[:10],
            }
        )

    rows.sort(key=lambda item: (item["match_count"], item["event_count"]), reverse=True)
    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify action 0x02 value buckets into tentative subfamilies.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_action02_subfamily_summary(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action02 subfamily summary saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
