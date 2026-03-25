"""Trace same-frame provenance for selected credit action patterns."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minion_outlier_compare import build_minion_outlier_compare


def _pattern_key(action: int, value: Optional[float]) -> str:
    return f"0x{action:02X}@{'nan' if value is None else round(value, 2)}"


def build_minion_action_provenance(
    truth_path: str,
    target_replay_name: str,
    action_hex: str = "0x02",
    top_pattern_limit: int = 12,
) -> Dict[str, object]:
    """Build a provenance report for selected target replay action patterns."""
    outlier = build_minion_outlier_compare(truth_path, target_replay_name)
    target_replay_file = outlier["target_fixture_directory"]

    matches = json.loads(Path(truth_path).read_text(encoding="utf-8")).get("matches", [])
    target_match = next(match for match in matches if match["replay_name"] == target_replay_name)
    replay_file = target_match["replay_file"]
    selected_patterns = [
        row["pattern"]
        for row in outlier["credit_pattern_rate_deltas"][: top_pattern_limit * 2]
        if row["pattern"].startswith(action_hex.lower()) or row["pattern"].startswith(action_hex.upper())
    ][:top_pattern_limit]

    parsed = VGRParser(replay_file, auto_truth=False).parse()
    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }

    by_frame: Dict[int, List[object]] = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.entity_id_be not in player_map:
            continue
        by_frame[event.frame_idx].append(event)

    rows = []
    for pattern in selected_patterns:
        target_action = int(pattern[2:4], 16)
        raw_value = pattern.split("@", 1)[1]
        target_value = None if raw_value == "nan" else float(raw_value)
        matched_events = []
        same_frame_patterns = Counter()
        same_frame_player_counts = []
        same_frame_same_action_other_player = 0
        same_frame_0e = 0
        same_frame_0f = 0
        same_frame_06 = 0
        same_frame_08 = 0

        for frame_idx, events in by_frame.items():
            frame_target_events = [
                event
                for event in events
                if event.action == target_action and (
                    (target_value is None and event.value is None)
                    or (target_value is not None and event.value is not None and round(event.value, 2) == target_value)
                )
            ]
            if not frame_target_events:
                continue

            matched_events.extend(frame_target_events)
            frame_players = {event.entity_id_be for event in frame_target_events}
            same_frame_player_counts.append(len(frame_players))

            for event in events:
                key = _pattern_key(event.action, event.value)
                same_frame_patterns[key] += 1
                if event.action == target_action and key == pattern and event.entity_id_be not in frame_players:
                    same_frame_same_action_other_player += 1
                if event.action == 0x0E and event.value == 1.0:
                    same_frame_0e += 1
                if event.action == 0x0F and event.value == 1.0:
                    same_frame_0f += 1
                if event.action == 0x06:
                    same_frame_06 += 1
                if event.action == 0x08:
                    same_frame_08 += 1

        rows.append(
            {
                "pattern": pattern,
                "event_count": len(matched_events),
                "unique_players": len({event.entity_id_be for event in matched_events}),
                "mean_same_frame_target_player_count": (
                    sum(same_frame_player_counts) / len(same_frame_player_counts)
                    if same_frame_player_counts
                    else 0.0
                ),
                "max_same_frame_target_player_count": max(same_frame_player_counts) if same_frame_player_counts else 0,
                "same_frame_same_action_other_player": same_frame_same_action_other_player,
                "same_frame_0e_count": same_frame_0e,
                "same_frame_0f_count": same_frame_0f,
                "same_frame_06_count": same_frame_06,
                "same_frame_08_count": same_frame_08,
                "top_same_frame_patterns": [
                    {"pattern": key, "count": count}
                    for key, count in same_frame_patterns.most_common(20)
                ],
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "replay_file": replay_file,
        "selected_patterns": selected_patterns,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Trace same-frame provenance for selected credit action patterns.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--action", default="0x02", help="Credit action family to inspect")
    parser.add_argument("--top-pattern-limit", type=int, default=12, help="How many patterns to inspect")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_action_provenance(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        action_hex=args.action,
        top_pattern_limit=args.top_pattern_limit,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion action provenance saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
