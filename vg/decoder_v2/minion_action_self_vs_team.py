"""Compare whether selected action patterns align with self vs teammate minion credits."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minion_outlier_compare import build_minion_outlier_compare


def _pattern_key(action: int, value: Optional[float]) -> str:
    return f"0x{action:02X}@{'nan' if value is None else round(value, 2)}"


def _player_teams(replay_file: str) -> Dict[int, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    rows = {}
    for team in ("left", "right"):
        for player in parsed["teams"][team]:
            if player.get("entity_id"):
                rows[_le_to_be(player["entity_id"])] = team
    return rows


def build_minion_action_self_vs_team_per_player(
    replay_file: str,
    selected_patterns: List[str],
) -> Dict[str, List[Dict[str, object]]]:
    """Measure self/teammate/opponent linkage per player for selected patterns."""
    team_map = _player_teams(replay_file)
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    name_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    by_frame = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.entity_id_be in team_map:
            by_frame[event.frame_idx].append(event)

    player_rows: Dict[str, List[Dict[str, object]]] = {name: [] for name in name_map.values()}
    for pattern in selected_patterns:
        target_action = int(pattern[2:4], 16)
        raw_value = pattern.split("@", 1)[1]
        target_value = None if raw_value == "nan" else float(raw_value)

        per_player_counts = defaultdict(lambda: {
            "target_event_count": 0,
            "self_0e_count": 0,
            "self_0f_count": 0,
            "teammate_0e_count": 0,
            "teammate_0f_count": 0,
            "opponent_0e_count": 0,
            "opponent_0f_count": 0,
            "self_presence_count": 0,
            "teammate_presence_count": 0,
            "opponent_presence_count": 0,
        })

        for frame_events in by_frame.values():
            matched = [
                event
                for event in frame_events
                if event.action == target_action and (
                    (target_value is None and event.value is None)
                    or (target_value is not None and event.value is not None and round(event.value, 2) == target_value)
                )
            ]
            if not matched:
                continue
            for event in matched:
                player_name = name_map[event.entity_id_be]
                counts = per_player_counts[player_name]
                counts["target_event_count"] += 1
                event_team = team_map[event.entity_id_be]
                saw_self = False
                saw_teammate = False
                saw_opponent = False
                for sibling in frame_events:
                    if sibling.action not in (0x0E, 0x0F) or sibling.value != 1.0:
                        continue
                    if sibling.entity_id_be == event.entity_id_be:
                        saw_self = True
                        if sibling.action == 0x0E:
                            counts["self_0e_count"] += 1
                        else:
                            counts["self_0f_count"] += 1
                    elif team_map.get(sibling.entity_id_be) == event_team:
                        saw_teammate = True
                        if sibling.action == 0x0E:
                            counts["teammate_0e_count"] += 1
                        else:
                            counts["teammate_0f_count"] += 1
                    else:
                        saw_opponent = True
                        if sibling.action == 0x0E:
                            counts["opponent_0e_count"] += 1
                        else:
                            counts["opponent_0f_count"] += 1
                if saw_self:
                    counts["self_presence_count"] += 1
                if saw_teammate:
                    counts["teammate_presence_count"] += 1
                if saw_opponent:
                    counts["opponent_presence_count"] += 1

        for player_name in player_rows:
            counts = per_player_counts[player_name]
            target_events = counts["target_event_count"]
            player_rows[player_name].append(
                {
                    "pattern": pattern,
                    **counts,
                    "self_link_rate": ((counts["self_0e_count"] + counts["self_0f_count"]) / target_events) if target_events else 0.0,
                    "teammate_link_rate": ((counts["teammate_0e_count"] + counts["teammate_0f_count"]) / target_events) if target_events else 0.0,
                    "opponent_link_rate": ((counts["opponent_0e_count"] + counts["opponent_0f_count"]) / target_events) if target_events else 0.0,
                    "self_presence_rate": (counts["self_presence_count"] / target_events) if target_events else 0.0,
                    "teammate_presence_rate": (counts["teammate_presence_count"] / target_events) if target_events else 0.0,
                    "opponent_presence_rate": (counts["opponent_presence_count"] / target_events) if target_events else 0.0,
                }
            )

    return player_rows


def build_minion_action_self_vs_team(
    truth_path: str,
    target_replay_name: str,
    action_hex: str = "0x02",
    top_pattern_limit: int = 12,
) -> Dict[str, object]:
    """Measure whether action patterns align with self or teammate 0x0E/0x0F events."""
    outlier = build_minion_outlier_compare(truth_path, target_replay_name)
    matches = json.loads(Path(truth_path).read_text(encoding="utf-8")).get("matches", [])
    target_match = next(match for match in matches if match["replay_name"] == target_replay_name)
    replay_file = target_match["replay_file"]

    selected_patterns = [
        row["pattern"]
        for row in outlier["credit_pattern_rate_deltas"][: top_pattern_limit * 2]
        if row["pattern"].startswith(action_hex.lower()) or row["pattern"].startswith(action_hex.upper())
    ][:top_pattern_limit]

    team_map = _player_teams(replay_file)
    by_frame = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.entity_id_be in team_map:
            by_frame[event.frame_idx].append(event)

    rows = []
    for pattern in selected_patterns:
        target_action = int(pattern[2:4], 16)
        raw_value = pattern.split("@", 1)[1]
        target_value = None if raw_value == "nan" else float(raw_value)

        self_0e = self_0f = teammate_0e = teammate_0f = opponent_0e = opponent_0f = 0
        self_presence = teammate_presence = opponent_presence = 0
        target_events = 0

        for frame_events in by_frame.values():
            matched = [
                event
                for event in frame_events
                if event.action == target_action and (
                    (target_value is None and event.value is None)
                    or (target_value is not None and event.value is not None and round(event.value, 2) == target_value)
                )
            ]
            if not matched:
                continue
            for event in matched:
                target_events += 1
                event_team = team_map[event.entity_id_be]
                saw_self = False
                saw_teammate = False
                saw_opponent = False
                for sibling in frame_events:
                    if sibling.action not in (0x0E, 0x0F) or sibling.value != 1.0:
                        continue
                    if sibling.entity_id_be == event.entity_id_be:
                        saw_self = True
                        if sibling.action == 0x0E:
                            self_0e += 1
                        else:
                            self_0f += 1
                    elif team_map.get(sibling.entity_id_be) == event_team:
                        saw_teammate = True
                        if sibling.action == 0x0E:
                            teammate_0e += 1
                        else:
                            teammate_0f += 1
                    else:
                        saw_opponent = True
                        if sibling.action == 0x0E:
                            opponent_0e += 1
                        else:
                            opponent_0f += 1
                if saw_self:
                    self_presence += 1
                if saw_teammate:
                    teammate_presence += 1
                if saw_opponent:
                    opponent_presence += 1

        rows.append(
            {
                "pattern": pattern,
                "target_event_count": target_events,
                "self_0e_count": self_0e,
                "self_0f_count": self_0f,
                "teammate_0e_count": teammate_0e,
                "teammate_0f_count": teammate_0f,
                "opponent_0e_count": opponent_0e,
                "opponent_0f_count": opponent_0f,
                "self_presence_count": self_presence,
                "teammate_presence_count": teammate_presence,
                "opponent_presence_count": opponent_presence,
                "self_link_rate": ((self_0e + self_0f) / target_events) if target_events else 0.0,
                "teammate_link_rate": ((teammate_0e + teammate_0f) / target_events) if target_events else 0.0,
                "opponent_link_rate": ((opponent_0e + opponent_0f) / target_events) if target_events else 0.0,
                "self_presence_rate": (self_presence / target_events) if target_events else 0.0,
                "teammate_presence_rate": (teammate_presence / target_events) if target_events else 0.0,
                "opponent_presence_rate": (opponent_presence / target_events) if target_events else 0.0,
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
    parser = argparse.ArgumentParser(description="Measure whether action patterns align with self or teammate minion credits.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--action", default="0x02", help="Credit action family to inspect")
    parser.add_argument("--top-pattern-limit", type=int, default=12, help="How many patterns to inspect")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_action_self_vs_team(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        action_hex=args.action,
        top_pattern_limit=args.top_pattern_limit,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion action self-vs-team report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
