#!/usr/bin/env python3
"""
Gold Correlation Search - Find gold by correlating nearby values with truth.

Strategy: Find ALL occurrences of player entity IDs (BE) in the last frame.
At each occurrence, read values at various offsets in various formats.
For each (offset, format), check if the per-player values correlate with truth gold.

If gold is stored near entity IDs, we'll find a strong correlation at one specific offset.
"""

import sys
import struct
import json
import math
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
                eid_be = struct.unpack('>H', struct.pack('<H', eid_le))[0]
                ns = pos + len(marker)
                ne = ns
                while ne < len(data) and ne < ns + 30:
                    if data[ne] < 32 or data[ne] > 126:
                        break
                    ne += 1
                name = data[ns:ne].decode('ascii', errors='replace')
                if eid_le not in seen and len(name) >= 3 and not name.startswith('GameMode'):
                    players.append({'name': name, 'eid_le': eid_le, 'eid_be': eid_be, 'block_pos': pos})
                    seen.add(eid_le)
            pos += 1
    return players


def load_frames(replay_file):
    p = Path(replay_file)
    d = p.parent
    base = p.stem.rsplit('.', 1)[0]
    return sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))


def pearson_corr(xs, ys):
    """Compute Pearson correlation coefficient."""
    n = len(xs)
    if n < 3:
        return 0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0
    return num / (dx * dy)


def analyze_match(match, match_idx):
    """Find gold correlation in a single match."""
    print(f"\n{'='*70}")
    print(f"Match {match_idx + 1}")

    frames = load_frames(match['replay_file'])
    if not frames:
        print("  No frames!")
        return

    # Get player info
    frame0 = frames[0].read_bytes()
    players = extract_players(frame0)

    # Map truth names to players
    name_map = {}
    for tname, tdata in match['players'].items():
        short = tname.split('_', 1)[-1] if '_' in tname else tname
        for p in players:
            if p['name'] == short or tname.endswith(p['name']):
                name_map[tname] = p
                break

    if len(name_map) < 8:
        print(f"  Only matched {len(name_map)}/{len(match['players'])} players, skipping")
        return

    # Build truth gold per entity ID (BE)
    truth_gold = {}
    for tname, tdata in match['players'].items():
        if tname in name_map:
            truth_gold[name_map[tname]['eid_be']] = tdata['gold']

    print(f"  Players: {len(truth_gold)}")
    print(f"  Truth gold range: {min(truth_gold.values())} - {max(truth_gold.values())}")

    # Load last frame
    last_data = frames[-1].read_bytes()
    print(f"  Last frame: {len(last_data):,} bytes")

    # Find ALL positions of each player's entity ID (BE) in last frame
    eid_positions = defaultdict(list)
    for eid_be in truth_gold:
        eid_bytes = struct.pack('>H', eid_be)
        pos = 0
        while True:
            pos = last_data.find(eid_bytes, pos)
            if pos == -1:
                break
            eid_positions[eid_be].append(pos)
            pos += 1

    for eid, positions in sorted(eid_positions.items()):
        print(f"  EID {eid}: {len(positions)} occurrences in last frame")

    # For each occurrence of EACH entity ID:
    # Read value at various relative offsets in various formats
    # Build per-player value lists for each (offset, format) combo
    # Then check correlation with truth gold

    formats = {
        'u16_le': ('<H', 2),
        'u16_be': ('>H', 2),
        'u32_le': ('<I', 4),
        'u32_be': ('>I', 4),
        'f32_le': ('<f', 4),
        'f32_be': ('>f', 4),
    }

    # Strategy: for each (offset, format), collect the MAXIMUM or SUM value seen
    # across all occurrences of each entity ID
    # Then correlate with truth gold

    best_corr = 0
    best_info = None

    # Test offsets from -40 to +40
    for delta in range(-40, 41):
        for fmt_name, (fmt_str, fmt_size) in formats.items():
            # For each player, collect ALL values at this (offset, format)
            player_max_values = {}
            player_sum_values = {}
            player_last_values = {}

            valid = True
            for eid_be, positions in eid_positions.items():
                values = []
                for epos in positions:
                    vpos = epos + delta
                    if vpos < 0 or vpos + fmt_size > len(last_data):
                        continue
                    try:
                        val = struct.unpack_from(fmt_str, last_data, vpos)[0]
                    except:
                        continue
                    # Filter: gold should be positive and in reasonable range
                    if fmt_name.startswith('f32'):
                        if not (0 < val < 100000) or math.isnan(val) or math.isinf(val):
                            continue
                    elif fmt_name.startswith('u32'):
                        if val > 100000:
                            continue
                    values.append(val)

                if not values:
                    valid = False
                    break

                player_max_values[eid_be] = max(values)
                player_sum_values[eid_be] = sum(values)
                player_last_values[eid_be] = values[-1]

            if not valid or len(player_max_values) < 8:
                continue

            # Correlate max values with truth gold
            eids = sorted(truth_gold.keys())
            truth_vec = [truth_gold[e] for e in eids]

            for strategy_name, vals_dict in [('max', player_max_values), ('last', player_last_values)]:
                if not all(e in vals_dict for e in eids):
                    continue
                val_vec = [vals_dict[e] for e in eids]
                corr = pearson_corr(truth_vec, val_vec)

                if abs(corr) > 0.85 and abs(corr) > best_corr:
                    best_corr = abs(corr)
                    best_info = {
                        'delta': delta, 'format': fmt_name,
                        'strategy': strategy_name, 'corr': corr,
                        'truth': truth_vec, 'detected': val_vec,
                    }

                if abs(corr) > 0.9:
                    print(f"  HIGH CORR: delta={delta:+3d} {fmt_name:8s} ({strategy_name}): r={corr:.4f}")
                    for eid in eids:
                        tg = truth_gold[eid]
                        dv = vals_dict[eid]
                        print(f"    EID {eid}: truth={tg:6d}, detected={dv:10.1f}, ratio={dv/tg:.3f}")

    if best_info:
        print(f"\n  BEST: delta={best_info['delta']:+d} {best_info['format']} ({best_info['strategy']}) r={best_info['corr']:.4f}")
    else:
        print(f"\n  No strong correlations found (best r < 0.85)")

    # Also try: look at the event stream for gold-earning events
    # Maybe there are incremental gold records in specific frames
    # Check frame-by-frame gold accumulation for a single player
    print(f"\n  --- Frame-by-frame analysis (sample player) ---")
    sample_eid = list(truth_gold.keys())[0]
    sample_gold = truth_gold[sample_eid]
    sample_bytes = struct.pack('>H', sample_eid)
    print(f"  Sample: EID {sample_eid}, truth gold = {sample_gold}")

    # For each frame at 25% intervals, count entity ID occurrences
    for fi_pct in [0, 25, 50, 75, 100]:
        fi = min(int(len(frames) * fi_pct / 100), len(frames) - 1)
        fdata = frames[fi].read_bytes()
        count = 0
        pos = 0
        while True:
            pos = fdata.find(sample_bytes, pos)
            if pos == -1:
                break
            count += 1
            pos += 1
        print(f"    Frame {fi:4d} ({fi_pct:3d}%): EID appears {count} times")


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    for match_idx in range(min(3, len(truth['matches']))):
        match = truth['matches'][match_idx]
        analyze_match(match, match_idx)


if __name__ == '__main__':
    main()
