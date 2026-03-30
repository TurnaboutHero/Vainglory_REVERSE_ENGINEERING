"""Evaluate alternative assist counting rules against truth-covered fixtures."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from vg.analysis.decode_tournament import _resolve_truth_player_name
from vg.core.kda_detector import KDADetector
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .kda_postgame_audit import _load_truth_matches


@dataclass(frozen=True)
class AssistRule:
    name: str
    require_flag: bool
    min_credit_count: int
    gold_only_threshold: Optional[float]

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "require_flag": self.require_flag,
            "min_credit_count": self.min_credit_count,
            "gold_only_threshold": self.gold_only_threshold,
        }


RULES = (
    AssistRule("current", True, 2, None),
    AssistRule("flag_len1", True, 1, None),
    AssistRule("flag_len3", True, 3, None),
    AssistRule("flag_or_gold_gt1", True, 2, 1.0),
    AssistRule("flag_or_gold_gt2", True, 2, 2.0),
    AssistRule("flag_or_gold_gt5", True, 2, 5.0),
    AssistRule("gold_only_gt1", False, 1, 1.0),
    AssistRule("gold_only_gt2", False, 1, 2.0),
    AssistRule("gold_only_gt5", False, 1, 5.0),
)


def _count_assists_for_rule(
    detector: KDADetector,
    team_map: Dict[int, str],
    valid_eids: List[int],
    *,
    game_duration: int,
    kill_buffer: int,
    rule: AssistRule,
) -> Dict[int, int]:
    assists = {eid: 0 for eid in valid_eids}
    max_ts = game_duration + kill_buffer

    for kill_event in detector.kill_events:
        if kill_event.timestamp is not None and kill_event.timestamp > max_ts:
            continue
        killer_eid = kill_event.killer_eid
        killer_team = team_map.get(killer_eid)
        if not killer_team:
            continue

        credits_by_eid: Dict[int, List[float]] = defaultdict(list)
        for credit in kill_event.credits:
            credits_by_eid[credit.eid].append(credit.value)

        for eid, values in credits_by_eid.items():
            if eid == killer_eid:
                continue
            if team_map.get(eid) != killer_team:
                continue

            has_flag = any(abs(value - 1.0) < 0.01 for value in values)
            eligible = False
            if rule.require_flag:
                eligible = has_flag and len(values) >= rule.min_credit_count
            if not eligible and rule.gold_only_threshold is not None:
                eligible = any(value > rule.gold_only_threshold for value in values if abs(value - 1.0) >= 0.01)
            if eligible:
                assists[eid] += 1

    return assists


def build_assist_rule_research(
    truth_path: str,
    *,
    kill_buffer: int = 3,
    complete_only: bool = True,
) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    rule_rows = []

    for rule in RULES:
        correct = total = 0
        mismatch_rows = []

        for match in matches:
            fixture_directory = str(Path(match["replay_file"]).parent.name)
            if complete_only and "Incomplete" in fixture_directory:
                continue

            replay_file = str(match["replay_file"])
            parsed = VGRParser(replay_file, auto_truth=False).parse()
            duration = int(match["match_info"]["duration_seconds"])
            player_map: Dict[int, Dict[str, object]] = {}
            team_map: Dict[int, str] = {}
            ordered_players = []
            for team_label in ("left", "right"):
                for player in parsed["teams"][team_label]:
                    entity_id = player.get("entity_id")
                    if not entity_id:
                        continue
                    entity_be = _le_to_be(entity_id)
                    player_map[entity_be] = player
                    team_map[entity_be] = team_label
                    ordered_players.append((entity_be, player))

            detector = KDADetector(set(player_map))
            for frame_idx, data in load_frames(replay_file):
                detector.process_frame(frame_idx, data)

            assists = _count_assists_for_rule(
                detector,
                team_map,
                [entity_be for entity_be, _ in ordered_players],
                game_duration=duration,
                kill_buffer=kill_buffer,
                rule=rule,
            )

            for entity_be, player in ordered_players:
                truth_name = _resolve_truth_player_name(player["name"], match["players"])
                if not truth_name:
                    continue
                truth_player = match["players"][truth_name]
                if truth_player.get("assists") is None:
                    continue
                total += 1
                predicted = assists[entity_be]
                expected = int(truth_player["assists"])
                if predicted == expected:
                    correct += 1
                else:
                    mismatch_rows.append(
                        {
                            "replay_name": match["replay_name"],
                            "player_name": player["name"],
                            "hero_name": player.get("hero_name"),
                            "truth_assists": expected,
                            "predicted_assists": predicted,
                            "diff": predicted - expected,
                        }
                    )

        pct = round((correct / total) * 100, 4) if total else 0.0
        rule_rows.append(
            {
                "rule": rule.to_dict(),
                "correct": correct,
                "total": total,
                "pct": pct,
                "mismatch_count": len(mismatch_rows),
                "mismatch_rows": mismatch_rows[:100],
            }
        )

    rule_rows.sort(key=lambda row: (row["correct"], -row["mismatch_count"]), reverse=True)
    return {
        "truth_path": str(Path(truth_path).resolve()),
        "kill_buffer": kill_buffer,
        "complete_only": complete_only,
        "rules": rule_rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate alternative assist counting rules.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", type=int, default=3, help="Kill buffer seconds")
    parser.add_argument("--all-fixtures", action="store_true", help="Include incomplete fixtures")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_assist_rule_research(
        args.truth,
        kill_buffer=args.kill_buffer,
        complete_only=not args.all_fixtures,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Assist rule research saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
