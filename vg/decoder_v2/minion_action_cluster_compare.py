"""Compare clustering behavior for selected credit patterns in a target replay."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minion_outlier_compare import build_minion_outlier_compare
from .minion_research import _load_truth_matches


def _pattern_key(action: int, value: Optional[float]) -> str:
    return f"0x{action:02X}@{'nan' if value is None else round(value, 2)}"


def _player_map(replay_file: str) -> Dict[int, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }


def _collect_pattern_cluster_stats(replay_file: str, selected_patterns: List[str], window_bytes: int = 100) -> Dict[str, Dict[str, object]]:
    player_map = _player_map(replay_file)
    events_by_pattern: Dict[str, List[Tuple[int, int, int]]] = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.entity_id_be not in player_map:
            continue
        pattern = _pattern_key(event.action, event.value)
        if pattern not in selected_patterns:
            continue
        events_by_pattern[pattern].append((event.frame_idx, event.file_offset, event.entity_id_be))

    rows = {}
    for pattern, events in events_by_pattern.items():
        events.sort()
        clusters = []
        current: List[Tuple[int, int, int]] = []
        for frame_idx, offset, entity_id_be in events:
            if not current:
                current = [(frame_idx, offset, entity_id_be)]
                continue
            prev_frame, prev_offset, _ = current[-1]
            if frame_idx == prev_frame and (offset - prev_offset) <= window_bytes:
                current.append((frame_idx, offset, entity_id_be))
            else:
                clusters.append(current)
                current = [(frame_idx, offset, entity_id_be)]
        if current:
            clusters.append(current)

        cluster_sizes = [len(cluster) for cluster in clusters]
        multi_player_clusters = sum(1 for cluster in clusters if len({eid for _, _, eid in cluster}) >= 2)
        unique_players = len({eid for _, _, eid in events})
        rows[pattern] = {
            "event_count": len(events),
            "cluster_count": len(clusters),
            "mean_cluster_size": (sum(cluster_sizes) / len(cluster_sizes)) if cluster_sizes else 0.0,
            "max_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
            "multi_player_cluster_count": multi_player_clusters,
            "unique_players": unique_players,
        }
    return rows


def build_minion_action_cluster_compare(
    truth_path: str,
    target_replay_name: str,
    action_hex: str = "0x02",
    top_pattern_limit: int = 12,
) -> Dict[str, object]:
    """Compare clustering behavior of selected action patterns in target vs baseline fixtures."""
    compare = build_minion_outlier_compare(truth_path, target_replay_name)
    selected_patterns = [
        pattern
        for pattern in [row["pattern"] for row in compare["credit_pattern_rate_deltas"][:top_pattern_limit * 2]]
        if pattern.startswith(action_hex.lower()) or pattern.startswith(action_hex.upper())
    ][:top_pattern_limit]

    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]
    target_match = next(match for match in complete_matches if match["replay_name"] == target_replay_name)
    target_stats = _collect_pattern_cluster_stats(target_match["replay_file"], selected_patterns)

    baseline_stats: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for match in complete_matches:
        if match["replay_name"] == target_replay_name:
            continue
        match_stats = _collect_pattern_cluster_stats(match["replay_file"], selected_patterns)
        for pattern in selected_patterns:
            if pattern in match_stats:
                baseline_stats[pattern].append(match_stats[pattern])

    pattern_rows = []
    for pattern in selected_patterns:
        target = target_stats.get(pattern, {})
        baseline = baseline_stats.get(pattern, [])
        if baseline:
            mean_event_count = sum(item["event_count"] for item in baseline) / len(baseline)
            mean_cluster_size = sum(item["mean_cluster_size"] for item in baseline) / len(baseline)
            mean_multi_player_clusters = sum(item["multi_player_cluster_count"] for item in baseline) / len(baseline)
            max_event_count = max(item["event_count"] for item in baseline)
        else:
            mean_event_count = None
            mean_cluster_size = None
            mean_multi_player_clusters = None
            max_event_count = None
        pattern_rows.append(
            {
                "pattern": pattern,
                "target": target,
                "baseline_peer_count": len(baseline),
                "baseline_mean_event_count": mean_event_count,
                "baseline_mean_cluster_size": mean_cluster_size,
                "baseline_mean_multi_player_clusters": mean_multi_player_clusters,
                "baseline_max_event_count": max_event_count,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "action_hex": action_hex,
        "selected_patterns": selected_patterns,
        "patterns": pattern_rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare clustering behavior of selected action patterns in a target replay.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--action", default="0x02", help="Credit action family to inspect")
    parser.add_argument("--top-pattern-limit", type=int, default=12, help="How many patterns to include")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_action_cluster_compare(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        action_hex=args.action,
        top_pattern_limit=args.top_pattern_limit,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion action cluster compare saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
