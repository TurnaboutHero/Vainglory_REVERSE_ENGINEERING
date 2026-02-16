#!/usr/bin/env python3
"""
Assist Over-Detection Investigation
====================================
Investigate why 6 players have MORE detected assists than truth.
Focus on Blackfeather players who show worst over-detection.

Error cases:
  M1 2604_Ray (Blackfeather): detected=2, truth=0 (+2)
  M3 3004_TenshiiHime (Blackfeather): detected=9, truth=8 (+1)
  M4 3004_TenshiiHime (Blackfeather): detected=11, truth=7 (+4)
  M5 2600_Acex (Lyra): detected=1, truth=0 (+1)
  M6 2600_Acex (Lorelai): detected=12, truth=11 (+1)
  M6 2600_TenshilHime (Blackfeather): detected=10, truth=6 (+4)
"""

import struct
import json
import sys
import os
from pathlib import Path
from collections import defaultdict

# Add parent dirs to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from kda_detector import KDADetector, KILL_HEADER, CREDIT_HEADER, DEATH_HEADER

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

with open(TRUTH_PATH) as f:
    truth_data = json.load(f)

# Error case match indices (0-based): M1=0, M3=2, M4=3, M5=4, M6=5
ERROR_CASES = [
    {"match_idx": 0, "player": "2604_Ray", "hero": "Blackfeather", "truth_a": 0, "det_a": 2},
    {"match_idx": 2, "player": "3004_TenshiiHime", "hero": "Blackfeather", "truth_a": 8, "det_a": 9},
    {"match_idx": 3, "player": "3004_TenshiiHime", "hero": "Blackfeather", "truth_a": 7, "det_a": 11},
    {"match_idx": 4, "player": "2600_Acex", "hero": "Lyra", "truth_a": 0, "det_a": 1},
    {"match_idx": 5, "player": "2600_Acex", "hero": "Lorelai", "truth_a": 11, "det_a": 12},
    {"match_idx": 5, "player": "2600_TenshilHime", "hero": "Blackfeather", "truth_a": 6, "det_a": 10},
]


def read_all_frames(replay_path):
    """Read all frame files for a replay."""
    p = Path(replay_path)
    frame_dir = p.parent
    # Get replay name (everything before .N.vgr)
    replay_name = p.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def frame_index(fp):
        try:
            return int(fp.stem.split('.')[-1])
        except ValueError:
            return 0
    frames.sort(key=frame_index)

    frame_boundaries = []
    all_data = bytearray()
    for fp in frames:
        start = len(all_data)
        chunk = fp.read_bytes()
        all_data.extend(chunk)
        frame_boundaries.append((start, len(all_data), int(fp.stem.split('.')[-1])))

    return bytes(all_data), frame_boundaries


def get_frame_for_offset(offset, frame_boundaries):
    """Get frame index for a byte offset."""
    for start, end, fidx in frame_boundaries:
        if start <= offset < end:
            return fidx
    return -1


def parse_player_blocks(data):
    """Extract player entity IDs and teams from player blocks."""
    MARKER1 = bytes([0xDA, 0x03, 0xEE])
    MARKER2 = bytes([0xE0, 0x03, 0xEE])

    players = {}
    search_start = 0
    seen_names = set()

    while True:
        pos1 = data.find(MARKER1, search_start)
        pos2 = data.find(MARKER2, search_start)

        candidates = []
        if pos1 != -1: candidates.append((pos1, MARKER1))
        if pos2 != -1: candidates.append((pos2, MARKER2))

        if not candidates:
            break

        pos, marker = min(candidates, key=lambda x: x[0])
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
            except:
                name = ""

            if len(name) >= 3 and name not in seen_names and not name.startswith('GameMode'):
                entity_id = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little') if pos + 0xA7 <= len(data) else None
                team_byte = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                team = "left" if team_byte == 1 else ("right" if team_byte == 2 else "unknown")

                players[name] = {
                    "entity_id_le": entity_id,
                    "entity_id_be": struct.pack(">H", entity_id) if entity_id else None,
                    "eid_be_int": struct.unpack(">H", struct.pack("<H", entity_id))[0] if entity_id else None,
                    "team": team,
                    "block_offset": pos,
                }
                seen_names.add(name)

        search_start = pos + 1

    return players


def analyze_match_assists(match_idx, target_player_key, truth_assists):
    """Deep analysis of assist credit records for a specific match and player."""
    match = truth_data["matches"][match_idx]
    replay_file = match["replay_file"]
    duration = match["match_info"]["duration_seconds"]

    print(f"\n{'='*80}")
    print(f"MATCH {match_idx+1}: {Path(replay_file).parent.parent.name}/{Path(replay_file).parent.name}")
    print(f"Duration: {duration}s")
    print(f"Target: {target_player_key} (truth assists={truth_assists})")
    print(f"{'='*80}")

    # Read all frames
    all_data, frame_boundaries = read_all_frames(replay_file)
    print(f"Total data: {len(all_data):,} bytes, {len(frame_boundaries)} frames")

    # Get player blocks from first frame only
    first_frame_path = Path(replay_file)
    first_frame_data = first_frame_path.read_bytes()
    players = parse_player_blocks(first_frame_data)

    # Build entity maps
    eid_to_name = {}
    eid_to_team = {}
    name_to_eid = {}
    for pname, pinfo in players.items():
        eid_be = pinfo["eid_be_int"]
        eid_to_name[eid_be] = pname
        eid_to_team[eid_be] = pinfo["team"]
        name_to_eid[pname] = eid_be

    print(f"\nPlayers:")
    for pname, pinfo in players.items():
        truth_p = match["players"].get(pname, {})
        print(f"  {pname}: eid=0x{pinfo['eid_be_int']:04X}, team={pinfo['team']}, "
              f"hero={truth_p.get('hero_name','?')}, truth_KDA={truth_p.get('kills','?')}/{truth_p.get('deaths','?')}/{truth_p.get('assists','?')}")

    # Find target player
    # Handle fuzzy matching for player names
    target_eid = None
    target_team = None
    target_name_matched = None
    for pname in players:
        # Exact or prefix match
        if pname == target_player_key or target_player_key.startswith(pname) or pname.startswith(target_player_key):
            target_eid = players[pname]["eid_be_int"]
            target_team = players[pname]["team"]
            target_name_matched = pname
            break

    if target_eid is None:
        # Try fuzzy - remove one char differences
        import difflib
        matches = difflib.get_close_matches(target_player_key, list(players.keys()), n=1, cutoff=0.7)
        if matches:
            target_name_matched = matches[0]
            target_eid = players[target_name_matched]["eid_be_int"]
            target_team = players[target_name_matched]["team"]

    if target_eid is None:
        print(f"ERROR: Could not find player {target_player_key}")
        return None

    print(f"\nTarget matched: {target_name_matched} -> eid=0x{target_eid:04X}, team={target_team}")

    # Now run KDA detection
    valid_eids = set(eid_to_name.keys())
    detector = KDADetector(valid_eids)

    # Process each frame
    for start, end, fidx in frame_boundaries:
        frame_data = all_data[start:end]
        detector.process_frame(fidx, frame_data)

    team_map = {eid: eid_to_team[eid] for eid in valid_eids}
    results = detector.get_results(game_duration=duration, team_map=team_map)

    # Print all detected assists
    detected_assists_count = results[target_eid].assists if target_eid in results else 0
    print(f"\nDetected assists for {target_name_matched}: {detected_assists_count} (truth={truth_assists})")
    print(f"Difference: +{detected_assists_count - truth_assists}")

    # Now do DEEP analysis: for each kill event, show what credit records exist
    # and whether target_eid got counted as an assist
    print(f"\n{'~'*70}")
    print(f"KILL-BY-KILL CREDIT RECORD ANALYSIS")
    print(f"{'~'*70}")

    assists_given_to_target = []

    for kill_num, kev in enumerate(detector.kill_events, 1):
        killer_eid = kev.killer_eid
        killer_name = eid_to_name.get(killer_eid, f"0x{killer_eid:04X}")
        killer_team = eid_to_team.get(killer_eid, "?")

        # Check if target gets an assist for this kill
        credits_by_eid = defaultdict(list)
        for cr in kev.credits:
            credits_by_eid[cr.eid].append(cr)

        target_gets_assist = False
        if target_eid != killer_eid and target_eid in credits_by_eid:
            vals = [cr.value for cr in credits_by_eid[target_eid]]
            has_1_0 = any(abs(v - 1.0) < 0.01 for v in vals)
            same_team = (eid_to_team.get(target_eid) == killer_team)
            if has_1_0 and same_team:
                target_gets_assist = True

        if target_gets_assist:
            assists_given_to_target.append(kill_num)
            ts_str = f"ts={kev.timestamp:.1f}s" if kev.timestamp else "ts=?"
            print(f"\n  KILL #{kill_num}: {killer_name} ({killer_team}) [{ts_str}] frame={kev.frame_idx}")
            print(f"  ** {target_name_matched} GETS ASSIST HERE **")
            print(f"  Credit records ({len(kev.credits)} total):")
            for cr in kev.credits:
                cr_name = eid_to_name.get(cr.eid, f"0x{cr.eid:04X}")
                cr_team = eid_to_team.get(cr.eid, "?")
                marker = " <-- TARGET" if cr.eid == target_eid else ""
                marker += " [KILLER]" if cr.eid == killer_eid else ""
                print(f"    eid=0x{cr.eid:04X} ({cr_name}, {cr_team}): value={cr.value}{marker}")

            # Show raw bytes around this kill for forensic analysis
            # Find the kill in the data
            print(f"  Raw bytes context (kill offset in frame):")
            for start, end, fidx in frame_boundaries:
                if fidx == kev.frame_idx:
                    frame_data = all_data[start:end]
                    # Find kill header in this frame at the right offset
                    kill_offset = kev.file_offset
                    # Show bytes from -20 to +200 around kill
                    ctx_start = max(0, kill_offset - 20)
                    ctx_end = min(len(frame_data), kill_offset + 200)
                    raw = frame_data[ctx_start:ctx_end]
                    # Show hex dump in lines of 32
                    for i in range(0, len(raw), 32):
                        hex_str = ' '.join(f'{b:02X}' for b in raw[i:i+32])
                        abs_off = ctx_start + i
                        print(f"    {abs_off:06X}: {hex_str}")
                    break

    # Now identify which assists are FALSE (over-detected)
    # We expect truth_assists correct ones, so the excess are false
    excess = detected_assists_count - truth_assists
    if excess > 0:
        print(f"\n{'~'*70}")
        print(f"OVER-DETECTION SUMMARY: {excess} false assist(s)")
        print(f"Target got assists on kills: {assists_given_to_target}")
        print(f"{'~'*70}")

    return {
        "match_idx": match_idx,
        "player": target_player_key,
        "target_eid": target_eid,
        "detected_assists": detected_assists_count,
        "truth_assists": truth_assists,
        "excess": excess,
        "assist_kill_numbers": assists_given_to_target,
        "total_kills_in_match": len(detector.kill_events),
    }


def main():
    print("=" * 80)
    print("ASSIST OVER-DETECTION INVESTIGATION")
    print("=" * 80)

    all_results = []

    for case in ERROR_CASES:
        result = analyze_match_assists(
            case["match_idx"],
            case["player"],
            case["truth_a"],
        )
        if result:
            all_results.append(result)

    # Summary
    print(f"\n\n{'='*80}")
    print("SUMMARY OF ALL ERROR CASES")
    print(f"{'='*80}")
    for r in all_results:
        print(f"  M{r['match_idx']+1} {r['player']}: detected={r['detected_assists']}, "
              f"truth={r['truth_assists']}, excess=+{r['excess']}, "
              f"assist_on_kills={r['assist_kill_numbers']}")


if __name__ == "__main__":
    main()
