"""Replay completeness and signal extraction for decoder_v2."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from vg.core.kda_detector import KDADetector
from vg.core.unified_decoder import _DEATH_HEADER, _ITEM_ACQUIRE_HEADER, _le_to_be
from vg.core.vgr_parser import VGRParser

from .models import CompletenessAssessment, CompletenessStatus, ReplaySignalSummary


def load_frames(replay_file: str) -> List[Tuple[int, bytes]]:
    """Load replay frames as `(frame_index, bytes)` tuples."""
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit(".", 1)[0]
    return [
        (int(frame.stem.split(".")[-1]), frame.read_bytes())
        for frame in sorted(frame_dir.glob(f"{replay_name}.*.vgr"), key=lambda p: int(p.stem.split(".")[-1]))
    ]


def _scan_max_timestamp(
    all_data: bytes,
    header: bytes,
    timestamp_offset: int,
    guards: Sequence[Tuple[int, bytes]] = (),
) -> Optional[float]:
    """Scan the largest valid float timestamp for a header family."""
    pos = 0
    values = []
    while True:
        idx = all_data.find(header, pos)
        if idx == -1:
            break
        pos = idx + 1
        if idx + timestamp_offset + 4 > len(all_data):
            continue
        if any(all_data[idx + rel:idx + rel + len(expected)] != expected for rel, expected in guards):
            continue
        try:
            ts = struct.unpack_from(">f", all_data, idx + timestamp_offset)[0]
        except struct.error:
            continue
        if 0 < ts < 5000:
            values.append(ts)
    return max(values) if values else None


def extract_replay_signals(replay_file: str) -> ReplaySignalSummary:
    """Extract timing/completeness signals from a replay."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    frames = load_frames(replay_file)
    all_data = b"".join(data for _, data in frames)

    valid_eids = {
        _le_to_be(player["entity_id"])
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }

    detector = KDADetector(valid_eids)
    for frame_idx, data in frames:
        detector.process_frame(frame_idx, data)

    max_kill_ts = max((event.timestamp for event in detector.kill_events if event.timestamp is not None), default=None)
    max_player_death_ts = max((event.timestamp for event in detector.death_events), default=None)
    max_death_header_ts = _scan_max_timestamp(
        all_data,
        _DEATH_HEADER,
        9,
        guards=((3, b"\x00\x00"), (7, b"\x00\x00")),
    )
    max_item_ts = _scan_max_timestamp(
        all_data,
        _ITEM_ACQUIRE_HEADER,
        17,
        guards=((3, b"\x00\x00"),),
    )

    crystal_ts = None
    if all_data:
        crystal_events = []
        pos = 0
        while True:
            idx = all_data.find(_DEATH_HEADER, pos)
            if idx == -1:
                break
            pos = idx + 1
            if idx + 13 > len(all_data):
                continue
            if (
                all_data[idx + 3:idx + 5] != b"\x00\x00"
                or all_data[idx + 7:idx + 9] != b"\x00\x00"
            ):
                continue
            eid = struct.unpack_from(">H", all_data, idx + 5)[0]
            ts = struct.unpack_from(">f", all_data, idx + 9)[0]
            if 2000 <= eid <= 2005 and 60 < ts < 2400:
                crystal_events.append(ts)
        if crystal_events:
            crystal_ts = max(crystal_events)

    return ReplaySignalSummary(
        replay_name=parsed["replay_name"],
        replay_file=parsed["replay_file"],
        frame_count=len(frames),
        max_frame_index=frames[-1][0] if frames else 0,
        crystal_ts=crystal_ts,
        max_kill_ts=max_kill_ts,
        max_player_death_ts=max_player_death_ts,
        max_death_header_ts=max_death_header_ts,
        max_item_ts=max_item_ts,
    )


def assess_completeness(signals: ReplaySignalSummary) -> CompletenessAssessment:
    """Apply a conservative completeness heuristic."""
    crystal_ts = signals.crystal_ts
    max_death_ts = signals.max_player_death_ts
    max_death_header_ts = signals.max_death_header_ts

    if (
        crystal_ts is not None
        and max_death_ts is not None
        and abs(crystal_ts - max_death_ts) <= 30
    ):
        return CompletenessAssessment(
            status=CompletenessStatus.COMPLETE_CONFIRMED,
            reason="Crystal death agrees with player-death tail within 30s.",
            signals=signals,
        )

    if (
        crystal_ts is None
        and max_death_ts is not None
        and max_death_ts >= 1500
        and (max_death_header_ts is None or abs(max_death_header_ts - max_death_ts) <= 30)
    ):
        return CompletenessAssessment(
            status=CompletenessStatus.COMPLETE_CONFIRMED,
            reason="No crystal death, but late-game death tail reaches >=1500s without conflicting death-header signal.",
            signals=signals,
        )

    if (
        max_death_ts is not None
        and max_death_header_ts is not None
        and max_death_ts >= 1400
        and signals.frame_count >= 140
        and abs(max_death_header_ts - max_death_ts) <= 30
    ):
        return CompletenessAssessment(
            status=CompletenessStatus.COMPLETE_CONFIRMED,
            reason="Long replay with late, self-consistent death tail even though crystal evidence is weak or inconsistent.",
            signals=signals,
        )

    if (
        max_death_ts is not None
        and max_death_header_ts is not None
        and signals.max_item_ts is not None
        and max_death_ts >= 1000
        and signals.frame_count >= 110
        and abs(max_death_header_ts - max_death_ts) <= 30
        and abs(signals.max_item_ts - max_death_header_ts) <= 30
    ):
        return CompletenessAssessment(
            status=CompletenessStatus.COMPLETE_CONFIRMED,
            reason="Late-game death, generic death-header, and item tails are mutually consistent in a long replay.",
            signals=signals,
        )

    if (
        crystal_ts is None
        and max_death_ts is not None
        and max_death_header_ts is not None
        and max_death_ts < 600
        and (max_death_header_ts - max_death_ts) > 300
        and signals.frame_count < 90
    ):
        return CompletenessAssessment(
            status=CompletenessStatus.INCOMPLETE_CONFIRMED,
            reason="No crystal death, short frame count, and large gap between player-death tail and generic death-header tail.",
            signals=signals,
        )

    return CompletenessAssessment(
        status=CompletenessStatus.COMPLETENESS_UNKNOWN,
        reason="Signals do not support a safe complete/incomplete decision yet.",
        signals=signals,
    )
