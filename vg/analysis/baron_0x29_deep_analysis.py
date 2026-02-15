#!/usr/bin/env python3
"""
Baron 0x29 Event Deep Analysis
Investigate the anomalous 100% correlation between Baron's 0x29 events and kills.

Research Questions:
1. Is 0x29 Baron-specific (hero ability code) or a universal kill event?
2. Do other heroes have different action codes for their abilities?
3. Is the 6 kills = 6 0x29 match coincidental or causal?
4. Does Baron in other replays also show 0x29 events?
"""

import sys
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_parser import VGRParser


def read_all_frames(replay_dir: Path) -> bytes:
    """Read all .vgr frames in order."""
    frames = list(replay_dir.glob("*.vgr"))
    def frame_index(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0
    frames.sort(key=frame_index)
    return b"".join(f.read_bytes() for f in frames)


def find_0x29_events(data: bytes, entity_id: int) -> List[Dict]:
    """Find all 0x29 action events from a specific entity.

    Event format: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]
    """
    pattern = entity_id.to_bytes(2, 'little') + b'\x00\x00\x29'
    events = []
    idx = 0

    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break

        # Extract full event (assuming ~37 bytes total)
        event_start = idx
        event_end = min(idx + 37, len(data))
        event_bytes = data[event_start:event_end]

        events.append({
            'offset': idx,
            'entity_id': entity_id,
            'action_code': 0x29,
            'payload_hex': event_bytes[5:].hex(),  # After [ID][00 00][29]
            'full_hex': event_bytes.hex()
        })

        idx += 1

    return events


def count_0x29_by_source_range(data: bytes) -> Dict[str, int]:
    """Count 0x29 events by entity ID range."""
    ranges = {
        'system': (0, 1),           # ID 0
        'infrastructure': (1, 1000),    # 1-999
        'turrets': (1000, 20000),       # 1000-19999
        'minions': (20000, 50000),      # 20000-49999
        'players': (50000, 60000),      # 50000-59999
        'other': (60000, 70000)         # 60000+
    }

    counts = defaultdict(int)
    action_pattern = b'\x00\x00\x29'  # [00 00][0x29]

    idx = 0
    while True:
        idx = data.find(action_pattern, idx)
        if idx == -1:
            break

        # Entity ID is 2 bytes before the action pattern
        if idx >= 2:
            entity_id = int.from_bytes(data[idx-2:idx], 'little')

            # Categorize by range
            categorized = False
            for range_name, (min_id, max_id) in ranges.items():
                if min_id <= entity_id < max_id:
                    counts[range_name] += 1
                    categorized = True
                    break

            if not categorized:
                counts['unknown'] += 1

        idx += 1

    return dict(counts)


def scan_all_player_events(data: bytes, player_entity_ids: List[int]) -> Dict[int, Dict[str, int]]:
    """Scan all action codes for each player entity."""
    player_events = {}

    for entity_id in player_entity_ids:
        base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
        counts = Counter()

        idx = 0
        while True:
            idx = data.find(base, idx)
            if idx == -1:
                break
            if idx + 4 < len(data):
                action_code = data[idx + 4]
                counts[action_code] += 1
            idx += 1

        player_events[entity_id] = {f"0x{act:02X}": cnt for act, cnt in counts.items() if cnt > 0}

    return player_events


def estimate_frame_from_offset(offset: int, avg_frame_size: int = 75000) -> int:
    """Rough estimate of frame number from byte offset."""
    return offset // avg_frame_size


def analyze_replay(replay_path: str, replay_name: str, truth_data: Dict) -> Dict:
    """Analyze a single replay for Baron 0x29 patterns."""
    print(f"\n{'='*80}")
    print(f"ANALYZING: {replay_name}")
    print(f"{'='*80}")

    replay_dir = Path(replay_path)

    # Parse replay metadata
    parser = VGRParser(replay_path, auto_truth=False)
    parsed = parser.parse()

    # Read all frame data
    all_data = read_all_frames(replay_dir)
    total_size = len(all_data)
    print(f"[DATA] Total replay size: {total_size:,} bytes ({len(list(replay_dir.glob('*.vgr')))} frames)")

    # Extract player entity IDs
    players = []
    for team in ['left', 'right']:
        for p in parsed['teams'][team]:
            if p['entity_id']:
                players.append({
                    'name': p['name'],
                    'entity_id': p['entity_id'],
                    'hero_name': p.get('hero_name', 'Unknown'),
                    'kills': truth_data['players'].get(p['name'], {}).get('kills', 0),
                    'deaths': truth_data['players'].get(p['name'], {}).get('deaths', 0)
                })

    print(f"\n[DATA] Players in replay:")
    for p in players:
        print(f"  {p['name']:15s} | Entity {p['entity_id']:5d} | {p['hero_name']:15s} | {p['kills']}K/{p['deaths']}D")

    # 1. Count 0x29 by source range
    print(f"\n{'='*80}")
    print("TASK 1: Count 0x29 events by entity source range")
    print(f"{'='*80}")
    range_counts = count_0x29_by_source_range(all_data)
    print("[STAT:0x29_total_count]", sum(range_counts.values()))
    for range_name, count in sorted(range_counts.items()):
        print(f"[STAT:0x29_{range_name}]", count)

    # 2. Find all player-sourced 0x29 events
    print(f"\n{'='*80}")
    print("TASK 2: Player-sourced 0x29 events (detailed)")
    print(f"{'='*80}")

    player_0x29_events = {}
    for p in players:
        events = find_0x29_events(all_data, p['entity_id'])
        player_0x29_events[p['entity_id']] = events

        print(f"\n{p['name']:15s} (Entity {p['entity_id']}, {p['hero_name']}, {p['kills']}K/{p['deaths']}D)")
        print(f"  0x29 events: {len(events)}")

        if len(events) > 0:
            print(f"  Event details:")
            for i, evt in enumerate(events, 1):
                frame_est = estimate_frame_from_offset(evt['offset'])
                print(f"    #{i}: Offset {evt['offset']:8d} (~frame {frame_est:3d}) | Payload: {evt['payload_hex'][:64]}")
                if i >= 10:  # Limit to first 10
                    print(f"    ... ({len(events) - 10} more events)")
                    break

    # 3. Compare Baron vs other heroes
    print(f"\n{'='*80}")
    print("TASK 3: Baron comparison - Event volume and action diversity")
    print(f"{'='*80}")

    all_player_events = scan_all_player_events(all_data, [p['entity_id'] for p in players])

    baron_entities = [p for p in players if 'Baron' in p['hero_name']]
    other_entities = [p for p in players if 'Baron' not in p['hero_name']]

    if baron_entities:
        baron = baron_entities[0]
        baron_events = all_player_events.get(baron['entity_id'], {})
        baron_total = sum(baron_events.values())
        baron_0x29_count = baron_events.get('0x29', 0)

        print(f"\nBaron ({baron['name']}, Entity {baron['entity_id']}):")
        print(f"  Total events: {baron_total}")
        print(f"  Unique action codes: {len(baron_events)}")
        print(f"  0x29 events: {baron_0x29_count}")
        print(f"  Top 10 action codes:")
        sorted_actions = sorted(baron_events.items(), key=lambda x: x[1], reverse=True)
        for action, count in sorted_actions[:10]:
            print(f"    {action}: {count}")

    print(f"\nOther heroes:")
    for p in other_entities:
        p_events = all_player_events.get(p['entity_id'], {})
        p_total = sum(p_events.values())
        p_0x29_count = p_events.get('0x29', 0)

        print(f"\n{p['name']:15s} ({p['hero_name']}, Entity {p['entity_id']}):")
        print(f"  Total events: {p_total}")
        print(f"  Unique action codes: {len(p_events)}")
        print(f"  0x29 events: {p_0x29_count}")
        if p_total > 0:
            print(f"  Top 5 action codes:")
            sorted_actions = sorted(p_events.items(), key=lambda x: x[1], reverse=True)
            for action, count in sorted_actions[:5]:
                print(f"    {action}: {count}")

    # 4. Temporal analysis - when do 0x29 events occur?
    print(f"\n{'='*80}")
    print("TASK 4: Temporal distribution of Baron 0x29 events")
    print(f"{'='*80}")

    if baron_entities:
        baron_0x29 = player_0x29_events.get(baron['entity_id'], [])

        if baron_0x29:
            print(f"\nBaron 0x29 event timeline ({len(baron_0x29)} events):")
            for i, evt in enumerate(baron_0x29, 1):
                frame_est = estimate_frame_from_offset(evt['offset'])
                print(f"  Event {i}: Frame ~{frame_est:3d} (offset {evt['offset']:8d})")

            # Check spacing
            if len(baron_0x29) > 1:
                offsets = [evt['offset'] for evt in baron_0x29]
                gaps = [offsets[i+1] - offsets[i] for i in range(len(offsets)-1)]
                avg_gap = sum(gaps) / len(gaps)
                print(f"\n[STAT:baron_0x29_avg_gap] {avg_gap:.0f} bytes (~{avg_gap/75000:.1f} frames)")
                print(f"[FINDING] Baron 0x29 events are {'evenly spaced' if max(gaps)/min(gaps) < 2 else 'irregularly spaced'}")
        else:
            print("[FINDING] Baron has ZERO 0x29 events in this replay")

    # 5. Build summary result
    result = {
        'replay_name': replay_name,
        'replay_path': replay_path,
        'total_bytes': total_size,
        'frame_count': len(list(replay_dir.glob('*.vgr'))),
        '0x29_by_source_range': range_counts,
        'players': []
    }

    for p in players:
        p_events = all_player_events.get(p['entity_id'], {})
        p_0x29 = player_0x29_events.get(p['entity_id'], [])

        result['players'].append({
            'name': p['name'],
            'entity_id': p['entity_id'],
            'hero_name': p['hero_name'],
            'kills': p['kills'],
            'deaths': p['deaths'],
            'total_events': sum(p_events.values()),
            'unique_action_codes': len(p_events),
            '0x29_count': len(p_0x29),
            '0x29_events': p_0x29[:20],  # First 20 events
            'top_action_codes': dict(sorted(p_events.items(), key=lambda x: x[1], reverse=True)[:10])
        })

    return result


def main():
    """Run Baron 0x29 deep analysis on multiple replays."""

    # Replay configurations
    replays = [
        {
            'name': '21.11.04',
            'path': 'D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/',
            'truth': {
                'players': {
                    'RudolfBoy': {'hero_name': 'Baron', 'kills': 6, 'deaths': 2},
                    'GGGilgu': {'hero_name': 'Petal', 'kills': 3, 'deaths': 2},
                    'Sunhyeonsu': {'hero_name': 'Phinn', 'kills': 2, 'deaths': 0},
                    'happywansun7': {'hero_name': 'Caine', 'kills': 3, 'deaths': 4},
                    'KNOXX': {'hero_name': 'Yates', 'kills': 1, 'deaths': 4},
                    'khh5656': {'hero_name': 'Karas', 'kills': 0, 'deaths': 3}
                }
            }
        },
        {
            'name': '21.12.06',
            'path': 'D:/Desktop/My Folder/Game/VG/vg replay/21.12.06/cache/',
            'truth': {
                'players': {
                    'RudolfBoy': {'hero_name': 'Baron', 'kills': 6, 'deaths': 4},
                    'GGGilgu': {'hero_name': 'Petal', 'kills': 2, 'deaths': 5},
                    'Sunhyeonsu': {'hero_name': 'Ardan', 'kills': 0, 'deaths': 2},
                    'happywansun7': {'hero_name': 'Caine', 'kills': 7, 'deaths': 2},
                    'KNOXX': {'hero_name': 'Yates', 'kills': 1, 'deaths': 3},
                    'khh5656': {'hero_name': 'Kinetic', 'kills': 4, 'deaths': 2}
                }
            }
        }
    ]

    all_results = []

    for replay_config in replays:
        result = analyze_replay(
            replay_config['path'],
            replay_config['name'],
            replay_config['truth']
        )
        all_results.append(result)

    # Cross-replay comparison
    print(f"\n\n{'='*80}")
    print("CROSS-REPLAY COMPARISON")
    print(f"{'='*80}")

    print("\nBaron 0x29 events across replays:")
    for result in all_results:
        baron_data = [p for p in result['players'] if 'Baron' in p['hero_name']]
        if baron_data:
            b = baron_data[0]
            print(f"  {result['replay_name']:10s}: {b['0x29_count']:2d} events | {b['kills']}K/{b['deaths']}D")

    print("\n[FINDING] Key observations:")
    print("  1. If Baron has matching 0x29 count in BOTH replays → Hero-specific ability code")
    print("  2. If Baron has 0x29 in one but not other → Coincidental match in 21.11.04")
    print("  3. If other heroes ALSO have 0x29 → Universal action code (not Baron-specific)")

    # Save results
    output_path = Path(__file__).parent.parent / 'output' / 'baron_0x29_investigation.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump({
            'investigation': 'Baron 0x29 Event Deep Analysis',
            'hypothesis': '0x29 may be Baron-specific ability code, not universal kill event',
            'replays_analyzed': len(all_results),
            'results': all_results
        }, f, indent=2)

    print(f"\n[FINDING] Analysis complete. Results saved to {output_path}")
    print(f"[STAT:replays_analyzed] {len(all_results)}")


if __name__ == '__main__':
    main()
