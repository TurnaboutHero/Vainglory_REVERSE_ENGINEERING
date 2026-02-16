#!/usr/bin/env python3
"""
Team Label Heuristic Research
==============================
Investigate how to determine correct left/right team labels from VGR replay data
WITHOUT relying on truth data.

Problem: team_id byte at +0xD5 correctly GROUPS players (100%), but the
1=left / 2=right mapping is WRONG in ~50% of matches.

Hypotheses tested:
  A. Do players with LOWER entity IDs consistently map to one side?
  B. Does team_id=1 always have lower or higher entity IDs?
  C. Is there a pattern in entity ID ordering (contiguous)?
  D. Is there a byte in the replay header or frame 0 that indicates mapping?
  E. Does player block ORDER correlate with team?
  F. Does turret entity ID clustering correlate?
"""

import json
import struct
import os
from pathlib import Path
from collections import defaultdict

# ===== CONFIGURATION =====

TRUTH_PATH = r'D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_truth.json'

# Known swap status: which matches have team_id byte swapped vs truth
# M2,M3,M5,M8,M10 swapped; M1,M4,M6,M7,M11 correct; M9 incomplete
SWAP_STATUS = {
    1: False, 2: True, 3: True, 4: False, 5: True,
    6: False, 7: False, 8: True, 9: None, 10: True, 11: False,
}

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])


def parse_player_blocks_raw(data):
    """Parse player blocks from frame 0, returning raw fields."""
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

                    # Read wide range of bytes around +0xD5 for pattern search
                    nearby_bytes = {}
                    for off in range(0xC0, 0xE0):
                        if pos + off < len(data):
                            nearby_bytes[off] = data[pos + off]

                    players.append({
                        'name': name,
                        'entity_id_le': entity_id_le,
                        'team_id': team_id,
                        'hero_id': hero_id,
                        'block_offset': pos,
                        'marker': marker.hex(),
                        'position': len(players),
                        'nearby_bytes': nearby_bytes,
                    })
                    seen.add(name)

        search_start = pos + 1

    return players


def match_to_truth(parsed_players, truth_players):
    """Match parsed player names to truth player names."""
    for p in parsed_players:
        p['truth_team'] = None
        for tname, tdata in truth_players.items():
            # Strip prefix number (e.g., "2600_Acex" -> "Acex")
            parts = tname.split('_', 1)
            short_name = parts[1] if len(parts) > 1 else tname
            if p['name'] == short_name or p['name'] == tname:
                p['truth_team'] = tdata['team']
                p['truth_name'] = tname
                break
        # Derived parsed team from byte
        if p['team_id'] == 1:
            p['parsed_team'] = 'left'
        elif p['team_id'] == 2:
            p['parsed_team'] = 'right'
        else:
            p['parsed_team'] = 'unknown'


def scan_header_bytes(data, num_bytes=512):
    """Return first N bytes of the replay for pattern analysis."""
    return data[:num_bytes]


def find_turret_clusters(replay_file):
    """Find turret entity ID clusters from all frames."""
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))

    # Only scan first few frames for turret entity IDs
    entity_counts = defaultdict(int)
    for frame_path in frames[:10]:
        data = frame_path.read_bytes()
        idx = 0
        while idx < len(data) - 5:
            if data[idx + 2:idx + 4] == b'\x00\x00':
                eid = struct.unpack('<H', data[idx:idx + 2])[0]
                if 1024 <= eid <= 19970:
                    entity_counts[eid] += 1
                idx += 37
            else:
                idx += 1

    # Filter to turret-like entities (high count, appear in multiple early frames)
    turret_candidates = sorted([eid for eid, cnt in entity_counts.items() if cnt > 50])

    if len(turret_candidates) < 2:
        return [], []

    # Split by largest gap
    max_gap = 0
    split_idx = len(turret_candidates) // 2
    for i in range(len(turret_candidates) - 1):
        gap = turret_candidates[i + 1] - turret_candidates[i]
        if gap > max_gap:
            max_gap = gap
            split_idx = i + 1

    return turret_candidates[:split_idx], turret_candidates[split_idx:]


def main():
    print("=" * 80)
    print("TEAM LABEL HEURISTIC RESEARCH")
    print("=" * 80)
    print()

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    matches_data = []

    # ===== PHASE 1: Extract raw data from all matches =====
    print("[STAGE:begin:data_extraction]")
    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        replay_file = match['replay_file']

        if not Path(replay_file).exists():
            print(f"  M{match_num}: SKIP (file not found)")
            continue

        with open(replay_file, 'rb') as f:
            data = f.read()

        players = parse_player_blocks_raw(data)
        match_to_truth(players, match['players'])

        # Get header bytes
        header = scan_header_bytes(data, 1024)

        swapped = SWAP_STATUS.get(match_num)

        matches_data.append({
            'match_num': match_num,
            'replay_file': replay_file,
            'players': players,
            'swapped': swapped,
            'header': header,
            'winner': match['match_info']['winner'],
        })

        status = 'SWAPPED' if swapped else ('CORRECT' if swapped is False else 'INCOMPLETE')
        print(f"\n  M{match_num} ({status}) - {len(players)} players")
        for p in players:
            print(f"    {p['name']:20s}  eid_LE={p['entity_id_le']:5d}  "
                  f"team_byte={p['team_id']}  parsed={p['parsed_team']:5s}  "
                  f"truth={str(p.get('truth_team', '?')):5s}")

    print(f"\n[STAGE:end:data_extraction]")

    # ===== PHASE 2: Hypothesis A - Entity ID ordering =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS A: Lower entity IDs -> consistent team mapping?")
    print("=" * 80)

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        team1_eids = sorted([p['entity_id_le'] for p in players if p['team_id'] == 1])
        team2_eids = sorted([p['entity_id_le'] for p in players if p['team_id'] == 2])

        if not team1_eids or not team2_eids:
            continue

        team1_min = min(team1_eids)
        team1_max = max(team1_eids)
        team2_min = min(team2_eids)
        team2_max = max(team2_eids)
        team1_avg = sum(team1_eids) / len(team1_eids)
        team2_avg = sum(team2_eids) / len(team2_eids)

        # Which team has lower entity IDs?
        lower_team_byte = 1 if team1_avg < team2_avg else 2

        # What is the TRUTH team for the lower-EID group?
        lower_eids_players = [p for p in players if p['team_id'] == lower_team_byte]
        truth_teams = [p.get('truth_team') for p in lower_eids_players if p.get('truth_team')]
        lower_truth = truth_teams[0] if truth_teams else '?'

        status = 'SWAPPED' if md['swapped'] else 'CORRECT'
        print(f"\n  M{md['match_num']} ({status}):")
        print(f"    team_byte=1 eids: {team1_eids}  avg={team1_avg:.0f}")
        print(f"    team_byte=2 eids: {team2_eids}  avg={team2_avg:.0f}")
        print(f"    Lower-EID group: team_byte={lower_team_byte}  -> truth={lower_truth}")

    # ===== PHASE 2B: Check if lower EIDs are ALWAYS left =====
    print("\n\n--- SUMMARY: Does lower-EID group = left team? ---")
    lower_is_left_count = 0
    lower_is_right_count = 0
    total_checked = 0

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        team1_eids = [p['entity_id_le'] for p in players if p['team_id'] == 1]
        team2_eids = [p['entity_id_le'] for p in players if p['team_id'] == 2]

        if not team1_eids or not team2_eids:
            continue

        team1_avg = sum(team1_eids) / len(team1_eids)
        team2_avg = sum(team2_eids) / len(team2_eids)

        lower_team_byte = 1 if team1_avg < team2_avg else 2
        lower_players = [p for p in players if p['team_id'] == lower_team_byte]
        truth_teams = [p.get('truth_team') for p in lower_players if p.get('truth_team')]
        lower_truth = truth_teams[0] if truth_teams else None

        if lower_truth == 'left':
            lower_is_left_count += 1
        elif lower_truth == 'right':
            lower_is_right_count += 1
        total_checked += 1

        print(f"  M{md['match_num']}: lower-EID group is truth '{lower_truth}' team")

    print(f"\n  Lower-EID = left:  {lower_is_left_count}/{total_checked}")
    print(f"  Lower-EID = right: {lower_is_right_count}/{total_checked}")

    # ===== PHASE 3: Hypothesis B - team_id=1 entity ID consistency =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS B: team_byte=1 always has lower or higher EIDs?")
    print("=" * 80)

    byte1_lower_count = 0
    byte1_higher_count = 0
    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        team1_eids = [p['entity_id_le'] for p in players if p['team_id'] == 1]
        team2_eids = [p['entity_id_le'] for p in players if p['team_id'] == 2]

        if not team1_eids or not team2_eids:
            continue

        t1_avg = sum(team1_eids) / len(team1_eids)
        t2_avg = sum(team2_eids) / len(team2_eids)

        if t1_avg < t2_avg:
            byte1_lower_count += 1
            print(f"  M{md['match_num']}: team_byte=1 has LOWER eids ({t1_avg:.0f} < {t2_avg:.0f})")
        else:
            byte1_higher_count += 1
            print(f"  M{md['match_num']}: team_byte=1 has HIGHER eids ({t1_avg:.0f} > {t2_avg:.0f})")

    print(f"\n  team_byte=1 LOWER:  {byte1_lower_count}/{byte1_lower_count + byte1_higher_count}")
    print(f"  team_byte=1 HIGHER: {byte1_higher_count}/{byte1_lower_count + byte1_higher_count}")

    # ===== PHASE 4: Hypothesis C - Entity ID contiguity =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS C: Entity ID contiguity and gap patterns")
    print("=" * 80)

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        all_eids = sorted([p['entity_id_le'] for p in players])

        # Check gaps between consecutive entity IDs
        gaps = []
        for i in range(len(all_eids) - 1):
            gaps.append(all_eids[i + 1] - all_eids[i])

        # Check if teams are interleaved or contiguous
        team_sequence = [p['team_id'] for p in sorted(players, key=lambda x: x['entity_id_le'])]

        print(f"\n  M{md['match_num']}: eids={all_eids}")
        print(f"    gaps={gaps}")
        print(f"    team order by eid: {team_sequence}")

    # ===== PHASE 5: Hypothesis D - Header bytes =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS D: Header/early bytes that differ between swapped/correct")
    print("=" * 80)

    # Compare headers between swapped and correct matches
    correct_headers = [md['header'] for md in matches_data if md['swapped'] is False]
    swapped_headers = [md['header'] for md in matches_data if md['swapped'] is True]

    if correct_headers and swapped_headers:
        # Find byte positions that consistently differ
        print("\n  Scanning first 512 bytes for consistent differences...")
        discriminating_offsets = []

        for offset in range(min(len(correct_headers[0]), 512)):
            correct_vals = set()
            swapped_vals = set()

            for h in correct_headers:
                if offset < len(h):
                    correct_vals.add(h[offset])
            for h in swapped_headers:
                if offset < len(h):
                    swapped_vals.add(h[offset])

            # Check if the values are disjoint (perfectly separates swapped vs correct)
            if correct_vals and swapped_vals and not correct_vals.intersection(swapped_vals):
                discriminating_offsets.append((offset, sorted(correct_vals), sorted(swapped_vals)))

        if discriminating_offsets:
            print(f"  Found {len(discriminating_offsets)} discriminating byte offsets!")
            for off, cv, sv in discriminating_offsets[:20]:
                print(f"    Offset 0x{off:04X}: correct={[hex(x) for x in cv]}  swapped={[hex(x) for x in sv]}")
        else:
            print("  No perfectly discriminating header bytes found.")

    # ===== PHASE 6: Player block order vs team =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS E: Player block order (position in file) vs truth team")
    print("=" * 80)

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = sorted(md['players'], key=lambda p: p['block_offset'])

        positions = []
        for i, p in enumerate(players):
            positions.append(f"{p['truth_team'] or '?'}")

        print(f"  M{md['match_num']}: block order -> truth teams: {positions}")

    # ===== PHASE 7: Player block nearby bytes =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS F: Bytes near team_id that differ between swapped/correct")
    print("=" * 80)

    # For each nearby offset, collect (offset, team_byte_value, truth_team, match_swapped)
    for off in range(0xC0, 0xE0):
        vals_correct_t1_left = []   # In correct matches, team_byte=1 -> truth=left
        vals_correct_t2_right = []
        vals_swapped_t1_right = []  # In swapped matches, team_byte=1 -> truth=right
        vals_swapped_t2_left = []

        for md in matches_data:
            if md['swapped'] is None:
                continue
            for p in md['players']:
                if off not in p['nearby_bytes']:
                    continue
                val = p['nearby_bytes'][off]
                if md['swapped'] is False:
                    if p['team_id'] == 1:
                        vals_correct_t1_left.append(val)
                    elif p['team_id'] == 2:
                        vals_correct_t2_right.append(val)
                else:
                    if p['team_id'] == 1:
                        vals_swapped_t1_right.append(val)
                    elif p['team_id'] == 2:
                        vals_swapped_t2_left.append(val)

        # Check if this byte differs between team_byte=1-correct and team_byte=1-swapped
        set_c1 = set(vals_correct_t1_left)
        set_s1 = set(vals_swapped_t1_right)
        if set_c1 and set_s1 and not set_c1.intersection(set_s1):
            print(f"  Offset 0x{off:02X}: DISCRIMINATES team_byte=1 correct vs swapped!")
            print(f"    correct(t1=left): {sorted(set_c1)}")
            print(f"    swapped(t1=right): {sorted(set_s1)}")

    # ===== PHASE 8: Entity ID absolute values =====
    print("\n" + "=" * 80)
    print("ANALYSIS: Entity ID absolute values and ranges per match")
    print("=" * 80)

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']

        left_truth_eids = sorted([p['entity_id_le'] for p in players if p.get('truth_team') == 'left'])
        right_truth_eids = sorted([p['entity_id_le'] for p in players if p.get('truth_team') == 'right'])

        print(f"\n  M{md['match_num']} ({'SWAPPED' if md['swapped'] else 'CORRECT'}):")
        print(f"    Truth LEFT  eids: {left_truth_eids}  range=[{min(left_truth_eids)}-{max(left_truth_eids)}]  avg={sum(left_truth_eids)/len(left_truth_eids):.0f}")
        print(f"    Truth RIGHT eids: {right_truth_eids}  range=[{min(right_truth_eids)}-{max(right_truth_eids)}]  avg={sum(right_truth_eids)/len(right_truth_eids):.0f}")

        if sum(left_truth_eids) / len(left_truth_eids) < sum(right_truth_eids) / len(right_truth_eids):
            print(f"    -> Truth LEFT has LOWER eids")
        else:
            print(f"    -> Truth RIGHT has LOWER eids")

    # ===== PHASE 9: Turret clustering correlation =====
    print("\n" + "=" * 80)
    print("HYPOTHESIS G: Turret cluster entity IDs correlate with player teams")
    print("=" * 80)

    for md in matches_data:
        if md['swapped'] is None:
            continue

        replay_file = md['replay_file']
        print(f"\n  M{md['match_num']}:")

        try:
            turret_g1, turret_g2 = find_turret_clusters(replay_file)
            if turret_g1 and turret_g2:
                t1_avg = sum(turret_g1) / len(turret_g1)
                t2_avg = sum(turret_g2) / len(turret_g2)
                print(f"    Turret group 1: {len(turret_g1)} entities, avg eid={t1_avg:.0f}, range=[{min(turret_g1)}-{max(turret_g1)}]")
                print(f"    Turret group 2: {len(turret_g2)} entities, avg eid={t2_avg:.0f}, range=[{min(turret_g2)}-{max(turret_g2)}]")

                # Compare to player entity IDs
                players = md['players']
                left_truth_eids = [p['entity_id_le'] for p in players if p.get('truth_team') == 'left']
                right_truth_eids = [p['entity_id_le'] for p in players if p.get('truth_team') == 'right']

                if left_truth_eids and right_truth_eids:
                    left_avg = sum(left_truth_eids) / len(left_truth_eids)
                    right_avg = sum(right_truth_eids) / len(right_truth_eids)

                    # Which turret group is closer to left players?
                    d_g1_left = abs(t1_avg - left_avg)
                    d_g1_right = abs(t1_avg - right_avg)
                    d_g2_left = abs(t2_avg - left_avg)
                    d_g2_right = abs(t2_avg - right_avg)

                    print(f"    Left  player avg eid: {left_avg:.0f}")
                    print(f"    Right player avg eid: {right_avg:.0f}")
                    print(f"    Distance: turret_g1-left={d_g1_left:.0f}, turret_g1-right={d_g1_right:.0f}")
                    print(f"    Distance: turret_g2-left={d_g2_left:.0f}, turret_g2-right={d_g2_right:.0f}")

                    if d_g1_left < d_g1_right:
                        print(f"    -> Turret group 1 (lower eids) aligns with LEFT players")
                    else:
                        print(f"    -> Turret group 1 (lower eids) aligns with RIGHT players")
            else:
                print(f"    Could not cluster turrets")
        except Exception as e:
            print(f"    Error: {e}")

    # ===== PHASE 10: Entity ID digit pattern =====
    print("\n" + "=" * 80)
    print("ANALYSIS: Player entity ID numeric prefixes")
    print("=" * 80)

    # Check if player names have numeric prefixes that correlate with entity IDs
    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        print(f"\n  M{md['match_num']}:")
        for p in sorted(players, key=lambda x: x['entity_id_le']):
            truth_name = p.get('truth_name', p['name'])
            parts = truth_name.split('_', 1)
            prefix = parts[0] if len(parts) > 1 and parts[0].isdigit() else 'N/A'
            print(f"    {truth_name:25s}  eid={p['entity_id_le']:5d}  team_byte={p['team_id']}  truth={p.get('truth_team','?'):5s}  name_prefix={prefix}")

    # ===== FINAL SUMMARY =====
    print("\n" + "=" * 80)
    print("FINAL SUMMARY: Entity ID -> Team Mapping Patterns")
    print("=" * 80)

    # Key question: can we predict truth team from entity IDs alone?
    # Group all players and check the rule: lower EID group = left
    all_correct = 0
    all_wrong = 0

    for md in matches_data:
        if md['swapped'] is None:
            continue
        players = md['players']
        all_eids = sorted(set(p['entity_id_le'] for p in players))

        # Median split
        median_eid = all_eids[len(all_eids) // 2]

        for p in players:
            predicted = 'left' if p['entity_id_le'] <= median_eid else 'right'
            truth = p.get('truth_team')
            if truth:
                if predicted == truth:
                    all_correct += 1
                else:
                    all_wrong += 1

    print(f"\n  Median-split heuristic (lower eid = left):")
    print(f"    Correct: {all_correct}")
    print(f"    Wrong:   {all_wrong}")
    print(f"    Accuracy: {all_correct / (all_correct + all_wrong) * 100:.1f}%" if (all_correct + all_wrong) > 0 else "    No data")

    # Also check: team_byte value correlates with name prefix
    print("\n  Name prefix analysis (does player name prefix correlate with team?):")
    prefix_team_map = defaultdict(lambda: defaultdict(int))
    for md in matches_data:
        if md['swapped'] is None:
            continue
        for p in md['players']:
            truth_name = p.get('truth_name', p['name'])
            parts = truth_name.split('_', 1)
            if len(parts) > 1 and parts[0].isdigit():
                prefix = int(parts[0])
                truth = p.get('truth_team', '?')
                prefix_team_map[md['match_num']][(prefix, truth)] = prefix_team_map[md['match_num']].get((prefix, truth), 0) + 1

    for mnum in sorted(prefix_team_map.keys()):
        print(f"    M{mnum}: {dict(prefix_team_map[mnum])}")


if __name__ == '__main__':
    main()
