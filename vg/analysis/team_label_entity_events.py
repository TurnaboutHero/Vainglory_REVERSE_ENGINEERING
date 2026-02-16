#!/usr/bin/env python3
"""
Team Label via Entity Event Position Data
============================================
Search the 37-byte entity event format for position data:
  [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]

For player entity IDs, scan ALL action codes and payload offsets
for float32 values that discriminate left vs right teams.

Focus: First 3 frames (early game = spawn positions).
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


def find_entity_events(data, valid_eids_le, max_events=5000):
    """Find [EntityID LE][00 00][ActionCode][Payload 32B] events for player eids."""
    events = []
    idx = 0
    while idx < len(data) - 37 and len(events) < max_events:
        # Check for [eid_LE 2B][00 00] pattern
        if data[idx + 2] == 0 and data[idx + 3] == 0:
            eid_le = struct.unpack_from("<H", data, idx)[0]
            if eid_le in valid_eids_le:
                action = data[idx + 4]
                payload = data[idx + 5:idx + 37]  # 32 bytes
                events.append({
                    'eid_le': eid_le,
                    'eid_be': le_to_be(eid_le),
                    'action': action,
                    'payload': payload,
                    'offset': idx,
                })
                idx += 37
                continue
        idx += 1
    return events


def main():
    print("=" * 80)
    print("ENTITY EVENT POSITION RESEARCH")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    # ===== STEP 1: Action code distribution for player entities =====
    print("\n[STEP 1] Action code distribution for player entity events")

    match = truth_data['matches'][0]
    replay_file = match['replay_file']
    with open(replay_file, 'rb') as f:
        frame0 = f.read()
    players = parse_player_blocks(frame0)
    valid_eids_le = set(p['eid_le'] for p in players)

    frames = load_frames(replay_file, max_frames=3)
    for fi, fdata in frames[:1]:
        events = find_entity_events(fdata, valid_eids_le, max_events=10000)
        print(f"\n  Frame {fi}: {len(events)} entity events for players")

        # Count by action code
        action_counts = defaultdict(int)
        for ev in events:
            action_counts[ev['action']] += 1

        print(f"  Action code distribution:")
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"    0x{action:02X}: {count:5d} events")

    # ===== STEP 2: Per-action-code float scan across matches =====
    print("\n" + "=" * 80)
    print("[STEP 2] Float scan per action code across 5 matches (frame 0 only)")
    print("=" * 80)

    # Collect all events from first 5 matches, frame 0 only
    # Group by (action_code, payload_offset, endian) and check left/right separation
    all_values = defaultdict(lambda: {'left': [], 'right': []})

    for mi, match in enumerate(truth_data['matches'][:5]):
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)
        valid_eids_le = set(p['eid_le'] for p in players)

        # Build truth team map
        eid_to_truth = {}
        for p in players:
            for pname, pdata in match['players'].items():
                short = pname.split('_', 1)[1] if '_' in pname else pname
                if p['name'] == short or p['name'] == pname:
                    eid_to_truth[p['eid_le']] = pdata['team']
                    break

        frames = load_frames(replay_file, max_frames=1)
        for fi, fdata in frames:
            events = find_entity_events(fdata, valid_eids_le, max_events=10000)

            for ev in events:
                team = eid_to_truth.get(ev['eid_le'])
                if not team:
                    continue

                action = ev['action']
                payload = ev['payload']

                # Scan every 4-byte window as float32 (BE and LE)
                for off in range(0, min(28, len(payload) - 3)):
                    # Big endian
                    val = struct.unpack_from(">f", payload, off)[0]
                    if not math.isnan(val) and not math.isinf(val) and abs(val) < 10000 and abs(val) > 0.01:
                        all_values[(action, off, 'BE')][team].append(val)

                    # Little endian
                    val = struct.unpack_from("<f", payload, off)[0]
                    if not math.isnan(val) and not math.isinf(val) and abs(val) < 10000 and abs(val) > 0.01:
                        all_values[(action, off, 'LE')][team].append(val)

    # Score each (action, offset, endian) by separation
    scored = []
    for (action, off, endian), teams in all_values.items():
        left_vals = teams['left']
        right_vals = teams['right']
        if len(left_vals) < 10 or len(right_vals) < 10:
            continue

        avg_l = sum(left_vals) / len(left_vals)
        avg_r = sum(right_vals) / len(right_vals)
        std_l = (sum((v - avg_l)**2 for v in left_vals) / len(left_vals)) ** 0.5
        std_r = (sum((v - avg_r)**2 for v in right_vals) / len(right_vals)) ** 0.5

        combined_std = std_l + std_r
        if combined_std < 0.01:
            continue

        sep = abs(avg_l - avg_r) / combined_std

        scored.append({
            'action': action,
            'offset': off,
            'endian': endian,
            'avg_left': avg_l,
            'avg_right': avg_r,
            'std_left': std_l,
            'std_right': std_r,
            'sep': sep,
            'n_left': len(left_vals),
            'n_right': len(right_vals),
        })

    scored.sort(key=lambda x: -x['sep'])

    print(f"\n  Scanned {len(all_values)} (action, offset, endian) combos")
    print(f"  {len(scored)} had sufficient data (≥10 per team)")

    print(f"\n  Top 20 discriminating (action, offset, endian):")
    print(f"  {'Act':>4s} {'Off':>4s} {'End':>3s} {'AvgL':>8s} {'AvgR':>8s} "
          f"{'StdL':>6s} {'StdR':>6s} {'Sep':>6s} {'nL':>4s} {'nR':>4s}")
    for r in scored[:20]:
        print(f"  0x{r['action']:02X} {r['offset']:4d} {r['endian']:>3s} "
              f"{r['avg_left']:8.1f} {r['avg_right']:8.1f} "
              f"{r['std_left']:6.1f} {r['std_right']:6.1f} {r['sep']:6.2f} "
              f"{r['n_left']:4d} {r['n_right']:4d}")

    # ===== STEP 3: Validate top candidates across ALL matches =====
    if scored and scored[0]['sep'] > 0.5:
        print("\n" + "=" * 80)
        print("[STEP 3] Validate top candidate across ALL 10 matches")
        print("=" * 80)

        best = scored[0]
        target_action = best['action']
        target_off = best['offset']
        target_endian = best['endian']
        fmt = ">f" if target_endian == 'BE' else "<f"

        print(f"  Testing: action=0x{target_action:02X}, offset={target_off}, endian={target_endian}")
        print(f"  Expected: left_avg≈{best['avg_left']:.1f}, right_avg≈{best['avg_right']:.1f}")

        correct = 0
        total = 0

        for mi, match in enumerate(truth_data['matches']):
            match_num = mi + 1
            replay_file = match['replay_file']
            if not Path(replay_file).exists() or "Incomplete" in replay_file:
                continue

            with open(replay_file, 'rb') as f:
                frame0 = f.read()
            players = parse_player_blocks(frame0)
            valid_eids_le = set(p['eid_le'] for p in players)

            eid_to_truth = {}
            for p in players:
                for pname, pdata in match['players'].items():
                    short = pname.split('_', 1)[1] if '_' in pname else pname
                    if p['name'] == short or p['name'] == pname:
                        eid_to_truth[p['eid_le']] = pdata['team']
                        break

            frames = load_frames(replay_file, max_frames=1)
            for fi, fdata in frames:
                events = find_entity_events(fdata, valid_eids_le, max_events=10000)

                byte1_vals = []
                byte2_vals = []
                left_vals = []
                right_vals = []

                for ev in events:
                    if ev['action'] != target_action:
                        continue
                    if target_off + 4 > len(ev['payload']):
                        continue

                    val = struct.unpack_from(fmt, ev['payload'], target_off)[0]
                    if math.isnan(val) or math.isinf(val) or abs(val) > 10000:
                        continue

                    team = eid_to_truth.get(ev['eid_le'])
                    if team == 'left':
                        left_vals.append(val)
                    elif team == 'right':
                        right_vals.append(val)

                    # Also track by team_byte
                    for p in players:
                        if p['eid_le'] == ev['eid_le']:
                            if p['team_id'] == 1:
                                byte1_vals.append(val)
                            elif p['team_id'] == 2:
                                byte2_vals.append(val)
                            break

                if left_vals and right_vals:
                    avg_l = sum(left_vals) / len(left_vals)
                    avg_r = sum(right_vals) / len(right_vals)

                    # Predict: if avg_l matches best['avg_left'] pattern
                    # Check direction consistency
                    direction_ok = (best['avg_left'] < best['avg_right'] and avg_l < avg_r) or \
                                   (best['avg_left'] > best['avg_right'] and avg_l > avg_r)

                    total += 1
                    if direction_ok:
                        correct += 1

                    b1_avg = sum(byte1_vals) / len(byte1_vals) if byte1_vals else 0
                    b2_avg = sum(byte2_vals) / len(byte2_vals) if byte2_vals else 0

                    print(f"  M{match_num}: left_avg={avg_l:7.1f}, right_avg={avg_r:7.1f} "
                          f"(b1={b1_avg:7.1f}, b2={b2_avg:7.1f}) "
                          f"→ {'OK' if direction_ok else 'FAIL'}")

        if total:
            print(f"\n  Validation: {correct}/{total} = {correct/total*100:.1f}%")
    else:
        print("\n  No candidate with separation > 0.5. Position data not found in entity events.")

        # ===== STEP 4: Look for OTHER header types near player eids =====
        print("\n" + "=" * 80)
        print("[STEP 4] Search for other event headers near player entity IDs")
        print("=" * 80)

        match = truth_data['matches'][0]
        replay_file = match['replay_file']
        frames = load_frames(replay_file, max_frames=1)

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)
        valid_eids_be = set(p['eid_be'] for p in players)

        # Find all 3-byte patterns that appear before player eids (BE)
        header_counts = defaultdict(int)
        for fi, fdata in frames:
            for eid_be in valid_eids_be:
                eid_bytes = struct.pack(">H", eid_be)
                pos = 0
                while True:
                    pos = fdata.find(eid_bytes, pos)
                    if pos == -1:
                        break
                    # Check various offsets before eid for 3-byte headers
                    for pre_off in [2, 3, 4, 5]:
                        if pos >= pre_off:
                            header = fdata[pos - pre_off:pos - pre_off + 3]
                            header_counts[(header.hex(), pre_off)] += 1
                    pos += 1

        print(f"  3-byte patterns before player eids (BE) in frame 0:")
        for (hex_str, pre_off), count in sorted(header_counts.items(), key=lambda x: -x[1])[:20]:
            print(f"    {hex_str} (at -{pre_off}): {count} occurrences")

    print("\n" + "=" * 80)
    print("RESEARCH COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
