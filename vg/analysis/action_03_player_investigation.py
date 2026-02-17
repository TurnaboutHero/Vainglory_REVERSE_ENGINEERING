#!/usr/bin/env python3
"""
Action 0x03 Player Investigation - Why does it only affect 1 player?
"""

import sys
from pathlib import Path
import struct
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Match 1 with action 0x03
    match = truth_data['matches'][0]
    replay_path = Path(match['replay_file'])

    print("[OBJECTIVE] Identify which player receives action 0x03 events")
    print(f"[DATA] Match: {replay_path.name}")
    print()

    # Load decoder
    decoder = UnifiedDecoder(str(replay_path))
    decoded = decoder.decode()

    print("[DATA] Player roster:")
    for p in decoded.all_players:
        print(f"  Entity {p.entity_id} (BE: {_le_to_be(p.entity_id)}): {p.name} - {p.hero_name} - Team {p.team}")
    print()

    player_eids_be = {_le_to_be(p.entity_id) for p in decoded.all_players}

    # Load binary
    with open(replay_path, 'rb') as f:
        data = f.read()

    # Extract action 0x03 credits
    CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
    action_03_events = []

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == CREDIT_HEADER:
            eid_be = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            if action == 0x03:
                action_03_events.append({
                    'offset': i,
                    'eid_be': eid_be,
                    'value': round(value, 2),
                    'is_player': eid_be in player_eids_be
                })

            i += 12
        else:
            i += 1

    print(f"[DATA] Total action 0x03 events: {len(action_03_events)}")
    print()

    # Group by entity ID
    from collections import Counter
    eid_distribution = Counter([e['eid_be'] for e in action_03_events])

    print("[FINDING] Entity ID distribution for action 0x03:")
    for eid, count in eid_distribution.most_common():
        is_player = eid in player_eids_be
        # Find player name if applicable
        player_name = "Unknown"
        if is_player:
            for p in decoded.all_players:
                if _le_to_be(p.entity_id) == eid:
                    player_name = f"{p.name} ({p.hero_name})"
                    break

        print(f"  Entity {eid}: {count} events - {'PLAYER: ' + player_name if is_player else 'NON-PLAYER'}")

    print()
    print("[FINDING] First 10 action 0x03 events:")
    for e in action_03_events[:10]:
        is_player = e['eid_be'] in player_eids_be
        print(f"  Offset {e['offset']:7d}: Entity {e['eid_be']:5d}, Value {e['value']}, Player: {is_player}")

    print()
    print("[LIMITATION] If entity is non-player, action 0x03 may be for objectives/turrets/observers")


if __name__ == '__main__':
    main()
