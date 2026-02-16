"""
Search for alternative minion kill patterns
============================================
Hypothesis: Missing minion kills might be in:
1. Credit records with different values (not just 1.0)
2. Different event headers (not [10 04 1D])
3. Multiple action bytes combined
"""
import os
import struct
import json
from collections import defaultdict
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

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
                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")
                players.append({"eid_be": eid_be, "hero_name": hero_name})
            pos += 1
    return players


print("[STAGE:begin:alternative_patterns]")
print("=" * 80)
print("Testing Alternative Minion Kill Patterns on Match 6")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

# Match 6
match = truth_data["matches"][5]
replay_file = match["replay_file"]
replay_dir = os.path.dirname(replay_file)
basename = os.path.basename(replay_file)
prefix = basename[:-6]

cache_dir = os.path.join(replay_dir, "cache")
if not os.path.exists(cache_dir):
    cache_dir = replay_dir

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
for frame_idx in range(500):
    fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
    if not os.path.exists(fpath):
        if frame_idx > 10 and len(all_frames) > 0:
            break
        continue
    with open(fpath, "rb") as f:
        all_frames.append(f.read())

concatenated = b''.join(all_frames)

print(f"[DATA] Match 6: {len(all_frames)} frames, {len(concatenated):,} bytes")
print(f"\nTruth minion kills:")
total_truth = sum(truth_minion_kills.values())
for eid in sorted(valid_eids):
    hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
    print(f"  EID {eid:04X} ({hero:12s}): {truth_minion_kills[eid]:3d}")
print(f"  TOTAL: {total_truth}")

# Test 1: Combine multiple action bytes (0x0E + 0x0D + 0x0C + 0x0B)
print("\n" + "=" * 80)
print("Test 1: Combine action bytes 0x0E, 0x0D, 0x0C, 0x0B with value=1.0")
print("=" * 80)

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
action_bytes_to_test = [0x0E, 0x0D, 0x0C, 0x0B]

counts_combined = defaultdict(int)
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

    if abs(value - 1.0) < 0.01 and action in action_bytes_to_test:
        counts_combined[eid] += 1

    pos += 3

perfect = 0
total_detected = sum(counts_combined.values())
print(f"\nTotal detected: {total_detected} (truth: {total_truth}, diff: {total_detected - total_truth:+d})")
for eid in sorted(valid_eids):
    truth = truth_minion_kills[eid]
    detected = counts_combined.get(eid, 0)
    diff = detected - truth
    if diff == 0:
        perfect += 1
    hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
    status = "OK" if diff == 0 else "ERR"
    print(f"  {status}: EID {eid:04X} ({hero:12s}) Truth:{truth:3d} Detected:{detected:3d} Diff:{diff:+4d}")

print(f"[STAT:combined_action_bytes] {perfect}/10 perfect, total_error={sum(abs(counts_combined.get(eid, 0) - truth_minion_kills[eid]) for eid in valid_eids)}")

# Test 2: ANY value (not just 1.0) with action 0x0E
print("\n" + "=" * 80)
print("Test 2: Action 0x0E with ANY value (not just 1.0)")
print("=" * 80)

counts_any_value = defaultdict(int)
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

    action = concatenated[pos + 11]

    if action == 0x0E:
        counts_any_value[eid] += 1

    pos += 3

perfect = 0
total_detected = sum(counts_any_value.values())
print(f"\nTotal detected: {total_detected} (truth: {total_truth}, diff: {total_detected - total_truth:+d})")
for eid in sorted(valid_eids):
    truth = truth_minion_kills[eid]
    detected = counts_any_value.get(eid, 0)
    diff = detected - truth
    if diff == 0:
        perfect += 1
    hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
    status = "OK" if diff == 0 else "ERR"
    print(f"  {status}: EID {eid:04X} ({hero:12s}) Truth:{truth:3d} Detected:{detected:3d} Diff:{diff:+4d}")

print(f"[STAT:any_value_0x0E] {perfect}/10 perfect")

# Test 3: Check if truth might be WRONG (compare to other matches)
print("\n" + "=" * 80)
print("Test 3: Compare Match 6 truth to match duration ratio")
print("=" * 80)

all_match_stats = []
for mi, m in enumerate(truth_data["matches"][:9]):
    if mi == 8:
        continue
    duration = m["match_info"]["duration_seconds"]
    total_mk = sum(p.get("minion_kills", 0) for p in m["players"].values() if p.get("minion_kills") is not None)
    mk_per_min = total_mk / (duration / 60) if duration > 0 else 0
    all_match_stats.append({
        "match": mi + 1,
        "duration": duration,
        "total_minion_kills": total_mk,
        "mk_per_min": mk_per_min,
    })

print(f"\nMinion kills per minute across matches:")
for s in all_match_stats:
    print(f"  Match {s['match']}: {s['total_minion_kills']:4d} MK in {s['duration']:4d}s = {s['mk_per_min']:.1f} MK/min")

avg_mk_per_min = sum(s["mk_per_min"] for s in all_match_stats) / len(all_match_stats)
match6_expected = avg_mk_per_min * (match["match_info"]["duration_seconds"] / 60)
print(f"\nAverage: {avg_mk_per_min:.1f} MK/min")
print(f"Match 6 expected (based on avg): {match6_expected:.0f} MK")
print(f"Match 6 truth: {total_truth} MK")
print(f"Match 6 detected (0x0E, value=1.0): {sum(counts_combined.get(eid, 0) for eid in valid_eids if eid in counts_combined)} MK")

if abs(match6_expected - sum(counts_combined.values())) < abs(total_truth - sum(counts_combined.values())):
    print(f"\n[FINDING] Detected count ({sum(counts_combined.values())}) is closer to expected ({match6_expected:.0f}) than truth ({total_truth})")
    print(f"[LIMITATION] Truth data for Match 6 may be inaccurate")

print("\n[STAGE:status:success]")
print("[STAGE:end:alternative_patterns]")

os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/minion_alternative_patterns.json", "w") as f:
    json.dump({
        "match6_truth_total": total_truth,
        "detected_0x0E_value1.0": sum(counts_combined.get(eid, 0) for eid in valid_eids if eid in counts_combined),
        "all_match_stats": all_match_stats,
        "avg_mk_per_min": avg_mk_per_min,
        "match6_expected_mk": match6_expected,
    }, f, indent=2)

print("\n[FINDING] Results saved to .omc/scientist/minion_alternative_patterns.json")
