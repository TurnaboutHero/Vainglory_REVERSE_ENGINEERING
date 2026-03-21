"""Inspect same-frame context around minion credit events."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .credit_events import iter_credit_events
from .minion_research import _load_truth_matches


DEFAULT_HEADER_HEXES = (
    "10041d",
    "18043e",
    "100430",
    "28043f",
    "08042c",
    "080424",
    "18040d",
    "18041c",
    "18041e",
)


def _round_value(value: Optional[float]) -> object:
    return round(value, 2) if value is not None else "nan"


def _summarize_counter(counter: Counter, total_samples: int, label_name: str) -> List[Dict[str, object]]:
    rows = []
    for key, count in counter.most_common(20):
        row = {
            label_name: key,
            "count": count,
            "per_target_event": (count / total_samples) if total_samples else 0.0,
        }
        rows.append(row)
    return rows


def _summarize_differential_counts(
    positive_counter: Counter,
    nonpositive_counter: Counter,
    positive_total: int,
    nonpositive_total: int,
    label_name: str,
) -> List[Dict[str, object]]:
    rows = []
    for key in set(positive_counter) | set(nonpositive_counter):
        positive_count = positive_counter.get(key, 0)
        nonpositive_count = nonpositive_counter.get(key, 0)
        positive_rate = (positive_count / positive_total) if positive_total else 0.0
        nonpositive_rate = (nonpositive_count / nonpositive_total) if nonpositive_total else 0.0
        if positive_count + nonpositive_count < 20:
            continue
        rows.append(
            {
                label_name: key,
                "positive_count": positive_count,
                "nonpositive_count": nonpositive_count,
                "positive_per_target_event": positive_rate,
                "nonpositive_per_target_event": nonpositive_rate,
                "delta_per_target_event": positive_rate - nonpositive_rate,
                "rate_ratio": (positive_rate / nonpositive_rate) if nonpositive_rate else None,
            }
        )
    rows.sort(
        key=lambda item: (
            item["delta_per_target_event"],
            item["positive_count"] - item["nonpositive_count"],
        ),
        reverse=True,
    )
    return rows[:20]


def build_minion_window_report(
    replay_file: str,
    truth_path: Optional[str] = None,
    byte_window: int = 96,
    header_hexes: Iterable[str] = DEFAULT_HEADER_HEXES,
) -> Dict[str, object]:
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    replay_name = parsed["replay_name"]
    frames = {frame_idx: data for frame_idx, data in load_frames(replay_file)}
    header_bytes = [(header_hex, bytes.fromhex(header_hex)) for header_hex in header_hexes]

    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }

    truth_players: Dict[str, Dict[str, object]] = {}
    if truth_path:
        for match in _load_truth_matches(truth_path):
            if match["replay_name"] == replay_name:
                truth_players = match.get("players", {})
                break

    all_credit_events = list(iter_credit_events(replay_file))
    frame_entity_events: Dict[Tuple[int, int], List[object]] = defaultdict(list)
    for event in all_credit_events:
        frame_entity_events[(event.frame_idx, event.entity_id_be)].append(event)

    player_rows: Dict[str, Dict[str, object]] = {}
    positive_header_counter = Counter()
    nonpositive_header_counter = Counter()
    positive_credit_counter = Counter()
    nonpositive_credit_counter = Counter()
    positive_target_samples = 0
    nonpositive_target_samples = 0

    baseline_0e_by_player = Counter()
    for event in all_credit_events:
        if event.action == 0x0E and event.value == 1.0 and event.entity_id_be in player_map:
            baseline_0e_by_player[player_map[event.entity_id_be]] += 1

    for event in all_credit_events:
        if event.entity_id_be not in player_map:
            continue
        if event.action not in (0x0E, 0x0F) or event.value != 1.0:
            continue

        player_name = player_map[event.entity_id_be]
        player_row = player_rows.setdefault(
            player_name,
            {
                "player_name": player_name,
                "truth_minion_kills": truth_players.get(player_name, {}).get("minion_kills"),
                "baseline_0e": baseline_0e_by_player.get(player_name, 0),
                "residual_vs_0e": None,
                "target_0e_samples": 0,
                "target_0f_samples": 0,
                "neighbor_headers": Counter(),
                "same_frame_credit_patterns": Counter(),
            },
        )
        if player_row["truth_minion_kills"] is not None:
            player_row["residual_vs_0e"] = player_row["truth_minion_kills"] - player_row["baseline_0e"]

        if event.action == 0x0E:
            player_row["target_0e_samples"] += 1
        else:
            player_row["target_0f_samples"] += 1

        data = frames[event.frame_idx]
        start = max(0, event.file_offset - byte_window)
        end = min(len(data), event.file_offset + 12 + byte_window)
        window = data[start:end]
        for header_hex, header in header_bytes:
            count = window.count(header)
            if count:
                player_row["neighbor_headers"][header_hex] += count

        sibling_events = frame_entity_events[(event.frame_idx, event.entity_id_be)]
        for sibling in sibling_events:
            if sibling.file_offset == event.file_offset:
                continue
            pattern = f"0x{sibling.action:02X}@{_round_value(sibling.value)}"
            player_row["same_frame_credit_patterns"][pattern] += 1

    player_output = []
    for player_name, row in sorted(player_rows.items()):
        residual = row["residual_vs_0e"]
        target_samples = row["target_0e_samples"] + row["target_0f_samples"]
        is_positive = residual is not None and residual > 0
        if is_positive:
            positive_target_samples += target_samples
            positive_header_counter.update(row["neighbor_headers"])
            positive_credit_counter.update(row["same_frame_credit_patterns"])
        else:
            nonpositive_target_samples += target_samples
            nonpositive_header_counter.update(row["neighbor_headers"])
            nonpositive_credit_counter.update(row["same_frame_credit_patterns"])

        player_output.append(
            {
                "player_name": player_name,
                "truth_minion_kills": row["truth_minion_kills"],
                "baseline_0e": row["baseline_0e"],
                "residual_vs_0e": residual,
                "target_0e_samples": row["target_0e_samples"],
                "target_0f_samples": row["target_0f_samples"],
                "top_neighbor_headers": _summarize_counter(row["neighbor_headers"], target_samples, "header_hex"),
                "top_same_frame_credit_patterns": _summarize_counter(
                    row["same_frame_credit_patterns"], target_samples, "pattern"
                ),
            }
        )

    return {
        "replay_name": replay_name,
        "replay_file": str(Path(replay_file).resolve()),
        "byte_window": byte_window,
        "candidate_headers": list(header_hexes),
        "aggregate": {
            "players": len(player_output),
            "positive_residual_players": sum(1 for row in player_output if (row["residual_vs_0e"] or 0) > 0),
            "nonpositive_or_unknown_players": sum(1 for row in player_output if (row["residual_vs_0e"] or 0) <= 0),
            "positive_target_samples": positive_target_samples,
            "nonpositive_target_samples": nonpositive_target_samples,
            "positive_header_summary": _summarize_counter(
                positive_header_counter, positive_target_samples, "header_hex"
            ),
            "nonpositive_header_summary": _summarize_counter(
                nonpositive_header_counter, nonpositive_target_samples, "header_hex"
            ),
            "positive_enriched_headers": _summarize_differential_counts(
                positive_header_counter,
                nonpositive_header_counter,
                positive_target_samples,
                nonpositive_target_samples,
                "header_hex",
            ),
            "positive_credit_pattern_summary": _summarize_counter(
                positive_credit_counter, positive_target_samples, "pattern"
            ),
            "nonpositive_credit_pattern_summary": _summarize_counter(
                nonpositive_credit_counter, nonpositive_target_samples, "pattern"
            ),
            "positive_enriched_credit_patterns": _summarize_differential_counts(
                positive_credit_counter,
                nonpositive_credit_counter,
                positive_target_samples,
                nonpositive_target_samples,
                "pattern",
            ),
        },
        "players": player_output,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect same-frame context around 0x0E/0x0F minion credit events.")
    parser.add_argument("replay_file", help="Path to replay .0.vgr")
    parser.add_argument("--truth", help="Optional truth JSON for residual grouping")
    parser.add_argument("--byte-window", type=int, default=96, help="Byte radius around each target event")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_window_report(
        replay_file=args.replay_file,
        truth_path=args.truth,
        byte_window=args.byte_window,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion window report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
