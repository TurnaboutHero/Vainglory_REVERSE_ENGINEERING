#!/usr/bin/env python3
"""
Action Byte 0x03 Full Replay Analysis

Tournament replays (1 frame): 0x03 appears 100-169 times, always value=1.0
Full replays (200 frames): 0x03 appears 17,000-37,000 times!

This script investigates:
1. Which entities receive 0x03 credits (players? all entities?)
2. Value distribution (always 1.0 or varied?)
3. Temporal patterns across frames
4. Correlation with other action bytes (0x0E minion, 0x06 gold, etc.)
5. Entity type breakdown (player vs structure vs minion)
"""

import struct
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

# Credit record structure: [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B]
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
CREDIT_RECORD_SIZE = 12

def extract_player_entities(cache_dir: Path) -> Dict[int, str]:
    """Extract player entity IDs from .0.vgr file."""
    vgr0 = list(cache_dir.glob('*.0.vgr'))[0]
    decoder = UnifiedDecoder(str(vgr0))
    decoded = decoder.decode()
    return {_le_to_be(p.entity_id): p.hero_name for p in decoded.all_players}

def load_all_frames(cache_dir: Path) -> bytes:
    """Load all frame data from .vgr files."""
    vgr_files = sorted(
        cache_dir.glob('*.vgr'),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    print(f"[DATA] Loading {len(vgr_files)} frame files from {cache_dir.name}")
    return b''.join(f.read_bytes() for f in vgr_files)

def classify_entity(eid: int, player_eids: set) -> str:
    """Classify entity by ID range."""
    if eid in player_eids:
        return 'player'
    elif 50000 <= eid < 60000:
        return 'player_range'
    elif 1000 <= eid < 20000:
        return 'structure'
    elif 20000 <= eid < 50000:
        return 'minion'
    elif 0 <= eid < 1000:
        return 'system'
    else:
        return 'unknown'

def analyze_action_03(data: bytes, player_eids: Dict[int, str]) -> dict:
    """Comprehensive analysis of action byte 0x03."""

    results = {
        'total_count': 0,
        'entity_counts': defaultdict(int),
        'entity_types': defaultdict(int),
        'value_distribution': defaultdict(int),
        'values': [],
        'player_breakdown': defaultdict(int),
        'temporal_samples': [],  # Sample every N occurrences
        'correlation_window': defaultdict(lambda: defaultdict(int)),
    }

    player_eid_set = set(player_eids.keys())

    # Find all credit records
    idx = 0
    all_credits = []

    while idx < len(data) - CREDIT_RECORD_SIZE:
        if data[idx:idx+3] == CREDIT_HEADER:
            try:
                # Parse: [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B]
                eid = struct.unpack('>H', data[idx+5:idx+7])[0]
                value = struct.unpack('>f', data[idx+7:idx+11])[0]
                action = data[idx+11]

                all_credits.append((idx, eid, value, action))

            except struct.error:
                pass

            idx += CREDIT_RECORD_SIZE
        else:
            idx += 1

    print(f"[DATA] Total credit records: {len(all_credits)}")

    # Analyze 0x03 credits
    action_03_indices = []

    for i, (pos, eid, value, action) in enumerate(all_credits):
        if action == 0x03:
            results['total_count'] += 1
            results['entity_counts'][eid] += 1

            entity_type = classify_entity(eid, player_eid_set)
            results['entity_types'][entity_type] += 1

            # Value distribution (rounded to 2 decimals)
            value_rounded = round(value, 2)
            results['value_distribution'][value_rounded] += 1
            results['values'].append(value)

            # Player breakdown
            if eid in player_eids:
                results['player_breakdown'][player_eids[eid]] += 1

            # Temporal sampling (every 1000th occurrence)
            if results['total_count'] % 1000 == 0:
                results['temporal_samples'].append({
                    'occurrence': results['total_count'],
                    'position': pos,
                    'entity': eid,
                    'value': value
                })

            action_03_indices.append(i)

    # Correlation analysis: check nearby action bytes
    for i in action_03_indices[:1000]:  # Sample first 1000 for performance
        # Check 10 records before and after
        for offset in range(-10, 11):
            if offset == 0:
                continue
            nearby_idx = i + offset
            if 0 <= nearby_idx < len(all_credits):
                nearby_action = all_credits[nearby_idx][3]
                results['correlation_window'][offset][nearby_action] += 1

    return results

def print_analysis(replay_name: str, results: dict, player_eids: Dict[int, str]):
    """Print comprehensive analysis results."""

    print(f"\n{'='*80}")
    print(f"[OBJECTIVE] Analyze action byte 0x03 in {replay_name}")
    print(f"{'='*80}\n")

    print(f"[STAT:total_0x03_count] {results['total_count']:,}")

    # Entity type distribution
    print(f"\n[FINDING] Entity Type Distribution:")
    for entity_type, count in sorted(results['entity_types'].items(), key=lambda x: -x[1]):
        pct = 100 * count / results['total_count']
        print(f"  {entity_type:15s}: {count:6,} ({pct:5.1f}%)")

    # Value distribution
    print(f"\n[FINDING] Value Distribution (top 20):")
    top_values = sorted(results['value_distribution'].items(), key=lambda x: -x[1])[:20]
    for value, count in top_values:
        pct = 100 * count / results['total_count']
        print(f"  {value:8.2f}: {count:6,} ({pct:5.1f}%)")

    if results['values']:
        import statistics
        print(f"\n[STAT:value_mean] {statistics.mean(results['values']):.4f}")
        print(f"[STAT:value_median] {statistics.median(results['values']):.4f}")
        print(f"[STAT:value_min] {min(results['values']):.4f}")
        print(f"[STAT:value_max] {max(results['values']):.4f}")

    # Player breakdown
    if results['player_breakdown']:
        print(f"\n[FINDING] Player Distribution:")
        for hero, count in sorted(results['player_breakdown'].items(), key=lambda x: -x[1]):
            pct = 100 * count / results['total_count']
            print(f"  {hero:20s}: {count:6,} ({pct:5.1f}%)")

    # Top entities
    print(f"\n[FINDING] Top 15 Entities by 0x03 Count:")
    top_entities = sorted(results['entity_counts'].items(), key=lambda x: -x[1])[:15]
    for eid, count in top_entities:
        entity_type = classify_entity(eid, set(player_eids.keys()))
        hero_name = player_eids.get(eid, '')
        pct = 100 * count / results['total_count']
        print(f"  eid {eid:5d} ({entity_type:12s}) {hero_name:15s}: {count:6,} ({pct:5.1f}%)")

    # Temporal pattern
    if results['temporal_samples']:
        print(f"\n[FINDING] Temporal Samples (every 1000th occurrence):")
        for sample in results['temporal_samples'][:10]:
            print(f"  Occurrence {sample['occurrence']:5,}: pos={sample['position']:8,}, "
                  f"eid={sample['entity']:5d}, value={sample['value']:.2f}")

    # Correlation with other action bytes
    print(f"\n[FINDING] Nearby Action Bytes (within ±10 records, first 1000 samples):")
    print(f"  Offset | Action Byte Frequencies")
    print(f"  -------|" + "-" * 50)

    for offset in sorted(results['correlation_window'].keys()):
        action_counts = results['correlation_window'][offset]
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ', '.join(f"0x{act:02X}={cnt}" for act, cnt in top_actions)
        print(f"  {offset:+3d}    | {action_str}")

def main():
    print("[STAGE:begin:data_loading]")

    replay_dirs = [
        Path('D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache'),  # 216 frames
        Path('D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache'),  # 206 frames
        Path('D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache'),  # 195 frames
    ]

    for replay_dir in replay_dirs:
        if not replay_dir.exists():
            print(f"[LIMITATION] Replay directory not found: {replay_dir}")
            continue

        try:
            # Extract player entities
            player_eids = extract_player_entities(replay_dir)
            print(f"[DATA] {len(player_eids)} players: {list(player_eids.values())}")

            # Load all frame data
            all_data = load_all_frames(replay_dir)
            print(f"[DATA] Total data size: {len(all_data):,} bytes")

            # Analyze action 0x03
            results = analyze_action_03(all_data, player_eids)

            # Print results
            print_analysis(replay_dir.parent.name, results, player_eids)

        except Exception as e:
            print(f"[LIMITATION] Error analyzing {replay_dir.name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

if __name__ == '__main__':
    main()
