#!/usr/bin/env python3
"""
Universal KDA Decoder - Final Analysis

CRITICAL BREAKTHROUGH:
- 0x29 is Baron-specific ability, NOT kill signature
- 0x00 and 0x05 are universal across all high-kill players
- Hypothesis: 0x00 or 0x05 contain kill/death information in payload

Strategy:
1. Count 0x00 and 0x05 events per player
2. Compare counts to truth K/D/A
3. Analyze payload structure for victim/killer encoding
4. Check if count correlates with kills, deaths, assists, or K+D+A
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


TRUTH_KDA = {
    'Baron': {'K': 6, 'D': 2, 'A': 4, 'KDA': 12},
    'Petal': {'K': 3, 'D': 2, 'A': 4, 'KDA': 9},
    'Phinn': {'K': 2, 'D': 0, 'A': 8, 'KDA': 10},
    'Caine': {'K': 3, 'D': 4, 'A': 1, 'KDA': 8},
    'Yates': {'K': 1, 'D': 4, 'A': 2, 'KDA': 7},
    'Amael': {'K': 0, 'D': 3, 'A': 4, 'KDA': 7},
}


def analyze_universal_codes(replay_dir: str):
    """Analyze 0x00 and 0x05 events for KDA correlation."""

    replay_path = Path(replay_dir)
    vgr_files = sorted(replay_path.glob('*.vgr'), key=lambda p: int(p.stem.split('.')[-1]))

    print("[OBJECTIVE] Decode kills/deaths from universal action codes 0x00 and 0x05")
    print(f"[DATA] Replay: {replay_dir}")

    # Extract players
    parser = VGRParser(str(replay_dir))
    data = parser.parse()
    all_players = data['teams']['left'] + data['teams']['right']

    player_map = {}  # entity_id -> hero_name
    for player in all_players:
        entity_id = player.get('entity_id')
        if entity_id:
            hero = player.get('hero_name', 'Unknown')
            player_map[entity_id] = hero

    # Count events per player per code
    event_counts = defaultdict(lambda: defaultdict(int))  # entity_id -> action_code -> count

    # Collect events with player references in payload
    events_with_players = defaultdict(list)  # action_code -> [events]

    for vgr_file in vgr_files:
        frame_num = int(vgr_file.stem.split('.')[-1])
        frame_data = vgr_file.read_bytes()
        offset = 0

        while offset + 37 <= len(frame_data):
            entity_id = struct.unpack('<H', frame_data[offset:offset+2])[0]
            marker = frame_data[offset+2:offset+4]

            if marker == b'\x00\x00':
                action_code = frame_data[offset+4]
                payload = frame_data[offset+5:offset+37]

                # Count events for player entities
                if entity_id in player_map:
                    event_counts[entity_id][action_code] += 1

                # Check for player references in payload
                if action_code in [0x00, 0x05]:
                    player_refs = []
                    for i in range(0, 31, 2):
                        val = struct.unpack('<H', payload[i:i+2])[0]
                        if val in player_map:
                            player_refs.append((i, val))

                    if player_refs:
                        events_with_players[action_code].append({
                            'frame': frame_num,
                            'source': entity_id,
                            'player_refs': player_refs,
                            'payload_hex': payload.hex(),
                        })

                offset += 37
            else:
                offset += 1

    # Analysis: Compare counts to truth KDA
    print(f"\n[FINDING] Event counts vs Truth KDA:")
    print(f"{'Hero':>10s} {'K':>3s} {'D':>3s} {'A':>3s} {'KDA':>4s} | {'0x00':>5s} {'0x05':>5s} {'0x29':>5s} | Best Match")

    for entity_id in sorted(player_map.keys()):
        hero = player_map[entity_id]
        truth = TRUTH_KDA.get(hero, {})

        k = truth.get('K', 0)
        d = truth.get('D', 0)
        a = truth.get('A', 0)
        kda = truth.get('KDA', 0)

        count_00 = event_counts[entity_id][0x00]
        count_05 = event_counts[entity_id][0x05]
        count_29 = event_counts[entity_id][0x29]

        # Find best match
        matches = []
        if count_00 == k:
            matches.append("0x00=K")
        if count_05 == k:
            matches.append("0x05=K")
        if count_00 == d:
            matches.append("0x00=D")
        if count_05 == d:
            matches.append("0x05=D")
        if count_00 == a:
            matches.append("0x00=A")
        if count_05 == a:
            matches.append("0x05=A")
        if count_00 == kda:
            matches.append("0x00=KDA")
        if count_05 == kda:
            matches.append("0x05=KDA")

        match_str = ", ".join(matches) if matches else "-"

        print(f"{hero:>10s} {k:3d} {d:3d} {a:3d} {kda:4d} | {count_00:5d} {count_05:5d} {count_29:5d} | {match_str}")

    # Payload analysis
    print(f"\n[FINDING] Player references in 0x00 payloads: {len(events_with_players[0x00])}")
    print(f"[FINDING] Player references in 0x05 payloads: {len(events_with_players[0x05])}")

    # Sample 0x00 events with player refs
    if events_with_players[0x00]:
        print(f"\n[FINDING] Sample 0x00 events with player references (first 5):")
        for evt in events_with_players[0x00][:5]:
            source_hero = player_map.get(evt['source'], 'Unknown')
            refs = []
            for offset, player_id in evt['player_refs']:
                ref_hero = player_map.get(player_id, 'Unknown')
                refs.append(f"@{offset}:{ref_hero}")
            refs_str = ", ".join(refs)
            print(f"  Frame {evt['frame']:3d}: {source_hero:>10s} -> [{refs_str}]")

    # Sample 0x05 events with player refs
    if events_with_players[0x05]:
        print(f"\n[FINDING] Sample 0x05 events with player references (first 5):")
        for evt in events_with_players[0x05][:5]:
            source_hero = player_map.get(evt['source'], 'Unknown')
            refs = []
            for offset, player_id in evt['player_refs']:
                ref_hero = player_map.get(player_id, 'Unknown')
                refs.append(f"@{offset}:{ref_hero}")
            refs_str = ", ".join(refs)
            print(f"  Frame {evt['frame']:3d}: {source_hero:>10s} -> [{refs_str}]")

    # Save results
    output_dir = Path("vg/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        'event_counts': {
            player_map[eid]: {
                '0x00': event_counts[eid][0x00],
                '0x05': event_counts[eid][0x05],
                '0x29': event_counts[eid][0x29],
            }
            for eid in player_map.keys()
        },
        'truth_kda': TRUTH_KDA,
        '0x00_with_player_refs': len(events_with_players[0x00]),
        '0x05_with_player_refs': len(events_with_players[0x05]),
    }

    json_path = output_dir / 'universal_kda_analysis.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n[FINDING] Analysis saved to {json_path}")


if __name__ == "__main__":
    replay_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    analyze_universal_codes(replay_dir)
