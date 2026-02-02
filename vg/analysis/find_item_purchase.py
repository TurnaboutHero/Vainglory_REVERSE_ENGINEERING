#!/usr/bin/env python3
"""
Find Item Purchase Events
아이템 구매 이벤트 탐색
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data():
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_unique_events_early_game(replay_dir: Path, replay_name: str, entity_id: int) -> dict:
    """
    Find events in early frames (when items are typically purchased).
    게임 초반 프레임에서 발생하는 이벤트 찾기 (아이템 구매 시점)
    """
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    events_by_frame = defaultdict(list)

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    # Focus on first 10 frames (early game, item shop)
    for frame_path in frame_files[:15]:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        idx = 0

        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break

            if idx + 36 <= len(data):
                action = data[idx + 4]
                payload = data[idx + 5:idx + 36]

                events_by_frame[frame_num].append({
                    'action': action,
                    'payload': payload.hex(),
                    'payload_bytes': list(payload[:20])
                })
            idx += 1

    return events_by_frame


def analyze_ringo_test():
    """Analyze Ringo Death Test for item events (no items purchased)."""
    print("=" * 70)
    print("Ringo Death Test Analysis (No Items Purchased)")
    print("=" * 70)

    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\replay-test")
    frame_files = list(replay_dir.glob("*.vgr"))

    if not frame_files:
        print("No replay files found")
        return

    # Get replay name from first file
    first_file = sorted(frame_files, key=lambda p: int(p.stem.split('.')[-1]))[0]
    replay_name = '.'.join(first_file.stem.split('.')[:-1])

    print(f"Replay: {replay_name}")

    # Entity ID for Ringo
    entity_id = 56325

    events = find_unique_events_early_game(replay_dir, replay_name, entity_id)

    print(f"\nEvents in first 15 frames for entity {entity_id}:")
    for frame, evts in sorted(events.items()):
        print(f"\nFrame {frame}:")
        action_counts = defaultdict(int)
        for e in evts:
            action_counts[e['action']] += 1
        for action, count in sorted(action_counts.items()):
            print(f"  0x{action:02X}: {count}x")


def analyze_tournament_match():
    """Analyze tournament match for item purchase patterns."""
    print("\n" + "=" * 70)
    print("Tournament Match Analysis (Items Purchased)")
    print("=" * 70)

    truth = load_truth_data()
    match = truth['matches'][0]  # First match

    replay_file = match['replay_file']
    replay_dir = Path(replay_file).parent
    replay_name = match['replay_name']

    print(f"Match: {replay_name[:50]}...")

    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()

    # Get one player
    player = parsed['teams']['left'][0]
    entity_id = player.get('entity_id')
    player_name = player['name']

    print(f"\nPlayer: {player_name} (Entity: {entity_id})")

    events = find_unique_events_early_game(replay_dir, replay_name, entity_id)

    print(f"\nEvents in first 15 frames:")
    for frame, evts in sorted(events.items()):
        print(f"\nFrame {frame}:")
        for e in evts:
            print(f"  0x{e['action']:02X}: {e['payload_bytes'][:15]}")


def compare_early_events():
    """Compare early game events between different matches."""
    print("\n" + "=" * 70)
    print("Comparing Early Game Events Across Matches")
    print("=" * 70)

    truth = load_truth_data()

    # Collect action codes from frame 0-2 across all matches
    all_early_actions = defaultdict(int)

    for match in truth['matches']:
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                if not entity_id:
                    continue

                events = find_unique_events_early_game(replay_dir, replay_name, entity_id)

                for frame in [0, 1, 2]:
                    for e in events.get(frame, []):
                        all_early_actions[e['action']] += 1

    print("\nAction codes in frames 0-2 across all matches:")
    sorted_actions = sorted(all_early_actions.items(), key=lambda x: -x[1])
    for action, count in sorted_actions[:20]:
        print(f"  0x{action:02X}: {count} occurrences")


def find_potential_item_action():
    """
    Find action codes that might represent item purchases.
    Look for actions that:
    1. Appear in early frames (shop phase)
    2. Have consistent payload patterns
    3. Occur multiple times per player (multiple items)
    """
    print("\n" + "=" * 70)
    print("Finding Potential Item Purchase Actions")
    print("=" * 70)

    truth = load_truth_data()

    # Track payload patterns for each action
    action_payloads = defaultdict(list)

    for match in truth['matches'][:3]:  # First 3 matches
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                if not entity_id:
                    continue

                events = find_unique_events_early_game(replay_dir, replay_name, entity_id)

                # Look at all early frames
                for frame in range(10):
                    for e in events.get(frame, []):
                        action_payloads[e['action']].append({
                            'player': player['name'],
                            'frame': frame,
                            'payload': e['payload_bytes']
                        })

    # Analyze each action
    print("\nAnalyzing payload patterns:")

    for action in sorted(action_payloads.keys()):
        payloads = action_payloads[action]
        if len(payloads) < 5:
            continue

        # Check if payloads have varying values at certain offsets
        # (item ID would vary, but structure would be consistent)
        print(f"\n0x{action:02X} ({len(payloads)} occurrences):")

        # Show sample payloads
        for p in payloads[:5]:
            print(f"  Frame {p['frame']}: {p['payload'][:12]}")


if __name__ == "__main__":
    analyze_ringo_test()
    analyze_tournament_match()
    compare_early_events()
    find_potential_item_action()
