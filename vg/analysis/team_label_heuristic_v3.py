#!/usr/bin/env python3
"""
Team Label Heuristic Research v3
=================================
Deep investigation into the team_byte <-> name prefix relationship.

v2 findings:
- Name prefix does NOT predict left/right (20%)
- Entity IDs are interleaved
- No header bytes discriminate
- team_byte=1 does NOT consistently map to lower or higher prefix

New hypotheses:
- H1: The "x+1" prefix (e.g., 2600 vs 2599) = LEFT team always
- H2: The prefix that's a multiple of some number = LEFT
- H3: Some byte in the FULL player block (not just 0xC0-0xE0) predicts truth team
- H4: The "sub" player (prefix xx04) always follows one team
- H5: Scan wider range of offsets in player block for truth-team indicator
- H6: Look at entity ID big-endian representation for patterns
"""

import json
import struct
from pathlib import Path
from collections import defaultdict

TRUTH_PATH = r'D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_truth.json'

SWAP_STATUS = {
    1: False, 2: True, 3: True, 4: False, 5: True,
    6: False, 7: False, 8: True, 9: None, 10: True, 11: False,
}

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])


def parse_player_blocks_extended(data):
    """Parse player blocks with FULL byte dump (0x00 - 0x100)."""
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""

            if len(name) >= 3 and not name.startswith('GameMode'):
                if name not in seen:
                    entity_id_le = None
                    if pos + 0xA5 + 2 <= len(data):
                        entity_id_le = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little')

                    team_id = None
                    if pos + 0xD5 < len(data):
                        team_id = data[pos + 0xD5]

                    # Full byte dump: 0x00 to 0x100
                    full_bytes = {}
                    for off in range(0x00, 0x100):
                        if pos + off < len(data):
                            full_bytes[off] = data[pos + off]

                    players.append({
                        'name': name,
                        'entity_id_le': entity_id_le,
                        'team_id': team_id,
                        'block_offset': pos,
                        'marker': marker.hex(),
                        'position': len(players),
                        'full_bytes': full_bytes,
                    })
                    seen.add(name)

        search_start = pos + 1

    return players


def get_name_prefix(name):
    parts = name.split('_', 1)
    if len(parts) > 1 and parts[0].isdigit():
        return int(parts[0])
    # Handle case like "3000" with no underscore
    if name.isdigit():
        return int(name)
    return None


def main():
    print("=" * 80)
    print("TEAM LABEL HEURISTIC RESEARCH v3 - EXHAUSTIVE BYTE SCAN")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    # ===== ANALYSIS 1: Prefix pattern analysis =====
    print("\n[OBJECTIVE] Find which PREFIX maps to LEFT across all matches")
    print()

    # Check: is the HIGHER of the two main prefixes always LEFT?
    # Main prefixes: the two that have >= 4 players
    print("=" * 80)
    print("PREFIX ANALYSIS: Which prefix number maps to LEFT?")
    print("=" * 80)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        status = 'SWAPPED' if swapped else ('CORRECT' if swapped is False else 'INCOMPLETE')

        prefix_groups = defaultdict(lambda: {'left': 0, 'right': 0})
        for pname, pdata in match['players'].items():
            prefix = get_name_prefix(pname)
            if prefix is not None:
                prefix_groups[prefix][pdata['team']] += 1

        sorted_prefs = sorted(prefix_groups.keys())

        # Identify which prefix is "left team"
        left_prefix = None
        right_prefix = None
        for pref in sorted_prefs:
            counts = prefix_groups[pref]
            if counts['left'] > counts['right']:
                left_prefix = pref
            elif counts['right'] > counts['left']:
                right_prefix = pref

        # Check prefix relationship
        if left_prefix and right_prefix:
            diff = left_prefix - right_prefix
            ratio = left_prefix / right_prefix if right_prefix else 0
            mod_left = left_prefix % 100
            mod_right = right_prefix % 100
            print(f"  M{match_num:2d} ({status:9s}): LEFT_pref={left_prefix}  RIGHT_pref={right_prefix}  "
                  f"diff={diff:+4d}  left%100={mod_left}  right%100={mod_right}")

    # ===== ANALYSIS 2: Check if left_prefix % 100 is always a specific value =====
    print("\n" + "=" * 80)
    print("KEY INSIGHT: Name prefix modulo patterns")
    print("=" * 80)

    left_mods = []
    right_mods = []
    sub_mods = []  # The "sub" player (prefix ending in 04)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        prefix_groups = defaultdict(lambda: {'left': 0, 'right': 0})
        for pname, pdata in match['players'].items():
            prefix = get_name_prefix(pname)
            if prefix is not None:
                prefix_groups[prefix][pdata['team']] += 1

        for pref, counts in prefix_groups.items():
            mod = pref % 100
            if counts['left'] > counts['right']:
                left_mods.append((match_num, pref, mod))
            elif counts['right'] > counts['left']:
                right_mods.append((match_num, pref, mod))

    print(f"\n  LEFT team prefixes and their mod-100:")
    for mn, pref, mod in left_mods:
        print(f"    M{mn}: prefix={pref}, mod100={mod}")

    print(f"\n  RIGHT team prefixes and their mod-100:")
    for mn, pref, mod in right_mods:
        print(f"    M{mn}: prefix={pref}, mod100={mod}")

    left_mod_set = set(m for _, _, m in left_mods)
    right_mod_set = set(m for _, _, m in right_mods)
    print(f"\n  LEFT  mod100 values: {sorted(left_mod_set)}")
    print(f"  RIGHT mod100 values: {sorted(right_mod_set)}")

    if not left_mod_set.intersection(right_mod_set):
        print(f"  *** PERFECT SEPARATOR: left mod100 != right mod100 ***")
    else:
        print(f"  Overlap: {left_mod_set.intersection(right_mod_set)}")

    # ===== ANALYSIS 3: Exhaustive byte scan =====
    print("\n" + "=" * 80)
    print("EXHAUSTIVE BYTE SCAN: Find ANY byte in player block that predicts truth team")
    print("=" * 80)
    print("  For each offset 0x00-0xFF, check if values separate truth=left from truth=right")

    # Collect: for each offset, all values seen for left-team players vs right-team players
    offset_left_vals = defaultdict(list)
    offset_right_vals = defaultdict(list)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)

        # Match to truth
        for p in players:
            p['truth_team'] = None
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

            if not p['truth_team']:
                continue

            for off, val in p['full_bytes'].items():
                if p['truth_team'] == 'left':
                    offset_left_vals[off].append((match_num, val, p['name']))
                else:
                    offset_right_vals[off].append((match_num, val, p['name']))

    # Find discriminating offsets
    print("\n  Checking 256 offsets...")
    discriminators = []

    for off in range(0x100):
        left_vals = set(v for _, v, _ in offset_left_vals.get(off, []))
        right_vals = set(v for _, v, _ in offset_right_vals.get(off, []))

        if left_vals and right_vals:
            overlap = left_vals.intersection(right_vals)
            if not overlap:
                discriminators.append((off, left_vals, right_vals))
                print(f"  *** Offset 0x{off:02X}: PERFECT - left={sorted(left_vals)}, right={sorted(right_vals)}")
            elif len(overlap) < min(len(left_vals), len(right_vals)) * 0.3:
                # Partial discriminator
                pct_overlap = len(overlap) / max(len(left_vals), len(right_vals)) * 100
                if pct_overlap < 20:
                    print(f"      Offset 0x{off:02X}: PARTIAL ({pct_overlap:.0f}% overlap) - "
                          f"left unique={sorted(left_vals - overlap)}, right unique={sorted(right_vals - overlap)}, "
                          f"shared={sorted(overlap)}")

    if not discriminators:
        print("  No perfect discriminators found in player block bytes 0x00-0xFF")

    # ===== ANALYSIS 4: Check team_byte vs truth with prefix =====
    # The key: name prefix is ALWAYS available in binary.
    # So: group by prefix, check team_byte. If team_byte varies for same prefix across matches,
    # that means prefix alone can't be used... but maybe prefix + team_byte + some rule?

    print("\n" + "=" * 80)
    print("CRITICAL: Prefix + team_byte -> truth team correlation table")
    print("=" * 80)

    # For each match: what team_byte does the LEFT-team prefix get?
    print(f"\n  {'Match':>5s}  {'Left Prefix':>12s}  {'L-byte':>7s}  {'Right Prefix':>13s}  {'R-byte':>7s}  {'Swapped':>8s}")
    print(f"  {'-----':>5s}  {'----------':>12s}  {'------':>7s}  {'----------':>13s}  {'------':>7s}  {'-------':>8s}")

    correlation_data = []

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)

        # Match to truth
        for p in players:
            p['truth_team'] = None
            p['prefix'] = get_name_prefix(p['name'])
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    p['truth_name'] = tname
                    break

        # Find which prefix = left team, and what team_byte that prefix gets
        prefix_team_bytes = defaultdict(lambda: {'team_bytes': set(), 'truth_teams': set()})
        for p in players:
            pref = p['prefix']
            if pref is None:
                continue
            prefix_team_bytes[pref]['team_bytes'].add(p['team_id'])
            if p['truth_team']:
                prefix_team_bytes[pref]['truth_teams'].add(p['truth_team'])

        left_pref = None
        right_pref = None
        left_byte = None
        right_byte = None

        for pref, info in prefix_team_bytes.items():
            if 'left' in info['truth_teams'] and len(info['truth_teams']) == 1:
                left_pref = pref
                left_byte = sorted(info['team_bytes'])[0] if info['team_bytes'] else None
            elif 'right' in info['truth_teams'] and len(info['truth_teams']) == 1:
                right_pref = pref
                right_byte = sorted(info['team_bytes'])[0] if info['team_bytes'] else None

        status = 'SWAPPED' if swapped else 'CORRECT'
        if left_pref and right_pref:
            print(f"  M{match_num:3d}  {left_pref:12d}  {left_byte:7d}  {right_pref:13d}  {right_byte:7d}  {status:>8s}")
            correlation_data.append({
                'match': match_num,
                'left_pref': left_pref,
                'left_byte': left_byte,
                'right_pref': right_pref,
                'right_byte': right_byte,
                'swapped': swapped,
            })

    # ===== ANALYSIS 5: Is there a rule based on prefix value? =====
    print("\n" + "=" * 80)
    print("RULE EXTRACTION: What determines team_byte assignment?")
    print("=" * 80)

    # Check: does left team ALWAYS get team_byte equal to (prefix relationship)?
    print("\n  In CORRECT matches (team_byte=1 -> left):")
    for d in correlation_data:
        if not d['swapped']:
            print(f"    M{d['match']}: left_pref={d['left_pref']} gets byte={d['left_byte']}, "
                  f"right_pref={d['right_pref']} gets byte={d['right_byte']}")

    print("\n  In SWAPPED matches (team_byte=1 -> right):")
    for d in correlation_data:
        if d['swapped']:
            print(f"    M{d['match']}: left_pref={d['left_pref']} gets byte={d['left_byte']}, "
                  f"right_pref={d['right_pref']} gets byte={d['right_byte']}")

    # ===== ANALYSIS 6: Entity ID Big Endian values =====
    print("\n" + "=" * 80)
    print("ENTITY ID: Big Endian representation analysis")
    print("=" * 80)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)

        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        for p in sorted(players, key=lambda x: x['entity_id_le']):
            eid_le = p['entity_id_le']
            eid_be = struct.pack('>H', eid_le)
            eid_be_val = struct.unpack('>H', struct.pack('<H', eid_le))[0]
            truth = p.get('truth_team', '?')
            print(f"    {p['name']:20s}  eid_LE=0x{eid_le:04X}({eid_le:5d})  "
                  f"eid_BE=0x{eid_be_val:04X}({eid_be_val:5d})  "
                  f"team_byte={p['team_id']}  truth={truth if truth else '?'}")

    # ===== ANALYSIS 7: Read bytes BEFORE player block marker =====
    print("\n" + "=" * 80)
    print("PRE-MARKER BYTES: Check 16 bytes BEFORE each player block marker")
    print("=" * 80)

    # Maybe the team is encoded BEFORE the DA 03 EE marker
    pre_marker_left = defaultdict(list)
    pre_marker_right = defaultdict(list)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)

        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

            if not p.get('truth_team'):
                continue

            block_off = p['block_offset']
            if block_off >= 32:
                for i in range(32):
                    byte_off = block_off - 32 + i
                    val = data[byte_off]
                    key = f'pre_{32-i}'  # pre_32 to pre_1
                    if p['truth_team'] == 'left':
                        pre_marker_left[key].append(val)
                    else:
                        pre_marker_right[key].append(val)

    # Check for discriminating pre-marker bytes
    for i in range(32, 0, -1):
        key = f'pre_{i}'
        left_vals = set(pre_marker_left.get(key, []))
        right_vals = set(pre_marker_right.get(key, []))
        if left_vals and right_vals and not left_vals.intersection(right_vals):
            print(f"  *** pre_{i} bytes before marker: PERFECT - left={sorted(left_vals)}, right={sorted(right_vals)}")

    print("  (Checking for partial discriminators with < 30% overlap...)")
    for i in range(32, 0, -1):
        key = f'pre_{i}'
        left_vals = set(pre_marker_left.get(key, []))
        right_vals = set(pre_marker_right.get(key, []))
        if left_vals and right_vals:
            overlap = left_vals.intersection(right_vals)
            if overlap and len(overlap) < max(len(left_vals), len(right_vals)) * 0.3:
                print(f"      pre_{i}: PARTIAL - left unique={sorted(left_vals - overlap)}, "
                      f"right unique={sorted(right_vals - overlap)}, shared={sorted(overlap)}")

    # ===== ANALYSIS 8: Block-to-block gap analysis =====
    print("\n" + "=" * 80)
    print("BLOCK GAP: Distance between consecutive player blocks")
    print("=" * 80)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)
        players_sorted = sorted(players, key=lambda p: p['block_offset'])

        for p in players_sorted:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        prev_off = None
        for p in players_sorted:
            gap = p['block_offset'] - prev_off if prev_off is not None else 0
            truth = p.get('truth_team', '?')
            print(f"    offset=0x{p['block_offset']:06X}  gap={gap:5d}  "
                  f"{p['name']:20s}  team_byte={p['team_id']}  truth={truth if truth else '?'}")
            prev_off = p['block_offset']

    # ===== FINAL: Check entity ID byte at 0xA5 interpreted differently =====
    print("\n" + "=" * 80)
    print("ENTITY ID DECOMPOSITION: Check if any bits of entity ID correlate with team")
    print("=" * 80)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_extended(data)

        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        for p in sorted(players, key=lambda x: x['entity_id_le']):
            eid = p['entity_id_le']
            # Decompose: eid = base + slot
            # In Vainglory: entity IDs seem to be base + (256 * slot_index)
            base = eid % 256
            slot = eid // 256
            truth = p.get('truth_team', '?')
            print(f"    {p['name']:20s}  eid={eid:5d} = {slot}*256 + {base:3d}  "
                  f"team_byte={p['team_id']}  truth={truth if truth else '?'}")


if __name__ == '__main__':
    main()
