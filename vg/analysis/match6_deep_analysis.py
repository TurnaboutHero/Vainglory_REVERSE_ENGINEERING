"""
Match 6 Deep Analysis - Why does minion detection fail here?
=============================================================
Match 6 has 9/10 players with errors, all under-counting.
Let's investigate what's different about this match.
"""
import os
import struct
import json
from collections import defaultdict, Counter
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


print("[STAGE:begin:match6_analysis]")
print("=" * 80)
print("Match 6 Deep Analysis - Longest Match with Highest Error Rate")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

# Match 6 (index 5)
match = truth_data["matches"][5]
print(f"\n[DATA] Match 6 info:")
print(f"  Duration: {match['match_info']['duration_seconds']} seconds ({match['match_info']['duration_seconds']/60:.1f} minutes)")
print(f"  Score: {match['match_info']['score_left']}-{match['match_info']['score_right']}")

replay_file = match["replay_file"]
replay_dir = os.path.dirname(replay_file)
basename = os.path.basename(replay_file)
prefix = basename[:-6]

cache_dir = os.path.join(replay_dir, "cache")
if not os.path.exists(cache_dir):
    cache_dir = replay_dir

# Load frame 0
frame0_path = os.path.join(cache_dir, f"{prefix}.0.vgr")
if not os.path.exists(frame0_path):
    frame0_path = replay_file

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
frame_sizes = []
for frame_idx in range(500):
    fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
    if not os.path.exists(fpath):
        if frame_idx > 10 and len(all_frames) > 0:
            break
        continue
    with open(fpath, "rb") as f:
        data = f.read()
        all_frames.append(data)
        frame_sizes.append(len(data))

print(f"\n[DATA] Loaded {len(all_frames)} frames")
print(f"  Total bytes: {sum(frame_sizes):,}")
print(f"  Avg frame size: {sum(frame_sizes)/len(frame_sizes):,.0f} bytes")
print(f"  Min frame size: {min(frame_sizes):,} bytes")
print(f"  Max frame size: {max(frame_sizes):,} bytes")

concatenated = b''.join(all_frames)

# Analyze all [10 04 1D] credit records
print("\n" + "=" * 80)
print("Analyzing ALL [10 04 1D] credit records")
print("=" * 80)

action_byte_dist = Counter()
value_ranges = defaultdict(int)
pos = 0
total_credits = 0

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

    total_credits += 1
    action_byte_dist[action] += 1

    # Categorize values
    if abs(value - 1.0) < 0.01:
        value_ranges["value=1.0"] += 1
    elif 0 < value < 1:
        value_ranges["0<value<1"] += 1
    elif 1 < value < 10:
        value_ranges["1<value<10"] += 1
    elif 10 <= value < 100:
        value_ranges["10<=value<100"] += 1
    elif 100 <= value < 1000:
        value_ranges["100<=value<1000"] += 1
    else:
        value_ranges["other"] += 1

    pos += 3

print(f"\n[STAT:total_credit_records] {total_credits}")
print(f"\nAction byte distribution:")
for action, count in sorted(action_byte_dist.items(), key=lambda x: -x[1])[:20]:
    print(f"  0x{action:02X}: {count:5d} ({100*count/total_credits:.1f}%)")

print(f"\nValue range distribution:")
for vrange, count in sorted(value_ranges.items(), key=lambda x: -x[1]):
    print(f"  {vrange:20s}: {count:5d} ({100*count/total_credits:.1f}%)")

# Try searching for minion kill patterns with different action bytes
print("\n" + "=" * 80)
print("Testing all action bytes with value=1.0 for minion kills")
print("=" * 80)

best_action_bytes_match6 = []

for action_byte in range(0x00, 0x30):
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

    # Calculate errors
    total_error = sum(abs(counts.get(eid, 0) - truth_minion_kills[eid]) for eid in valid_eids)
    perfect = sum(1 for eid in valid_eids if counts.get(eid, 0) == truth_minion_kills[eid])

    if perfect > 0 or total_error < 200:
        best_action_bytes_match6.append({
            "action": action_byte,
            "perfect": perfect,
            "total_error": total_error,
            "counts": dict(counts),
        })

# Sort by perfect matches, then by total error
best_action_bytes_match6.sort(key=lambda x: (-x["perfect"], x["total_error"]))

print(f"\nTop action bytes for Match 6:")
for i, ab in enumerate(best_action_bytes_match6[:10], 1):
    print(f"  {i}. 0x{ab['action']:02X}: {ab['perfect']}/10 perfect, total_error={ab['total_error']}")

# Show details for best
if best_action_bytes_match6:
    best = best_action_bytes_match6[0]
    print(f"\nBest action byte 0x{best['action']:02X} details:")
    for eid in sorted(valid_eids):
        truth = truth_minion_kills[eid]
        detected = best['counts'].get(eid, 0)
        diff = detected - truth
        hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
        status = "OK" if diff == 0 else "ERROR"
        print(f"  {status}: EID {eid:04X} ({hero:12s}) Truth:{truth:3d} Detected:{detected:3d} Diff:{diff:+4d}")

print("\n[STAGE:status:success]")
print("[STAGE:end:match6_analysis]")

# Save results
os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/match6_analysis.json", "w") as f:
    json.dump({
        "match": 6,
        "duration_seconds": match['match_info']['duration_seconds'],
        "frames": len(all_frames),
        "total_bytes": sum(frame_sizes),
        "total_credit_records": total_credits,
        "action_byte_distribution": {f"0x{k:02X}": v for k, v in action_byte_dist.most_common(20)},
        "value_range_distribution": value_ranges,
        "best_action_bytes": [
            {"action": f"0x{ab['action']:02X}", "perfect": ab["perfect"], "total_error": ab["total_error"]}
            for ab in best_action_bytes_match6[:10]
        ]
    }, f, indent=2)

print("\n[FINDING] Match 6 analysis saved to .omc/scientist/match6_analysis.json")
