"""Profile same-frame context for action 0x02 value buckets across complete fixtures."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minion_research import _load_truth_matches


def _pattern_key(action: int, value: Optional[float]) -> str:
    return f"0x{action:02X}@{'nan' if value is None else round(value, 2)}"


def _player_entities(replay_file: str) -> set[int]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        _le_to_be(player["entity_id"])
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }


def build_action02_value_context_profile(truth_path: str) -> Dict[str, object]:
    """Profile same-frame context for action 0x02 values across complete fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    by_value = defaultdict(lambda: {"event_count": 0, "same_frame_patterns": Counter(), "match_count": 0})
    for match in complete_matches:
        valid_players = _player_entities(match["replay_file"])
        by_frame = defaultdict(list)
        seen_values_in_match = set()
        for event in iter_credit_events(match["replay_file"]):
            if event.entity_id_be not in valid_players:
                continue
            by_frame[event.frame_idx].append(event)

        for events in by_frame.values():
            target_events = [event for event in events if event.action == 0x02 and event.value is not None]
            if not target_events:
                continue
            frame_patterns = [_pattern_key(event.action, event.value) for event in events]
            for target in target_events:
                value = round(target.value, 2)
                seen_values_in_match.add(value)
                by_value[value]["event_count"] += 1
                by_value[value]["same_frame_patterns"].update(frame_patterns)

        for value in seen_values_in_match:
            by_value[value]["match_count"] += 1

    rows = []
    for value, stats in by_value.items():
        event_count = stats["event_count"]
        rows.append(
            {
                "value": value,
                "match_count": stats["match_count"],
                "event_count": event_count,
                "top_same_frame_patterns": [
                    {
                        "pattern": pattern,
                        "count": count,
                        "per_event": (count / event_count) if event_count else 0.0,
                    }
                    for pattern, count in stats["same_frame_patterns"].most_common(20)
                ],
            }
        )
    rows.sort(key=lambda item: (item["match_count"], item["event_count"]), reverse=True)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile same-frame context for action 0x02 value buckets.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_action02_value_context_profile(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action02 value context profile saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
