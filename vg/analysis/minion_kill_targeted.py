#!/usr/bin/env python3
"""
Minion Kill Targeted Search - Use known record structure to find minion kill pattern.

Known patterns:
  Kill:  [18 04 1C] [00 00] [killer_eid BE] ...
  Death: [08 04 31] [00 00] [victim_eid BE] ...
  Credit:[10 04 1D] [00 00] [eid BE] ...

All follow format: [3-byte header] [00 00] [eid BE uint16]
So minion kills likely follow the same format with a different header.

Strategy:
1. Find ALL positions of player entity IDs (BE) in concatenated frames
2. Check if [00 00] appears at offset -2 from entity ID
3. If so, extract 3 bytes before [00 00] as candidate action code
4. Count candidate codes per player
5. Match against truth minion_kills

Also try: the entity ID might be the VICTIM (minion), not the player.
In that case, look for player entity IDs at different positions relative to the action code.
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

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


def approach1_action_codes(data, players, truth_mk):
    """Find action codes before [00 00] [player_eid BE]."""
    print("\n  === Approach 1: [header 3B] [00 00] [player_eid BE] ===")

    # Count action codes per player
    code_counts = defaultdict(lambda: defaultdict(int))  # code -> {eid_be: count}

    for p in players:
        eid_bytes = struct.pack('>H', p['eid_be'])
        pos = 0
        while True:
            pos = data.find(eid_bytes, pos)
            if pos == -1:
                break
            # Check for [00 00] at offset -2
            if pos >= 5 and data[pos-2:pos] == b'\x00\x00':
                code = data[pos-5:pos-2]
                code_counts[code][p['eid_be']] += 1
            pos += 1

    # Check which codes match truth minion_kills
    print(f"  Found {len(code_counts)} unique 3-byte codes before [00 00] [eid]")

    matches = []
    close_matches = []

    for code, eid_counts in code_counts.items():
        if len(eid_counts) < 5:  # Must appear for at least 5 players
            continue

        # Check exact match
        exact = True
        close = True
        total_diff = 0
        for eid_be, truth_count in truth_mk.items():
            detected = eid_counts.get(eid_be, 0)
            if detected != truth_count:
                exact = False
            diff = abs(detected - truth_count)
            total_diff += diff
            if diff > max(3, truth_count * 0.2):
                close = False

        code_hex = ' '.join(f'{b:02X}' for b in code)
        if exact:
            print(f"  EXACT MATCH: [{code_hex}]")
            matches.append(code)
        elif close:
            print(f"  CLOSE MATCH: [{code_hex}] total_diff={total_diff}")
            for eid_be in sorted(truth_mk.keys()):
                t = truth_mk[eid_be]
                d = eid_counts.get(eid_be, 0)
                flag = "OK" if t == d else f"diff={d-t:+d}"
                print(f"    EID {eid_be}: truth={t:4d}, detected={d:4d} {flag}")
            close_matches.append((code, total_diff))

    # Also show top codes by total count
    if not matches and not close_matches:
        print("\n  Top 20 action codes by total player-entity hits:")
        ranked = sorted(code_counts.items(),
                       key=lambda x: sum(x[1].values()), reverse=True)
        for code, eid_counts in ranked[:20]:
            code_hex = ' '.join(f'{b:02X}' for b in code)
            total = sum(eid_counts.values())
            n_players = len(eid_counts)
            # Show per-player counts
            counts_str = ', '.join(f'{eid_counts.get(eid, 0)}' for eid in sorted(truth_mk.keys()))
            truth_str = ', '.join(f'{truth_mk[eid]}' for eid in sorted(truth_mk.keys()))
            print(f"    [{code_hex}] total={total:5d}, {n_players} players: [{counts_str}]")
            if code == ranked[0][0]:  # For top code, also show truth
                print(f"    {'':15s} truth: [{truth_str}]")

    return matches


def approach2_wider_offsets(data, players, truth_mk):
    """Try wider search: entity ID at various offsets from 1-3 byte patterns."""
    print("\n  === Approach 2: Brute-force ALL 2-byte patterns, wider offsets ===")

    # Instead of top-N, try ALL 2-byte patterns that appear frequently enough
    # For each player's entity ID, find all occurrences
    eid_positions = {}
    for p in players:
        eid_bytes = struct.pack('>H', p['eid_be'])
        positions = []
        pos = 0
        while True:
            pos = data.find(eid_bytes, pos)
            if pos == -1:
                break
            positions.append(pos)
            pos += 1
        eid_positions[p['eid_be']] = positions

    # For each offset from entity ID position, extract 2-byte values and count
    # Then check if any 2-byte value's count matches truth
    min_mk = min(truth_mk.values())
    max_mk = max(truth_mk.values())
    total_mk = sum(truth_mk.values())

    print(f"  Truth minion_kills range: {min_mk} - {max_mk}, total: {total_mk}")

    for delta in range(-20, 21):
        if delta in (0, 1):  # Skip entity ID itself
            continue

        # For each player, extract 2-byte values at this offset
        pattern_counts = defaultdict(lambda: defaultdict(int))

        for eid_be, positions in eid_positions.items():
            for epos in positions:
                vpos = epos + delta
                if vpos < 0 or vpos + 2 > len(data):
                    continue
                val = data[vpos:vpos+2]
                pattern_counts[val][eid_be] += 1

        # Check each pattern
        for pattern, eid_counts in pattern_counts.items():
            if len(eid_counts) < 5:
                continue

            # Check exact match
            exact = True
            for eid_be, truth_count in truth_mk.items():
                if eid_counts.get(eid_be, 0) != truth_count:
                    exact = False
                    break

            if exact:
                pat_hex = ' '.join(f'{b:02X}' for b in pattern)
                print(f"  EXACT MATCH at delta={delta:+d}: pattern=[{pat_hex}]")
                for eid_be in sorted(truth_mk.keys()):
                    print(f"    EID {eid_be}: {truth_mk[eid_be]}")
                return [pattern]

    print("  No exact matches found with 2-byte patterns")
    return []


def approach3_single_byte_action(data, players, truth_mk):
    """Try: [eid BE] [00 00] [single action byte] ... counting per player."""
    print("\n  === Approach 3: [eid BE] [00 00] [action byte] ===")

    code_counts = defaultdict(lambda: defaultdict(int))

    for p in players:
        eid_bytes = struct.pack('>H', p['eid_be'])
        pos = 0
        while True:
            pos = data.find(eid_bytes, pos)
            if pos == -1:
                break
            # Check for [00 00] after entity ID, then action byte
            if pos + 5 <= len(data) and data[pos+2:pos+4] == b'\x00\x00':
                action = data[pos+4]
                code_counts[action][p['eid_be']] += 1
            pos += 1

    print(f"  Found {len(code_counts)} unique action bytes after [eid] [00 00]")

    for action in sorted(code_counts.keys()):
        eid_counts = code_counts[action]
        if len(eid_counts) < 5:
            continue

        exact = all(eid_counts.get(eid, 0) == truth_mk[eid] for eid in truth_mk)
        if exact:
            print(f"  EXACT MATCH: action=0x{action:02X}")
            return [bytes([action])]

        # Check closeness
        total_diff = sum(abs(eid_counts.get(eid, 0) - truth_mk[eid]) for eid in truth_mk)
        total_truth = sum(truth_mk.values())
        if total_diff < total_truth * 0.1:  # Within 10%
            counts_str = ', '.join(f'{eid_counts.get(eid, 0)}' for eid in sorted(truth_mk.keys()))
            truth_str = ', '.join(f'{truth_mk[eid]}' for eid in sorted(truth_mk.keys()))
            print(f"  CLOSE: action=0x{action:02X} diff={total_diff}/{total_truth}")
            print(f"    Detected: [{counts_str}]")
            print(f"    Truth:    [{truth_str}]")

    return []


def approach4_cumulative_counter(data, players, truth_mk):
    """Look for minion kill counter stored as a value in the LAST frame only."""
    print("\n  === Approach 4: Counter value in last frame (near entity ID) ===")

    # Load just the last frame
    # Actually we have all frames concatenated. Let me work with what we have.
    # For each player, find their entity ID in the last portion of data.
    # Check if any nearby uint16/uint32 value matches their truth minion_kills.

    # We need the last frame separately
    return []


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    for match_idx in [0, 1, 2]:
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}: {match['replay_name'][:50]}...")

        data, n_frames = load_all_frames(match['replay_file'])
        frame0 = Path(match['replay_file']).parent
        base = Path(match['replay_file']).stem.rsplit('.', 1)[0]
        frame0_path = list(frame0.glob(f'{base}.0.vgr'))[0]
        frame0_data = frame0_path.read_bytes()
        players = extract_players(frame0_data)

        # Map truth to entity IDs
        truth_mk = {}
        for tname, tdata in match['players'].items():
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p in players:
                if p['name'] == short or tname.endswith(p['name']):
                    truth_mk[p['eid_be']] = tdata.get('minion_kills', 0)
                    break

        print(f"  Players: {len(truth_mk)}, Frames: {n_frames}")
        print(f"  Truth minion_kills:")
        for eid_be in sorted(truth_mk.keys()):
            name = next((p['name'] for p in players if p['eid_be'] == eid_be), '?')
            print(f"    {name:15s} (EID {eid_be}): {truth_mk[eid_be]}")

        # Run all approaches
        approach1_action_codes(data, players, truth_mk)
        approach3_single_byte_action(data, players, truth_mk)
        approach2_wider_offsets(data, players, truth_mk)


if __name__ == '__main__':
    main()
