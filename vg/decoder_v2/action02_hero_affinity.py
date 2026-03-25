"""Summarize hero affinity for action 0x02 value buckets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .minion_research import _load_player_credit_counters, _load_truth_matches


def build_action02_hero_affinity(truth_path: str) -> Dict[str, object]:
    """Build a hero-affinity summary for action 0x02 value buckets."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    hero_counts: Dict[float, Counter] = {}
    value_examples: Dict[float, List[Dict[str, object]]] = {}
    for match in complete_matches:
        parsed = VGRParser(match["replay_file"], auto_truth=False).parse()
        hero_map = {
            player["name"]: player.get("hero_name", "Unknown")
            for team in ("left", "right")
            for player in parsed["teams"][team]
        }
        counters = _load_player_credit_counters(match["replay_file"])
        for player_name, counter in counters.items():
            hero_name = hero_map.get(player_name, "Unknown")
            for (action, value), count in counter.items():
                if action != 0x02 or value == "nan" or count <= 0:
                    continue
                hero_counts.setdefault(value, Counter())
                hero_counts[value][hero_name] += count
                value_examples.setdefault(value, [])
                if len(value_examples[value]) < 20:
                    value_examples[value].append(
                        {
                            "hero_name": hero_name,
                            "player_name": player_name,
                            "fixture_directory": Path(match["replay_file"]).parent.name,
                            "count": count,
                        }
                    )

    rows = []
    for value, counter in hero_counts.items():
        total = sum(counter.values())
        top_hero, top_count = counter.most_common(1)[0]
        rows.append(
            {
                "value": value,
                "total_count": total,
                "unique_heroes": len(counter),
                "top_heroes": [
                    {"hero_name": hero_name, "count": count, "share": (count / total) if total else 0.0}
                    for hero_name, count in counter.most_common(10)
                ],
                "top_hero_name": top_hero,
                "top_hero_share": (top_count / total) if total else 0.0,
                "examples": value_examples[value],
            }
        )
    rows.sort(key=lambda item: (item["top_hero_share"], item["total_count"]), reverse=True)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize hero affinity for action 0x02 value buckets.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_action02_hero_affinity(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action02 hero affinity saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
