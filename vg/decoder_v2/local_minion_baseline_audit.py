"""Audit target replay minion baselines against the local replay pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .batch_decode import decode_replay_batch
from .minion_policy import collect_player_minion_policy_context


def _percentile_rank(values: List[int], target: int) -> Optional[float]:
    if not values:
        return None
    less_or_equal = sum(1 for value in values if value <= target)
    return less_or_equal / len(values)


def build_local_minion_baseline_audit(base_path: str, target_replay_name: str) -> Dict[str, object]:
    batch = decode_replay_batch(base_path)
    replay_rows = []
    hero_pool: Dict[str, List[int]] = {}
    target_rows: List[Dict[str, object]] = []

    for match in batch["matches"]:
        if match["completeness_status"] != "complete_confirmed":
            continue
        replay_file = str(match["replay_file"])
        is_finals = "Law Enforcers (Finals)" in replay_file
        context = collect_player_minion_policy_context(replay_file)
        for player in match["players"]:
            row = {
                "replay_name": match["replay_name"],
                "replay_file": replay_file,
                "is_finals": is_finals,
                "player_name": player["name"],
                "hero_name": player["hero_name"],
                "team": player["team"],
                "baseline_0e": int(context.get(player["name"], {}).get("baseline_0e", 0)),
                "mixed_total": int(context.get(player["name"], {}).get("mixed_total", 0)),
                "mixed_ratio": float(context.get(player["name"], {}).get("mixed_ratio", 0.0)),
            }
            replay_rows.append(row)
            if not is_finals:
                hero_pool.setdefault(player["hero_name"], []).append(row["baseline_0e"])
            if match["replay_name"] == target_replay_name:
                target_rows.append(row)

    hero_summary = {}
    for hero_name, values in sorted(hero_pool.items()):
        ordered = sorted(values)
        hero_summary[hero_name] = {
            "count": len(ordered),
            "min": ordered[0],
            "max": ordered[-1],
            "median": ordered[len(ordered) // 2],
        }

    target_analysis = []
    for row in target_rows:
        pool_values = hero_pool.get(row["hero_name"], [])
        target_analysis.append(
            {
                **row,
                "hero_pool_count": len(pool_values),
                "hero_pool_percentile": _percentile_rank(pool_values, row["baseline_0e"]),
            }
        )

    return {
        "base_path": str(Path(base_path).resolve()),
        "target_replay_name": target_replay_name,
        "complete_replays": len({row["replay_name"] for row in replay_rows}),
        "nonfinals_complete_replays": len({row["replay_name"] for row in replay_rows if not row["is_finals"]}),
        "hero_summary": hero_summary,
        "target_rows": target_analysis,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit target replay minion baselines against local replay pool.")
    parser.add_argument("base_path", help="Replay root directory")
    parser.add_argument("--target-replay-name", required=True, help="Replay name to analyze")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_local_minion_baseline_audit(args.base_path, args.target_replay_name)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Local minion baseline audit saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
