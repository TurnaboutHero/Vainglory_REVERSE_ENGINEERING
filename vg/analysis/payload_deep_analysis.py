#!/usr/bin/env python3
"""
Payload Deep Analysis - Phase 2.1
각 액션 코드의 페이로드 내 오프셋별 값과 K/D/A 상관관계 분석
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple
import struct

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data() -> Dict:
    """Load tournament truth data."""
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_events_for_entity(replay_dir: Path, replay_name: str, entity_id: int) -> List[Dict]:
    """Extract all events for a specific entity with full payload."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    events = []
    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        idx = 0

        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break

            if idx + 5 <= len(data):
                action = data[idx + 4]
                # Extract up to 32 bytes of payload
                payload_end = min(idx + 36, len(data))
                payload = data[idx + 5:payload_end]

                events.append({
                    'frame': frame_num,
                    'offset': idx,
                    'action': action,
                    'payload': payload.hex(),
                    'payload_bytes': list(payload)
                })
            idx += 1

    return events


def analyze_payload_patterns(events: List[Dict], stat_value: int, stat_name: str) -> Dict:
    """
    Analyze if any payload offset contains a value matching the stat.
    Look for:
    1. Direct byte match
    2. Cumulative count at specific offset
    3. Little-endian 2-byte value
    """
    results = {
        'stat_name': stat_name,
        'stat_value': stat_value,
        'matches': []
    }

    if stat_value == 0:
        return results

    # Group events by action code
    by_action = defaultdict(list)
    for e in events:
        by_action[e['action']].append(e['payload_bytes'])

    for action, payloads in by_action.items():
        if len(payloads) < 1:
            continue

        # Check each offset position
        max_len = max(len(p) for p in payloads)

        for offset in range(min(max_len, 20)):  # Check first 20 bytes
            # Method 1: Count how many times stat_value appears at this offset
            direct_matches = sum(1 for p in payloads if len(p) > offset and p[offset] == stat_value)

            # Method 2: Check if the last payload has the stat_value (cumulative)
            if payloads and len(payloads[-1]) > offset:
                last_value = payloads[-1][offset]
                if last_value == stat_value:
                    results['matches'].append({
                        'action': action,
                        'offset': offset,
                        'type': 'cumulative_byte',
                        'last_value': last_value
                    })

            # Method 3: Check 2-byte little-endian at this offset
            if payloads and len(payloads[-1]) > offset + 1:
                last_2byte = payloads[-1][offset] | (payloads[-1][offset + 1] << 8)
                if last_2byte == stat_value:
                    results['matches'].append({
                        'action': action,
                        'offset': offset,
                        'type': 'cumulative_2byte_le',
                        'last_value': last_2byte
                    })

            # Method 4: Count of events equals stat_value
            if len(payloads) == stat_value:
                results['matches'].append({
                    'action': action,
                    'offset': -1,  # N/A - event count itself
                    'type': 'event_count',
                    'count': len(payloads)
                })

    return results


def find_cross_entity_patterns(replay_dir: Path, replay_name: str,
                                killer_entity: int, victim_entity: int,
                                victim_deaths: int) -> List[Dict]:
    """
    Find events where killer and victim entity IDs appear together.
    This might indicate kill/death relationship.
    """
    patterns = []

    killer_bytes = killer_entity.to_bytes(2, 'little')
    victim_bytes = victim_entity.to_bytes(2, 'little')

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        # Look for victim entity pattern
        victim_pattern = victim_bytes + b'\x00\x00'
        idx = 0

        while True:
            idx = data.find(victim_pattern, idx)
            if idx == -1:
                break

            if idx + 36 <= len(data):
                action = data[idx + 4]
                payload = data[idx + 5:idx + 36]

                # Check if killer entity ID appears in payload
                killer_pos = payload.find(killer_bytes)
                if killer_pos != -1:
                    patterns.append({
                        'frame': frame_num,
                        'victim_entity': victim_entity,
                        'killer_entity': killer_entity,
                        'action': action,
                        'killer_offset_in_payload': killer_pos,
                        'payload': payload.hex()
                    })
            idx += 1

    return patterns


def main():
    print("=" * 60)
    print("Payload Deep Analysis - K/D/A Pattern Search")
    print("=" * 60)
    print()

    truth = load_truth_data()

    # Collect all player data with entity IDs
    all_players = []

    for match in truth['matches']:
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"Processing: {replay_name[:40]}...")

        # Parse replay to get entity IDs
        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        # Build entity to player mapping
        entity_to_player = {}
        player_to_entity = {}

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if entity_id and truth_player:
                    entity_to_player[entity_id] = {
                        'name': player_name,
                        'team': team,
                        'kills': truth_player.get('kills', 0),
                        'deaths': truth_player.get('deaths', 0),
                        'assists': truth_player.get('assists', 0)
                    }
                    player_to_entity[player_name] = entity_id

                    all_players.append({
                        'replay_name': replay_name,
                        'replay_dir': replay_dir,
                        'player_name': player_name,
                        'entity_id': entity_id,
                        'team': team,
                        'kills': truth_player.get('kills', 0),
                        'deaths': truth_player.get('deaths', 0),
                        'assists': truth_player.get('assists', 0),
                        'entity_to_player': entity_to_player,
                        'player_to_entity': player_to_entity
                    })

    print(f"\nTotal players with entity IDs: {len(all_players)}")
    print()

    # Analysis 1: Find payload offset patterns matching K/D/A
    print("=" * 60)
    print("Analysis 1: Payload Offset Patterns")
    print("=" * 60)

    offset_matches = defaultdict(lambda: {'kills': 0, 'deaths': 0, 'assists': 0})

    for player in all_players[:20]:  # Sample first 20 for speed
        events = extract_events_for_entity(
            player['replay_dir'],
            player['replay_name'],
            player['entity_id']
        )

        for stat_name in ['kills', 'deaths', 'assists']:
            stat_value = player[stat_name]
            if stat_value == 0:
                continue

            result = analyze_payload_patterns(events, stat_value, stat_name)

            for m in result['matches']:
                key = (m['action'], m['offset'], m['type'])
                offset_matches[key][stat_name] += 1

    # Report findings
    print("\nPayload patterns that matched stats (action, offset, type):")
    sorted_matches = sorted(offset_matches.items(), key=lambda x: sum(x[1].values()), reverse=True)

    for (action, offset, match_type), counts in sorted_matches[:30]:
        total = sum(counts.values())
        print(f"  0x{action:02X} offset={offset:2d} type={match_type:20s} | K:{counts['kills']:2d} D:{counts['deaths']:2d} A:{counts['assists']:2d} | Total:{total}")

    print()

    # Analysis 2: Cross-entity patterns (killer-victim relationships)
    print("=" * 60)
    print("Analysis 2: Cross-Entity Kill Patterns")
    print("=" * 60)

    cross_patterns = defaultdict(int)

    for player in all_players:
        if player['deaths'] == 0:
            continue

        victim_entity = player['entity_id']
        victim_team = player['team']

        # Find potential killers (opposite team)
        for other in all_players:
            if other['replay_name'] != player['replay_name']:
                continue
            if other['team'] == victim_team:
                continue
            if other['kills'] == 0:
                continue

            killer_entity = other['entity_id']

            patterns = find_cross_entity_patterns(
                player['replay_dir'],
                player['replay_name'],
                killer_entity,
                victim_entity,
                player['deaths']
            )

            for p in patterns:
                key = (p['action'], p['killer_offset_in_payload'])
                cross_patterns[key] += 1

    print("\nCross-entity patterns (victim event with killer ID in payload):")
    sorted_cross = sorted(cross_patterns.items(), key=lambda x: x[1], reverse=True)

    for (action, offset), count in sorted_cross[:20]:
        print(f"  Action 0x{action:02X}, killer at payload offset {offset}: {count} occurrences")

    print()

    # Analysis 3: Event count correlation
    print("=" * 60)
    print("Analysis 3: Event Count Exact Matches")
    print("=" * 60)

    event_count_matches = defaultdict(lambda: {'kills': 0, 'deaths': 0, 'assists': 0, 'total_checked': 0})

    for player in all_players:
        events = extract_events_for_entity(
            player['replay_dir'],
            player['replay_name'],
            player['entity_id']
        )

        # Count by action
        action_counts = defaultdict(int)
        for e in events:
            action_counts[e['action']] += 1

        for action, count in action_counts.items():
            event_count_matches[action]['total_checked'] += 1

            if count == player['kills'] and player['kills'] > 0:
                event_count_matches[action]['kills'] += 1
            if count == player['deaths'] and player['deaths'] > 0:
                event_count_matches[action]['deaths'] += 1
            if count == player['assists'] and player['assists'] > 0:
                event_count_matches[action]['assists'] += 1

    print("\nAction codes with event count matching stats:")

    for action in sorted(event_count_matches.keys()):
        m = event_count_matches[action]
        if m['kills'] > 0 or m['deaths'] > 0 or m['assists'] > 0:
            total_matches = m['kills'] + m['deaths'] + m['assists']
            print(f"  0x{action:02X}: K={m['kills']:2d} D={m['deaths']:2d} A={m['assists']:2d} (checked {m['total_checked']} players)")

    print()
    print("=" * 60)
    print("Analysis Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
