"""
Overcount Diagnostic: Analyze +1 overcounting in kills and deaths
=================================================================
For each match with overcounting, show all detected events with timestamps
to identify if the extra event is at game start, end, or elsewhere.
"""
import os
import struct
import json
from collections import Counter, defaultdict

TRUTH_PATH = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json"
with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")
try:
    from vg.core.vgr_mapping import BINARY_HERO_ID_MAP
except:
    BINARY_HERO_ID_MAP = {}

KILL_HDR = bytes([0x18, 0x04, 0x1C])
DEATH_HDR = bytes([0x08, 0x04, 0x31])


def find_player_entities(frame0_data):
    players = []
    for marker_bytes in [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]:
        pos = 0
        while True:
            pos = frame0_data.find(marker_bytes, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(frame0_data):
                eid_le = struct.unpack_from("<H", frame0_data, pos + 0xA5)[0]
                eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)
                hero_id = struct.unpack_from("<H", frame0_data, pos + 0xA9)[0]
                team = frame0_data[pos + 0xD5]
                team_str = "left" if team == 1 else "right" if team == 2 else f"unk_{team}"
                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")
                players.append({
                    "eid_le": eid_le, "eid_be": eid_be,
                    "hero_id": hero_id, "hero_name": hero_name, "team": team_str,
                })
            pos += 1
    return players


def find_kills(data, valid_eids_be, frame_idx):
    results = []
    pos = 0
    while True:
        pos = data.find(KILL_HDR, pos)
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
        eid = struct.unpack_from(">H", data, pos+5)[0]
        if eid in valid_eids_be:
            ts = None
            if pos >= 7:
                ts = struct.unpack_from(">f", data, pos - 7)[0]
                if not (0 < ts < 1800):
                    ts = None
            results.append({"eid": eid, "ts": ts, "pos": pos, "frame": frame_idx})
        pos += 1
    return results


def find_deaths(data, valid_eids_be, frame_idx):
    results = []
    pos = 0
    while True:
        pos = data.find(DEATH_HDR, pos)
        if pos == -1:
            break
        if pos + 13 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", data, pos+5)[0]
        ts = struct.unpack_from(">f", data, pos+9)[0]
        if eid in valid_eids_be and 0 < ts < 1800:
            results.append({"eid": eid, "ts": ts, "pos": pos, "frame": frame_idx})
        pos += 1
    return results


# Known overcounting cases from v1:
# Kills: Match 5 Kestrel +1, Match 6 Samuel +1
# Deaths: Match 1 Magnus +1, Match 2 Tony +1, Match 3 Phinn/Skaarf +1,
#          Match 5 Warhawk +1, Match 6 Lyra +1, Match 10 Ardan/Grace +1

print("=" * 80)
print("OVERCOUNT DIAGNOSTIC")
print("=" * 80)
print()

for match_idx, match in enumerate(truth_data["matches"]):
    replay_file = match["replay_file"]
    if not os.path.exists(replay_file):
        continue

    replay_dir = os.path.dirname(replay_file)
    basename = os.path.basename(replay_file)
    if not basename.endswith(".0.vgr"):
        continue
    prefix = basename[:-6]

    cache_dir = os.path.join(replay_dir, "cache")
    if not os.path.exists(cache_dir):
        cache_dir = replay_dir

    frame0_path = os.path.join(cache_dir, f"{prefix}.0.vgr")
    if not os.path.exists(frame0_path):
        frame0_path = replay_file
    if not os.path.exists(frame0_path):
        continue

    with open(frame0_path, "rb") as f:
        frame0 = f.read()

    players = find_player_entities(frame0)
    if not players:
        continue

    eid_be_to_player = {p["eid_be"]: p for p in players}
    valid_eids = set(eid_be_to_player.keys())

    truth_players = match["players"]
    truth_heroes = {pdata["hero_name"]: pdata for pname, pdata in truth_players.items()}
    player_to_truth = {}
    for p in players:
        if p["hero_name"] in truth_heroes:
            player_to_truth[p["eid_be"]] = truth_heroes[p["hero_name"]]

    # Collect ALL events with full detail
    all_kills = []
    all_deaths = []
    total_frames = 0
    game_duration = match["match_info"]["duration_seconds"]

    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and total_frames > 0:
                break
            continue
        with open(fpath, "rb") as f:
            data = f.read()
        total_frames += 1
        all_kills.extend(find_kills(data, valid_eids, frame_idx))
        all_deaths.extend(find_deaths(data, valid_eids, frame_idx))

    # Check for overcounting
    kill_counts = Counter(k["eid"] for k in all_kills)
    death_counts = Counter(d["eid"] for d in all_deaths)

    overcounted_heroes = []
    for eid_be, p in eid_be_to_player.items():
        truth_match = player_to_truth.get(eid_be)
        if not truth_match:
            continue

        dk = kill_counts.get(eid_be, 0)
        dd = death_counts.get(eid_be, 0)
        tk = truth_match["kills"]
        td = truth_match["deaths"]

        if dk > tk or dd > td:
            overcounted_heroes.append({
                "hero": truth_match["hero_name"],
                "eid_be": eid_be,
                "det_k": dk, "truth_k": tk,
                "det_d": dd, "truth_d": td,
            })

    if not overcounted_heroes:
        continue

    print(f"Match {match_idx+1}: duration={game_duration}s, frames={total_frames}")
    print()

    for oc in overcounted_heroes:
        hero = oc["hero"]
        eid = oc["eid_be"]

        # Show kill overcounting
        if oc["det_k"] > oc["truth_k"]:
            hero_kills = sorted([k for k in all_kills if k["eid"] == eid],
                               key=lambda x: x["ts"] or 0)
            print(f"  {hero} KILL OVERCOUNT: det={oc['det_k']} truth={oc['truth_k']} (+{oc['det_k']-oc['truth_k']})")
            for i, k in enumerate(hero_kills):
                ts_pct = f"{100*k['ts']/game_duration:.0f}%" if k['ts'] else "?"
                late = " <<< LATE" if k['ts'] and k['ts'] > game_duration else ""
                print(f"    Kill #{i+1}: ts={k['ts']:8.1f}s  frame={k['frame']:3d}  "
                      f"pos=0x{k['pos']:06X}  ({ts_pct} of game){late}")

        # Show death overcounting
        if oc["det_d"] > oc["truth_d"]:
            hero_deaths = sorted([d for d in all_deaths if d["eid"] == eid],
                                key=lambda x: x["ts"] or 0)
            print(f"  {hero} DEATH OVERCOUNT: det={oc['det_d']} truth={oc['truth_d']} (+{oc['det_d']-oc['truth_d']})")
            for i, d in enumerate(hero_deaths):
                ts_pct = f"{100*d['ts']/game_duration:.0f}%" if d['ts'] else "?"
                late = " <<< LATE" if d['ts'] and d['ts'] > game_duration else ""
                print(f"    Death #{i+1}: ts={d['ts']:8.1f}s  frame={d['frame']:3d}  "
                      f"pos=0x{d['pos']:06X}  ({ts_pct} of game){late}")

    print()

# Summary: check if overcounted events cluster at game end
print("=" * 80)
print("PATTERN: Are overcounted events near game end?")
print("=" * 80)
print()
print("If the extra event is consistently > game_duration, we can filter by timestamp.")
