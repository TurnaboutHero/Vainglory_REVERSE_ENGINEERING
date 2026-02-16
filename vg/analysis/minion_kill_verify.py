#!/usr/bin/env python3
"""
Minion Kill Verification - Validate [00 0E] pattern at eid offset +19.

Found: pattern [00 0E] at delta=-19 from player entity ID (BE) matches
minion_kills exactly for Matches 1 and 2. Verify on all matches.
Also examine the full record structure around this pattern.
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']
PATTERN = b'\x00\x0E'
EID_OFFSET = 19  # Entity ID (BE) is 19 bytes after pattern start


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
                    players.append({'name': name, 'eid_le': eid_le, 'eid_be': eid_be})
                    seen.add(eid_le)
            pos += 1
    return players


def load_all_frames(replay_file):
    p = Path(replay_file)
    d = p.parent
    base = p.stem.rsplit('.', 1)[0]
    frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))
    data = b''
    for f in frames:
        data += f.read_bytes()
    return data, len(frames)


def count_pattern_per_player(data, pattern, eid_offset, valid_eids):
    """Count pattern occurrences per player entity ID."""
    counts = defaultdict(int)
    examples = defaultdict(list)  # Store first 3 examples per player

    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break

        eid_pos = pos + eid_offset
        if eid_pos + 2 > len(data):
            pos += 1
            continue

        eid_be = struct.unpack('>H', data[eid_pos:eid_pos + 2])[0]
        if eid_be in valid_eids:
            counts[eid_be] += 1
            if len(examples[eid_be]) < 3:
                # Extract context: 5 bytes before pattern to 30 bytes after
                ctx_start = max(0, pos - 5)
                ctx_end = min(len(data), pos + 30)
                examples[eid_be].append({
                    'offset': pos,
                    'context': data[ctx_start:ctx_end],
                    'rel_start': pos - ctx_start,
                })
        pos += 1

    return counts, examples


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    total_correct = 0
    total_players = 0

    for match_idx, match in enumerate(truth['matches']):
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}: {match['replay_name'][:50]}...")

        # Skip incomplete match 9
        if match_idx == 8:
            print("  SKIPPED (incomplete)")
            continue

        try:
            data, n_frames = load_all_frames(match['replay_file'])
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

        frame0_path = Path(match['replay_file'])
        base_dir = frame0_path.parent
        base_name = frame0_path.stem.rsplit('.', 1)[0]
        f0 = list(base_dir.glob(f'{base_name}.0.vgr'))[0]
        players = extract_players(f0.read_bytes())

        # Map truth to entity IDs
        truth_mk = {}
        name_by_eid = {}
        for tname, tdata in match['players'].items():
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p in players:
                if p['name'] == short or tname.endswith(p['name']):
                    truth_mk[p['eid_be']] = tdata.get('minion_kills', 0)
                    name_by_eid[p['eid_be']] = tname
                    break

        valid_eids = set(truth_mk.keys())
        counts, examples = count_pattern_per_player(data, PATTERN, EID_OFFSET, valid_eids)

        match_correct = 0
        match_total = len(truth_mk)

        print(f"  Frames: {n_frames}, Data: {len(data):,} bytes")
        print(f"  {'Player':25s} {'Truth':>6s} {'Detected':>8s} {'Diff':>6s} {'Status'}")
        print(f"  {'-'*60}")
        for eid in sorted(truth_mk.keys()):
            t = truth_mk[eid]
            d = counts.get(eid, 0)
            diff = d - t
            ok = "OK" if diff == 0 else f"MISS"
            if diff == 0:
                match_correct += 1
            name = name_by_eid.get(eid, f'EID_{eid}')
            print(f"  {name:25s} {t:6d} {d:8d} {diff:+6d} {ok}")

        total_correct += match_correct
        total_players += match_total
        pct = match_correct / match_total * 100 if match_total > 0 else 0
        print(f"  Match accuracy: {match_correct}/{match_total} ({pct:.1f}%)")

        # Show record structure for first player with examples
        if examples:
            first_eid = list(examples.keys())[0]
            print(f"\n  Record structure examples (EID {first_eid} = {name_by_eid.get(first_eid, '?')}):")
            for ex in examples[first_eid]:
                ctx = ex['context']
                hex_str = ' '.join(f'{b:02X}' for b in ctx)
                # Mark pattern position
                rel = ex['rel_start']
                print(f"    Offset 0x{ex['offset']:X}: {hex_str}")
                # Show positions
                marker = ' ' * (rel * 3) + '^^' + ' ' * ((EID_OFFSET - 2) * 3 - 1) + '^^^^'
                print(f"    {'':25s} {' ' * (rel * 3)}PAT{' ' * ((EID_OFFSET - 2) * 3 - 4)}EID")

    print(f"\n{'='*70}")
    pct = total_correct / total_players * 100 if total_players > 0 else 0
    print(f"TOTAL: {total_correct}/{total_players} ({pct:.1f}%)")

    # Also try variations: [00 0E] might be part of a larger pattern
    # Let's see what bytes are consistently around the [00 0E] pattern
    print(f"\n--- Pattern context analysis (Match 1) ---")
    match = truth['matches'][0]
    data, _ = load_all_frames(match['replay_file'])
    f0 = list(Path(match['replay_file']).parent.glob(
        f'{Path(match["replay_file"]).stem.rsplit(".", 1)[0]}.0.vgr'))[0]
    players = extract_players(f0.read_bytes())
    valid_eids = set()
    for tname, tdata in match['players'].items():
        short = tname.split('_', 1)[-1] if '_' in tname else tname
        for p in players:
            if p['name'] == short or tname.endswith(p['name']):
                valid_eids.add(p['eid_be'])
                break

    # Find all pattern occurrences with valid player eids
    consistent_bytes = defaultdict(lambda: defaultdict(int))
    total_found = 0
    pos = 0
    while True:
        pos = data.find(PATTERN, pos)
        if pos == -1:
            break
        eid_pos = pos + EID_OFFSET
        if eid_pos + 2 > len(data):
            pos += 1
            continue
        eid_be = struct.unpack('>H', data[eid_pos:eid_pos + 2])[0]
        if eid_be in valid_eids:
            total_found += 1
            # Record bytes at each relative position
            for rel in range(-5, 30):
                abs_pos = pos + rel
                if 0 <= abs_pos < len(data):
                    consistent_bytes[rel][data[abs_pos]] += 1
        pos += 1

    print(f"Total valid occurrences: {total_found}")
    print(f"Byte consistency (position -> most common byte, count/total):")
    for rel in sorted(consistent_bytes.keys()):
        bc = consistent_bytes[rel]
        most_common = max(bc.items(), key=lambda x: x[1])
        pct = most_common[1] / total_found * 100
        marker = ""
        if rel in (0, 1):
            marker = " <-- PATTERN"
        elif rel == EID_OFFSET or rel == EID_OFFSET + 1:
            marker = " <-- EID"
        print(f"  +{rel:3d}: 0x{most_common[0]:02X} ({most_common[1]:4d}/{total_found} = {pct:5.1f}%){marker}")


if __name__ == '__main__':
    main()
