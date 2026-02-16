#!/usr/bin/env python3
"""
Gold Cluster Search - Find a region in the last frame where 10 values
match all 10 truth gold values.

Approach: scan for ANY uint16/uint32/float32 values in gold range,
then look for spatial clusters of 10+ matches.
Also try: searching every frame for gold accumulation patterns.
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']


def extract_players(data):
    players = []
    seen = set()
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(data):
                eid_le = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                team = data[pos + 0xD5]
                ns = pos + len(marker)
                ne = ns
                while ne < len(data) and ne < ns + 30:
                    if data[ne] < 32 or data[ne] > 126:
                        break
                    ne += 1
                name = data[ns:ne].decode('ascii', errors='replace')
                if eid_le not in seen and len(name) >= 3 and not name.startswith('GameMode'):
                    players.append({'name': name, 'eid_le': eid_le, 'team': team, 'block_pos': pos})
                    seen.add(eid_le)
            pos += 1
    return players


def load_frames(replay_file):
    p = Path(replay_file)
    d = p.parent
    base = p.stem.rsplit('.', 1)[0]
    return sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))


def find_gold_cluster_u16(data, truth_golds, tolerance=200):
    """Find positions where uint16 LE values match truth gold values."""
    gold_set = set(truth_golds)
    matches = []
    for i in range(len(data) - 1):
        val = struct.unpack_from('<H', data, i)[0]
        for g in gold_set:
            if abs(val - g) <= tolerance:
                matches.append((i, val, g))
                break

    # Look for clusters: 10 matches within a 200-byte window
    if not matches:
        return []

    clusters = []
    for start_idx in range(len(matches)):
        cluster = [matches[start_idx]]
        for j in range(start_idx + 1, len(matches)):
            if matches[j][0] - matches[start_idx][0] > 500:
                break
            cluster.append(matches[j])

        matched_golds = set(m[2] for m in cluster)
        if len(matched_golds) >= len(gold_set) * 0.7:
            clusters.append(cluster)

    return clusters[:3]  # Top 3 clusters


def find_gold_cluster_f32(data, truth_golds, tolerance=200, endian='<'):
    """Find positions where float32 values match truth gold values."""
    gold_set = set(truth_golds)
    fmt = f'{endian}f'
    matches = []
    for i in range(len(data) - 3):
        try:
            val = struct.unpack_from(fmt, data, i)[0]
        except:
            continue
        if not (1000 < val < 50000):
            continue
        for g in gold_set:
            if abs(val - g) <= tolerance:
                matches.append((i, val, g))
                break

    # Look for clusters
    if not matches:
        return []

    clusters = []
    for start_idx in range(len(matches)):
        cluster = [matches[start_idx]]
        for j in range(start_idx + 1, len(matches)):
            if matches[j][0] - matches[start_idx][0] > 500:
                break
            cluster.append(matches[j])

        matched_golds = set(m[2] for m in cluster)
        if len(matched_golds) >= len(gold_set) * 0.7:
            clusters.append(cluster)

    return clusters[:3]


def find_gold_cluster_u32(data, truth_golds, tolerance=200):
    """Find positions where uint32 LE values match truth gold values."""
    gold_set = set(truth_golds)
    matches = []
    for i in range(len(data) - 3):
        val = struct.unpack_from('<I', data, i)[0]
        if not (1000 < val < 50000):
            continue
        for g in gold_set:
            if abs(val - g) <= tolerance:
                matches.append((i, val, g))
                break

    if not matches:
        return []

    clusters = []
    for start_idx in range(len(matches)):
        cluster = [matches[start_idx]]
        for j in range(start_idx + 1, len(matches)):
            if matches[j][0] - matches[start_idx][0] > 500:
                break
            cluster.append(matches[j])

        matched_golds = set(m[2] for m in cluster)
        if len(matched_golds) >= len(gold_set) * 0.7:
            clusters.append(cluster)

    return clusters[:3]


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Test on first 3 matches
    for match_idx in [0, 1, 2]:
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}")

        frames = load_frames(match['replay_file'])
        if not frames:
            continue

        frame0 = frames[0].read_bytes()
        players = extract_players(frame0)
        truth_golds = [pdata['gold'] for pdata in match['players'].values()]
        print(f"  Truth golds: {sorted(truth_golds)}")
        print(f"  Range: {min(truth_golds)} - {max(truth_golds)}")

        # Search last frame
        last_data = frames[-1].read_bytes()
        print(f"  Last frame: {len(last_data):,} bytes")

        # Strategy 1: uint16 LE cluster
        clusters = find_gold_cluster_u16(last_data, truth_golds, tolerance=150)
        if clusters:
            print(f"\n  [u16 LE] Found {len(clusters)} cluster(s):")
            for ci, cluster in enumerate(clusters):
                region = f"0x{cluster[0][0]:X}-0x{cluster[-1][0]:X}"
                matched = set(m[2] for m in cluster)
                print(f"    Cluster {ci}: {region}, {len(matched)}/{len(truth_golds)} golds matched, {len(cluster)} hits")
                for pos, val, gold in cluster[:15]:
                    print(f"      0x{pos:05X}: {val:6d} (truth={gold})")
        else:
            print(f"\n  [u16 LE] No clusters found")

        # Strategy 2: float32 BE cluster
        clusters = find_gold_cluster_f32(last_data, truth_golds, tolerance=150, endian='>')
        if clusters:
            print(f"\n  [f32 BE] Found {len(clusters)} cluster(s):")
            for ci, cluster in enumerate(clusters):
                region = f"0x{cluster[0][0]:X}-0x{cluster[-1][0]:X}"
                matched = set(m[2] for m in cluster)
                print(f"    Cluster {ci}: {region}, {len(matched)}/{len(truth_golds)} golds matched, {len(cluster)} hits")
                for pos, val, gold in cluster[:15]:
                    print(f"      0x{pos:05X}: {val:8.1f} (truth={gold})")
        else:
            print(f"\n  [f32 BE] No clusters found")

        # Strategy 3: float32 LE cluster
        clusters = find_gold_cluster_f32(last_data, truth_golds, tolerance=150, endian='<')
        if clusters:
            print(f"\n  [f32 LE] Found {len(clusters)} cluster(s):")
            for ci, cluster in enumerate(clusters):
                region = f"0x{cluster[0][0]:X}-0x{cluster[-1][0]:X}"
                matched = set(m[2] for m in cluster)
                print(f"    Cluster {ci}: {region}, {len(matched)}/{len(truth_golds)} golds matched, {len(cluster)} hits")
                for pos, val, gold in cluster[:15]:
                    print(f"      0x{pos:05X}: {val:8.1f} (truth={gold})")
        else:
            print(f"\n  [f32 LE] No clusters found")

        # Strategy 4: uint32 LE cluster
        clusters = find_gold_cluster_u32(last_data, truth_golds, tolerance=150)
        if clusters:
            print(f"\n  [u32 LE] Found {len(clusters)} cluster(s):")
            for ci, cluster in enumerate(clusters):
                region = f"0x{cluster[0][0]:X}-0x{cluster[-1][0]:X}"
                matched = set(m[2] for m in cluster)
                print(f"    Cluster {ci}: {region}, {len(matched)}/{len(truth_golds)} golds matched, {len(cluster)} hits")
                for pos, val, gold in cluster[:15]:
                    print(f"      0x{pos:05X}: {val:6d} (truth={gold})")
        else:
            print(f"\n  [u32 LE] No clusters found")

        # Strategy 5: Search across ALL frames for gold progression
        # The gold value that matches truth should appear in one of the later frames
        # and grow over time. Check frames at 25%, 50%, 75%, 100%
        print(f"\n  --- Gold progression search (f32 BE) ---")
        check_indices = [0, len(frames)//4, len(frames)//2, 3*len(frames)//4, len(frames)-1]
        for fi in check_indices:
            fdata = frames[fi].read_bytes()
            # Count how many truth gold values appear as f32 BE
            found = 0
            for g in truth_golds:
                target = struct.pack('>f', float(g))
                if fdata.find(target) != -1:
                    found += 1
            target_max = struct.pack('>f', float(max(truth_golds)))
            print(f"    Frame {fi:4d}: {found}/{len(truth_golds)} truth golds found as f32 BE")


if __name__ == '__main__':
    main()
