"""Generic credit-event parsing for decoder_v2."""

from __future__ import annotations

import math
import struct
from collections import defaultdict
from typing import Dict, Iterable, List

from vg.core.unified_decoder import _CREDIT_HEADER

from .completeness import load_frames
from .models import CreditEventRecord


def iter_credit_events(replay_file: str) -> Iterable[CreditEventRecord]:
    """Yield raw credit events for a replay."""
    for frame_idx, data in load_frames(replay_file):
        pos = 0
        while True:
            pos = data.find(_CREDIT_HEADER, pos)
            if pos == -1:
                break
            if pos + 12 > len(data):
                pos += 1
                continue
            if data[pos + 3:pos + 5] != b"\x00\x00":
                pos += 1
                continue

            entity_id_be = struct.unpack_from(">H", data, pos + 5)[0]
            raw_value = struct.unpack_from(">f", data, pos + 7)[0]
            action = data[pos + 11]
            value_is_finite = not (math.isnan(raw_value) or math.isinf(raw_value))
            value = raw_value if value_is_finite else None

            yield CreditEventRecord(
                frame_idx=frame_idx,
                entity_id_be=entity_id_be,
                action=action,
                value=value,
                file_offset=pos,
                raw_record_hex=data[pos:pos + 12].hex(),
                padding_ok=True,
                value_is_finite=value_is_finite,
            )
            pos += 1


def collect_credit_events_by_entity(replay_file: str) -> Dict[int, List[CreditEventRecord]]:
    """Collect credit events grouped by BE entity id."""
    grouped: Dict[int, List[CreditEventRecord]] = defaultdict(list)
    for event in iter_credit_events(replay_file):
        grouped[event.entity_id_be].append(event)
    return grouped
