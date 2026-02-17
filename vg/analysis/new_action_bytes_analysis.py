"""
Analysis of unknown action bytes 0x05, 0x09, 0x0A, 0x0B, 0x0C found in full replays.

These action bytes appear in full replays (200 frames) but not in tournament replays (1 frame):
- 0x05: 28~338 occurrences
- 0x09: 63~87 occurrences
- 0x0A: 60~85 occurrences
- 0x0B: 71~109 occurrences
- 0x0C: 96~147 occurrences

Goal: Determine the purpose of each action byte through statistical analysis.
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple
import struct

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

# Replay directories
REPLAY_DIRS = [
    'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
]

# Action bytes to analyze
TARGET_ACTIONS = [0x05, 0x09, 0x0A, 0x0B, 0x0C]

# Known action bytes for comparison
KNOWN_ACTIONS = {
    0x06: 'gold_income',
    0x08: 'passive_gold',
    0x0D: 'jungle_gold',
    0x0E: 'minion_kill',
    0x0F: 'minion_gold',
}


def extract_credit_records(data: bytes, target_actions: List[int]) -> List[Dict]:
    """
    Extract credit records matching target action bytes.

    Format: [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B] (12 bytes)
    """
    records = []
    header = bytes([0x10, 0x04, 0x1D])

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == header and data[i+3:i+5] == b'\x00\x00':
            # Extract fields
            eid = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            if action in target_actions:
                records.append({
                    'offset': i,
                    'eid': eid,
                    'value': value,
                    'action': action,
                })
            i += 12
        else:
            i += 1

    return records


def categorize_entity(eid: int) -> str:
    """Categorize entity by ID range."""
    if 50000 <= eid < 60000:
        return 'player'
    elif 20000 <= eid < 50000:
        return 'minion'
    elif 1000 <= eid < 20000:
        return 'structure'
    elif eid < 1000:
        return 'system'
    else:
        return 'unknown'


def analyze_action_byte(records: List[Dict], action_byte: int, player_map: Dict[int, str]) -> Dict:
    """Comprehensive analysis of a single action byte."""
    action_records = [r for r in records if r['action'] == action_byte]

    if not action_records:
        return {'count': 0}

    # Entity distribution
    entity_cats = Counter(categorize_entity(r['eid']) for r in action_records)

    # Value statistics
    values = [r['value'] for r in action_records]
    values_sorted = sorted(values)

    # Hero distribution (for player entities)
    hero_dist = Counter()
    for r in action_records:
        if r['eid'] in player_map:
            hero_dist[player_map[r['eid']]] += 1

    # Unique entity IDs
    unique_eids = set(r['eid'] for r in action_records)

    # Value range analysis
    value_counter = Counter(values)
    common_values = value_counter.most_common(10)

    return {
        'count': len(action_records),
        'entity_distribution': dict(entity_cats),
        'unique_entities': len(unique_eids),
        'value_stats': {
            'min': min(values),
            'max': max(values),
            'mean': sum(values) / len(values),
            'median': values_sorted[len(values_sorted) // 2],
        },
        'common_values': common_values,
        'hero_distribution': dict(hero_dist),
        'sample_records': action_records[:5],  # First 5 for inspection
    }


def analyze_clustering(data: bytes, records: List[Dict], window_size: int = 100) -> Dict:
    """Analyze co-occurrence patterns within offset windows."""
    action_pairs = defaultdict(int)

    for i, rec in enumerate(records):
        # Find records within window
        nearby = [r for r in records
                  if r != rec and abs(r['offset'] - rec['offset']) <= window_size]

        for other in nearby:
            pair = tuple(sorted([rec['action'], other['action']]))
            action_pairs[pair] += 1

    return dict(action_pairs)


def main():
    print("[STAGE:begin:data_loading]")

    all_results = {}

    for replay_dir in REPLAY_DIRS:
        cache_dir = Path(replay_dir)
        if not cache_dir.exists():
            print(f"[LIMITATION] Directory not found: {replay_dir}")
            continue

        # Find .0.vgr file (frame 0 for player data)
        vgr0_files = list(cache_dir.glob('*.0.vgr'))
        if not vgr0_files:
            print(f"[LIMITATION] No .0.vgr file in {replay_dir}")
            continue

        vgr0_path = vgr0_files[0]
        print(f"\n[DATA] Analyzing: {vgr0_path.parent.name}")

        # Extract player entity map
        try:
            decoder = UnifiedDecoder(str(vgr0_path))
            decoded = decoder.decode()
            player_map = {_le_to_be(p.entity_id): p.hero_name for p in decoded.all_players}
            print(f"[DATA] Found {len(player_map)} players: {list(player_map.values())}")
        except Exception as e:
            print(f"[LIMITATION] Failed to decode player data: {e}")
            continue

        # Collect all credit records from all frames
        all_records = []
        vgr_files = sorted(cache_dir.glob('*.vgr'))
        print(f"[DATA] Processing {len(vgr_files)} frame files...")

        for vgr_file in vgr_files:
            try:
                with open(vgr_file, 'rb') as f:
                    data = f.read()
                    records = extract_credit_records(data, TARGET_ACTIONS)
                    all_records.extend(records)
            except Exception as e:
                print(f"[LIMITATION] Failed to read {vgr_file.name}: {e}")

        print(f"[FINDING] Extracted {len(all_records)} credit records with target action bytes")

        # Analyze each action byte
        replay_results = {}
        for action in TARGET_ACTIONS:
            analysis = analyze_action_byte(all_records, action, player_map)
            replay_results[f'0x{action:02X}'] = analysis

            if analysis['count'] > 0:
                print(f"\n[FINDING] Action 0x{action:02X}: {analysis['count']} occurrences")
                print(f"[STAT:0x{action:02X}_count] {analysis['count']}")
                print(f"[STAT:0x{action:02X}_entities] {analysis['entity_distribution']}")
                print(f"[STAT:0x{action:02X}_value_mean] {analysis['value_stats']['mean']:.2f}")
                print(f"[STAT:0x{action:02X}_value_range] [{analysis['value_stats']['min']:.2f}, {analysis['value_stats']['max']:.2f}]")

                if analysis['common_values']:
                    print(f"[FINDING] Most common values for 0x{action:02X}:")
                    for val, count in analysis['common_values'][:3]:
                        print(f"  {val:.2f}: {count} times")

                if analysis['hero_distribution']:
                    print(f"[FINDING] Hero distribution for 0x{action:02X}:")
                    for hero, count in sorted(analysis['hero_distribution'].items(),
                                             key=lambda x: x[1], reverse=True)[:5]:
                        print(f"  {hero}: {count}")

        # Clustering analysis
        print("\n[STAGE:begin:clustering_analysis]")
        clustering = analyze_clustering(None, all_records, window_size=100)
        print("[FINDING] Action byte co-occurrence patterns (within 100 bytes):")
        for pair, count in sorted(clustering.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"[STAT:cluster_{pair[0]:02X}_{pair[1]:02X}] {count}")
        print("[STAGE:end:clustering_analysis]")

        all_results[replay_dir] = replay_results

    print("\n[STAGE:end:data_loading]")

    # Save results
    import json
    output_path = Path(__file__).parent.parent / 'output' / 'new_action_bytes_analysis.json'
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"[FINDING] Results saved to {output_path}")


if __name__ == '__main__':
    main()
