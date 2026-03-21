"""Generic player-event parsing for decoder_v2."""

from __future__ import annotations

import struct
from collections import defaultdict
from typing import Dict, Iterable, List

from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .models import PlayerEventRecord


EVENT_RECORD_SIZE = 37
PAYLOAD_SIZE = 32


def _load_player_entities_le(replay_file: str) -> Dict[int, str]:
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    return {
        player["entity_id"]: player["name"]
        for team in ("left", "right")
        for player in parsed["teams"][team]
        if player.get("entity_id")
    }


def iter_player_events(replay_file: str) -> Iterable[PlayerEventRecord]:
    """Yield raw player event records from the LE event stream."""
    player_entities = _load_player_entities_le(replay_file)
    for frame_idx, data in load_frames(replay_file):
        idx = 0
        while idx < len(data) - 5:
            if data[idx + 2:idx + 4] == b"\x00\x00":
                entity_id_le = struct.unpack("<H", data[idx:idx + 2])[0]
                if entity_id_le in player_entities and idx + 5 + PAYLOAD_SIZE <= len(data):
                    payload = data[idx + 5:idx + 5 + PAYLOAD_SIZE]
                    yield PlayerEventRecord(
                        frame_idx=frame_idx,
                        entity_id_le=entity_id_le,
                        action=data[idx + 4],
                        payload_hex=payload.hex(),
                    )
                    idx += EVENT_RECORD_SIZE
                    continue
            idx += 1


def collect_player_events_by_entity(replay_file: str) -> Dict[int, List[PlayerEventRecord]]:
    """Collect player events grouped by LE entity id."""
    grouped: Dict[int, List[PlayerEventRecord]] = defaultdict(list)
    for event in iter_player_events(replay_file):
        grouped[event.entity_id_le].append(event)
    return grouped
