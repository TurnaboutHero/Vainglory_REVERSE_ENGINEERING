"""Low-level player block parsing for decoder_v2."""

from __future__ import annotations

from typing import Iterable, List

from .models import PlayerBlockRecord


PLAYER_BLOCK_MARKERS = (b"\xDA\x03\xEE", b"\xE0\x03\xEE")


def iter_player_blocks(data: bytes) -> Iterable[PlayerBlockRecord]:
    """Yield player block records in on-disk order."""
    seen_names = set()
    search_start = 0

    while True:
        pos = -1
        marker = None
        for candidate in PLAYER_BLOCK_MARKERS:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        name = ""
        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode("ascii")
            except UnicodeDecodeError:
                name = ""

        if len(name) >= 3 and not name.startswith("GameMode") and name not in seen_names:
            seen_names.add(name)
            entity_id = None
            hero_id = None
            hero_hash_hex = None
            team_byte = None

            if pos + 0xA7 <= len(data):
                entity_id = int.from_bytes(data[pos + 0xA5:pos + 0xA7], "little")
            if pos + 0xAB <= len(data):
                hero_id = int.from_bytes(data[pos + 0xA9:pos + 0xAB], "little")
            if pos + 0xAF <= len(data):
                hero_hash_hex = data[pos + 0xAB:pos + 0xAF].hex()
            if pos + 0xD5 < len(data):
                team_byte = data[pos + 0xD5]

            yield PlayerBlockRecord(
                name=name,
                marker_offset=pos,
                marker_hex=marker.hex(" "),
                entity_id_le=entity_id,
                hero_id_le=hero_id,
                hero_hash_hex=hero_hash_hex,
                team_byte=team_byte,
            )

        search_start = pos + 1


def parse_player_blocks(data: bytes) -> List[PlayerBlockRecord]:
    """Parse all player blocks into a list."""
    return list(iter_player_blocks(data))
