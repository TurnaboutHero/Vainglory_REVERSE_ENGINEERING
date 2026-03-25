"""Audit fixed minion policies by series and replay to show where they fail or abstain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .minion_policy import (
    MINION_POLICY_CHOICES,
    MINION_POLICY_NONE,
    evaluate_player_minion_policy,
)
from .minion_research import _load_truth_matches


def _score_rows(rows: List[Dict[str, object]]) -> Dict[str, object]:
    accepted_rows = [row for row in rows if row["accepted"]]
    accepted_exact = sum(int(row["error"] == 0) for row in accepted_rows)
    accepted_error = len(accepted_rows) - accepted_exact
    precision = accepted_exact / len(accepted_rows) if accepted_rows else 0.0
    coverage = len(accepted_rows) / len(rows) if rows else 0.0
    return {
        "player_rows": len(rows),
        "accepted_rows": len(accepted_rows),
        "accepted_exact": accepted_exact,
        "accepted_error": accepted_error,
        "precision": precision,
        "coverage": coverage,
    }


def _collect_policy_rows(matches: List[Dict[str, object]], policy: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for match in matches:
        replay_file = str(match["replay_file"])
        fixture_directory = str(Path(replay_file).parent.resolve())
        series_directory = str(Path(replay_file).parent.parent.resolve())
        completeness_status = (
            "incomplete_confirmed"
            if "Incomplete" in Path(replay_file).parent.name
            else "complete_confirmed"
        )
        decisions = evaluate_player_minion_policy(
            policy=policy,
            replay_file=replay_file,
            completeness_status=completeness_status,
        )
        for player_name, truth_player in match["players"].items():
            truth_mk = truth_player.get("minion_kills")
            if truth_mk is None:
                continue
            decision = decisions.get(player_name)
            if not decision:
                continue
            rows.append(
                {
                    "policy": policy,
                    "series": series_directory,
                    "replay_name": match["replay_name"],
                    "fixture_directory": fixture_directory,
                    "is_incomplete_fixture": completeness_status != "complete_confirmed",
                    "player_name": player_name,
                    "accepted": decision.accepted,
                    "baseline_0e": decision.baseline_0e,
                    "mixed_total": decision.mixed_total,
                    "mixed_ratio": decision.mixed_ratio,
                    "truth_minion_kills": truth_mk,
                    "error": decision.baseline_0e - truth_mk,
                    "reason": decision.reason,
                }
            )
    return rows


def _group_score(rows: List[Dict[str, object]], group_key: str) -> List[Dict[str, object]]:
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row[group_key]), []).append(row)
    results = []
    for group_name in sorted(grouped):
        summary = _score_rows(grouped[group_name])
        summary[group_key] = group_name
        results.append(summary)
    return results


def build_minion_policy_stability_audit(truth_path: str) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    policies = {}
    for policy in MINION_POLICY_CHOICES:
        rows = _collect_policy_rows(matches, policy)
        complete_rows = [row for row in rows if not row["is_incomplete_fixture"]]
        incomplete_rows = [row for row in rows if row["is_incomplete_fixture"]]
        policies[policy] = {
            "overall": _score_rows(rows),
            "complete_only": _score_rows(complete_rows),
            "incomplete_only": _score_rows(incomplete_rows),
            "by_series": _group_score(rows, "series"),
            "by_replay": _group_score(rows, "replay_name"),
            "rows": rows,
        }
    return {
        "truth_path": str(Path(truth_path).resolve()),
        "policies": policies,
        "recommended_default": MINION_POLICY_NONE,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit fixed minion policy stability by series and replay.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_minion_policy_stability_audit(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion policy stability audit saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
