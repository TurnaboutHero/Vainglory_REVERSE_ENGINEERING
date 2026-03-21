"""Cross-fixture research for credit action 0x04 values."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .credit_events import iter_credit_events


def _load_truth_matches(truth_path: str) -> List[Dict]:
    return json.loads(Path(truth_path).read_text(encoding="utf-8")).get("matches", [])


def _load_action4_value_counters(replay_file: str) -> Dict[int, Dict[float, int]]:
    counters: Dict[int, Dict[float, int]] = defaultdict(dict)
    for event in iter_credit_events(replay_file):
        if event.action != 0x04 or event.value is None:
            continue
        rounded = round(event.value, 2)
        counters.setdefault(event.entity_id_be, {})
        counters[event.entity_id_be][rounded] = counters[event.entity_id_be].get(rounded, 0) + 1
    return counters


def build_action4_feature_report(truth_path: str) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    complete_matches = [m for m in matches if "Incomplete" not in Path(m["replay_file"]).parent.name]
    truth_errors: Dict[float, List[int]] = defaultdict(list)
    residual_errors: Dict[float, List[int]] = defaultdict(list)

    from vg.core.vgr_parser import VGRParser
    from vg.core.unified_decoder import _le_to_be

    for match in complete_matches:
        parsed = VGRParser(match["replay_file"], auto_truth=False).parse()
        player_map = {
            _le_to_be(player["entity_id"]): player["name"]
            for team in ("left", "right")
            for player in parsed["teams"][team]
            if player.get("entity_id")
        }
        action4 = _load_action4_value_counters(match["replay_file"])
        # baseline 0x0E counts from current minion research assumptions
        from .minions import collect_minion_candidates

        baseline = {item.player_name: item.action_0e_value_1 for item in collect_minion_candidates(match["replay_file"])}
        for entity_be, value_counts in action4.items():
            name = player_map.get(entity_be)
            if not name or name not in match["players"]:
                continue
            truth_mk = match["players"][name].get("minion_kills")
            if truth_mk is None:
                continue
            residual = truth_mk - baseline.get(name, 0)
            for value, count in value_counts.items():
                truth_errors[value].append(abs(count - truth_mk))
                residual_errors[value].append(abs(count - residual))

    by_truth = [
        {
            "value": value,
            "mae_to_truth": sum(errors) / len(errors),
            "max_abs_error_to_truth": max(errors),
            "count": len(errors),
        }
        for value, errors in truth_errors.items()
        if len(errors) >= 5
    ]
    by_truth.sort(key=lambda item: (item["mae_to_truth"], item["max_abs_error_to_truth"], -item["count"]))

    by_residual = [
        {
            "value": value,
            "mae_to_residual": sum(errors) / len(errors),
            "max_abs_error_to_residual": max(errors),
            "count": len(errors),
        }
        for value, errors in residual_errors.items()
        if len(errors) >= 5
    ]
    by_residual.sort(key=lambda item: (item["mae_to_residual"], item["max_abs_error_to_residual"], -item["count"]))

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "top_action4_values_vs_truth": by_truth[:50],
        "top_action4_values_vs_residual": by_residual[:50],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research action 0x04 values across complete fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output path")
    args = parser.parse_args(argv)

    report = build_action4_feature_report(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action4 feature report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
