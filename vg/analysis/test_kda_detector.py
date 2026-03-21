"""Quick manual test for KDADetector against a known replay fixture."""

from __future__ import annotations

import os
from sys import path as sys_path

sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.kda_detector import KDADetector


# Test on primary replay (21.11.04)
CACHE_DIR = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

ENTITIES_BE = {
    0x05DC: "Phinn",
    0x05DD: "Yates",
    0x05DE: "Caine",
    0x05DF: "Petal",
    0x05E0: "Karas",
    0x05E1: "Baron",
}

TRUTH = {
    "Phinn": {"K": 2, "D": 0},
    "Yates": {"K": 1, "D": 4},
    "Caine": {"K": 3, "D": 4},
    "Karas": {"K": 0, "D": 3},
    "Petal": {"K": 3, "D": 2},
    "Baron": {"K": 6, "D": 2},
}


def main() -> None:
    print("Loading frames...")
    detector = KDADetector(valid_entity_ids=set(ENTITIES_BE.keys()))

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

    results = detector.get_results()

    print(f"{'Player':8s} {'K':>3s} {'TK':>3s} {'':10s} {'D':>3s} {'TD':>3s}")
    total_k = total_d = 0
    for eid, name in sorted(ENTITIES_BE.items(), key=lambda x: x[1]):
        result = results[eid]
        truth_k = TRUTH[name]["K"]
        truth_d = TRUTH[name]["D"]
        k_ok = "OK" if result.kills == truth_k else f"MISS({result.kills-truth_k:+d})"
        d_ok = "OK" if result.deaths == truth_d else f"MISS({result.deaths-truth_d:+d})"
        if result.kills == truth_k:
            total_k += 1
        if result.deaths == truth_d:
            total_d += 1
        print(
            f"  {name:8s} {result.kills:3d} {truth_k:3d} [{k_ok:>8s}] "
            f"{result.deaths:3d} {truth_d:3d} [{d_ok:>8s}]"
        )

    print()
    print(f"Kill accuracy:  {total_k}/6")
    print(f"Death accuracy: {total_d}/6")

    team_map = {}
    left = {"Phinn", "Petal", "Baron"}
    for eid, name in ENTITIES_BE.items():
        team_map[eid] = "left" if name in left else "right"

    pairs = detector.get_kill_death_pairs(team_map)
    print(f"\nKill-Death pairs: {len(pairs)}")
    for pair in pairs:
        killer = ENTITIES_BE.get(pair["killer_eid"], "?")
        victim = ENTITIES_BE.get(pair["victim_eid"], "?") if pair["victim_eid"] else "?"
        dt_str = f"dt={pair['dt']:.2f}s" if pair["dt"] else ""
        print(f"  {killer:8s} -> {victim:8s}  ts={pair['kill_ts']:.1f}  {dt_str}")

    if total_k == 6 and total_d == 6:
        print("\nDONE - Module works correctly!")
    else:
        print("\nWARNING: Results differ!")


if __name__ == "__main__":
    main()
