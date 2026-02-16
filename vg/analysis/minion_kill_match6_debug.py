#!/usr/bin/env python3
"""
Debug Match 6 minion kill under-counting.

Match 6 detects significantly fewer minion kills than truth (e.g., 226 vs 234).
Investigate: are there minion kill records with different structure in this match?
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


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


def scan_credit_actions(data, valid_eids):
    """Scan ALL credit records and categorize by action byte."""
    action_counts = defaultdict(lambda: defaultdict(int))

    pos = 0
    while True:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue

        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in valid_eids:
            pos += 1
            continue

        value = struct.unpack_from(">f", data, pos + 7)[0]
        action_byte = data[pos + 11] if pos + 12 <= len(data) else None

        if abs(value - 1.0) < 0.01 and action_byte is not None:
            action_counts[action_byte][eid] += 1

        pos += 3  # Skip header

    return action_counts


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Compare Match 6 vs Match 1 (good match)
    for match_idx in [0, 5]:  # Match 1 and Match 6
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}: {match['replay_name'][:50]}...")

        p = Path(match['replay_file'])
        d = p.parent
        base = p.stem.rsplit('.', 1)[0]
        frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))

        data = b''
        for f in frames:
            data += f.read_bytes()

        f0 = frames[0].read_bytes()
        players = extract_players(f0)
        valid_eids = set()
        truth_mk = {}
        for tname, tdata in match['players'].items():
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p_obj in players:
                if p_obj['name'] == short or tname.endswith(p_obj['name']):
                    valid_eids.add(p_obj['eid_be'])
                    truth_mk[p_obj['eid_be']] = tdata.get('minion_kills', 0)
                    break

        print(f"  Frames: {len(frames)}, Data: {len(data):,} bytes")

        # Scan all credit records with value=1.0 and categorize by action byte
        action_counts = scan_credit_actions(data, valid_eids)

        print(f"\n  Action bytes after credit [10 04 1D][00 00][eid][1.0]:")
        for action in sorted(action_counts.keys()):
            eid_counts = action_counts[action]
            total = sum(eid_counts.values())
            counts_str = ', '.join(f'{eid_counts.get(eid, 0)}' for eid in sorted(truth_mk.keys()))
            truth_str = ', '.join(f'{truth_mk[eid]}' for eid in sorted(truth_mk.keys()))
            # Check if this matches truth
            match_pct = sum(1 for eid in truth_mk if eid_counts.get(eid, 0) == truth_mk[eid]) / len(truth_mk) * 100
            print(f"    0x{action:02X}: total={total:5d} [{counts_str}]  match={match_pct:.0f}%")
            if action == 0x0E:
                print(f"    {'':6s} truth:        [{truth_str}]")
                # Show per-player diff
                for eid in sorted(truth_mk.keys()):
                    t = truth_mk[eid]
                    d_val = eid_counts.get(eid, 0)
                    if t != d_val:
                        name = next((pp['name'] for pp in players if pp['eid_be'] == eid), '?')
                        print(f"          {name}: truth={t}, detected={d_val}, diff={d_val-t:+d}")

        # Check if combining action bytes could work
        print(f"\n  Combining action bytes:")
        # Try 0x0E alone
        e_counts = action_counts.get(0x0E, {})
        total_diff_0e = sum(abs(e_counts.get(eid, 0) - truth_mk[eid]) for eid in truth_mk)
        print(f"    0x0E alone: total_diff={total_diff_0e}")

        # Try 0x0E + 0x0F
        combined = defaultdict(int)
        for action in [0x0E, 0x0F]:
            for eid, c in action_counts.get(action, {}).items():
                combined[eid] += c
        total_diff_ef = sum(abs(combined.get(eid, 0) - truth_mk[eid]) for eid in truth_mk)
        print(f"    0x0E + 0x0F: total_diff={total_diff_ef}")

        # Try other combinations
        for action2 in sorted(action_counts.keys()):
            if action2 == 0x0E:
                continue
            combined2 = defaultdict(int)
            for eid, c in e_counts.items():
                combined2[eid] += c
            for eid, c in action_counts.get(action2, {}).items():
                combined2[eid] += c
            total_diff2 = sum(abs(combined2.get(eid, 0) - truth_mk[eid]) for eid in truth_mk)
            if total_diff2 < total_diff_0e:
                print(f"    0x0E + 0x{action2:02X}: total_diff={total_diff2} (better!)")

        # Frame-by-frame analysis: check if missing kills happen at specific times
        print(f"\n  Frame-by-frame minion kill accumulation:")
        cumulative = defaultdict(int)
        for fi, frame_path in enumerate(frames):
            fdata = frame_path.read_bytes()
            frame_actions = scan_credit_actions(fdata, valid_eids)
            frame_0e = frame_actions.get(0x0E, {})
            for eid, c in frame_0e.items():
                cumulative[eid] += c

            if fi % 30 == 0 or fi == len(frames) - 1:
                total = sum(cumulative.values())
                print(f"    Frame {fi:4d}: total_minion_kills={total}")


if __name__ == '__main__':
    main()
