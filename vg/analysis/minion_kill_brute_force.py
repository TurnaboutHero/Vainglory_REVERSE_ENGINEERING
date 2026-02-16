"""
Minion Kill Detection - Brute Force Frequency Matching
========================================================
Uses the same technique that successfully found kill/death patterns:
brute-force frequency matching to find patterns that match truth data.

Current accuracy: 97.1% (67/69) using [10 04 1D] with value=1.0 and action byte 0x0E
Goal: Improve to 90%+ or validate current approach is optimal.
"""
import os
import struct
import json
from collections import defaultdict
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.kda_detector import KDADetector
from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

TRUTH_PATH = "vg/output/tournament_truth.json"

def find_player_entities(frame0_data):
    """Extract player entities from frame 0."""
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

                # Extract player name
                name_start = pos + 3
                name_end = name_start
                while name_end < len(frame0_data) and name_end < name_start + 30:
                    byte = frame0_data[name_end]
                    if byte < 32 or byte > 126:
                        break
                    name_end += 1
                player_name = ""
                if name_end > name_start:
                    try:
                        player_name = frame0_data[name_start:name_end].decode('ascii')
                    except Exception:
                        pass

                players.append({
                    "eid_le": eid_le, "eid_be": eid_be,
                    "hero_id": hero_id, "hero_name": hero_name, "team": team_str,
                    "player_name": player_name,
                })
            pos += 1
    return players


print("[STAGE:begin:validation]")
print("=" * 80)
print("PHASE 1: Validate Current Minion Detection (action byte 0x0E)")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

total_perfect = 0
total_players = 0
all_errors = []
match_results = []

for match_idx, match in enumerate(truth_data["matches"][:9]):
    if match_idx == 8:  # Skip match 9 (incomplete)
        continue

    replay_file = match["replay_file"]
    if not os.path.exists(replay_file):
        print(f"Match {match_idx + 1}: SKIP (file not found)")
        continue

    replay_dir = os.path.dirname(replay_file)
    basename = os.path.basename(replay_file)
    if not basename.endswith(".0.vgr"):
        print(f"Match {match_idx + 1}: SKIP (invalid filename)")
        continue
    prefix = basename[:-6]

    cache_dir = os.path.join(replay_dir, "cache")
    if not os.path.exists(cache_dir):
        cache_dir = replay_dir

    # Load frame 0
    frame0_path = os.path.join(cache_dir, f"{prefix}.0.vgr")
    if not os.path.exists(frame0_path):
        frame0_path = replay_file
    if not os.path.exists(frame0_path):
        print(f"Match {match_idx + 1}: SKIP (frame 0 not found)")
        continue

    with open(frame0_path, "rb") as f:
        frame0 = f.read()

    players = find_player_entities(frame0)
    if not players:
        print(f"Match {match_idx + 1}: SKIP (no players found)")
        continue

    # Map entity IDs to truth data
    truth_players = match["players"]
    truth_by_hero = {pdata["hero_name"]: pdata for pname, pdata in truth_players.items()}

    eid_to_truth = {}
    for p in players:
        if p["hero_name"] in truth_by_hero:
            eid_to_truth[p["eid_be"]] = truth_by_hero[p["hero_name"]]

    valid_eids = set([p["eid_be"] for p in players])

    # Run KDADetector
    detector = KDADetector(valid_entity_ids=valid_eids)
    total_frames = 0

    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and total_frames > 0:
                break
            continue
        with open(fpath, "rb") as f:
            data = f.read()
        detector.process_frame(frame_idx, data)
        total_frames += 1

    results = detector.get_results()

    # Compare with truth
    match_errors = []
    match_name = match.get("replay_name", "")[:40]
    print(f"\nMatch {match_idx + 1}: {match_name}... ({total_frames} frames)")

    for eid, result in results.items():
        truth = eid_to_truth.get(eid)
        if not truth:
            continue

        truth_mk = truth.get("minion_kills")
        if truth_mk is None:
            continue

        detected_mk = result.minion_kills
        total_players += 1
        diff = detected_mk - truth_mk

        if diff == 0:
            total_perfect += 1
        else:
            hero = None
            for p in players:
                if p["eid_be"] == eid:
                    hero = p["hero_name"]
                    break
            match_errors.append({
                "match": match_idx + 1,
                "eid": eid,
                "hero": hero,
                "truth": truth_mk,
                "detected": detected_mk,
                "diff": diff,
            })
            all_errors.append(match_errors[-1])

    if match_errors:
        for err in match_errors:
            print(f"  ERROR: EID {err['eid']:04X} ({err['hero']:12s}) Truth:{err['truth']:3d} Detected:{err['detected']:3d} Diff:{err['diff']:+3d}")
    else:
        print(f"  OK - All {len([e for e in eid_to_truth.values() if e.get('minion_kills') is not None])} players perfect")

    match_results.append({
        "match": match_idx + 1,
        "total_frames": total_frames,
        "players_checked": len([e for e in eid_to_truth.values() if e.get("minion_kills") is not None]),
        "errors": len(match_errors),
    })

print("\n" + "=" * 80)
print(f"[STAT:accuracy] {total_perfect}/{total_players} ({100*total_perfect/total_players:.1f}%)")
print(f"[STAT:errors] {len(all_errors)}")
print("[STAGE:status:success]")
print("[STAGE:end:validation]")

if all_errors:
    print("\n" + "=" * 80)
    print("ERROR ANALYSIS")
    print("=" * 80)
    for err in all_errors:
        print(f"Match {err['match']}: EID {err['eid']:04X} ({err['hero']:12s}) Diff:{err['diff']:+3d} (Truth:{err['truth']:3d}, Detected:{err['detected']:3d})")

# Save detailed results
output = {
    "validation_date": "2026-02-16",
    "total_matches": len([m for m in match_results]),
    "total_players": total_players,
    "total_perfect": total_perfect,
    "accuracy": total_perfect / total_players if total_players > 0 else 0,
    "errors": all_errors,
    "match_results": match_results,
}

os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/minion_validation.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n[FINDING] Validation results saved to .omc/scientist/minion_validation.json")
