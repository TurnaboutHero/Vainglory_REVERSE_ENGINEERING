"""Minion candidate logging for decoder_v2."""

from __future__ import annotations

import struct
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import assess_completeness, extract_replay_signals, load_frames
from .credit_events import iter_credit_events
from .models import MinionCandidateSummary


def collect_minion_candidates(replay_file: str) -> List[MinionCandidateSummary]:
    """Collect per-player minion-related candidate counts from credit events."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    counters: Dict[int, Counter] = {eid: Counter() for eid in player_map}
    last_frames: Dict[int, Dict[str, Optional[int]]] = {
        eid: {"0e": None, "0f": None, "0d": None} for eid in player_map
    }

    for event in iter_credit_events(replay_file):
        eid = event.entity_id_be
        if eid not in counters:
            continue

        if event.value is not None and abs(event.value - 1.0) < 0.01 and event.action == 0x0E:
            counters[eid]["0e_value_1"] += 1
            last_frames[eid]["0e"] = event.frame_idx
        elif event.value is not None and abs(event.value - 1.0) < 0.01 and event.action == 0x0F:
            counters[eid]["0f_value_1"] += 1
            last_frames[eid]["0f"] = event.frame_idx
        elif event.action == 0x0D:
            counters[eid]["0d_total"] += 1
            last_frames[eid]["0d"] = event.frame_idx

    return [
        MinionCandidateSummary(
            player_name=player_map[eid],
            player_eid_be=eid,
            action_0e_value_1=counter.get("0e_value_1", 0),
            action_0f_value_1=counter.get("0f_value_1", 0),
            action_0d_total=counter.get("0d_total", 0),
            last_0e_frame=last_frames[eid]["0e"],
            last_0f_frame=last_frames[eid]["0f"],
            last_0d_frame=last_frames[eid]["0d"],
        )
        for eid, counter in sorted(counters.items(), key=lambda item: player_map[item[0]])
    ]


def collect_minion_event_log(replay_file: str) -> Dict[str, List[Dict[str, int]]]:
    """Collect per-player frame-level minion-related credit counts."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    player_map = {
        _le_to_be(player["entity_id"]): player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }
    per_player: Dict[str, List[Dict[str, int]]] = {name: [] for name in player_map.values()}

    frame_counters: Dict[int, Dict[int, Counter]] = {
        eid: {} for eid in player_map
    }
    for event in iter_credit_events(replay_file):
        eid = event.entity_id_be
        if eid not in player_map:
            continue
        by_frame = frame_counters[eid].setdefault(event.frame_idx, Counter())
        if event.value is not None and abs(event.value - 1.0) < 0.01 and event.action == 0x0E:
            by_frame["0e_value_1"] += 1
        elif event.value is not None and abs(event.value - 1.0) < 0.01 and event.action == 0x0F:
            by_frame["0f_value_1"] += 1
        elif event.action == 0x0D:
            by_frame["0d_total"] += 1

    for frame_idx, _ in load_frames(replay_file):
        for eid in player_map:
            counter = frame_counters[eid].get(frame_idx, Counter())
            per_player[player_map[eid]].append(
                {
                    "frame_idx": frame_idx,
                    "action_0e_value_1": counter.get("0e_value_1", 0),
                    "action_0f_value_1": counter.get("0f_value_1", 0),
                    "action_0d_total": counter.get("0d_total", 0),
                }
            )

    return per_player


def compare_minion_candidates_to_truth(
    replay_file: str,
    truth_path: str,
) -> Dict[str, object]:
    """Compare current minion candidate counts to truth for a replay."""
    truth_data = json_load(truth_path)
    replay_name = Path(replay_file).stem.rsplit(".", 1)[0]
    truth_match = next(
        (match for match in truth_data["matches"] if match["replay_name"] == replay_name),
        None,
    )
    if truth_match is None:
        raise ValueError(f"Replay not found in truth: {replay_name}")

    signals = extract_replay_signals(replay_file)
    assessment = assess_completeness(signals)
    candidates = collect_minion_candidates(replay_file)
    event_log = collect_minion_event_log(replay_file)
    rows = []
    max_frame_index = signals.max_frame_index
    for candidate in candidates:
        truth_player = truth_match["players"].get(candidate.player_name)
        truth_mk = truth_player.get("minion_kills") if truth_player else None
        cumulative_0e = 0
        cumulative_0f = 0
        sample_event_log = []
        for item in event_log.get(candidate.player_name, []):
            cumulative_0e += item["action_0e_value_1"]
            cumulative_0f += item["action_0f_value_1"]
            if item["action_0e_value_1"] or item["action_0f_value_1"] or item["action_0d_total"]:
                sample_event_log.append(
                    {
                        "frame_idx": item["frame_idx"],
                        "delta_0e": item["action_0e_value_1"],
                        "delta_0f": item["action_0f_value_1"],
                        "delta_0d": item["action_0d_total"],
                        "cum_0e": cumulative_0e,
                        "cum_0f": cumulative_0f,
                    }
                )
        rows.append(
            {
                "player_name": candidate.player_name,
                "player_eid_be": candidate.player_eid_be,
                "truth_minion_kills": truth_mk,
                "action_0e_value_1": candidate.action_0e_value_1,
                "action_0f_value_1": candidate.action_0f_value_1,
                "action_0d_total": candidate.action_0d_total,
                "last_0e_frame": candidate.last_0e_frame,
                "last_0f_frame": candidate.last_0f_frame,
                "last_0d_frame": candidate.last_0d_frame,
                "frames_after_last_0e": (max_frame_index - candidate.last_0e_frame)
                if candidate.last_0e_frame is not None
                else None,
                "diff_vs_0e": candidate.action_0e_value_1 - truth_mk if truth_mk is not None else None,
                "sample_event_log": sample_event_log[:80],
            }
        )
    return {
        "replay_name": replay_name,
        "assessment": assessment.to_dict(),
        "rows": rows,
    }


def json_load(path: str) -> Dict[str, object]:
    import json

    return json.loads(Path(path).read_text(encoding="utf-8"))
