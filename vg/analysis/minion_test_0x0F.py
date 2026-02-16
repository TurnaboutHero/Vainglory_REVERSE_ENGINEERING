"""
Test action byte 0x0F vs 0x0E across all matches
================================================
Hypothesis: 0x0F might capture additional minion kills that 0x0E misses.
"""
import os
import struct
import json
from collections import defaultdict
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

TRUTH_PATH = "vg/output/tournament_truth.json"
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

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
                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")
                players.append({"eid_be": eid_be, "hero_name": hero_name})
            pos += 1
    return players


def count_minion_kills(concatenated, valid_eids, action_byte):
    """Count minion kills using [10 04 1D] with value=1.0 and specified action byte."""
    counts = defaultdict(int)
    pos = 0

    while True:
        pos = concatenated.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(concatenated):
            pos += 1
            continue

        if concatenated[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", concatenated, pos + 5)[0]
        if eid not in valid_eids:
            pos += 1
            continue

        value = struct.unpack_from(">f", concatenated, pos + 7)[0]
        action = concatenated[pos + 11]

        if abs(value - 1.0) < 0.01 and action == action_byte:
            counts[eid] += 1

        pos += 3

    return counts


print("[STAGE:begin:action_byte_comparison]")
print("=" * 80)
print("Testing Action Byte 0x0E vs 0x0F Across All Matches")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

results_0E = []
results_0F = []
results_combined = []

for match_idx, match in enumerate(truth_data["matches"][:9]):
    if match_idx == 8:  # Skip match 9
        continue

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

    # Load frame 0
    frame0_path = os.path.join(cache_dir, f"{prefix}.0.vgr")
    if not os.path.exists(frame0_path):
        frame0_path = replay_file
    if not os.path.exists(frame0_path):
        continue

    with open(frame0_path, "rb") as f:
        frame0 = f.read()

    players = find_player_entities(frame0)
    truth_by_hero = {pdata["hero_name"]: pdata for pname, pdata in match["players"].items()}

    truth_minion_kills = {}
    for p in players:
        if p["hero_name"] in truth_by_hero:
            mk = truth_by_hero[p["hero_name"]].get("minion_kills")
            if mk is not None:
                truth_minion_kills[p["eid_be"]] = mk

    valid_eids = set(truth_minion_kills.keys())

    # Load all frames
    all_frames = []
    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and len(all_frames) > 0:
                break
            continue
        with open(fpath, "rb") as f:
            all_frames.append(f.read())

    concatenated = b''.join(all_frames)

    # Test both action bytes
    counts_0E = count_minion_kills(concatenated, valid_eids, 0x0E)
    counts_0F = count_minion_kills(concatenated, valid_eids, 0x0F)

    # Calculate accuracy for each
    perfect_0E = sum(1 for eid in valid_eids if counts_0E.get(eid, 0) == truth_minion_kills[eid])
    perfect_0F = sum(1 for eid in valid_eids if counts_0F.get(eid, 0) == truth_minion_kills[eid])

    # Test combined (0x0E OR 0x0F)
    counts_combined = defaultdict(int)
    for eid in valid_eids:
        counts_combined[eid] = counts_0E.get(eid, 0) + counts_0F.get(eid, 0)
    perfect_combined = sum(1 for eid in valid_eids if counts_combined.get(eid, 0) == truth_minion_kills[eid])

    total = len(valid_eids)

    results_0E.append({"match": match_idx + 1, "perfect": perfect_0E, "total": total})
    results_0F.append({"match": match_idx + 1, "perfect": perfect_0F, "total": total})
    results_combined.append({"match": match_idx + 1, "perfect": perfect_combined, "total": total})

    print(f"\nMatch {match_idx + 1}: ({len(all_frames)} frames)")
    print(f"  0x0E:      {perfect_0E}/{total} ({100*perfect_0E/total:.1f}%)")
    print(f"  0x0F:      {perfect_0F}/{total} ({100*perfect_0F/total:.1f}%)")
    print(f"  Combined:  {perfect_combined}/{total} ({100*perfect_combined/total:.1f}%)")

    # Show differences for Match 6 (the problematic one)
    if match_idx == 5:
        print(f"\n  Match 6 detailed comparison:")
        for eid in sorted(valid_eids):
            truth = truth_minion_kills[eid]
            det_0E = counts_0E.get(eid, 0)
            det_0F = counts_0F.get(eid, 0)
            det_combined = counts_combined.get(eid, 0)
            hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)

            diff_0E = det_0E - truth
            diff_0F = det_0F - truth
            diff_combined = det_combined - truth

            best = "0E" if abs(diff_0E) <= abs(diff_0F) and abs(diff_0E) <= abs(diff_combined) else \
                   "0F" if abs(diff_0F) <= abs(diff_combined) else "BOTH"

            print(f"    EID {eid:04X} ({hero:12s}) Truth:{truth:3d} 0E:{det_0E:3d}({diff_0E:+3d}) 0F:{det_0F:3d}({diff_0F:+3d}) Both:{det_combined:3d}({diff_combined:+3d}) Best:{best}")

# Overall statistics
total_perfect_0E = sum(r["perfect"] for r in results_0E)
total_perfect_0F = sum(r["perfect"] for r in results_0F)
total_perfect_combined = sum(r["perfect"] for r in results_combined)
total_players = sum(r["total"] for r in results_0E)

print("\n" + "=" * 80)
print("OVERALL RESULTS")
print("=" * 80)
print(f"[STAT:0x0E_accuracy] {total_perfect_0E}/{total_players} ({100*total_perfect_0E/total_players:.1f}%)")
print(f"[STAT:0x0F_accuracy] {total_perfect_0F}/{total_players} ({100*total_perfect_0F/total_players:.1f}%)")
print(f"[STAT:combined_accuracy] {total_perfect_combined}/{total_players} ({100*total_perfect_combined/total_players:.1f}%)")

if total_perfect_0F > total_perfect_0E:
    print(f"\n[FINDING] 0x0F is BETTER than 0x0E by {total_perfect_0F - total_perfect_0E} players")
elif total_perfect_0E > total_perfect_0F:
    print(f"\n[FINDING] 0x0E is BETTER than 0x0F by {total_perfect_0E - total_perfect_0F} players")
else:
    print(f"\n[FINDING] 0x0E and 0x0F have EQUAL accuracy")

if total_perfect_combined > max(total_perfect_0E, total_perfect_0F):
    print(f"[FINDING] Combining 0x0E + 0x0F improves accuracy by {total_perfect_combined - max(total_perfect_0E, total_perfect_0F)} players")

print("\n[STAGE:status:success]")
print("[STAGE:end:action_byte_comparison]")

# Save results
os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/action_byte_comparison.json", "w") as f:
    json.dump({
        "results_0E": results_0E,
        "results_0F": results_0F,
        "results_combined": results_combined,
        "summary": {
            "0x0E": {"perfect": total_perfect_0E, "total": total_players, "accuracy": total_perfect_0E / total_players},
            "0x0F": {"perfect": total_perfect_0F, "total": total_players, "accuracy": total_perfect_0F / total_players},
            "combined": {"perfect": total_perfect_combined, "total": total_players, "accuracy": total_perfect_combined / total_players},
        }
    }, f, indent=2)

print("\n[FINDING] Comparison results saved to .omc/scientist/action_byte_comparison.json")
