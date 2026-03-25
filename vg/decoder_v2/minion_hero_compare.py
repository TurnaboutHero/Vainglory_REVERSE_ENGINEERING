"""Compare outlier minion patterns against the same heroes in other complete fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .minion_outlier_compare import build_minion_outlier_compare
from .minion_research import _load_player_credit_counters, _load_truth_matches


def _load_player_heroes(replay_file: str) -> Dict[str, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        player["name"]: player.get("hero_name", "Unknown")
        for team in ("left", "right")
        for player in parsed["teams"][team]
    }


def build_minion_hero_compare(
    truth_path: str,
    target_replay_name: str,
    top_pattern_limit: int = 8,
) -> Dict[str, object]:
    """Compare positive-residual target players against same-hero peers in other fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]
    target_match = next(match for match in complete_matches if match["replay_name"] == target_replay_name)
    outlier_compare = build_minion_outlier_compare(truth_path, target_replay_name)
    selected_patterns = [row["pattern"] for row in outlier_compare["credit_pattern_rate_deltas"][:top_pattern_limit]]

    target_counters = _load_player_credit_counters(target_match["replay_file"])
    target_heroes = _load_player_heroes(target_match["replay_file"])

    target_rows = []
    for player_name, player_truth in target_match["players"].items():
        if player_name not in target_counters:
            continue
        baseline_0e = target_counters[player_name][(0x0E, 1.0)]
        residual = player_truth["minion_kills"] - baseline_0e
        if residual <= 0:
            continue

        hero_name = target_heroes.get(player_name, "Unknown")
        peer_rows = []
        for match in complete_matches:
            if match["replay_name"] == target_replay_name:
                continue
            heroes = _load_player_heroes(match["replay_file"])
            counters = _load_player_credit_counters(match["replay_file"])
            for peer_name, peer_truth in match["players"].items():
                peer_mk = peer_truth.get("minion_kills")
                if heroes.get(peer_name) != hero_name or peer_name not in counters or peer_mk is None:
                    continue
                peer_baseline_0e = counters[peer_name][(0x0E, 1.0)]
                peer_rows.append(
                    {
                        "replay_name": match["replay_name"],
                        "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                        "player_name": peer_name,
                        "hero_name": hero_name,
                        "residual_vs_0e": peer_mk - peer_baseline_0e,
                        "pattern_counts": {
                            pattern: counters[peer_name].get(
                                (int(pattern[2:4], 16), float(pattern.split("@", 1)[1])) if pattern.split("@", 1)[1] != "nan" else (int(pattern[2:4], 16), "nan"),
                                0,
                            )
                            for pattern in selected_patterns
                        },
                    }
                )

        target_rows.append(
            {
                "player_name": player_name,
                "hero_name": hero_name,
                "truth_minion_kills": player_truth["minion_kills"],
                "baseline_0e": baseline_0e,
                "residual_vs_0e": residual,
                "target_pattern_counts": {
                    pattern: target_counters[player_name].get(
                        (int(pattern[2:4], 16), float(pattern.split("@", 1)[1])) if pattern.split("@", 1)[1] != "nan" else (int(pattern[2:4], 16), "nan"),
                        0,
                    )
                    for pattern in selected_patterns
                },
                "same_hero_peer_count": len(peer_rows),
                "same_hero_peers": peer_rows,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "selected_patterns": selected_patterns,
        "rows": target_rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare outlier minion patterns against the same heroes in other complete fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--top-pattern-limit", type=int, default=8, help="How many outlier patterns to compare")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_hero_compare(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        top_pattern_limit=args.top_pattern_limit,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion hero compare saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
