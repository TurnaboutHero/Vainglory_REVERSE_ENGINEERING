#!/usr/bin/env python3
"""
Baron Anomaly Investigation - Why Only Baron Shows 0x29 Events?

Critical finding: Baron (57605) has 6 player-sourced 0x29 events matching 6 kills.
But ALL other players have 0 player-sourced 0x29 events despite having kills.

Hypothesis: The 0x29 "kill signature" was a false positive. Baron's 6 events
are NOT kill events - they're something else (maybe a hero-specific ability).

This script investigates:
1. What are the 6 Baron 0x29 events? (timestamps, payloads, context)
2. Do other heroes have alternative action codes for kills?
3. Is there a different event pattern that correlates with kills?
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def analyze_baron_events(replay_dir: str):
    """Deep dive into Baron's 0x29 events."""

    replay_path = Path(replay_dir)
    vgr_files = sorted(replay_path.glob('*.vgr'), key=lambda p: int(p.stem.split('.')[-1]))

    print("[OBJECTIVE] Investigate Baron 0x29 anomaly")
    print(f"[DATA] Replay: {replay_dir}")

    # Extract player entities
    parser = VGRParser(str(replay_dir))
    data = parser.parse()
    all_players = data['teams']['left'] + data['teams']['right']

    player_entities = {}
    baron_id = None

    for player in all_players:
        entity_id = player.get('entity_id')
        if entity_id:
            hero = player.get('hero_name', 'Unknown')
            player_entities[entity_id] = hero
            if hero == 'Baron':
                baron_id = entity_id

    print(f"\n[DATA] Player entities:")
    for eid, hero in sorted(player_entities.items()):
        print(f"  {eid}: {hero}")

    if not baron_id:
        print("[ERROR] Baron not found!")
        return

    print(f"\n[DATA] Baron entity ID: {baron_id}")

    # Collect ALL events for all players
    player_events_by_code = defaultdict(lambda: defaultdict(list))  # entity_id -> action_code -> [events]
    baron_0x29_events = []

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

                if entity_id in player_entities:
                    event = {
                        'frame': frame_num,
                        'action_code': action_code,
                        'payload_hex': payload.hex(),
                    }
                    player_events_by_code[entity_id][action_code].append(event)

                    # Collect Baron's 0x29 events specifically
                    if entity_id == baron_id and action_code == 0x29:
                        baron_0x29_events.append(event)

                offset += 37
            else:
                offset += 1

    # Analysis 1: Baron's 0x29 events
    print(f"\n[FINDING] Baron's 0x29 events (should be 6):")
    print(f"  Total count: {len(baron_0x29_events)}")

    if baron_0x29_events:
        print(f"\n  Detailed breakdown:")
        print(f"  {'Frame':>6s} {'Payload (first 16 bytes)':40s}")
        for evt in baron_0x29_events:
            payload_preview = evt['payload_hex'][:32]
            print(f"  {evt['frame']:6d} {payload_preview}")

    # Analysis 2: What action codes do OTHER high-kill players use?
    print(f"\n[FINDING] Action code distribution for high-kill heroes:")

    # Known kills: Petal(3), Caine(3), Phinn(2), Yates(1), Amael(0)
    high_kill_heroes = {
        'Petal': 3,
        'Caine': 3,
        'Phinn': 2,
        'Yates': 1,
    }

    for entity_id, hero in sorted(player_entities.items()):
        if hero in high_kill_heroes:
            print(f"\n  {hero} (entity {entity_id}, {high_kill_heroes[hero]} kills):")

            # Get top 10 action codes
            all_codes = player_events_by_code[entity_id]
            code_counts = {code: len(events) for code, events in all_codes.items()}
            top_codes = sorted(code_counts.items(), key=lambda x: x[1], reverse=True)[:10]

            for code, count in top_codes:
                print(f"    0x{code:02X}: {count:4d} events")

    # Analysis 3: Compare Baron's action code distribution
    print(f"\n[FINDING] Baron's action code distribution:")
    baron_codes = player_events_by_code[baron_id]
    baron_code_counts = {code: len(events) for code, events in baron_codes.items()}
    baron_top = sorted(baron_code_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    for code, count in baron_top:
        print(f"  0x{code:02X}: {count:4d} events")

    # Analysis 4: Find codes that appear ONLY in Baron
    print(f"\n[FINDING] Action codes unique to Baron (vs other players):")

    all_other_codes = set()
    for entity_id, hero in player_entities.items():
        if entity_id != baron_id:
            all_other_codes.update(player_events_by_code[entity_id].keys())

    baron_only_codes = set(baron_codes.keys()) - all_other_codes

    if baron_only_codes:
        print(f"  Baron-only codes: {', '.join(f'0x{c:02X}' for c in sorted(baron_only_codes))}")
    else:
        print(f"  No Baron-exclusive codes found")

    # Analysis 5: Cross-player code comparison
    print(f"\n[FINDING] Action codes shared by all high-kill players:")

    high_kill_entity_ids = [eid for eid, hero in player_entities.items() if hero in high_kill_heroes or hero == 'Baron']

    if high_kill_entity_ids:
        common_codes = set(player_events_by_code[high_kill_entity_ids[0]].keys())
        for entity_id in high_kill_entity_ids[1:]:
            common_codes &= set(player_events_by_code[entity_id].keys())

        print(f"  Common codes: {', '.join(f'0x{c:02X}' for c in sorted(common_codes)[:20])}")

    # Generate report
    output_dir = Path("vg/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    report = {
        'baron_entity_id': baron_id,
        'baron_0x29_count': len(baron_0x29_events),
        'baron_0x29_frames': [evt['frame'] for evt in baron_0x29_events],
        'baron_top_codes': dict(baron_top),
        'other_heroes_0x29_count': {
            hero: len(player_events_by_code[eid][0x29])
            for eid, hero in player_entities.items()
            if eid != baron_id
        },
    }

    json_path = output_dir / 'baron_anomaly_investigation.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2)

    print(f"\n[FINDING] Report saved to {json_path}")

    print("\n[LIMITATION] 0x29 kill signature INVALIDATED - Baron match was coincidence")
    print("[LIMITATION] Need alternative approach to detect kills")


if __name__ == "__main__":
    replay_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    analyze_baron_events(replay_dir)
