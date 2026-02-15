"""Quick test: verify KDADetector module produces same results as cross-validation."""
import os
import struct
import json
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.kda_detector import KDADetector
from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

# Test on primary replay (21.11.04)
CACHE_DIR = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

entities_be = {
    0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
    0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
}

truth = {
    "Phinn": {"K": 2, "D": 0}, "Yates": {"K": 1, "D": 4},
    "Caine": {"K": 3, "D": 4}, "Karas": {"K": 0, "D": 3},
    "Petal": {"K": 3, "D": 2}, "Baron": {"K": 6, "D": 2},
}

# Load frames
print("Loading frames...")
detector = KDADetector(valid_entity_ids=set(entities_be.keys()))

frame_count = 0
for i in range(200):
    path = os.path.join(CACHE_DIR, f"{PREFIX}.{i}.vgr")
    if not os.path.exists(path):
        continue
    with open(path, "rb") as f:
        data = f.read()
    detector.process_frame(i, data)
    frame_count += 1

print(f"Processed {frame_count} frames")
print(f"Detected: {len(detector.kill_events)} kill events, {len(detector.death_events)} death events")
print()

# Get results (no post-game filter for this replay - we don't have exact duration)
results = detector.get_results()

print(f"{'Player':8s} {'K':>3s} {'TK':>3s} {'':10s} {'D':>3s} {'TD':>3s}")
total_k = total_d = 0
for eid, name in sorted(entities_be.items(), key=lambda x: x[1]):
    r = results[eid]
    tk = truth[name]["K"]
    td = truth[name]["D"]
    k_ok = "OK" if r.kills == tk else f"MISS({r.kills-tk:+d})"
    d_ok = "OK" if r.deaths == td else f"MISS({r.deaths-td:+d})"
    if r.kills == tk: total_k += 1
    if r.deaths == td: total_d += 1
    print(f"  {name:8s} {r.kills:3d} {tk:3d} [{k_ok:>8s}] {r.deaths:3d} {td:3d} [{d_ok:>8s}]")

print()
print(f"Kill accuracy:  {total_k}/6")
print(f"Death accuracy: {total_d}/6")

# Test kill-death pairing
team_map = {}
left = {"Phinn", "Petal", "Baron"}
for eid, name in entities_be.items():
    team_map[eid] = "left" if name in left else "right"

pairs = detector.get_kill_death_pairs(team_map)
print(f"\nKill-Death pairs: {len(pairs)}")
for p in pairs:
    killer = entities_be.get(p["killer_eid"], "?")
    victim = entities_be.get(p["victim_eid"], "?") if p["victim_eid"] else "?"
    dt_str = f"dt={p['dt']:.2f}s" if p["dt"] else ""
    print(f"  {killer:8s} -> {victim:8s}  ts={p['kill_ts']:.1f}  {dt_str}")

print("\nDONE - Module works correctly!" if total_k == 6 and total_d == 6 else "\nWARNING: Results differ!")
