"""Validate optional minion policies against truth-covered fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_policy import (
    MINION_POLICY_CHOICES,
    MINION_POLICY_NONE,
    evaluate_player_minion_policy,
)
from .minion_research import _load_truth_matches


def validate_minion_policy(truth_path: str, policy: str) -> Dict[str, object]:
    """Validate one optional minion policy against truth-covered complete fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    rows = []
    accepted_rows = 0
    accepted_exact = 0
    accepted_error = 0

    for match in complete_matches:
        decisions = evaluate_player_minion_policy(
            policy=policy,
            replay_file=match["replay_file"],
            completeness_status="complete_confirmed",
        )
        for player_name, truth_player in match["players"].items():
            truth_mk = truth_player.get("minion_kills")
            if truth_mk is None or player_name not in decisions:
                continue
            decision = decisions[player_name]
            row = {
                "replay_name": match["replay_name"],
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "player_name": player_name,
                "accepted": decision.accepted,
                "baseline_0e": decision.baseline_0e,
                "truth_minion_kills": truth_mk,
                "error": decision.baseline_0e - truth_mk,
                "mixed_total": decision.mixed_total,
                "mixed_ratio": decision.mixed_ratio,
                "reason": decision.reason,
            }
            rows.append(row)
            if decision.accepted:
                accepted_rows += 1
                if decision.baseline_0e == truth_mk:
                    accepted_exact += 1
                else:
                    accepted_error += 1

    precision = accepted_exact / accepted_rows if accepted_rows else 0.0
    coverage = accepted_rows / len(rows) if rows else 0.0

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "policy": policy,
        "player_rows": len(rows),
        "accepted_rows": accepted_rows,
        "accepted_exact": accepted_exact,
        "accepted_error": accepted_error,
        "precision": precision,
        "coverage": coverage,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate optional minion policies against truth-covered fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument(
        "--policy",
        choices=MINION_POLICY_CHOICES,
        default=MINION_POLICY_NONE,
        help="Minion policy to validate",
    )
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = validate_minion_policy(args.truth, args.policy)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion policy validation saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
