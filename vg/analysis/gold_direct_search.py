#!/usr/bin/env python3
"""
Gold Direct Search - Find where total gold values are stored in replay frames.

Strategy: Search for known truth gold values (as various encodings) in the last frame,
then check if player entity IDs are nearby at consistent offsets.

Gold values in truth: 5800, 6300, 8600, 8700, 10600, 11800, 12900 etc.
These could be stored as: uint16 LE, uint16 BE, uint32 LE, uint32 BE, float32 LE, float32 BE
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']


def extract_players(data):
    """Extract player info from frame data."""
    players = []
    seen_eids = set()
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(data):
                eid_le = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                eid_be = struct.unpack('>H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                team_byte = data[pos + 0xD5]
                team = "left" if team_byte == 1 else "right" if team_byte == 2 else "?"
                name_start = pos + len(marker)
                name_end = name_start
                while name_end < len(data) and name_end < name_start + 30:
                    b = data[name_end]
                    if b < 32 or b > 126:
                        break
                    name_end += 1
                name = data[name_start:name_end].decode('ascii', errors='replace')
                if eid_le not in seen_eids and len(name) >= 3 and not name.startswith('GameMode'):
                    players.append({
                        'name': name, 'eid_le': eid_le, 'eid_be': eid_be,
                        'team': team, 'block_pos': pos,
                    })
                    seen_eids.add(eid_le)
            pos += 1
    return players


def load_frames(replay_file):
    """Load all frame files from replay directory."""
    replay_path = Path(replay_file)
    replay_dir = replay_path.parent
    base_name = replay_path.stem.rsplit('.', 1)[0]
    frames = sorted(
        replay_dir.glob(f'{base_name}.*.vgr'),
        key=lambda p: int(p.stem.split('.')[-1])
    )
    return frames


def search_gold_in_frame(data, players, truth_gold_map):
    """Search for truth gold values in frame data.

    truth_gold_map: dict of player_name -> gold_value
    Returns: dict of encoding -> offset_from_eid -> list of matches
    """
    # Build name -> eid mapping
    name_to_player = {}
    for p in players:
        for tname in truth_gold_map:
            if tname.split('_', 1)[-1] == p['name'] or tname.endswith(p['name']):
                name_to_player[tname] = p
                break

    # For each player, search for their gold value in various encodings
    results = defaultdict(lambda: defaultdict(list))

    for tname, gold in truth_gold_map.items():
        player = name_to_player.get(tname)
        if not player:
            continue

        # Try different encodings of the gold value
        encodings = {}

        # Exact value as uint16 LE/BE (if fits)
        if gold <= 65535:
            encodings['u16_le'] = struct.pack('<H', gold)
            encodings['u16_be'] = struct.pack('>H', gold)

        # As uint32 LE/BE
        encodings['u32_le'] = struct.pack('<I', gold)
        encodings['u32_be'] = struct.pack('>I', gold)

        # As float32 LE/BE
        encodings['f32_le'] = struct.pack('<f', float(gold))
        encodings['f32_be'] = struct.pack('>f', float(gold))

        # Gold divided by 100 (maybe stored as hundreds)
        gold_100 = gold // 100
        if gold_100 <= 65535:
            encodings['u16_le_div100'] = struct.pack('<H', gold_100)
            encodings['u16_be_div100'] = struct.pack('>H', gold_100)
        encodings['f32_le_div100'] = struct.pack('<f', float(gold_100))
        encodings['f32_be_div100'] = struct.pack('>f', float(gold_100))

        eid_le_bytes = struct.pack('<H', player['eid_le'])
        eid_be_bytes = struct.pack('>H', player['eid_le'])

        for enc_name, enc_bytes in encodings.items():
            pos = 0
            while True:
                pos = data.find(enc_bytes, pos)
                if pos == -1:
                    break

                # Check nearby offsets for player entity ID
                for delta in range(-40, 41):
                    if delta == 0:
                        continue
                    check = pos + delta
                    if check < 0 or check + 2 > len(data):
                        continue

                    if data[check:check+2] == eid_le_bytes:
                        results[enc_name][(delta, 'LE')].append({
                            'player': tname, 'gold': gold,
                            'gold_pos': pos, 'eid_pos': check,
                        })
                    if data[check:check+2] == eid_be_bytes:
                        results[enc_name][(delta, 'BE')].append({
                            'player': tname, 'gold': gold,
                            'gold_pos': pos, 'eid_pos': check,
                        })

                pos += 1

    return results


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Use first 3 matches for research
    for match_idx in [0, 1, 2]:
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}: {match['replay_name'][:40]}...")

        frames = load_frames(match['replay_file'])
        if not frames:
            print("  No frames found!")
            continue

        # Get players from frame 0
        frame0_data = frames[0].read_bytes()
        players = extract_players(frame0_data)

        # Build truth gold map
        truth_gold = {}
        for pname, pdata in match['players'].items():
            truth_gold[pname] = pdata['gold']

        print(f"  Players: {len(players)}, Frames: {len(frames)}")
        print(f"  Truth gold: {truth_gold}")

        # Search in LAST frame
        last_data = frames[-1].read_bytes()
        print(f"  Last frame size: {len(last_data):,} bytes")

        results = search_gold_in_frame(last_data, players, truth_gold)

        # Report encodings with matches for multiple players
        print(f"\n  Encoding patterns with player EID nearby:")
        for enc_name in sorted(results.keys()):
            for (delta, endian), matches in sorted(results[enc_name].items(), key=lambda x: -len(x[1])):
                unique_players = len(set(m['player'] for m in matches))
                if unique_players >= 3:  # At least 3 different players match
                    print(f"    {enc_name} @ delta={delta:+d} ({endian}): {unique_players} players matched")
                    for m in matches[:5]:
                        print(f"      {m['player']}: gold={m['gold']} at 0x{m['gold_pos']:X}")

        # Also search in frame 0 (player blocks might store gold)
        print(f"\n  --- Searching player block region in last frame ---")
        for p in players:
            # Find this player's block in last frame
            for marker in PLAYER_MARKERS:
                pos = 0
                while True:
                    pos = last_data.find(marker, pos)
                    if pos == -1:
                        break
                    if pos + 0xD6 <= len(last_data):
                        eid = struct.unpack('<H', last_data[pos + 0xA5:pos + 0xA5 + 2])[0]
                        if eid == p['eid_le']:
                            # Search gold value near this player block
                            tname = None
                            for tn in truth_gold:
                                if tn.split('_', 1)[-1] == p['name'] or tn.endswith(p['name']):
                                    tname = tn
                                    break
                            if tname:
                                gold = truth_gold[tname]
                                # Scan +0x00 to +0x200 for gold value
                                block = last_data[pos:pos + 0x300]
                                for enc_name, enc_bytes in [
                                    ('u16_le', struct.pack('<H', gold) if gold <= 65535 else None),
                                    ('u32_le', struct.pack('<I', gold)),
                                    ('f32_be', struct.pack('>f', float(gold))),
                                    ('f32_le', struct.pack('<f', float(gold))),
                                ]:
                                    if enc_bytes is None:
                                        continue
                                    off = block.find(enc_bytes)
                                    if off != -1:
                                        print(f"    {p['name']:15s} gold={gold:6d} found as {enc_name} at block+0x{off:03X}")
                    pos += 1


if __name__ == '__main__':
    main()
