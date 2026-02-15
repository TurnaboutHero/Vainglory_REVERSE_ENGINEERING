"""
Death Record [08 04 31] Multi-Replay Cross-Validation
=====================================================
Strict structural validation:
  [08 04 31] [00 00] [victim_eid BE] [00 00] [timestamp f32 BE] [00 00 00]
  - bytes[3:5] == 00 00
  - bytes[7:9] == 00 00
  - bytes[9:13] = valid game time (0 < ts < 1800)

Tests on ALL tournament replays with truth data.
"""
import os
import struct
import json
from collections import Counter

# Load truth
TRUTH_PATH = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json"
with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

# Hero ID to name mapping
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")
try:
    from vg.core.vgr_mapping import BINARY_HERO_ID_MAP
except:
    BINARY_HERO_ID_MAP = {}


def find_player_entities(frame0_data):
    """Extract player entities from frame 0 using DA/E0 03 EE markers."""
    players = []
    for marker_bytes in [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]:
        pos = 0
        while True:
            pos = frame0_data.find(marker_bytes, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(frame0_data):
                # Entity ID at +0xA5 (LE)
                eid_le = struct.unpack_from("<H", frame0_data, pos + 0xA5)[0]
                # Convert to BE for protocol matching
                eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)
                # Hero ID at +0xA9 (LE)
                hero_id = struct.unpack_from("<H", frame0_data, pos + 0xA9)[0]
                # Team at +0xD5
                team = frame0_data[pos + 0xD5]
                team_str = "left" if team == 1 else "right" if team == 2 else f"unk_{team}"

                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")

                players.append({
                    "eid_le": eid_le,
                    "eid_be": eid_be,
                    "hero_id": hero_id,
                    "hero_name": hero_name,
                    "team": team_str,
                    "marker_pos": pos,
                })
            pos += 1
    return players


def find_deaths_strict(data, valid_eids_be):
    """Find [08 04 31] with strict validation."""
    pattern = bytes([0x08, 0x04, 0x31])
    results = []
    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break
        if pos + 13 > len(data):
            pos += 1
            continue

        # Structural checks
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue
        if data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos+5)[0]
        ts = struct.unpack_from(">f", data, pos+9)[0]

        if eid in valid_eids_be and 0 < ts < 1800:
            results.append({"eid": eid, "ts": ts, "pos": pos})

        pos += 1
    return results


# =========================================================================
# Process each tournament replay
# =========================================================================
print("=" * 70)
print("CROSS-REPLAY VALIDATION: [08 04 31] Death Records")
print("=" * 70)
print()

results_summary = []

for match_idx, match in enumerate(truth_data["matches"]):
    replay_file = match["replay_file"]
    replay_name = match.get("replay_name", "unknown")[:50]

    if not os.path.exists(replay_file):
        continue

    replay_dir = os.path.dirname(replay_file)
    basename = os.path.basename(replay_file)
    if not basename.endswith(".0.vgr"):
        continue
    prefix = basename[:-6]

    # Check for cache directory
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

    # Find player entities
    players = find_player_entities(frame0)
    if not players:
        continue

    # Build entity ID maps
    eid_be_to_player = {}
    for p in players:
        eid_be_to_player[p["eid_be"]] = p
    valid_eids = set(eid_be_to_player.keys())

    # Match players to truth data
    truth_players = match["players"]
    truth_heroes = {pdata["hero_name"]: pdata for pname, pdata in truth_players.items()}

    # Try to match detected players to truth by hero name
    player_to_truth = {}
    for p in players:
        hero = p["hero_name"]
        if hero in truth_heroes:
            player_to_truth[p["eid_be"]] = truth_heroes[hero]

    # Count deaths across all frames
    death_counts_be = Counter()
    total_frames = 0

    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and total_frames > 0:
                break
            continue

        with open(fpath, "rb") as f:
            data = f.read()
        total_frames += 1

        deaths = find_deaths_strict(data, valid_eids)
        for d in deaths:
            death_counts_be[d["eid"]] += 1

    # Compare with truth
    total_detected = sum(death_counts_be.values())
    total_truth = sum(pdata["deaths"] for pdata in truth_players.values())

    # Per-player comparison
    per_player_ok = 0
    per_player_total = 0
    per_player_details = []

    for eid_be, count in death_counts_be.items():
        truth_match = player_to_truth.get(eid_be)
        if truth_match:
            per_player_total += 1
            truth_d = truth_match["deaths"]
            ok = count == truth_d
            if ok:
                per_player_ok += 1
            per_player_details.append({
                "hero": truth_match["hero_name"] if "hero_name" in truth_match else eid_be_to_player.get(eid_be, {}).get("hero_name", "?"),
                "detected": count,
                "truth": truth_d,
                "match": ok,
            })

    # Also count players with 0 detected deaths
    for eid_be, p in eid_be_to_player.items():
        if eid_be not in death_counts_be:
            truth_match = player_to_truth.get(eid_be)
            if truth_match:
                per_player_total += 1
                truth_d = truth_match["deaths"]
                ok = truth_d == 0
                if ok:
                    per_player_ok += 1
                per_player_details.append({
                    "hero": truth_match.get("hero_name", p.get("hero_name", "?")),
                    "detected": 0,
                    "truth": truth_d,
                    "match": ok,
                })

    total_match = total_detected == total_truth
    result = {
        "replay": replay_name,
        "frames": total_frames,
        "players": len(players),
        "total_detected": total_detected,
        "total_truth": total_truth,
        "total_match": total_match,
        "per_player_ok": per_player_ok,
        "per_player_total": per_player_total,
    }
    results_summary.append(result)

    status = "TOTAL MATCH!" if total_match else f"OFF BY {total_detected - total_truth:+d}"
    print(f"Match {match_idx+1}: {replay_name[:45]}")
    print(f"  Frames={total_frames}, Players={len(players)}, "
          f"Detected={total_detected}, Truth={total_truth} [{status}]")

    if per_player_details:
        matched = sum(1 for d in per_player_details if d["match"])
        total = len(per_player_details)
        print(f"  Per-player: {matched}/{total} matched")
        for d in sorted(per_player_details, key=lambda x: x["hero"]):
            ok = "OK" if d["match"] else f"OFF({d['detected']-d['truth']:+d})"
            print(f"    {d['hero']:15s}: detected={d['detected']}, truth={d['truth']} [{ok}]")
    print()


# Summary
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()

total_matches = sum(1 for r in results_summary if r["total_match"])
total_replays = len(results_summary)
print(f"Total match (sum): {total_matches}/{total_replays} replays")

# Per-player accuracy across all replays
all_player_ok = sum(r["per_player_ok"] for r in results_summary)
all_player_total = sum(r["per_player_total"] for r in results_summary)
print(f"Per-player accuracy: {all_player_ok}/{all_player_total} "
      f"({100*all_player_ok/all_player_total:.1f}%)" if all_player_total > 0 else "")

off_amounts = [abs(r["total_detected"] - r["total_truth"]) for r in results_summary]
print(f"Average absolute error: {sum(off_amounts)/len(off_amounts):.1f}" if off_amounts else "")

# Save
output = {
    "pattern": "[08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]",
    "validation": results_summary,
    "summary": {
        "replays_tested": total_replays,
        "total_matches": total_matches,
        "per_player_accuracy": f"{all_player_ok}/{all_player_total}",
    }
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/death_cross_validation.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
