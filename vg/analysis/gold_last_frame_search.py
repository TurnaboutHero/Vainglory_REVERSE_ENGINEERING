#!/usr/bin/env python3
"""
Gold Last Frame Search - Search for exact gold values stored in player blocks
of the LAST frame. Player blocks may contain final stats including gold.

Previous searches looked near entity IDs. This script does a comprehensive
offset scan within player blocks across multiple frames to find gold storage.
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']


def find_player_blocks(data, target_eids_le=None):
    """Find player block positions and their entity IDs."""
    blocks = []
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(data):
                eid_le = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                ns = pos + len(marker)
                ne = ns
                while ne < len(data) and ne < ns + 30:
                    if data[ne] < 32 or data[ne] > 126:
                        break
                    ne += 1
                name = data[ns:ne].decode('ascii', errors='replace')
                if len(name) >= 3 and not name.startswith('GameMode'):
                    if target_eids_le is None or eid_le in target_eids_le:
                        blocks.append({
                            'pos': pos,
                            'eid_le': eid_le,
                            'name': name,
                            'marker': marker,
                        })
            pos += 1
    return blocks


def search_gold_in_blocks(data, blocks, truth_gold_by_eid_le, search_range=512):
    """Search for truth gold values at fixed offsets from player block markers.

    Try uint16 LE/BE, uint32 LE/BE, float32 LE/BE, and gold/100 variants.
    """
    n_players = len(blocks)
    if n_players < 3:
        return []

    best_results = []

    for offset in range(0, search_range):
        # For each format, check if ALL players match at this offset
        for fmt_name, fmt_func in [
            ('u16_LE', lambda d, o: struct.unpack_from('<H', d, o)[0] if o + 2 <= len(d) else None),
            ('u16_BE', lambda d, o: struct.unpack_from('>H', d, o)[0] if o + 2 <= len(d) else None),
            ('u32_LE', lambda d, o: struct.unpack_from('<I', d, o)[0] if o + 4 <= len(d) else None),
            ('u32_BE', lambda d, o: struct.unpack_from('>I', d, o)[0] if o + 4 <= len(d) else None),
            ('f32_LE', lambda d, o: struct.unpack_from('<f', d, o)[0] if o + 4 <= len(d) else None),
            ('f32_BE', lambda d, o: struct.unpack_from('>f', d, o)[0] if o + 4 <= len(d) else None),
        ]:
            matches = 0
            close_matches = 0
            details = []
            for block in blocks:
                abs_pos = block['pos'] + offset
                if abs_pos + 4 > len(data):
                    continue
                try:
                    val = fmt_func(data, abs_pos)
                except:
                    continue
                if val is None:
                    continue

                truth = truth_gold_by_eid_le.get(block['eid_le'])
                if truth is None:
                    continue

                # Check various interpretations
                if val is None or (isinstance(val, float) and (math.isnan(val) or math.isinf(val))):
                    continue
                try:
                    candidates = [val, val * 100, val / 100, round(val)]
                except (ValueError, OverflowError):
                    continue
                for c in candidates:
                    if abs(c - truth) < 1:
                        matches += 1
                        details.append((block['name'], truth, c, 'exact'))
                        break
                    elif abs(c - truth) <= 100:
                        close_matches += 1
                        details.append((block['name'], truth, c, 'close'))
                        break

            if matches >= 3 or (matches + close_matches >= n_players * 0.7 and matches >= 2):
                best_results.append({
                    'offset': offset,
                    'format': fmt_name,
                    'exact': matches,
                    'close': close_matches,
                    'total': n_players,
                    'details': details,
                })

    return best_results


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Test on first 3 matches (use last frame of each)
    for match_idx in [0, 1, 2, 3]:
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}")

        p = Path(match['replay_file'])
        if not p.exists():
            print("  File not found!")
            continue

        d = p.parent
        base = p.stem.rsplit('.', 1)[0]
        frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))

        # Use last frame
        last_frame = frames[-1].read_bytes()
        # Also check second-to-last and first frames
        first_frame = frames[0].read_bytes()

        print(f"  Frames: {len(frames)}, Last frame: {frames[-1].name} ({len(last_frame):,} bytes)")

        # Build truth gold by eid_le
        truth_gold_by_eid_le = {}
        f0 = first_frame
        for marker in PLAYER_MARKERS:
            pos = 0
            while True:
                pos = f0.find(marker, pos)
                if pos == -1:
                    break
                if pos + 0xD6 <= len(f0):
                    eid_le = struct.unpack('<H', f0[pos + 0xA5:pos + 0xA5 + 2])[0]
                    ns = pos + len(marker)
                    ne = ns
                    while ne < len(f0) and ne < ns + 30:
                        if f0[ne] < 32 or f0[ne] > 126:
                            break
                        ne += 1
                    name = f0[ns:ne].decode('ascii', errors='replace')
                    if len(name) >= 3 and not name.startswith('GameMode'):
                        for tname, tdata in match['players'].items():
                            if 'gold' not in tdata:
                                continue
                            short = tname.split('_', 1)[-1] if '_' in tname else tname
                            if name == short or tname.endswith(name):
                                truth_gold_by_eid_le[eid_le] = tdata['gold']
                                break
                pos += 1

        print(f"  Players with gold truth: {len(truth_gold_by_eid_le)}")
        if not truth_gold_by_eid_le:
            continue

        # Search in last frame
        print(f"\n  Searching LAST frame ({frames[-1].name})...")
        blocks = find_player_blocks(last_frame, set(truth_gold_by_eid_le.keys()))
        print(f"  Found {len(blocks)} player blocks in last frame")

        if blocks:
            results = search_gold_in_blocks(last_frame, blocks, truth_gold_by_eid_le, search_range=600)
            if results:
                print(f"  Found {len(results)} promising offsets:")
                for r in sorted(results, key=lambda x: -x['exact']):
                    print(f"    offset=+{r['offset']:3d} ({r['format']}): {r['exact']} exact, {r['close']} close / {r['total']}")
                    for name, truth_val, detected, status in r['details']:
                        print(f"      {name:25s} truth={truth_val}, detected={detected:.1f} [{status}]")
            else:
                print("  No matches found in player blocks")

        # Also try: scan ENTIRE last frame for clusters of truth gold values
        print(f"\n  Scanning entire last frame for gold value clusters...")
        gold_values = sorted(truth_gold_by_eid_le.values())

        # Search for u16 LE encoding of gold values
        found_positions = defaultdict(list)
        for gold_val in gold_values:
            if gold_val > 65535:
                continue
            target_le = struct.pack('<H', gold_val)
            target_be = struct.pack('>H', gold_val)
            # Also try gold/100
            if gold_val % 100 == 0:
                g100 = gold_val // 100
                if g100 <= 65535:
                    target_div100_le = struct.pack('<H', g100)
                    target_div100_be = struct.pack('>H', g100)
                else:
                    target_div100_le = None
                    target_div100_be = None
            else:
                target_div100_le = None
                target_div100_be = None

            for target, fmt in [(target_le, 'u16LE'), (target_be, 'u16BE')]:
                pos = 0
                while True:
                    pos = last_frame.find(target, pos)
                    if pos == -1:
                        break
                    found_positions[pos].append((gold_val, fmt))
                    pos += 1

            # float32
            target_f32_be = struct.pack('>f', float(gold_val))
            target_f32_le = struct.pack('<f', float(gold_val))
            for target, fmt in [(target_f32_be, 'f32BE'), (target_f32_le, 'f32LE')]:
                pos = 0
                while True:
                    pos = last_frame.find(target, pos)
                    if pos == -1:
                        break
                    found_positions[pos].append((gold_val, fmt))
                    pos += 1

        # Find clusters (multiple gold values near each other)
        if found_positions:
            # Group positions into clusters (within 200 bytes of each other)
            sorted_positions = sorted(found_positions.keys())
            clusters = []
            current_cluster = [sorted_positions[0]]

            for i in range(1, len(sorted_positions)):
                if sorted_positions[i] - current_cluster[-1] < 200:
                    current_cluster.append(sorted_positions[i])
                else:
                    if len(current_cluster) >= 3:
                        clusters.append(current_cluster)
                    current_cluster = [sorted_positions[i]]
            if len(current_cluster) >= 3:
                clusters.append(current_cluster)

            if clusters:
                print(f"  Found {len(clusters)} clusters with 3+ gold values:")
                for ci, cluster in enumerate(clusters[:5]):
                    unique_golds = set()
                    for pos in cluster:
                        for gold_val, fmt in found_positions[pos]:
                            unique_golds.add(gold_val)
                    print(f"    Cluster {ci+1}: positions {cluster[0]:#x}-{cluster[-1]:#x}, "
                          f"{len(cluster)} hits, {len(unique_golds)} unique gold values")
                    for pos in cluster[:10]:
                        for gold_val, fmt in found_positions[pos]:
                            print(f"      pos={pos:#x} ({pos}): gold={gold_val} [{fmt}]")
            else:
                print("  No clusters found (no 3+ gold values within 200 bytes)")
        else:
            print("  No gold values found in any encoding")


if __name__ == '__main__':
    main()
