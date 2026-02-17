"""
Deep dive analysis: examining entity IDs, temporal patterns, and event context.
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
import struct

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

REPLAY_DIRS = [
    'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
    'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
]

TARGET_ACTIONS = [0x05, 0x09, 0x0A, 0x0B, 0x0C]


def extract_all_credit_records(data: bytes) -> list:
    """Extract ALL credit records for pattern comparison."""
    records = []
    header = bytes([0x10, 0x04, 0x1D])

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == header and data[i+3:i+5] == b'\x00\x00':
            eid = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

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


def analyze_entity_ids(records: list, action: int) -> dict:
    """Deep analysis of entity IDs for specific action."""
    action_recs = [r for r in records if r['action'] == action]

    eid_counter = Counter(r['eid'] for r in action_recs)

    # Group by entity ID ranges
    ranges = defaultdict(list)
    for eid, count in eid_counter.items():
        if 2000 <= eid <= 2100:
            ranges['2000-2100 (turrets/objectives)'].append((eid, count))
        elif 1000 <= eid < 2000:
            ranges['1000-1999 (structures)'].append((eid, count))
        elif 2100 <= eid < 20000:
            ranges['2100-19999 (other structures)'].append((eid, count))
        else:
            ranges['other'].append((eid, count))

    return {
        'total_unique_eids': len(eid_counter),
        'eid_frequency': dict(eid_counter.most_common(20)),
        'eid_ranges': {k: sorted(v) for k, v in ranges.items()},
    }


def analyze_context_window(data: bytes, records: list, action: int, window: int = 50) -> dict:
    """Analyze bytes around action records to identify context patterns."""
    action_recs = [r for r in records if r['action'] == action]

    # Sample surrounding bytes
    context_before = defaultdict(int)
    context_after = defaultdict(int)

    for rec in action_recs[:50]:  # Sample first 50
        offset = rec['offset']

        # Check for common headers before
        if offset >= 20:
            before = data[offset-20:offset]
            # Look for event headers
            for i in range(len(before) - 3):
                header = before[i:i+3]
                if header in [b'\x18\x04\x1C', b'\x08\x04\x31', b'\x18\x04\x3E', b'\x18\x04\x1E']:
                    context_before[header.hex()] += 1

        # Check after
        if offset + 12 + window < len(data):
            after = data[offset+12:offset+12+window]
            for i in range(len(after) - 3):
                header = after[i:i+3]
                if header in [b'\x18\x04\x1C', b'\x08\x04\x31', b'\x18\x04\x3E', b'\x18\x04\x1E', b'\x10\x04\x1D']:
                    context_after[header.hex()] += 1

    return {
        'headers_before': dict(context_before),
        'headers_after': dict(context_after),
    }


def compare_value_patterns(records: list) -> dict:
    """Compare value patterns across action bytes."""
    action_values = defaultdict(list)

    for rec in records:
        if rec['action'] in TARGET_ACTIONS:
            action_values[rec['action']].append(rec['value'])

    patterns = {}
    for action, values in action_values.items():
        unique_vals = set(values)
        patterns[f'0x{action:02X}'] = {
            'unique_count': len(unique_vals),
            'is_binary': unique_vals.issubset({0.0, 1.0}),
            'is_constant': len(unique_vals) == 1,
            'has_negatives': any(v < 0 for v in values),
            'sample_values': sorted(unique_vals)[:10],
        }

    return patterns


def analyze_temporal_distribution(replay_dir: str, action: int) -> dict:
    """Analyze how action bytes distribute across frames (time)."""
    cache_dir = Path(replay_dir)
    vgr_files = sorted(cache_dir.glob('*.vgr'))

    frame_counts = []

    for vgr_file in vgr_files:
        with open(vgr_file, 'rb') as f:
            data = f.read()
            records = extract_all_credit_records(data)
            count = sum(1 for r in records if r['action'] == action)
            frame_counts.append(count)

    # Find peaks
    peaks = []
    for i, count in enumerate(frame_counts):
        if count > 0:
            peaks.append((i, count))

    return {
        'total_frames': len(frame_counts),
        'frames_with_action': sum(1 for c in frame_counts if c > 0),
        'max_per_frame': max(frame_counts) if frame_counts else 0,
        'avg_per_active_frame': sum(frame_counts) / max(sum(1 for c in frame_counts if c > 0), 1),
        'peak_frames': sorted(peaks, key=lambda x: x[1], reverse=True)[:10],
    }


def main():
    print("[STAGE:begin:entity_analysis]")

    for replay_dir in REPLAY_DIRS:
        cache_dir = Path(replay_dir)
        if not cache_dir.exists():
            continue

        print(f"\n[DATA] Deep dive: {cache_dir.parent.name}")

        # Get player map
        vgr0_files = list(cache_dir.glob('*.0.vgr'))
        if not vgr0_files:
            continue

        decoder = UnifiedDecoder(str(vgr0_files[0]))
        decoded = decoder.decode()
        player_map = {_le_to_be(p.entity_id): p.hero_name for p in decoded.all_players}

        # Collect all records
        all_data = b''
        all_records = []
        for vgr_file in sorted(cache_dir.glob('*.vgr')):
            with open(vgr_file, 'rb') as f:
                data = f.read()
                all_data += data
                all_records.extend(extract_all_credit_records(data))

        print(f"[DATA] Total credit records: {len(all_records)}")

        # Analyze each action byte
        for action in TARGET_ACTIONS:
            action_recs = [r for r in all_records if r['action'] == action]
            if not action_recs:
                continue

            print(f"\n[FINDING] Action 0x{action:02X} - Entity ID Analysis:")
            eid_analysis = analyze_entity_ids(all_records, action)

            print(f"[STAT:0x{action:02X}_unique_entities] {eid_analysis['total_unique_eids']}")

            for range_name, eids in eid_analysis['eid_ranges'].items():
                if eids:
                    print(f"  {range_name}: {len(eids)} entities")
                    for eid, count in eids[:5]:
                        print(f"    eid={eid}: {count} occurrences")

            # Context analysis
            context = analyze_context_window(all_data[:1000000], all_records, action)  # Sample first 1MB
            if context['headers_before'] or context['headers_after']:
                print(f"[FINDING] Context patterns for 0x{action:02X}:")
                if context['headers_before']:
                    print(f"  Headers before: {context['headers_before']}")
                if context['headers_after']:
                    print(f"  Headers after: {context['headers_after']}")

            # Temporal distribution
            temporal = analyze_temporal_distribution(str(cache_dir), action)
            print(f"[FINDING] Temporal distribution 0x{action:02X}:")
            print(f"  Active in {temporal['frames_with_action']}/{temporal['total_frames']} frames")
            print(f"  Max per frame: {temporal['max_per_frame']}")
            if temporal['peak_frames'][:3]:
                print(f"  Peak frames: {temporal['peak_frames'][:3]}")

        # Value pattern comparison
        print("\n[FINDING] Value pattern comparison:")
        value_patterns = compare_value_patterns(all_records)
        for action_hex, pattern in value_patterns.items():
            print(f"  {action_hex}:")
            print(f"    Binary (0/1 only): {pattern['is_binary']}")
            print(f"    Constant value: {pattern['is_constant']}")
            print(f"    Has negatives: {pattern['has_negatives']}")
            if not pattern['is_binary'] and not pattern['is_constant']:
                print(f"    Sample values: {pattern['sample_values']}")

    print("\n[STAGE:end:entity_analysis]")


if __name__ == '__main__':
    main()
