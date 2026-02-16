#!/usr/bin/env python3
"""
Deep analysis of lone_1_0 credit records.

For every lone_1_0 false assist, extract:
- The exact action byte on the 1.0 credit
- Position in credit sequence (early/late)
- Whether it appears ONLY for Blackfeather players
- What byte follows the credit record

Also check: does applying assist post-game filter (ts > duration + 10) fix more errors?
"""

import struct
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter

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
        all_data.extend(fp.read_bytes())
        frame_boundaries.append((start, len(all_data), int(fp.stem.split('.')[-1])))
    return bytes(all_data), frame_boundaries


def parse_player_blocks(data):
    MARKER1 = bytes([0xDA, 0x03, 0xEE])
    MARKER2 = bytes([0xE0, 0x03, 0xEE])
    players = {}
    search_start = 0
    seen = set()
    while True:
        pos1 = data.find(MARKER1, search_start)
        pos2 = data.find(MARKER2, search_start)
        cands = []
        if pos1 != -1: cands.append((pos1, MARKER1))
        if pos2 != -1: cands.append((pos2, MARKER2))
        if not cands: break
        pos, marker = min(cands, key=lambda x: x[0])
        ns = pos + len(marker)
        ne = ns
        while ne < len(data) and ne < ns + 30:
            if data[ne] < 32 or data[ne] > 126: break
            ne += 1
        if ne > ns:
            try: name = data[ns:ne].decode('ascii')
            except: name = ""
            if len(name) >= 3 and name not in seen and not name.startswith('GameMode'):
                eid_le = int.from_bytes(data[pos+0xA5:pos+0xA5+2], 'little')
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                tb = data[pos+0xD5] if pos+0xD5 < len(data) else None
                team = "left" if tb == 1 else ("right" if tb == 2 else "unknown")
                players[name] = {"eid_be": eid_be, "team": team}
                seen.add(name)
        search_start = pos + 1
    return players


def scan_credits_detailed(data, start_pos, valid_eids):
    """Scan credits with full action byte and position info."""
    credits = []
    pos = start_pos
    max_scan = min(start_pos + 500, len(data))
    KILL_H = bytes([0x18, 0x04, 0x1C])
    CREDIT_H = bytes([0x10, 0x04, 0x1D])
    seq = 0
    while pos < max_scan:
        if (data[pos:pos+3] == KILL_H and pos+16 <= len(data)
                and data[pos+3:pos+5] == b'\x00\x00'
                and data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF'
                and data[pos+11:pos+15] == b'\x3F\x80\x00\x00'
                and data[pos+15] == 0x29):
            break
        if data[pos:pos+3] == CREDIT_H:
            if pos+12 <= len(data) and data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos+5)[0]
                value = struct.unpack_from(">f", data, pos+7)[0]
                action = data[pos+11]
                # Also get 2 bytes after action for context
                ctx_after = data[pos+12:pos+14].hex() if pos+14 <= len(data) else "??"
                if eid in valid_eids and 0 <= value <= 10000:
                    credits.append({
                        "eid": eid, "value": round(value, 2),
                        "action": action, "seq": seq,
                        "offset": pos, "ctx_after": ctx_after,
                    })
                    seq += 1
                pos += 12
                continue
        pos += 1
    return credits


def main():
    print("=" * 90)
    print("LONE_1_0 ACTION BYTE DEEP ANALYSIS")
    print("=" * 90)

    lone_1_0_details = []
    full_triplet_fp_details = []

    # Action byte distribution for all 1.0 credits
    action_byte_1_0_true_assist = Counter()
    action_byte_1_0_false_assist = Counter()
    action_byte_1_0_lone = Counter()

    for midx, match in enumerate(truth_data["matches"]):
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

        # Build truth assists
        import difflib
        truth_a_by_eid = {}
        hero_by_eid = {}
        for pt, pd in match["players"].items():
            if pt in players:
                truth_a_by_eid[players[pt]["eid_be"]] = pd.get("assists", 0)
                hero_by_eid[players[pt]["eid_be"]] = pd.get("hero_name", "?")
            else:
                ms = difflib.get_close_matches(pt, list(players.keys()), n=1, cutoff=0.7)
                if ms:
                    truth_a_by_eid[players[ms[0]]["eid_be"]] = pd.get("assists", 0)
                    hero_by_eid[players[ms[0]]["eid_be"]] = pd.get("hero_name", "?")

        # Analyze each kill
        for kill_num, kev in enumerate(detector.kill_events, 1):
            killer_eid = kev.killer_eid
            killer_team = eid_to_team.get(killer_eid, "?")
            kill_ts = kev.timestamp
            is_post_game = kill_ts is not None and kill_ts > duration + 10

            # Get detailed credits
            for start, end, fidx in frame_boundaries:
                if fidx == kev.frame_idx:
                    frame_data = all_data[start:end]
                    credits = scan_credits_detailed(frame_data, kev.file_offset + 16, valid_eids)
                    break
            else:
                credits = []

            for eid in valid_eids:
                if eid == killer_eid or eid_to_team.get(eid) != killer_team:
                    continue

                tc = [c for c in credits if c["eid"] == eid]
                has_1_0 = any(abs(c["value"] - 1.0) < 0.01 for c in tc)
                if not has_1_0:
                    continue

                # Classify
                has_gold_06 = any(c["action"] == 0x06 and c["value"] > 1.5 for c in tc)
                has_0b = any(c["action"] == 0x0B and abs(c["value"] - 1.0) < 0.01 for c in tc)
                has_0c = any(c["action"] == 0x0C for c in tc)

                is_full = has_gold_06 and has_0b and has_0c
                non_1_0 = [c for c in tc if abs(c["value"] - 1.0) > 0.01]
                is_lone = not non_1_0

                hero = hero_by_eid.get(eid, "?")
                pname = eid_to_name.get(eid, "?")

                # Find the 1.0 credit action byte
                one_credits = [c for c in tc if abs(c["value"] - 1.0) < 0.01]

                if is_lone:
                    for oc in one_credits:
                        action_byte_1_0_lone[oc["action"]] += 1
                        lone_1_0_details.append({
                            "match": midx + 1,
                            "kill_num": kill_num,
                            "player": pname,
                            "hero": hero,
                            "action": oc["action"],
                            "seq_pos": oc["seq"],
                            "total_credits": len(credits),
                            "ts": kill_ts,
                            "post_game": is_post_game,
                            "ctx_after": oc["ctx_after"],
                        })
                elif is_full:
                    for oc in one_credits:
                        if oc["action"] == 0x0B:
                            action_byte_1_0_true_assist[0x0B] += 1

    # Print findings
    print(f"\n{'='*90}")
    print(f"ALL lone_1_0 INSTANCES ({len(lone_1_0_details)} total)")
    print(f"{'='*90}")

    for d in lone_1_0_details:
        print(f"  M{d['match']} kill#{d['kill_num']}: {d['player']} ({d['hero']}) "
              f"action=0x{d['action']:02X} seq={d['seq_pos']}/{d['total_credits']} "
              f"ts={d['ts']:.1f}s post_game={d['post_game']} ctx_after={d['ctx_after']}")

    print(f"\n{'='*90}")
    print("ACTION BYTE DISTRIBUTION FOR 1.0 CREDITS")
    print(f"{'='*90}")
    print(f"  lone_1_0 action bytes: {dict((f'0x{k:02X}', v) for k, v in sorted(action_byte_1_0_lone.items()))}")
    print(f"  full_triplet 0x0B count: {action_byte_1_0_true_assist}")

    # Summary
    print(f"\n{'='*90}")
    print("LONE_1_0 HERO BREAKDOWN")
    print(f"{'='*90}")
    hero_counts = Counter()
    for d in lone_1_0_details:
        hero_counts[d["hero"]] += 1
    for hero, count in hero_counts.most_common():
        print(f"  {hero}: {count}")

    # Check action byte pattern
    print(f"\n{'='*90}")
    print("KEY INSIGHT: ACTION BYTE FILTER")
    print(f"{'='*90}")
    print(f"True assist credit 1.0 always has action byte 0x0B")
    print(f"lone_1_0 action byte distribution: {dict((f'0x{k:02X}', v) for k, v in sorted(action_byte_1_0_lone.items()))}")

    # Check if lone 1.0s all have a non-0x0B action byte
    non_0b_lone = sum(v for k, v in action_byte_1_0_lone.items() if k != 0x0B)
    is_0b_lone = action_byte_1_0_lone.get(0x0B, 0)
    print(f"\n  lone_1_0 with action 0x0B: {is_0b_lone}")
    print(f"  lone_1_0 with action != 0x0B: {non_0b_lone}")
    if is_0b_lone > 0:
        print(f"  WARNING: Some lone_1_0 have 0x0B - action byte alone won't filter all")
    else:
        print(f"  PERFECT: All lone_1_0 have non-0x0B action byte")


if __name__ == "__main__":
    main()
