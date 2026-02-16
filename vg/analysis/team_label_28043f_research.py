#!/usr/bin/env python3
"""
[28 04 3F] Event Research - Potential Position Data
=====================================================
Newly discovered header with 673 occurrences per frame (67/player).
This could be position update events.

Structure hypothesis (based on [18 04 3E] pattern):
  [28 04 3F] [00 00] [eid_BE 2B] [payload...]

Research plan:
1. Verify eid_BE at offset +5 matches player eids
2. Determine payload length (distance between consecutive events)
3. Scan payload for float32 values discriminating left/right
4. If found, validate across all 10 matches
"""

import json
import struct
import sys
import math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])

HEADER_28 = bytes([0x28, 0x04, 0x3F])


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def parse_player_blocks(data):
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    while True:
        pos = -1
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
        if pos == -1:
            break
        name_start = pos + 3
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            if data[name_end] < 32 or data[name_end] > 126:
                break
            name_end += 1
        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""
            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                eid_le = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little')
                team_id = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                players.append({
                    'name': name,
                    'eid_le': eid_le,
                    'eid_be': le_to_be(eid_le),
                    'team_id': team_id,
                })
                seen.add(name)
        search_start = pos + 1
    return players


def load_frames(replay_file, max_frames=None):
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))
    if max_frames:
        frames = frames[:max_frames]
    return [(int(f.stem.split('.')[-1]), f.read_bytes()) for f in frames]


def find_28_events(data, valid_eids_be=None, max_events=5000):
    """Find all [28 04 3F] events, optionally filtering to known player eids."""
    events = []
    pos = 0
    while len(events) < max_events:
        pos = data.find(HEADER_28, pos)
        if pos == -1:
            break

        # Extract next 60 bytes for analysis
        payload = data[pos:pos + 60] if pos + 60 <= len(data) else data[pos:]

        # Check if eid at various offsets matches player eids
        eid_be_at5 = struct.unpack_from(">H", data, pos + 5)[0] if pos + 7 <= len(data) else None
        eid_be_at3 = struct.unpack_from(">H", data, pos + 3)[0] if pos + 5 <= len(data) else None

        is_player = False
        eid = None
        eid_offset = None
        if valid_eids_be:
            if eid_be_at5 in valid_eids_be:
                is_player = True
                eid = eid_be_at5
                eid_offset = 5
            elif eid_be_at3 in valid_eids_be:
                is_player = True
                eid = eid_be_at3
                eid_offset = 3
        else:
            eid = eid_be_at5
            eid_offset = 5

        events.append({
            'offset': pos,
            'eid_be': eid,
            'eid_offset': eid_offset,
            'is_player': is_player,
            'payload': payload,
        })
        pos += 1

    return events


def main():
    print("=" * 80)
    print("[28 04 3F] EVENT RESEARCH")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    match = truth_data['matches'][0]
    replay_file = match['replay_file']

    with open(replay_file, 'rb') as f:
        frame0 = f.read()
    players = parse_player_blocks(frame0)
    valid_eids_be = set(p['eid_be'] for p in players)

    # ===== STEP 1: Structure Analysis =====
    print("\n[STEP 1] Event structure analysis")

    frames = load_frames(replay_file, max_frames=2)
    fdata = frames[0][1]

    events = find_28_events(fdata, valid_eids_be)
    player_events = [e for e in events if e['is_player']]

    print(f"  Total [28 04 3F] in frame 0: {len(events)}")
    print(f"  Player events (eid at +5): {len(player_events)}")

    # Determine event spacing (distance between consecutive events)
    offsets = [e['offset'] for e in events]
    if len(offsets) > 5:
        gaps = [offsets[i+1] - offsets[i] for i in range(min(50, len(offsets)-1))]
        from collections import Counter
        gap_counts = Counter(gaps)
        print(f"  Event spacing (top 5): {gap_counts.most_common(5)}")

    # Dump first 5 player events
    print(f"\n  First 10 player events (raw hex):")
    for ev in player_events[:10]:
        hex_str = ' '.join(f'{b:02X}' for b in ev['payload'][:50])
        p_name = '?'
        for p in players:
            if p['eid_be'] == ev['eid_be']:
                p_name = p['name']
                break
        print(f"    @{ev['offset']:6d} eid={ev['eid_be']} ({p_name:15s}): {hex_str}")

    # ===== STEP 2: Float scan in [28 04 3F] payload =====
    print("\n" + "=" * 80)
    print("[STEP 2] Float scan across 5 matches - [28 04 3F] events")
    print("=" * 80)

    all_values = defaultdict(lambda: {'left': [], 'right': []})

    for mi, match in enumerate(truth_data['matches'][:5]):
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        with open(replay_file, 'rb') as f:
            f0 = f.read()
        pls = parse_player_blocks(f0)
        veids = set(p['eid_be'] for p in pls)

        eid_to_truth = {}
        for p in pls:
            for pname, pdata in match['players'].items():
                short = pname.split('_', 1)[1] if '_' in pname else pname
                if p['name'] == short or p['name'] == pname:
                    eid_to_truth[p['eid_be']] = pdata['team']
                    break

        frs = load_frames(replay_file, max_frames=3)
        for fi, fd in frs:
            evts = find_28_events(fd, veids, max_events=5000)
            player_evts = [e for e in evts if e['is_player']]

            for ev in player_evts:
                team = eid_to_truth.get(ev['eid_be'])
                if not team:
                    continue

                payload = ev['payload']
                # Scan from offset 7 onwards (after header + 00 00 + eid)
                for off in range(7, min(50, len(payload) - 3)):
                    # Big endian float
                    val = struct.unpack_from(">f", payload, off)[0]
                    if not math.isnan(val) and not math.isinf(val) and 0.1 < abs(val) < 5000:
                        all_values[(off, 'BE')][team].append(val)

                    # Little endian float
                    val = struct.unpack_from("<f", payload, off)[0]
                    if not math.isnan(val) and not math.isinf(val) and 0.1 < abs(val) < 5000:
                        all_values[(off, 'LE')][team].append(val)

                    # Also try uint16 BE and LE
                    val_u16be = struct.unpack_from(">H", payload, off)[0]
                    val_u16le = struct.unpack_from("<H", payload, off)[0]
                    if 100 < val_u16be < 10000:
                        all_values[(off, 'u16BE')][team].append(val_u16be)
                    if 100 < val_u16le < 10000:
                        all_values[(off, 'u16LE')][team].append(val_u16le)

    # Score
    scored = []
    for (off, enc), teams in all_values.items():
        lv = teams['left']
        rv = teams['right']
        if len(lv) < 20 or len(rv) < 20:
            continue
        avg_l = sum(lv) / len(lv)
        avg_r = sum(rv) / len(rv)
        std_l = (sum((v - avg_l)**2 for v in lv) / len(lv)) ** 0.5
        std_r = (sum((v - avg_r)**2 for v in rv) / len(rv)) ** 0.5
        cs = std_l + std_r
        if cs < 0.01:
            continue
        sep = abs(avg_l - avg_r) / cs
        scored.append({
            'off': off, 'enc': enc,
            'avg_l': avg_l, 'avg_r': avg_r,
            'std_l': std_l, 'std_r': std_r,
            'sep': sep, 'nl': len(lv), 'nr': len(rv),
        })

    scored.sort(key=lambda x: -x['sep'])

    print(f"\n  Scanned {len(all_values)} (offset, encoding) combos")
    print(f"\n  Top 20 discriminating:")
    print(f"  {'Off':>4s} {'Enc':>5s} {'AvgL':>8s} {'AvgR':>8s} {'StdL':>7s} {'StdR':>7s} {'Sep':>6s} {'nL':>5s} {'nR':>5s}")
    for r in scored[:20]:
        print(f"  {r['off']:4d} {r['enc']:>5s} {r['avg_l']:8.1f} {r['avg_r']:8.1f} "
              f"{r['std_l']:7.1f} {r['std_r']:7.1f} {r['sep']:6.3f} {r['nl']:5d} {r['nr']:5d}")

    # ===== STEP 3: Per-player analysis of top candidate =====
    if scored:
        print("\n" + "=" * 80)
        print("[STEP 3] Per-player values for top 3 candidates")
        print("=" * 80)

        for rank, best in enumerate(scored[:3]):
            off = best['off']
            enc = best['enc']
            fmt_map = {'BE': '>f', 'LE': '<f', 'u16BE': '>H', 'u16LE': '<H'}
            fmt = fmt_map.get(enc, '>f')
            size = 4 if 'f' in fmt else 2

            print(f"\n  Candidate #{rank+1}: offset={off}, encoding={enc}")
            print(f"  {'Match':>5s} {'Player':>15s} {'Team':>6s} {'TB':>3s} {'Value':>10s}")

            for mi, match in enumerate(truth_data['matches'][:3]):
                replay_file = match['replay_file']
                if not Path(replay_file).exists() or "Incomplete" in replay_file:
                    continue

                with open(replay_file, 'rb') as f:
                    f0 = f.read()
                pls = parse_player_blocks(f0)
                veids = set(p['eid_be'] for p in pls)

                eid_to_truth = {}
                eid_to_name = {}
                eid_to_tb = {}
                for p in pls:
                    eid_to_tb[p['eid_be']] = p['team_id']
                    for pname, pdata in match['players'].items():
                        short = pname.split('_', 1)[1] if '_' in pname else pname
                        if p['name'] == short or p['name'] == pname:
                            eid_to_truth[p['eid_be']] = pdata['team']
                            eid_to_name[p['eid_be']] = p['name']
                            break

                frs = load_frames(replay_file, max_frames=1)
                for fi, fd in frs:
                    evts = find_28_events(fd, veids, max_events=5000)
                    pevts = [e for e in evts if e['is_player']]

                    player_vals = defaultdict(list)
                    for ev in pevts:
                        if off + size <= len(ev['payload']):
                            val = struct.unpack_from(fmt, ev['payload'], off)[0]
                            if enc.startswith('u16') or (not math.isnan(val) and not math.isinf(val)):
                                player_vals[ev['eid_be']].append(val)

                    for eid in sorted(player_vals.keys()):
                        vals = player_vals[eid]
                        avg = sum(vals) / len(vals)
                        name = eid_to_name.get(eid, '?')
                        team = eid_to_truth.get(eid, '?')
                        tb = eid_to_tb.get(eid, '?')
                        print(f"  M{mi+1:3d} {name:>15s} {str(team):>6s} {str(tb):>3s} {avg:10.1f} (n={len(vals)})")

    # ===== STEP 4: Check ALL header types in frame =====
    print("\n" + "=" * 80)
    print("[STEP 4] All [XX 04 YY] header types in frame 0")
    print("=" * 80)

    fdata = frames[0][1]
    header_counts = defaultdict(int)
    for i in range(len(fdata) - 3):
        if fdata[i + 1] == 0x04:
            h = (fdata[i], fdata[i + 2])
            header_counts[h] += 1

    print(f"  All [XX 04 YY] patterns:")
    for (a, b), count in sorted(header_counts.items(), key=lambda x: -x[1])[:25]:
        print(f"    [{a:02X} 04 {b:02X}]: {count:6d}")

    print("\n" + "=" * 80)
    print("RESEARCH COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
