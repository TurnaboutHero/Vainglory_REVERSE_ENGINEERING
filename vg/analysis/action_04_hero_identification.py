#!/usr/bin/env python3
"""
Action 0x04 Hero Identification - Which hero generates action 0x04?
"""

import sys
from pathlib import Path
import struct
import json
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Match 2 with action 0x04
    match = truth_data['matches'][1]
    replay_path = Path(match['replay_file'])

    print("[OBJECTIVE] Identify which hero/player generates action 0x04 events")
    print(f"[DATA] Match: {replay_path.name}")
    print()

    # Load decoder
    decoder = UnifiedDecoder(str(replay_path))
    decoded = decoder.decode()

    print("[DATA] Player roster:")
    for p in decoded.all_players:
        print(f"  Entity {p.entity_id} (BE: {_le_to_be(p.entity_id)}): {p.name:20s} - {p.hero_name:15s} - Team {p.team}")
    print()

    player_eids_be = {_le_to_be(p.entity_id) for p in decoded.all_players}

    # Load binary
    with open(replay_path, 'rb') as f:
        data = f.read()

    # Extract action 0x04 credits
    CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
    action_04_events = []

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == CREDIT_HEADER:
            eid_be = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            if action == 0x04:
                action_04_events.append({
                    'offset': i,
                    'eid_be': eid_be,
                    'value': round(value, 2),
                    'is_player': eid_be in player_eids_be
                })

            i += 12
        else:
            i += 1

    print(f"[DATA] Total action 0x04 events: {len(action_04_events)}")
    print()

    # Group by entity ID
    eid_distribution = Counter([e['eid_be'] for e in action_04_events])

    print("[FINDING] Entity ID distribution for action 0x04:")
    for eid, count in eid_distribution.most_common():
        is_player = eid in player_eids_be
        # Find player name if applicable
        player_info = "NON-PLAYER"
        if is_player:
            for p in decoded.all_players:
                if _le_to_be(p.entity_id) == eid:
                    player_info = f"PLAYER: {p.name:20s} ({p.hero_name})"
                    break

        print(f"  Entity {eid:5d}: {count:3d} events - {player_info}")

    print()

    # Value distribution
    value_dist = Counter([e['value'] for e in action_04_events])
    print("[FINDING] Value distribution for action 0x04:")
    for value, count in value_dist.most_common(10):
        print(f"  {value:8.2f}: {count} events")

    print()
    print("[FINDING] Comparison to Match 1 (action 0x03 = Blackfeather):")
    print("  Match 1: 2604_Ray - Blackfeather - 169 events (value=1.0)")
    print(f"  Match 2: action 0x04 - [see above]")


if __name__ == '__main__':
    main()
