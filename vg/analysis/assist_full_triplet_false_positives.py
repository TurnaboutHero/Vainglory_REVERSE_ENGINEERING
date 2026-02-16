#!/usr/bin/env python3
"""
Investigate full_triplet false positives.

The lone_1_0 filter catches 10/22 false positives. The remaining 12 are full_triplet.
Need to understand:
1. M5 Acex (Lyra) - 1 false triplet on kill #16 (ts=1147.6s, duration=1135s) -> POST-GAME?
2. M6 TenshiiHime (Blackfeather) - truth data mismatch? Name typo "TenshilHime" vs "TenshiiHime"
3. M6 Acex (Lorelai) - 1 extra
4. M9 incomplete match issues

Focus: check if post-game kills (timestamp > duration) explain remaining full_triplet false positives.
"""

import struct
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
import difflib

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from kda_detector import KDADetector

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

with open(TRUTH_PATH) as f:
    truth_data = json.load(f)


def read_all_frames(replay_path):
    p = Path(replay_path)
    frame_dir = p.parent
    replay_name = p.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def frame_index(fp):
        try: return int(fp.stem.split('.')[-1])
        except ValueError: return 0
    frames.sort(key=frame_index)
    frame_boundaries = []
    all_data = bytearray()
    for fp in frames:
        start = len(all_data)
        chunk = fp.read_bytes()
        all_data.extend(chunk)
        frame_boundaries.append((start, len(all_data), int(fp.stem.split('.')[-1])))
    return bytes(all_data), frame_boundaries


def parse_player_blocks(data):
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
        if not candidates: break
        pos, marker = min(candidates, key=lambda x: x[0])
        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126: break
            name_end += 1
        if name_end > name_start:
            try: name = data[name_start:name_end].decode('ascii')
            except: name = ""
            if len(name) >= 3 and name not in seen_names and not name.startswith('GameMode'):
                entity_id = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little')
                team_byte = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                team = "left" if team_byte == 1 else ("right" if team_byte == 2 else "unknown")
                eid_be = struct.unpack(">H", struct.pack("<H", entity_id))[0]
                players[name] = {"eid_be": eid_be, "team": team}
                seen_names.add(name)
        search_start = pos + 1
    return players


def scan_credits_with_action(data, start_pos, valid_eids):
    credits = []
    pos = start_pos
    max_scan = min(start_pos + 500, len(data))
    KILL_H = bytes([0x18, 0x04, 0x1C])
    CREDIT_H = bytes([0x10, 0x04, 0x1D])
    while pos < max_scan:
        if (data[pos:pos + 3] == KILL_H and pos + 16 <= len(data)
                and data[pos+3:pos+5] == b'\x00\x00'
                and data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF'
                and data[pos+11:pos+15] == b'\x3F\x80\x00\x00'
                and data[pos+15] == 0x29):
            break
        if data[pos:pos + 3] == CREDIT_H:
            if pos + 12 <= len(data) and data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11] if pos + 11 < len(data) else None
                if eid in valid_eids and 0 <= value <= 10000:
                    credits.append({"eid": eid, "value": round(value, 2), "action": action})
                pos += 12
                continue
        pos += 1
    return credits


def classify_assist(credits, target_eid):
    tc = [c for c in credits if c["eid"] == target_eid]
    if not tc:
        return "none"
    has_1_0 = any(abs(c["value"] - 1.0) < 0.01 for c in tc)
    if not has_1_0:
        return "none"
    has_gold_06 = any(c["action"] == 0x06 and c["value"] > 1.5 for c in tc)
    has_flag_0b = any(c["action"] == 0x0B and abs(c["value"] - 1.0) < 0.01 for c in tc)
    has_frac_0c = any(c["action"] == 0x0C for c in tc)
    if has_gold_06 and has_flag_0b and has_frac_0c:
        return "full_triplet"
    non_1_0 = [c for c in tc if abs(c["value"] - 1.0) > 0.01]
    if not non_1_0:
        return "lone_1_0"
    return "other"


def analyze_match_detail(midx):
    match = truth_data["matches"][midx]
    replay_file = match["replay_file"]
    duration = match["match_info"]["duration_seconds"]

    first_frame_data = Path(replay_file).read_bytes()
    players = parse_player_blocks(first_frame_data)
    all_data, frame_boundaries = read_all_frames(replay_file)

    eid_to_name = {}
    eid_to_team = {}
    for pname, pinfo in players.items():
        eid_to_name[pinfo["eid_be"]] = pname
        eid_to_team[pinfo["eid_be"]] = pinfo["team"]

    valid_eids = set(eid_to_name.keys())
    detector = KDADetector(valid_eids)
    for start, end, fidx in frame_boundaries:
        detector.process_frame(fidx, all_data[start:end])

    team_map = {eid: eid_to_team[eid] for eid in valid_eids}

    # Build truth mapping with fuzzy name matching
    truth_assists_by_eid = {}
    for pname_truth, pdata in match["players"].items():
        # Try exact match first
        if pname_truth in players:
            truth_assists_by_eid[players[pname_truth]["eid_be"]] = {
                "name": pname_truth, "assists": pdata.get("assists", 0),
                "hero": pdata.get("hero_name", "?"),
            }
        else:
            # Fuzzy match
            matches = difflib.get_close_matches(pname_truth, list(players.keys()), n=1, cutoff=0.7)
            if matches:
                eid = players[matches[0]]["eid_be"]
                truth_assists_by_eid[eid] = {
                    "name": pname_truth, "assists": pdata.get("assists", 0),
                    "hero": pdata.get("hero_name", "?"),
                    "matched_as": matches[0],
                }

    print(f"\n{'='*80}")
    print(f"Match {midx+1}: {Path(replay_file).parent.parent.name}/{Path(replay_file).parent.name}")
    print(f"Duration: {duration}s")
    print(f"{'='*80}")

    # Truth mapping
    print(f"\nTruth name mapping:")
    for eid, info in truth_assists_by_eid.items():
        mapped = info.get("matched_as", info["name"])
        print(f"  {info['name']} -> {eid_to_name.get(eid, '?')} (eid=0x{eid:04X}) hero={info['hero']} truth_A={info['assists']}")

    # Check which players have NO truth mapping
    for eid in valid_eids:
        if eid not in truth_assists_by_eid:
            print(f"  UNMAPPED: {eid_to_name.get(eid, '?')} (eid=0x{eid:04X})")

    # Per-kill assist analysis
    print(f"\nKill-by-kill assist classification:")
    player_assists = defaultdict(list)

    for kill_num, kev in enumerate(detector.kill_events, 1):
        killer_eid = kev.killer_eid
        killer_team = eid_to_team.get(killer_eid, "?")
        kill_ts = kev.timestamp

        # Get raw credits
        for start, end, fidx in frame_boundaries:
            if fidx == kev.frame_idx:
                frame_data = all_data[start:end]
                credits_raw = scan_credits_with_action(frame_data, kev.file_offset + 16, valid_eids)
                break
        else:
            credits_raw = []

        for eid in valid_eids:
            if eid == killer_eid or eid_to_team.get(eid) != killer_team:
                continue
            pattern = classify_assist(credits_raw, eid)
            if pattern != "none":
                is_post_game = kill_ts is not None and kill_ts > duration + 10
                player_assists[eid].append({
                    "kill_num": kill_num,
                    "pattern": pattern,
                    "timestamp": kill_ts,
                    "post_game": is_post_game,
                })

    # Print per-player analysis
    for eid in valid_eids:
        assists = player_assists.get(eid, [])
        if not assists:
            continue
        pname = eid_to_name.get(eid, "?")
        truth_info = truth_assists_by_eid.get(eid, {})
        truth_a = truth_info.get("assists", "?")
        hero = truth_info.get("hero", "?")

        full = sum(1 for a in assists if a["pattern"] == "full_triplet")
        lone = sum(1 for a in assists if a["pattern"] == "lone_1_0")
        post_game = sum(1 for a in assists if a["post_game"])
        total = len(assists)

        marker = ""
        if truth_a != "?" and total != truth_a:
            diff = total - truth_a
            marker = f" *** ERROR {'+' if diff > 0 else ''}{diff}"

        print(f"  {pname} ({hero}): total={total} truth={truth_a} "
              f"[full={full}, lone={lone}, post_game={post_game}]{marker}")

        # Show details for error cases
        if marker:
            for a in assists:
                pg = " POST-GAME" if a["post_game"] else ""
                ts_str = f"ts={a['timestamp']:.1f}s" if a["timestamp"] else "ts=?"
                print(f"    kill#{a['kill_num']}: {a['pattern']} {ts_str}{pg}")


# Analyze the problematic matches
print("ANALYZING MATCHES WITH ERRORS")
print("=" * 80)

# All matches
for i in range(len(truth_data["matches"])):
    analyze_match_detail(i)
