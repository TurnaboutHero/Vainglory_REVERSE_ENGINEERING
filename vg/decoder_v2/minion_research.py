"""Research utilities for minion kill signal discovery in decoder_v2."""

from __future__ import annotations

import argparse
import json
import math
import struct
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minions import compare_minion_candidates_to_truth, collect_minion_candidates


def _load_truth_matches(truth_path: str) -> List[Dict]:
    return json.loads(Path(truth_path).read_text(encoding="utf-8")).get("matches", [])


def _load_player_credit_counters(replay_file: str) -> Dict[str, Counter]:
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    counters: Dict[str, Counter] = defaultdict(Counter)
    for event in iter_credit_events(replay_file):
        eid = event.entity_id_be
        if eid not in player_map:
            continue
        key = (event.action, round(event.value, 2)) if event.value is not None else (event.action, "nan")
        counters[player_map[eid]][key] += 1
    return counters


def _load_player_action_counters(replay_file: str) -> Dict[str, Counter]:
    """Load generic player event action counts from the LE event stream."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    player_map = {
        player["entity_id"]: player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    prefix = replay_path.stem.rsplit(".", 1)[0]
    counters: Dict[str, Counter] = defaultdict(Counter)
    for frame in sorted(frame_dir.glob(f"{prefix}.*.vgr"), key=lambda p: int(p.stem.split(".")[-1])):
        data = frame.read_bytes()
        idx = 0
        while idx < len(data) - 5:
            if data[idx + 2:idx + 4] == b"\x00\x00":
                entity_id_le = struct.unpack("<H", data[idx:idx + 2])[0]
                if entity_id_le in player_map:
                    counters[player_map[entity_id_le]][data[idx + 4]] += 1
                    idx += 37
                    continue
            idx += 1
    return counters


def _resolve_truth_name(name: str, truth_players: Dict[str, Dict]) -> Optional[str]:
    if name in truth_players:
        return name
    lower_map = {key.lower(): key for key in truth_players}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    prefix = name.split("_", 1)[0]
    candidates = [key for key in truth_players if key.split("_", 1)[0] == prefix]
    if not candidates:
        return None
    import difflib

    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.85)
    return matches[0] if matches else None


def build_tail_activity_report(replay_file: str, truth_match: Dict[str, object]) -> Dict[str, object]:
    """Inspect activity after the last 0x0E occurrence for each player."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    player_map_le = {
        player["entity_id"]: player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    player_map_be = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    prefix = replay_path.stem.rsplit(".", 1)[0]
    frames = [
        (int(frame.stem.split(".")[-1]), frame.read_bytes())
        for frame in sorted(frame_dir.glob(f"{prefix}.*.vgr"), key=lambda p: int(p.stem.split(".")[-1]))
    ]

    minion_candidates = {row.player_name: row for row in collect_minion_candidates(replay_file)}
    rows = []
    for entity_le, player_name in player_map_le.items():
        truth_name = _resolve_truth_name(player_name, truth_match["players"])
        truth_mk = truth_match["players"][truth_name]["minion_kills"] if truth_name else None
        candidate = minion_candidates[player_name]
        tail_start = (candidate.last_0e_frame if candidate.last_0e_frame is not None else -1) + 1
        tail_credit = Counter()
        tail_actions = Counter()
        tail_credit_events = [
            event
            for event in iter_credit_events(replay_file)
            if event.entity_id_be == _le_to_be(entity_le) and event.frame_idx >= tail_start
        ]

        for frame_idx, data in frames:
            if frame_idx < tail_start:
                continue

            idx = 0
            while idx < len(data) - 5:
                if data[idx + 2:idx + 4] == b"\x00\x00":
                    entity_id_le = struct.unpack("<H", data[idx:idx + 2])[0]
                    if entity_id_le == entity_le:
                        tail_actions[data[idx + 4]] += 1
                        idx += 5
                        continue
                idx += 1

        for event in tail_credit_events:
            if event.value is not None:
                tail_credit[(event.action, round(event.value, 2))] += 1

        rows.append(
            {
                "player_name": player_name,
                "truth_name": truth_name,
                "truth_minion_kills": truth_mk,
                "count_0e": candidate.action_0e_value_1,
                "diff_vs_0e": candidate.action_0e_value_1 - truth_mk if truth_mk is not None else None,
                "last_0e_frame": candidate.last_0e_frame,
                "frames_after_last_0e": (frames[-1][0] - candidate.last_0e_frame) if candidate.last_0e_frame is not None else None,
                "tail_credit_top": [
                    {"action": action, "value": value, "count": count}
                    for (action, value), count in tail_credit.most_common(12)
                ],
                "tail_actions_top": [
                    {"action": action, "count": count}
                    for action, count in tail_actions.most_common(12)
                ],
            }
        )

    rows.sort(key=lambda row: (999 if row["diff_vs_0e"] is None else row["diff_vs_0e"], row["player_name"]))
    return {
        "replay_name": truth_match["replay_name"],
        "fixture_directory": Path(replay_file).parent.name,
        "rows": rows,
    }


def build_minion_research_report(truth_path: str) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    complete_matches = [m for m in matches if "Incomplete" not in Path(m["replay_file"]).parent.name]
    target_match6_replay_name = matches[5]["replay_name"] if len(matches) > 5 else None

    feature_errors: Dict[str, List[int]] = defaultdict(list)
    single_feature_errors: Dict[Tuple[int, object], List[int]] = defaultdict(list)
    action_feature_errors: Dict[int, List[int]] = defaultdict(list)
    additive_credit_feature_errors: Dict[Tuple[str, int, object], List[int]] = defaultdict(list)
    residual_credit_feature_errors: Dict[Tuple[int, object], List[int]] = defaultdict(list)
    residual_action_feature_errors: Dict[int, List[int]] = defaultdict(list)
    tail_action_pairs: Dict[int, List[Tuple[int, int]]] = defaultdict(list)
    match6_probe = None
    match6_tail = None
    incomplete_probe = None
    per_match_top_patterns = []

    for match in complete_matches:
        counters = _load_player_credit_counters(match["replay_file"])
        action_counters = _load_player_action_counters(match["replay_file"])
        rows = []
        for player_name, player_truth in match["players"].items():
            truth_mk = player_truth.get("minion_kills")
            if truth_mk is None or player_name not in counters:
                continue

            counter = counters[player_name]
            values = {
                "0E@1.0": counter[(0x0E, 1.0)],
                "0F@1.0": counter[(0x0F, 1.0)],
                "0D_total": sum(v for (action, _), v in counter.items() if action == 0x0D),
            }
            residual = truth_mk - values["0E@1.0"]
            values["0E+0F"] = values["0E@1.0"] + values["0F@1.0"]
            values["0E+0D"] = values["0E@1.0"] + values["0D_total"]

            for feature, value in values.items():
                feature_errors[feature].append(abs(value - truth_mk))
            for key, count in counter.items():
                single_feature_errors[key].append(abs(count - truth_mk))
                base = values["0E@1.0"]
                additive_credit_feature_errors[("plus", key[0], key[1])].append(abs((base + count) - truth_mk))
                additive_credit_feature_errors[("minus", key[0], key[1])].append(abs((base - count) - truth_mk))
                residual_credit_feature_errors[key].append(abs(count - residual))
            for action, count in action_counters.get(player_name, {}).items():
                action_feature_errors[action].append(abs(count - truth_mk))
                residual_action_feature_errors[action].append(abs(count - residual))

            rows.append(
                {
                    "player_name": player_name,
                    "truth_minion_kills": truth_mk,
                    "residual_vs_0e": residual,
                    "feature_values": values,
                    "top_credit_patterns": [
                        {"action": action, "value": value, "count": count}
                        for (action, value), count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:12]
                    ],
                    "top_residual_credit_patterns": [
                        {
                            "action": action,
                            "value": value,
                            "count": count,
                            "abs_diff_to_residual": abs(count - residual),
                        }
                        for (action, value), count in sorted(
                            counter.items(),
                            key=lambda item: (abs(item[1] - residual), -item[1], item[0]),
                        )[:12]
                    ],
                    "top_residual_actions": [
                        {
                            "action": action,
                            "count": count,
                            "abs_diff_to_residual": abs(count - residual),
                        }
                        for action, count in sorted(
                            action_counters.get(player_name, {}).items(),
                            key=lambda item: (abs(item[1] - residual), -item[1], item[0]),
                        )[:12]
                    ],
                }
            )
        per_match_top_patterns.append(
            {
                "replay_name": match["replay_name"],
                "fixture_directory": Path(match["replay_file"]).parent.name,
                "players": rows,
            }
        )
        if target_match6_replay_name and match["replay_name"] == target_match6_replay_name:
            match6_probe = compare_minion_candidates_to_truth(match["replay_file"], truth_path)
            match6_tail = build_tail_activity_report(match["replay_file"], match)
            for row in match6_tail["rows"]:
                diff = row["diff_vs_0e"]
                if diff is None:
                    continue
                for item in row["tail_actions_top"]:
                    tail_action_pairs[item["action"]].append((diff, item["count"]))

    for match in matches:
        if "Incomplete" in Path(match["replay_file"]).parent.name:
            incomplete_probe = compare_minion_candidates_to_truth(match["replay_file"], truth_path)
            break

    feature_summary = {
        feature: {
            "mae": sum(errors) / len(errors),
            "max_abs_error": max(errors),
            "count": len(errors),
        }
        for feature, errors in feature_errors.items()
        if errors
    }
    top_single_features = [
        {
            "action": action,
            "value": value,
            "mae": sum(errors) / len(errors),
            "max_abs_error": max(errors),
            "count": len(errors),
        }
        for (action, value), errors in single_feature_errors.items()
        if len(errors) >= 10
    ]
    top_single_features.sort(key=lambda item: (item["mae"], item["max_abs_error"], -item["count"]))
    top_action_features = [
        {
            "action": action,
            "mae": sum(errors) / len(errors),
            "max_abs_error": max(errors),
            "count": len(errors),
        }
        for action, errors in action_feature_errors.items()
        if len(errors) >= 10
    ]
    top_action_features.sort(key=lambda item: (item["mae"], item["max_abs_error"], -item["count"]))
    additive_feature_summary = [
        {
            "mode": mode,
            "action": action,
            "value": value,
            "mae": sum(errors) / len(errors),
            "max_abs_error": max(errors),
            "count": len(errors),
        }
        for (mode, action, value), errors in additive_credit_feature_errors.items()
        if len(errors) >= 10
    ]
    additive_feature_summary.sort(key=lambda item: (item["mae"], item["max_abs_error"], -item["count"]))
    residual_credit_summary = [
        {
            "action": action,
            "value": value,
            "mae_to_residual": sum(errors) / len(errors),
            "max_abs_error_to_residual": max(errors),
            "count": len(errors),
        }
        for (action, value), errors in residual_credit_feature_errors.items()
        if len(errors) >= 10
    ]
    residual_credit_summary.sort(key=lambda item: (item["mae_to_residual"], item["max_abs_error_to_residual"], -item["count"]))
    residual_action_summary = [
        {
            "action": action,
            "mae_to_residual": sum(errors) / len(errors),
            "max_abs_error_to_residual": max(errors),
            "count": len(errors),
        }
        for action, errors in residual_action_feature_errors.items()
        if len(errors) >= 10
    ]
    residual_action_summary.sort(key=lambda item: (item["mae_to_residual"], item["max_abs_error_to_residual"], -item["count"]))
    tail_action_summary = []
    for action, pairs in tail_action_pairs.items():
        if len(pairs) < 3:
            continue
        diffs = [diff for diff, _ in pairs]
        counts = [count for _, count in pairs]
        mean_diff = sum(diffs) / len(diffs)
        mean_count = sum(counts) / len(counts)
        cov = sum((diff - mean_diff) * (count - mean_count) for diff, count in pairs) / len(pairs)
        var_diff = sum((diff - mean_diff) ** 2 for diff in diffs) / len(pairs)
        var_count = sum((count - mean_count) ** 2 for count in counts) / len(pairs)
        corr = 0.0
        if var_diff > 0 and var_count > 0:
            corr = cov / ((var_diff ** 0.5) * (var_count ** 0.5))
        tail_action_summary.append(
            {
                "action": action,
                "corr_to_missing_vs_0e": corr,
                "sample_count": len(pairs),
                "mean_tail_count": mean_count,
                "mean_missing_vs_0e": mean_diff,
            }
        )
    tail_action_summary.sort(key=lambda item: abs(item["corr_to_missing_vs_0e"]), reverse=True)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "feature_summary": feature_summary,
        "top_single_features": top_single_features[:50],
        "top_action_features": top_action_features[:50],
        "additive_feature_summary": additive_feature_summary[:50],
        "residual_credit_summary": residual_credit_summary[:50],
        "residual_action_summary": residual_action_summary[:50],
        "match6_probe": match6_probe,
        "match6_tail_activity": match6_tail,
        "match6_tail_action_summary": tail_action_summary,
        "incomplete_probe": incomplete_probe,
        "per_match_top_patterns": per_match_top_patterns,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build minion signal research report for decoder_v2.")
    parser.add_argument(
        "--truth",
        default="vg/output/tournament_truth.json",
        help="Path to truth JSON",
    )
    parser.add_argument(
        "--output",
        help="Optional output path",
    )
    args = parser.parse_args(argv)

    report = build_minion_research_report(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion research report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
