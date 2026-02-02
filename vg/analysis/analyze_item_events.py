#!/usr/bin/env python3
"""
Analyze potential item purchase events (0x02).
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data():
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_0x02_events(replay_dir: Path, replay_name: str, entity_id: int) -> list:
    """Extract all 0x02 events for an entity."""
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

            if idx + 36 <= len(data):
                action = data[idx + 4]
                if action == 0x02:
                    payload = list(data[idx + 5:idx + 25])
                    events.append({
                        'frame': frame_num,
                        'payload': payload
                    })
            idx += 1

    return events


def main():
    print("=" * 70)
    print("Analyzing 0x02 Events (Potential Item Purchase)")
    print("=" * 70)
    print()

    truth = load_truth_data()
    match = truth['matches'][0]

    replay_file = match['replay_file']
    replay_dir = Path(replay_file).parent
    replay_name = match['replay_name']

    print(f"Match: {replay_name[:50]}...")
    print()

    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()

    # Analyze 0x02 for each player
    for team in ('left', 'right'):
        print(f"\n=== Team: {team} ===")
        for player in parsed['teams'][team]:
            entity_id = player.get('entity_id')
            player_name = player['name']

            if not entity_id:
                continue

            events = extract_0x02_events(replay_dir, replay_name, entity_id)

            print(f"\n{player_name} ({len(events)} events):")

            # Group by frame
            by_frame = defaultdict(list)
            for e in events:
                by_frame[e['frame']].append(e['payload'])

            for frame, payloads in sorted(by_frame.items())[:5]:  # First 5 frames
                print(f"  Frame {frame}:")
                for p in payloads:
                    # Look for potential item ID (might be in first few bytes)
                    print(f"    {p[:10]}")

    # Compare payload patterns
    print("\n" + "=" * 70)
    print("Looking for Item ID Pattern")
    print("=" * 70)

    # Collect all unique byte values at each offset
    all_events = []
    for team in ('left', 'right'):
        for player in parsed['teams'][team]:
            entity_id = player.get('entity_id')
            if not entity_id:
                continue
            events = extract_0x02_events(replay_dir, replay_name, entity_id)
            all_events.extend(events)

    print(f"\nTotal 0x02 events: {len(all_events)}")

    # Analyze byte patterns
    if all_events:
        print("\nByte values at each offset:")
        for offset in range(10):
            values = set()
            for e in all_events:
                if offset < len(e['payload']):
                    values.add(e['payload'][offset])
            print(f"  Offset {offset}: {len(values)} unique values - {sorted(values)[:10]}...")


if __name__ == "__main__":
    main()
