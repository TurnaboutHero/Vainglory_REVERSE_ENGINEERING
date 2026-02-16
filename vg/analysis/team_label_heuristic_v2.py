#!/usr/bin/env python3
"""
Team Label Heuristic Research v2
=================================
Focused analysis on the NAME PREFIX pattern discovered in v1.

Key observation from v1: Player names have numeric prefixes (e.g., "2600_Acex").
These prefixes group players into teams. The lower prefix in each match
MIGHT consistently map to one side.

Also deep-dive into:
- Entity ID interleaving patterns
- Whether team_byte correlates with name prefix ordering
- Exact relationship between prefix values and team assignment
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


def parse_player_blocks_raw(data):
    """Parse player blocks from frame 0."""
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

                    hero_id = None
                    if pos + 0xA9 + 2 <= len(data):
                        hero_id = int.from_bytes(data[pos + 0xA9:pos + 0xA9 + 2], 'little')

                    # Extract extended context: read bytes at strategic offsets
                    # Look for bytes that might encode team-side differently from team_id
                    extended = {}
                    # Read 32 bytes around entity_id location
                    for off in range(0xA0, 0xB0):
                        if pos + off < len(data):
                            extended[f'0x{off:02X}'] = data[pos + off]
                    # Read 32 bytes around team_id location
                    for off in range(0xD0, 0xE8):
                        if pos + off < len(data):
                            extended[f'0x{off:02X}'] = data[pos + off]

                    players.append({
                        'name': name,
                        'entity_id_le': entity_id_le,
                        'team_id': team_id,
                        'hero_id': hero_id,
                        'block_offset': pos,
                        'marker': marker.hex(),
                        'position': len(players),
                        'extended': extended,
                    })
                    seen.add(name)

        search_start = pos + 1

    return players


def get_name_prefix(name):
    """Extract numeric prefix from player name (e.g., '2600' from '2600_Acex')."""
    parts = name.split('_', 1)
    if len(parts) > 1 and parts[0].isdigit():
        return int(parts[0])
    return None


def main():
    print("=" * 80)
    print("TEAM LABEL HEURISTIC RESEARCH v2 - NAME PREFIX DEEP DIVE")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    # ===== ANALYSIS 1: Name prefix -> team mapping =====
    print("\n[OBJECTIVE] Determine if player name numeric prefix predicts left/right team")
    print()

    # Build dataset: for each match, what prefixes exist and which team they belong to
    print("=" * 80)
    print("MATCH-LEVEL: Name prefix to truth team mapping")
    print("=" * 80)

    prefix_team_data = []

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        status = 'SWAPPED' if swapped else ('CORRECT' if swapped is False else 'INCOMPLETE')

        # Group by prefix
        prefix_groups = defaultdict(list)
        for pname, pdata in match['players'].items():
            prefix = get_name_prefix(pname)
            if prefix is not None:
                prefix_groups[prefix].append({
                    'name': pname,
                    'team': pdata['team'],
                })

        # Determine which prefix maps to which team
        sorted_prefixes = sorted(prefix_groups.keys())
        print(f"\n  M{match_num} ({status}): prefixes = {sorted_prefixes}")

        for pref in sorted_prefixes:
            players = prefix_groups[pref]
            teams = set(p['team'] for p in players)
            team_str = '/'.join(sorted(teams))
            player_names = [p['name'] for p in players]
            print(f"    Prefix {pref}: team={team_str:5s} ({len(players)} players: {', '.join(player_names)})")

        # Record which prefix is higher/lower and which team it maps to
        if len(sorted_prefixes) >= 2:
            lower_pref = sorted_prefixes[0]
            higher_pref = sorted_prefixes[-1]

            lower_teams = set(p['team'] for p in prefix_groups[lower_pref])
            higher_teams = set(p['team'] for p in prefix_groups[higher_pref])

            # Handle 3-prefix case (some matches have a sub like 2604)
            # Main teams should be the ones with 5 players each
            main_prefixes = [p for p in sorted_prefixes if len(prefix_groups[p]) >= 4]
            sub_prefixes = [p for p in sorted_prefixes if len(prefix_groups[p]) < 4]

            prefix_team_data.append({
                'match_num': match_num,
                'swapped': swapped,
                'sorted_prefixes': sorted_prefixes,
                'main_prefixes': main_prefixes,
                'lower_pref': lower_pref,
                'higher_pref': higher_pref,
                'lower_teams': lower_teams,
                'higher_teams': higher_teams,
            })

    # ===== ANALYSIS 2: Does lower prefix = left consistently? =====
    print("\n" + "=" * 80)
    print("KEY TEST: Does LOWER name prefix consistently map to LEFT team?")
    print("=" * 80)

    lower_is_left = 0
    lower_is_right = 0
    lower_is_mixed = 0

    for d in prefix_team_data:
        if d['swapped'] is None:
            continue

        lower_teams = d['lower_teams']
        if lower_teams == {'left'}:
            lower_is_left += 1
            result = "LOWER=LEFT"
        elif lower_teams == {'right'}:
            lower_is_right += 1
            result = "LOWER=RIGHT"
        else:
            lower_is_mixed += 1
            result = f"MIXED: {lower_teams}"

        print(f"  M{d['match_num']}: {result}  (prefixes: {d['sorted_prefixes']}, lower={d['lower_pref']})")

    print(f"\n  [FINDING] Lower prefix = left:  {lower_is_left}/10")
    print(f"  [FINDING] Lower prefix = right: {lower_is_right}/10")
    print(f"  [FINDING] Lower prefix = mixed: {lower_is_mixed}/10")

    # ===== ANALYSIS 3: Does HIGHER prefix = left consistently? =====
    print("\n  Does HIGHER prefix consistently map to LEFT team?")

    higher_is_left = 0
    higher_is_right = 0
    higher_is_mixed = 0

    for d in prefix_team_data:
        if d['swapped'] is None:
            continue

        higher_teams = d['higher_teams']
        if higher_teams == {'left'}:
            higher_is_left += 1
        elif higher_teams == {'right'}:
            higher_is_right += 1
        else:
            higher_is_mixed += 1

    print(f"  Higher prefix = left:  {higher_is_left}/10")
    print(f"  Higher prefix = right: {higher_is_right}/10")
    print(f"  Higher prefix = mixed: {higher_is_mixed}/10")

    # ===== ANALYSIS 4: Does the MAIN lower prefix (>= 4 players) predict left? =====
    print("\n" + "=" * 80)
    print("REFINED: Main team prefix (>= 4 players) mapping")
    print("=" * 80)

    for d in prefix_team_data:
        if d['swapped'] is None:
            continue

        main = d['main_prefixes']
        if len(main) >= 2:
            lower_main = min(main)
            higher_main = max(main)
            # find the team for each
            lower_pref_data = [x for x in prefix_team_data if x['match_num'] == d['match_num']][0]
            print(f"  M{d['match_num']}: main_lower={lower_main}  main_higher={higher_main}  "
                  f"lower_team={d['lower_teams']}  higher_team={d['higher_teams']}")

    # ===== ANALYSIS 5: Entity IDs are interleaved - check the FIRST player block =====
    print("\n" + "=" * 80)
    print("ANALYSIS: First player in file -> which team?")
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

        players = parse_player_blocks_raw(data)
        if not players:
            continue

        # Match to truth
        for p in players:
            p['truth_team'] = None
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    p['truth_name'] = tname
                    break

        first = players[0]
        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"  M{match_num} ({status}): first_player={first['name']}, "
              f"team_byte={first['team_id']}, truth_team={first.get('truth_team', '?')}, "
              f"eid={first['entity_id_le']}")

    # ===== ANALYSIS 6: Name prefix vs team_byte correlation =====
    print("\n" + "=" * 80)
    print("ANALYSIS: Name prefix digit relationship to team_byte value")
    print("=" * 80)
    print("  Does the lower-prefix group always get team_byte=1 or always team_byte=2?")

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

        players = parse_player_blocks_raw(data)

        # Map names to truth
        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_name'] = tname
                    p['truth_team'] = tdata['team']
                    p['prefix'] = get_name_prefix(tname)
                    break

        # Group by prefix, get team_byte values
        prefix_bytes = defaultdict(set)
        for p in players:
            pref = p.get('prefix')
            if pref is not None:
                prefix_bytes[pref].add(p['team_id'])

        sorted_prefixes = sorted(prefix_bytes.keys())
        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        for pref in sorted_prefixes:
            byte_vals = sorted(prefix_bytes[pref])
            print(f"    Prefix {pref}: team_bytes = {byte_vals}")

    # ===== ANALYSIS 7: The defining question - what in the binary predicts swap? =====
    print("\n" + "=" * 80)
    print("DEEP ANALYSIS: Bytes in player block that predict team label swap")
    print("=" * 80)
    print("  Comparing bytes between correct and swapped matches at same offsets")

    # For each extended byte offset, check if values differ between swapped/correct
    # for players with the SAME truth team
    offset_analysis = defaultdict(lambda: {'left_correct': [], 'left_swapped': [],
                                            'right_correct': [], 'right_swapped': []})

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

        players = parse_player_blocks_raw(data)

        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

            truth = p.get('truth_team')
            if not truth:
                continue

            for off_key, val in p['extended'].items():
                if swapped:
                    offset_analysis[off_key][f'{truth}_swapped'].append(val)
                else:
                    offset_analysis[off_key][f'{truth}_correct'].append(val)

    # Find offsets where truth=left values are SAME regardless of swap status
    # (meaning the byte reflects true team, not the team_byte label)
    print("\n  Offsets where byte value is consistent for truth=left across correct/swapped:")
    for off_key in sorted(offset_analysis.keys()):
        d = offset_analysis[off_key]
        lc = set(d['left_correct'])
        ls = set(d['left_swapped'])
        rc = set(d['right_correct'])
        rs = set(d['right_swapped'])

        # Perfect: left-correct == left-swapped AND right-correct == right-swapped
        # AND left != right
        if lc and ls and rc and rs:
            left_all = lc | ls
            right_all = rc | rs
            if not left_all.intersection(right_all):
                print(f"    {off_key}: LEFT always={sorted(left_all)}, RIGHT always={sorted(right_all)} ** PERFECT DISCRIMINATOR **")

    # Also check: bytes that change WITH swap (correlate with team_byte, not truth)
    print("\n  Offsets where byte changes WITH swap (follows team_byte, not truth):")
    offset_analysis2 = defaultdict(lambda: {'byte1_correct': [], 'byte1_swapped': [],
                                             'byte2_correct': [], 'byte2_swapped': []})

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

        players = parse_player_blocks_raw(data)

        for p in players:
            tb = p['team_id']
            for off_key, val in p['extended'].items():
                if swapped:
                    offset_analysis2[off_key][f'byte{tb}_swapped'].append(val)
                else:
                    offset_analysis2[off_key][f'byte{tb}_correct'].append(val)

    for off_key in sorted(offset_analysis2.keys()):
        d = offset_analysis2[off_key]
        b1c = set(d['byte1_correct'])
        b1s = set(d['byte1_swapped'])
        b2c = set(d['byte2_correct'])
        b2s = set(d['byte2_swapped'])

        # Perfect correlation with team_byte: same values for same team_byte regardless of swap
        if b1c and b1s and b2c and b2s:
            byte1_all = b1c | b1s
            byte2_all = b2c | b2s
            if not byte1_all.intersection(byte2_all):
                print(f"    {off_key}: byte=1 always={sorted(byte1_all)}, byte=2 always={sorted(byte2_all)} (follows team_byte)")

    # ===== ANALYSIS 8: Look at raw header for global team indicator =====
    print("\n" + "=" * 80)
    print("HEADER ANALYSIS: Look for global bytes that indicate team mapping")
    print("=" * 80)

    # Read first 2048 bytes before any player block
    correct_pre_blocks = []
    swapped_pre_blocks = []

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

        # Find first player block
        players = parse_player_blocks_raw(data)
        if players:
            first_block_offset = min(p['block_offset'] for p in players)
            pre_block = data[:first_block_offset]
        else:
            pre_block = data[:2048]

        if swapped:
            swapped_pre_blocks.append((match_num, pre_block))
        else:
            correct_pre_blocks.append((match_num, pre_block))

    # Find bytes in the pre-block region that discriminate
    min_len = min(
        min(len(pb) for _, pb in correct_pre_blocks),
        min(len(pb) for _, pb in swapped_pre_blocks)
    )

    print(f"  Pre-block region length (min): {min_len} bytes")
    print(f"  Scanning for discriminating bytes...")

    disc_count = 0
    for offset in range(min_len):
        correct_vals = set(pb[offset] for _, pb in correct_pre_blocks)
        swapped_vals = set(pb[offset] for _, pb in swapped_pre_blocks)

        if correct_vals and swapped_vals and not correct_vals.intersection(swapped_vals):
            disc_count += 1
            if disc_count <= 30:
                print(f"    Offset 0x{offset:04X} ({offset}): correct={sorted(hex(x) for x in correct_vals)}  swapped={sorted(hex(x) for x in swapped_vals)}")

    print(f"  Total discriminating offsets: {disc_count}")

    # ===== ANALYSIS 9: Player block position 0 entity ID =====
    print("\n" + "=" * 80)
    print("ANALYSIS: Entity ID of position-0 player block and team_byte")
    print("=" * 80)
    print("  Position 0 = first player block encountered in binary")

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

        players = parse_player_blocks_raw(data)
        if not players:
            continue

        # Sort by block_offset to get true binary order
        players_ordered = sorted(players, key=lambda p: p['block_offset'])

        # Match to truth
        for p in players_ordered:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    p['truth_name'] = tname
                    break

        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}): block order ->")
        for i, p in enumerate(players_ordered):
            tt = p.get('truth_team', '?')
            print(f"    pos={i}  {p['name']:20s}  eid={p['entity_id_le']:5d}  "
                  f"team_byte={p['team_id']}  truth={tt if tt else '?'}")

    # ===== FINAL SYNTHESIS =====
    print("\n" + "=" * 80)
    print("SYNTHESIS: What heuristic works?")
    print("=" * 80)

    # Test heuristic: Use name prefix comparison
    # The name prefix is parsed from the replay binary too, so it's available without truth data
    print("\n  Testing heuristic: 'The team with the LOWER name prefix number is LEFT'")

    heuristic_correct = 0
    heuristic_wrong = 0
    heuristic_na = 0

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            heuristic_na += 1
            continue

        # Get prefixes
        prefix_groups = defaultdict(list)
        for pname, pdata in match['players'].items():
            prefix = get_name_prefix(pname)
            if prefix is not None:
                prefix_groups[prefix].append(pdata['team'])

        # Find the two main prefix groups
        sorted_prefixes = sorted(prefix_groups.keys())

        if len(sorted_prefixes) < 2:
            heuristic_na += 1
            continue

        # The lower main prefix group
        lower = sorted_prefixes[0]
        # Majority team for lower prefix
        lower_teams = prefix_groups[lower]
        lower_majority = max(set(lower_teams), key=lower_teams.count)

        if lower_majority == 'left':
            heuristic_correct += 1
            print(f"  M{match_num}: CORRECT (prefix {lower} -> {lower_majority})")
        else:
            heuristic_wrong += 1
            print(f"  M{match_num}: WRONG   (prefix {lower} -> {lower_majority})")

    total = heuristic_correct + heuristic_wrong
    if total > 0:
        print(f"\n  [STAT:accuracy] {heuristic_correct}/{total} = {heuristic_correct/total*100:.1f}%")
    print(f"  [STAT:na] {heuristic_na} (skipped)")

    # Test alternate: higher prefix = left
    print("\n  Testing alternate: 'The team with the HIGHER name prefix number is LEFT'")

    alt_correct = 0
    alt_wrong = 0

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        prefix_groups = defaultdict(list)
        for pname, pdata in match['players'].items():
            prefix = get_name_prefix(pname)
            if prefix is not None:
                prefix_groups[prefix].append(pdata['team'])

        sorted_prefixes = sorted(prefix_groups.keys())
        if len(sorted_prefixes) < 2:
            continue

        higher = sorted_prefixes[-1]
        higher_teams = prefix_groups[higher]
        higher_majority = max(set(higher_teams), key=higher_teams.count)

        if higher_majority == 'left':
            alt_correct += 1
            print(f"  M{match_num}: CORRECT (prefix {higher} -> {higher_majority})")
        else:
            alt_wrong += 1
            print(f"  M{match_num}: WRONG   (prefix {higher} -> {higher_majority})")

    total = alt_correct + alt_wrong
    if total > 0:
        print(f"\n  [STAT:alt_accuracy] {alt_correct}/{total} = {alt_correct/total*100:.1f}%")

    # ===== Test: Can we READ the prefix from the binary? =====
    print("\n" + "=" * 80)
    print("BINARY VERIFICATION: Are name prefixes readable from parsed player names?")
    print("=" * 80)
    print("  (Names are extracted from player blocks in frame 0)")

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

        players = parse_player_blocks_raw(data)

        # Check if name includes prefix
        prefixes_found = set()
        for p in players:
            prefix = get_name_prefix(p['name'])
            if prefix is not None:
                prefixes_found.add(prefix)

        # Check - does the raw parsed name include the prefix?
        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        for p in players:
            prefix = get_name_prefix(p['name'])
            print(f"    parsed_name='{p['name']:20s}'  prefix={prefix}")

        # Compare to truth names
        print(f"    Prefixes found in binary: {sorted(prefixes_found)}")
        truth_prefixes = set()
        for tname in match['players'].keys():
            pref = get_name_prefix(tname)
            if pref is not None:
                truth_prefixes.add(pref)
        print(f"    Prefixes in truth data:   {sorted(truth_prefixes)}")
        print(f"    Match: {'YES' if prefixes_found == truth_prefixes else 'PARTIAL - ' + str(prefixes_found.symmetric_difference(truth_prefixes))}")


if __name__ == '__main__':
    main()
