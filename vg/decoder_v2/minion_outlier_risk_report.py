"""Evaluate action 0x02 subfamily excess as a minion-outlier risk signal."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .minion_research import _load_player_credit_counters, _load_truth_matches


SOLO_SUBFAMILY_PATTERNS = ("0x02@17.4", "0x02@14.34", "0x02@9.54", "0x02@4.0")
MIXED_SUBFAMILY_PATTERNS = ("0x02@20.0", "0x02@-50.0")


def _load_player_heroes(replay_file: str) -> Dict[str, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        player["name"]: player.get("hero_name", "Unknown")
        for team in ("left", "right")
        for player in parsed["teams"][team]
    }


def _pattern_count(counter: Dict[tuple, int], pattern: str) -> int:
    action = int(pattern[2:4], 16)
    raw_value = pattern.split("@", 1)[1]
    key = (action, "nan") if raw_value == "nan" else (action, float(raw_value))
    return counter.get(key, 0)


def build_minion_outlier_risk_report(truth_path: str) -> Dict[str, object]:
    """Evaluate whether action 0x02 subfamily excess predicts positive residual rows."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    player_rows = []
    for match in complete_matches:
        counters = _load_player_credit_counters(match["replay_file"])
        heroes = _load_player_heroes(match["replay_file"])
        for player_name, player_truth in match["players"].items():
            if player_name not in counters or player_truth.get("minion_kills") is None:
                continue
            baseline_0e = counters[player_name][(0x0E, 1.0)]
            solo_total = sum(_pattern_count(counters[player_name], pattern) for pattern in SOLO_SUBFAMILY_PATTERNS)
            mixed_total = sum(_pattern_count(counters[player_name], pattern) for pattern in MIXED_SUBFAMILY_PATTERNS)
            player_rows.append(
                {
                    "replay_name": match["replay_name"],
                    "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                    "player_name": player_name,
                    "hero_name": heroes.get(player_name, "Unknown"),
                    "residual_vs_0e": player_truth["minion_kills"] - baseline_0e,
                    "solo_subfamily_total": solo_total,
                    "mixed_subfamily_total": mixed_total,
                }
            )

    rows_by_hero = defaultdict(list)
    for row in player_rows:
        rows_by_hero[row["hero_name"]].append(row)

    scored_rows = []
    for row in player_rows:
        peers = [
            peer
            for peer in rows_by_hero[row["hero_name"]]
            if not (peer["replay_name"] == row["replay_name"] and peer["player_name"] == row["player_name"])
        ]
        if peers:
            solo_peer_mean = sum(peer["solo_subfamily_total"] for peer in peers) / len(peers)
            mixed_peer_mean = sum(peer["mixed_subfamily_total"] for peer in peers) / len(peers)
        else:
            solo_peer_mean = None
            mixed_peer_mean = None

        scored_rows.append(
            {
                **row,
                "same_hero_peer_count": len(peers),
                "solo_peer_mean": solo_peer_mean,
                "mixed_peer_mean": mixed_peer_mean,
                "solo_excess_vs_peer_mean": (
                    row["solo_subfamily_total"] - solo_peer_mean if solo_peer_mean is not None else None
                ),
                "mixed_excess_vs_peer_mean": (
                    row["mixed_subfamily_total"] - mixed_peer_mean if mixed_peer_mean is not None else None
                ),
            }
        )

    positive_rows = [row for row in scored_rows if row["residual_vs_0e"] > 0]
    zero_rows = [row for row in scored_rows if row["residual_vs_0e"] == 0]

    def _count_over(rows: List[Dict[str, object]], key: str, threshold: float) -> int:
        return sum(1 for row in rows if row.get(key) is not None and row[key] > threshold)

    thresholds = [0, 10, 25, 50, 100, 200]
    threshold_rows = []
    for threshold in thresholds:
        threshold_rows.append(
            {
                "threshold": threshold,
                "positive_over_threshold": _count_over(positive_rows, "solo_excess_vs_peer_mean", threshold),
                "zero_over_threshold": _count_over(zero_rows, "solo_excess_vs_peer_mean", threshold),
                "positive_mixed_over_threshold": _count_over(positive_rows, "mixed_excess_vs_peer_mean", threshold),
                "zero_mixed_over_threshold": _count_over(zero_rows, "mixed_excess_vs_peer_mean", threshold),
            }
        )

    ranked = sorted(
        scored_rows,
        key=lambda row: (
            row["solo_excess_vs_peer_mean"] if row["solo_excess_vs_peer_mean"] is not None else float("-inf"),
            row["mixed_excess_vs_peer_mean"] if row["mixed_excess_vs_peer_mean"] is not None else float("-inf"),
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "threshold_summary": threshold_rows,
        "all_rows": scored_rows,
        "top_rows_by_solo_excess": ranked[:30],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate action 0x02 subfamily excess as a minion-outlier risk signal.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_outlier_risk_report(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion outlier risk report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
