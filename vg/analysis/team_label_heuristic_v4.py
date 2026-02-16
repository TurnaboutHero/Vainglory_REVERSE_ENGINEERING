#!/usr/bin/env python3
"""
Team Label Heuristic Research v4
=================================
v3 findings:
- NO byte in player block (0x00-0xFF) predicts truth team
- Name prefix groups players perfectly but does NOT predict left/right
- Entity IDs are ALWAYS 1500-1509 (BE), interleaved between teams
- team_byte at 0xD5 randomly assigns 1 or 2 to left team

New approach: Use GAME EVENT DATA to determine team side.
Hypotheses:
  H1: The team whose crystal (eid 2000-2005) is in lower-eid group = one specific side
  H2: Turret entity IDs correlate with player team (turrets near player = same team)
  H3: First frame event data contains position/coordinate that reveals map side
  H4: Kill events - which team kills which reveals left/right via event structure
  H5: Minion entity IDs correlate with team side
  H6: Crystal entity IDs (2000-2005) have a consistent mapping
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

KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def parse_player_blocks_raw(data):
    """Parse player blocks."""
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

                    players.append({
                        'name': name,
                        'entity_id_le': entity_id_le,
                        'team_id': team_id,
                        'block_offset': pos,
                    })
                    seen.add(name)

        search_start = pos + 1
    return players


def le_to_be(eid_le):
    """Convert LE uint16 to BE uint16."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_all_frames(replay_file):
    """Load all frame data for a replay."""
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return [(int(f.stem.split('.')[-1]), f.read_bytes()) for f in frames]


def find_first_kill_events(frames, valid_eids_be):
    """Find first few kill events and return killer/victim teams."""
    kills = []
    for frame_idx, data in frames:
        pos = 0
        while True:
            pos = data.find(KILL_HEADER, pos)
            if pos == -1:
                break
            if pos + 16 > len(data):
                pos += 1
                continue

            if (data[pos+3:pos+5] != b'\x00\x00' or
                data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF' or
                data[pos+11:pos+15] != b'\x3F\x80\x00\x00' or
                data[pos+15] != 0x29):
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid in valid_eids_be:
                ts = None
                if pos >= 7:
                    ts = struct.unpack_from(">f", data, pos - 7)[0]
                    if not (0 < ts < 1800):
                        ts = None
                kills.append({'killer_eid_be': eid, 'timestamp': ts, 'frame': frame_idx})

            pos += 16

        if len(kills) >= 5:
            break
    return kills


def find_first_death_events(frames, valid_eids_be):
    """Find first few death events."""
    deaths = []
    for frame_idx, data in frames:
        pos = 0
        while True:
            pos = data.find(DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(data):
                pos += 1
                continue

            if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            ts = struct.unpack_from(">f", data, pos + 9)[0]

            if eid in valid_eids_be and 0 < ts < 1800:
                deaths.append({'victim_eid_be': eid, 'timestamp': ts, 'frame': frame_idx})

            pos += 1

        if len(deaths) >= 5:
            break
    return deaths


def scan_infrastructure_entities(frames, max_frames=5):
    """Scan first N frames for infrastructure entity IDs (1000-20000 range)."""
    entity_counts = defaultdict(int)
    for frame_idx, data in frames[:max_frames]:
        idx = 0
        while idx < len(data) - 5:
            if data[idx + 2:idx + 4] == b'\x00\x00':
                eid = struct.unpack('<H', data[idx:idx + 2])[0]
                if 1024 <= eid <= 19970:
                    entity_counts[eid] += 1
                idx += 37
            else:
                idx += 1
    return entity_counts


def find_crystal_entities(frames):
    """Find crystal entity IDs (BE range ~2000-2005) from death events."""
    crystal_deaths = []
    for frame_idx, data in frames:
        pos = 0
        while True:
            pos = data.find(DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(data):
                pos += 1
                continue

            if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            ts = struct.unpack_from(">f", data, pos + 9)[0]

            # Crystal entity IDs are in range 2000-2010 (BE)
            if 2000 <= eid <= 2010 and 0 < ts < 2000:
                crystal_deaths.append({
                    'eid_be': eid, 'timestamp': ts, 'frame': frame_idx
                })

            pos += 1
    return crystal_deaths


def main():
    print("=" * 80)
    print("TEAM LABEL HEURISTIC RESEARCH v4 - EVENT-BASED APPROACH")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    # ===== ANALYSIS 1: Crystal entity ID mapping =====
    print("\n[OBJECTIVE] Find event-based heuristic for team left/right mapping")
    print()
    print("=" * 80)
    print("ANALYSIS 1: Crystal deaths - which crystal entity belongs to which team?")
    print("=" * 80)

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        status = 'SWAPPED' if swapped else 'CORRECT'
        winner = match['match_info']['winner']
        print(f"\n  M{match_num} ({status}, winner={winner}):")

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        # Build eid->team map
        eid_team = {}
        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    eid_be = le_to_be(p['entity_id_le'])
                    eid_team[eid_be] = tdata['team']
                    p['truth_team'] = tdata['team']
                    break

        # Load frames and find crystal deaths
        frames = load_all_frames(replay_file)
        crystal_deaths = find_crystal_entities(frames)

        if crystal_deaths:
            for cd in crystal_deaths:
                print(f"    Crystal death: eid_BE={cd['eid_be']}, ts={cd['timestamp']:.1f}s, frame={cd['frame']}")

            # The crystal that dies = loser's crystal
            # So crystal eid -> loser team -> other team is winner
            loser = 'right' if winner == 'left' else 'left'
            print(f"    Winner: {winner}, so destroyed crystal belongs to: {loser}")

    # ===== ANALYSIS 2: Turret clustering with team_byte correlation =====
    print("\n" + "=" * 80)
    print("ANALYSIS 2: Turret clusters vs player team_byte assignment")
    print("=" * 80)
    print("  Can we determine left/right from turret-player entity ID proximity?")

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        # Load frames
        frames = load_all_frames(replay_file)

        # Scan infrastructure entities
        infra = scan_infrastructure_entities(frames, max_frames=5)

        # Filter to turret-like (high count)
        turret_eids = sorted([eid for eid, cnt in infra.items() if cnt > 50])

        if len(turret_eids) < 4:
            print(f"\n  M{match_num}: Only {len(turret_eids)} turret candidates, skipping")
            continue

        # Split by largest gap
        max_gap = 0
        split_idx = len(turret_eids) // 2
        for i in range(len(turret_eids) - 1):
            gap = turret_eids[i + 1] - turret_eids[i]
            if gap > max_gap:
                max_gap = gap
                split_idx = i + 1

        turret_g1 = turret_eids[:split_idx]  # Lower turret eids
        turret_g2 = turret_eids[split_idx:]   # Higher turret eids

        # Get BE values for comparison
        turret_g1_be = sorted([le_to_be(e) for e in turret_g1])
        turret_g2_be = sorted([le_to_be(e) for e in turret_g2])

        # Now: which player team_byte group has eids closer to which turret group?
        # Player eids are all 1500-1509 BE, turrets are in different ranges
        # So proximity doesn't work directly on entity ID values

        # Alternative: within each frame, check if turret events and player events
        # share positional data (like being in the same packet section)

        status = 'SWAPPED' if swapped else 'CORRECT'
        winner = match['match_info']['winner']

        # Match truth team to turret group
        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

        print(f"\n  M{match_num} ({status}, winner={winner}):")
        print(f"    Turret group 1 (lower LE): {len(turret_g1)} entities, LE range=[{min(turret_g1)}-{max(turret_g1)}], BE range=[{min(turret_g1_be)}-{max(turret_g1_be)}]")
        print(f"    Turret group 2 (higher LE): {len(turret_g2)} entities, LE range=[{min(turret_g2)}-{max(turret_g2)}], BE range=[{min(turret_g2_be)}-{max(turret_g2_be)}]")

        # Check: which turret group gets destroyed when we know the winner?
        # The loser's turrets (including crystal) get destroyed
        # So identify which turret group has more destructions

        # Count last-frame appearances for each turret (if a turret stops appearing, it was destroyed)
        max_frame = max(fi for fi, _ in frames)
        last_frame_data = frames[-1][1] if frames else b''

        # Actually, let's just check crystal deaths
        crystal_deaths = find_crystal_entities(frames)
        if crystal_deaths:
            cd = crystal_deaths[0]
            crystal_be = cd['eid_be']
            crystal_le = struct.unpack('<H', struct.pack('>H', crystal_be))[0]
            # Is crystal in turret_g1 or turret_g2?
            if crystal_le in turret_g1 or any(abs(crystal_le - t) < 100 for t in turret_g1):
                print(f"    Crystal (BE={crystal_be}, LE={crystal_le}) is near turret group 1 (lower)")
                loser_group = "g1"
            elif crystal_le in turret_g2 or any(abs(crystal_le - t) < 100 for t in turret_g2):
                print(f"    Crystal (BE={crystal_be}, LE={crystal_le}) is near turret group 2 (higher)")
                loser_group = "g2"
            else:
                print(f"    Crystal (BE={crystal_be}, LE={crystal_le}) not clearly in either group")
                # Check BE proximity
                avg_g1_be = sum(turret_g1_be) / len(turret_g1_be)
                avg_g2_be = sum(turret_g2_be) / len(turret_g2_be)
                if abs(crystal_be - avg_g1_be) < abs(crystal_be - avg_g2_be):
                    print(f"      -> Closer to group 1 BE (avg={avg_g1_be:.0f} vs {avg_g2_be:.0f})")
                    loser_group = "g1"
                else:
                    print(f"      -> Closer to group 2 BE (avg={avg_g1_be:.0f} vs {avg_g2_be:.0f})")
                    loser_group = "g2"

            loser = 'right' if winner == 'left' else 'left'
            print(f"    Winner={winner}, so loser={loser}")
            print(f"    -> Destroyed crystal is in turret {loser_group}")
            print(f"    -> Turret {loser_group} = {loser} team's turrets")

    # ===== ANALYSIS 3: First kill - cross-team kill reveals team mapping =====
    print("\n" + "=" * 80)
    print("ANALYSIS 3: First kills - killer/victim cross-team identification")
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
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)
        valid_eids_be = set()
        eid_to_player = {}
        for p in players:
            eid_be = le_to_be(p['entity_id_le'])
            valid_eids_be.add(eid_be)
            p['eid_be'] = eid_be
            eid_to_player[eid_be] = p

            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break

        frames = load_all_frames(replay_file)
        kills = find_first_kill_events(frames, valid_eids_be)
        deaths = find_first_death_events(frames, valid_eids_be)

        status = 'SWAPPED' if swapped else 'CORRECT'
        print(f"\n  M{match_num} ({status}):")
        print(f"    First kills:")
        for k in kills[:3]:
            killer = eid_to_player.get(k['killer_eid_be'], {})
            print(f"      ts={k['timestamp']:.1f}s killer={killer.get('name','?')} "
                  f"(team_byte={killer.get('team_id','?')}, truth={killer.get('truth_team','?')})")

        print(f"    First deaths:")
        for d in deaths[:3]:
            victim = eid_to_player.get(d['victim_eid_be'], {})
            print(f"      ts={d['timestamp']:.1f}s victim={victim.get('name','?')} "
                  f"(team_byte={victim.get('team_id','?')}, truth={victim.get('truth_team','?')})")

    # ===== ANALYSIS 4: Win/Loss detection as team-label bootstrap =====
    print("\n" + "=" * 80)
    print("ANALYSIS 4: Win/Loss + Crystal as team-label bootstrap")
    print("=" * 80)
    print("  Key idea: crystal death tells us which team LOST")
    print("  If we can map crystal entity to a turret group, and turret group to team_byte...")
    print("  Then: crystal_team_byte -> loser, other team_byte -> winner")
    print()

    results_table = []

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        # Build team_byte -> player list
        team_byte_players = defaultdict(list)
        for p in players:
            for tname, tdata in match['players'].items():
                parts = tname.split('_', 1)
                short = parts[1] if len(parts) > 1 else tname
                if p['name'] == short or p['name'] == tname:
                    p['truth_team'] = tdata['team']
                    break
            team_byte_players[p['team_id']].append(p)

        # Load frames
        frames = load_all_frames(replay_file)

        # Find crystal deaths
        crystal_deaths = find_crystal_entities(frames)

        winner = match['match_info']['winner']
        loser = 'right' if winner == 'left' else 'left'
        status = 'SWAPPED' if swapped else 'CORRECT'

        # Scan infra
        infra = scan_infrastructure_entities(frames, max_frames=5)
        turret_eids = sorted([eid for eid, cnt in infra.items() if cnt > 50])

        if len(turret_eids) < 4:
            print(f"  M{match_num}: Not enough turrets")
            continue

        # Split turrets
        max_gap = 0
        split_idx = len(turret_eids) // 2
        for i in range(len(turret_eids) - 1):
            gap = turret_eids[i + 1] - turret_eids[i]
            if gap > max_gap:
                max_gap = gap
                split_idx = i + 1

        turret_g1 = turret_eids[:split_idx]
        turret_g2 = turret_eids[split_idx:]

        if crystal_deaths:
            cd = crystal_deaths[0]
            crystal_be = cd['eid_be']
            crystal_le = struct.unpack('<H', struct.pack('>H', crystal_be))[0]

            # Determine which turret group the crystal is in
            turret_g1_be = [le_to_be(e) for e in turret_g1]
            turret_g2_be = [le_to_be(e) for e in turret_g2]
            avg_g1_be = sum(turret_g1_be) / len(turret_g1_be)
            avg_g2_be = sum(turret_g2_be) / len(turret_g2_be)

            if abs(crystal_be - avg_g1_be) < abs(crystal_be - avg_g2_be):
                crystal_group = 1
            else:
                crystal_group = 2

            # Now: team_byte of players whose turrets include the destroyed crystal
            # We need to map turret groups to team_byte groups
            # Approach: count which team_byte's players are more associated with which turret group
            # Since entity IDs are interleaved and don't correlate, we need a different approach

            # Alternative: The crystal identifies the LOSER.
            # The loser = one team. The winner = other team.
            # If we know which team_byte corresponds to the loser, we can infer left/right.
            # Because: truth tells us winner=left or winner=right
            # So: if crystal_team_byte = X, then X = loser team byte
            #     if winner = 'left', then loser = 'right', so team_byte X -> 'right'

            # But HOW to find crystal_team_byte? We need to link crystal to a player team.
            # Crystal entity is in range 2000-2010 BE - we need to find what team_byte
            # those turrets/crystals belong to.

            # Let's check: does the win_loss_detector already handle this?
            # It uses turret clustering + player team proximity
            # But player entity IDs don't correlate spatially with turret entity IDs

            # NEW APPROACH: Check the KDA kill/death events.
            # When a player kills a turret or the crystal, we can see which team did it.
            # The WINNING team kills the LOSING team's crystal.

            # So: find who killed the crystal (credit records near crystal death)
            # That player's team_byte = WINNER's team_byte

            print(f"  M{match_num} ({status}, winner={winner}):")
            print(f"    Crystal BE={crystal_be}, ts={cd['timestamp']:.1f}s, frame={cd['frame']}")
            print(f"    Crystal near turret group {crystal_group} (g1_avg_BE={avg_g1_be:.0f}, g2_avg_BE={avg_g2_be:.0f})")

            results_table.append({
                'match': match_num,
                'swapped': swapped,
                'winner': winner,
                'crystal_be': crystal_be,
                'crystal_group': crystal_group,
                'status': status,
            })

    # ===== ANALYSIS 5: Score (kill counts) to resolve team mapping =====
    print("\n" + "=" * 80)
    print("ANALYSIS 5: Kill counts by team_byte vs truth score")
    print("=" * 80)
    print("  Idea: Count kills per team_byte group. Compare to truth score_left/score_right.")
    print("  If kills_by_byte1 matches score_left, then byte1=left. Otherwise byte1=right.")

    import sys as _sys
    _sys.path.insert(0, r'D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\core')
    from kda_detector import KDADetector

    heuristic_results = []

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        # Build team_byte -> eid set
        byte1_eids_be = set()
        byte2_eids_be = set()
        all_eids_be = set()

        for p in players:
            eid_be = le_to_be(p['entity_id_le'])
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids_be.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids_be.add(eid_be)

        # Run KDA detection
        detector = KDADetector(valid_entity_ids=all_eids_be)
        frames = load_all_frames(replay_file)
        duration = match['match_info']['duration_seconds']

        for frame_idx, frame_data in frames:
            detector.process_frame(frame_idx, frame_data)

        results = detector.get_results(game_duration=duration)

        # Count kills by team_byte
        byte1_kills = sum(results[eid].kills for eid in byte1_eids_be if eid in results)
        byte2_kills = sum(results[eid].kills for eid in byte2_eids_be if eid in results)
        byte1_deaths = sum(results[eid].deaths for eid in byte1_eids_be if eid in results)
        byte2_deaths = sum(results[eid].deaths for eid in byte2_eids_be if eid in results)

        truth_score_left = match['match_info']['score_left']
        truth_score_right = match['match_info']['score_right']

        status = 'SWAPPED' if swapped else 'CORRECT'
        winner = match['match_info']['winner']

        # Heuristic: if byte1_kills == score_left, then byte1=left
        # Score = total kills by that team
        # Note: score might include turret/objective kills too, so check both kills and deaths
        # Deaths of one team = kills by other team (for hero kills)
        # score_left = kills by left team = deaths of right team
        # byte1_kills should match score_left if byte1=left

        # Try: byte1_kills ~= score_left?
        diff_byte1_left = abs(byte1_kills - truth_score_left)
        diff_byte1_right = abs(byte1_kills - truth_score_right)

        if diff_byte1_left < diff_byte1_right:
            predicted = 'byte1=left'
            correct = not swapped  # If correct match, byte1=left is right prediction
        elif diff_byte1_left > diff_byte1_right:
            predicted = 'byte1=right'
            correct = swapped  # If swapped match, byte1=right is right prediction
        else:
            predicted = 'ambiguous'
            correct = None

        print(f"\n  M{match_num} ({status}, winner={winner}):")
        print(f"    byte1 kills={byte1_kills}, byte2 kills={byte2_kills}")
        print(f"    byte1 deaths={byte1_deaths}, byte2 deaths={byte2_deaths}")
        print(f"    truth: score_left={truth_score_left}, score_right={truth_score_right}")
        print(f"    diff byte1-vs-left={diff_byte1_left}, byte1-vs-right={diff_byte1_right}")
        print(f"    -> Predicted: {predicted}  {'CORRECT' if correct else 'WRONG' if correct is False else 'AMBIGUOUS'}")

        heuristic_results.append({
            'match': match_num,
            'predicted': predicted,
            'correct': correct,
            'byte1_kills': byte1_kills,
            'byte2_kills': byte2_kills,
            'truth_left': truth_score_left,
            'truth_right': truth_score_right,
        })

    # Summary
    print("\n" + "=" * 80)
    print("KILL-COUNT HEURISTIC SUMMARY")
    print("=" * 80)
    correct_count = sum(1 for r in heuristic_results if r['correct'] is True)
    wrong_count = sum(1 for r in heuristic_results if r['correct'] is False)
    ambig_count = sum(1 for r in heuristic_results if r['correct'] is None)
    total = len(heuristic_results)
    print(f"  Correct:   {correct_count}/{total}")
    print(f"  Wrong:     {wrong_count}/{total}")
    print(f"  Ambiguous: {ambig_count}/{total}")
    if correct_count + wrong_count > 0:
        print(f"  Accuracy (excl ambiguous): {correct_count}/{correct_count+wrong_count} = {correct_count/(correct_count+wrong_count)*100:.1f}%")

    # ===== ANALYSIS 6: Death-count heuristic =====
    print("\n" + "=" * 80)
    print("DEATH-COUNT HEURISTIC: byte1_deaths vs score_right")
    print("=" * 80)
    print("  score_left = kills by left team = deaths of right team")
    print("  So: byte1_deaths should match score_right if byte1=right (i.e., byte1=left's kills)")
    print()

    death_results = []
    for r in heuristic_results:
        mn = r['match']
        b1d = None
        b2d = None
        # Refetch from detector would be needed, but let's use the printed values
        pass

    # Actually let's use a cleaner version
    print("  Using kills directly:")
    print(f"  {'Match':>5s}  {'b1_K':>5s}  {'b2_K':>5s}  {'tL':>5s}  {'tR':>5s}  {'b1=L?':>6s}  {'Result':>10s}")
    for r in heuristic_results:
        b1k = r['byte1_kills']
        b2k = r['byte2_kills']
        tl = r['truth_left']
        tr = r['truth_right']

        # Check which assignment is better
        # If byte1=left: |b1k-tl| + |b2k-tr|
        # If byte1=right: |b1k-tr| + |b2k-tl|
        err_left = abs(b1k - tl) + abs(b2k - tr)
        err_right = abs(b1k - tr) + abs(b2k - tl)

        if err_left < err_right:
            assign = 'b1=L'
        elif err_right < err_left:
            assign = 'b1=R'
        else:
            assign = 'TIE'

        result = 'CORRECT' if r['correct'] else ('WRONG' if r['correct'] is False else 'AMBIG')
        print(f"  M{r['match']:3d}  {b1k:5d}  {b2k:5d}  {tl:5d}  {tr:5d}  {assign:>6s}  {result:>10s}")


if __name__ == '__main__':
    main()
