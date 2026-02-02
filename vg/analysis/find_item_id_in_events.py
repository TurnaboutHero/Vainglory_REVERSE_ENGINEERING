#!/usr/bin/env python3
"""
Find where item IDs might appear in replay events.
Search for known item ID values (101-423) in all event payloads.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser
from vgr_mapping import ITEM_ID_MAP


def load_truth_data():
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def search_item_ids_in_events(replay_dir: Path, replay_name: str, entity_id: int) -> dict:
    """Search for known item IDs in all events."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    item_ids = set(ITEM_ID_MAP.keys())  # 101-423
    found_items = defaultdict(list)

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files[:20]:  # First 20 frames
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

                # Search for item IDs in payload
                for offset in range(len(payload) - 1):
                    # Check single byte
                    val = payload[offset]
                    if val in item_ids:
                        found_items[(action, offset, 'byte')].append({
                            'frame': frame_num,
                            'value': val,
                            'item': ITEM_ID_MAP[val]['name']
                        })

                    # Check 2-byte little-endian
                    if offset < len(payload) - 1:
                        val_2b = payload[offset] | (payload[offset + 1] << 8)
                        if val_2b in item_ids:
                            found_items[(action, offset, '2byte')].append({
                                'frame': frame_num,
                                'value': val_2b,
                                'item': ITEM_ID_MAP[val_2b]['name']
                            })
            idx += 1

    return found_items


def main():
    print("=" * 70)
    print("Searching for Item IDs (101-423) in Event Payloads")
    print("=" * 70)
    print()

    truth = load_truth_data()
    match = truth['matches'][0]

    replay_file = match['replay_file']
    replay_dir = Path(replay_file).parent
    replay_name = match['replay_name']

    print(f"Known item IDs: {min(ITEM_ID_MAP.keys())} - {max(ITEM_ID_MAP.keys())}")
    print(f"Total items: {len(ITEM_ID_MAP)}")
    print()

    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()

    all_found = defaultdict(list)

    for team in ('left', 'right'):
        for player in parsed['teams'][team]:
            entity_id = player.get('entity_id')
            player_name = player['name']

            if not entity_id:
                continue

            found = search_item_ids_in_events(replay_dir, replay_name, entity_id)

            for key, items in found.items():
                for item in items:
                    item['player'] = player_name
                    all_found[key].append(item)

    print("Found item IDs at:")
    print()

    for (action, offset, val_type), items in sorted(all_found.items(), key=lambda x: -len(x[1])):
        if len(items) < 3:
            continue

        print(f"Action 0x{action:02X}, Offset {offset}, Type {val_type}: {len(items)} occurrences")

        # Show unique items
        unique_items = set()
        for item in items[:10]:
            unique_items.add((item['value'], item['item']))

        for val, name in sorted(unique_items):
            print(f"  - {val}: {name}")

        print()


if __name__ == "__main__":
    main()
