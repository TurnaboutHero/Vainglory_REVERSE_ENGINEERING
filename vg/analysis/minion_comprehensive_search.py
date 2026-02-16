"""
Comprehensive Minion Kill Pattern Search
=========================================
Expanded search beyond [XX 04 YY] structure.
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
                players.append({
                    "eid_be": eid_be,
                    "hero_name": hero_name,
                })
            pos += 1
    return players


print("[STAGE:begin:comprehensive_search]")
print("=" * 80)
print("Comprehensive Minion Kill Pattern Search")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

# Load match 1 (perfect with current method)
match = truth_data["matches"][0]
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

print(f"\n[DATA] Match 1 truth data:")
for eid, mk in sorted(truth_minion_kills.items()):
    hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
    print(f"  EID {eid:04X} ({hero:12s}): {mk:3d} minion kills")

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
print(f"\n[DATA] Loaded {len(all_frames)} frames, total {len(concatenated):,} bytes")

# Test current pattern: [10 04 1D] with value=1.0 and action byte 0x0E
print("\n" + "=" * 80)
print("Testing current pattern: [10 04 1D] with value=1.0 (f32 BE) and action 0x0E")
print("=" * 80)

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
counts_current = defaultdict(int)
pos = 0

while True:
    pos = concatenated.find(CREDIT_HEADER, pos)
    if pos == -1:
        break
    if pos + 12 > len(concatenated):
        pos += 1
        continue

    # Check structure: [10 04 1D] [00 00] [eid BE 2B] [value f32 BE 4B] [action 1B]
    if concatenated[pos+3:pos+5] != b'\x00\x00':
        pos += 1
        continue

    eid = struct.unpack_from(">H", concatenated, pos + 5)[0]
    if eid not in valid_eids:
        pos += 1
        continue

    value = struct.unpack_from(">f", concatenated, pos + 7)[0]
    action = concatenated[pos + 11]

    if abs(value - 1.0) < 0.01 and action == 0x0E:
        counts_current[eid] += 1

    pos += 3

print(f"\nResults with current pattern:")
perfect = 0
for eid in sorted(valid_eids):
    truth = truth_minion_kills[eid]
    detected = counts_current.get(eid, 0)
    diff = detected - truth
    status = "OK" if diff == 0 else "ERROR"
    if diff == 0:
        perfect += 1
    hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
    print(f"  {status}: EID {eid:04X} ({hero:12s}) Truth:{truth:3d} Detected:{detected:3d} Diff:{diff:+4d}")

print(f"\n[STAT:current_pattern_accuracy] {perfect}/{len(valid_eids)} ({100*perfect/len(valid_eids):.1f}%)")

# Now search for alternative action bytes
print("\n" + "=" * 80)
print("Searching alternative action bytes with [10 04 1D] and value=1.0...")
print("=" * 80)

best_action_bytes = []

for action_byte in range(0x00, 0x20):
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

    # Calculate accuracy
    perfect = sum(1 for eid in valid_eids if counts.get(eid, 0) == truth_minion_kills[eid])
    total = len(valid_eids)
    acc = perfect / total if total > 0 else 0

    if acc >= 0.8:
        best_action_bytes.append({
            "action_byte": action_byte,
            "accuracy": acc,
            "perfect": perfect,
            "total": total,
            "counts": dict(counts),
        })
        print(f"  Action byte 0x{action_byte:02X}: {perfect}/{total} ({acc*100:.1f}%)")

if best_action_bytes:
    print(f"\n[STAT:alternative_action_bytes] {len(best_action_bytes)} found with >80% accuracy")

    # Show details for best alternative
    best_action_bytes.sort(key=lambda x: (-x["accuracy"], -x["perfect"]))
    print("\nBest action byte details:")
    for ab in best_action_bytes[:3]:
        print(f"\n  Action byte 0x{ab['action_byte']:02X}: {ab['perfect']}/{ab['total']} ({ab['accuracy']*100:.1f}%)")
        for eid in sorted(valid_eids):
            truth = truth_minion_kills[eid]
            detected = ab['counts'].get(eid, 0)
            diff = detected - truth
            hero = next(p["hero_name"] for p in players if p["eid_be"] == eid)
            print(f"    EID {eid:04X} ({hero:12s}) Truth:{truth:3d} Detected:{detected:3d} Diff:{diff:+4d}")
else:
    print("\n[FINDING] No alternative action bytes found - 0x0E appears optimal for this structure")

print("\n[STAGE:status:success]")
print("[STAGE:end:comprehensive_search]")

# Save results
os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/minion_comprehensive_search.json", "w") as f:
    json.dump({
        "match": 1,
        "truth": {f"{k:04X}": v for k, v in truth_minion_kills.items()},
        "current_pattern": {
            "pattern": "10 04 1D",
            "structure": "[10 04 1D] [00 00] [eid BE] [1.0 f32 BE] [0E]",
            "accuracy": perfect / len(valid_eids),
        },
        "alternative_action_bytes": [
            {
                "action_byte": f"0x{ab['action_byte']:02X}",
                "accuracy": ab["accuracy"],
                "perfect": ab["perfect"],
                "total": ab["total"],
            }
            for ab in best_action_bytes[:10]
        ] if best_action_bytes else []
    }, f, indent=2)

print("\n[FINDING] Search results saved to .omc/scientist/minion_comprehensive_search.json")
