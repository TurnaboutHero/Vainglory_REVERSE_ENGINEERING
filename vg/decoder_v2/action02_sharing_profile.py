"""Profile action 0x02 value buckets by solo vs shared clustering behavior."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .credit_events import iter_credit_events
from .minion_research import _load_truth_matches


def _player_map(replay_file: str) -> Dict[int, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }


def _cluster_action02_events(replay_file: str, window_bytes: int = 100) -> Dict[float, Dict[str, int]]:
    player_map = _player_map(replay_file)
    by_value: Dict[float, List[Tuple[int, int, int]]] = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.entity_id_be not in player_map:
            continue
        if event.action != 0x02 or event.value is None:
            continue
        by_value[round(event.value, 2)].append((event.frame_idx, event.file_offset, event.entity_id_be))

    rows = {}
    for value, events in by_value.items():
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

        rows[value] = {
            "event_count": len(events),
            "cluster_count": len(clusters),
            "multi_player_cluster_count": sum(1 for cluster in clusters if len({eid for _, _, eid in cluster}) >= 2),
            "solo_cluster_count": sum(1 for cluster in clusters if len({eid for _, _, eid in cluster}) == 1),
            "unique_players": len({eid for _, _, eid in events}),
        }
    return rows


def build_action02_sharing_profile(truth_path: str, window_bytes: int = 100) -> Dict[str, object]:
    """Profile action 0x02 value buckets across complete fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    aggregate: Dict[float, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for match in complete_matches:
        value_rows = _cluster_action02_events(match["replay_file"], window_bytes=window_bytes)
        for value, stats in value_rows.items():
            aggregate[value]["match_count"] += 1
            for key, count in stats.items():
                aggregate[value][key] += count

    rows = []
    for value, stats in aggregate.items():
        cluster_count = stats["cluster_count"]
        multi_player_cluster_count = stats["multi_player_cluster_count"]
        rows.append(
            {
                "value": value,
                "match_count": stats["match_count"],
                "event_count": stats["event_count"],
                "cluster_count": cluster_count,
                "multi_player_cluster_count": multi_player_cluster_count,
                "solo_cluster_count": stats["solo_cluster_count"],
                "unique_players": stats["unique_players"],
                "shared_cluster_rate": (multi_player_cluster_count / cluster_count) if cluster_count else 0.0,
            }
        )
    rows.sort(key=lambda item: (item["match_count"], item["event_count"]), reverse=True)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "window_bytes": window_bytes,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile action 0x02 value buckets by solo vs shared clustering behavior.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--window-bytes", type=int, default=100, help="Cluster byte window")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_action02_sharing_profile(args.truth, window_bytes=args.window_bytes)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action02 sharing profile saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
