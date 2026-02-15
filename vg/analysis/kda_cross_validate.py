"""
KDA Cross-Validation: Kill [18 04 1C] + Death [08 04 31] on ALL tournament replays
==================================================================================
Kill pattern: [18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
Death pattern: [08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]

Tests per-player kill and death counts against truth data across 11 replays.
"""
import os
import struct
import json
from collections import Counter

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
    """Extract player entities from frame 0 using DA/E0 03 EE markers."""
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
                    "eid_le": eid_le,
                    "eid_be": eid_be,
                    "hero_id": hero_id,
                    "hero_name": hero_name,
                    "team": team_str,
                })
            pos += 1
    return players


def find_kills_strict(data, valid_eids_be):
    """Find [18 04 1C] [00 00] [eid BE] [FF FF FF FF] [3F 80 00 00] [29 ...]"""
    results = []
    pos = 0
    while True:
        pos = data.find(KILL_HDR, pos)
        if pos == -1:
            break
        if pos + 16 > len(data):
            pos += 1
            continue
        # Structural checks
        if (data[pos+3:pos+5] != b'\x00\x00' or
            data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF' or
            data[pos+11:pos+15] != b'\x3F\x80\x00\x00' or
            data[pos+15] != 0x29):
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos+5)[0]
        if eid in valid_eids_be:
            # Extract timestamp from 7 bytes before
            ts = None
            if pos >= 7:
                ts = struct.unpack_from(">f", data, pos - 7)[0]
                if not (0 < ts < 1800):
                    ts = None
            results.append({"eid": eid, "ts": ts, "pos": pos})
        pos += 1
    return results


def find_deaths_strict(data, valid_eids_be):
    """Find [08 04 31] [00 00] [eid BE] [00 00] [ts f32 BE]"""
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
            results.append({"eid": eid, "ts": ts, "pos": pos})
        pos += 1
    return results


# =========================================================================
# Process each tournament replay
# =========================================================================
print("=" * 80)
print("CROSS-REPLAY KDA VALIDATION: Kills [18 04 1C] + Deaths [08 04 31]")
print("=" * 80)
print()

all_results = []

for match_idx, match in enumerate(truth_data["matches"]):
    replay_file = match["replay_file"]
    replay_name = match.get("replay_name", "unknown")[:50]

    if not os.path.exists(replay_file):
        print(f"Match {match_idx+1}: SKIP (file not found)")
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
    if not players:
        print(f"Match {match_idx+1}: SKIP (no players found)")
        continue

    # Build maps
    eid_be_to_player = {p["eid_be"]: p for p in players}
    valid_eids = set(eid_be_to_player.keys())

    # Match to truth by hero name
    truth_players = match["players"]
    truth_heroes = {}
    for pname, pdata in truth_players.items():
        hero = pdata["hero_name"]
        truth_heroes[hero] = pdata

    player_to_truth = {}
    for p in players:
        hero = p["hero_name"]
        if hero in truth_heroes:
            player_to_truth[p["eid_be"]] = truth_heroes[hero]

    # Count kills and deaths across all frames
    kill_counts = Counter()
    death_counts = Counter()
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

        kills = find_kills_strict(data, valid_eids)
        for k in kills:
            kill_counts[k["eid"]] += 1

        deaths = find_deaths_strict(data, valid_eids)
        for d in deaths:
            death_counts[d["eid"]] += 1

    # Build per-player results
    per_player = []
    for eid_be, p in eid_be_to_player.items():
        truth_match = player_to_truth.get(eid_be)
        if not truth_match:
            continue

        dk = kill_counts.get(eid_be, 0)
        dd = death_counts.get(eid_be, 0)
        tk = truth_match["kills"]
        td = truth_match["deaths"]

        per_player.append({
            "hero": truth_match["hero_name"],
            "team": p["team"],
            "det_k": dk, "truth_k": tk, "k_ok": dk == tk,
            "det_d": dd, "truth_d": td, "d_ok": dd == td,
        })

    # Summary
    k_ok = sum(1 for pp in per_player if pp["k_ok"])
    d_ok = sum(1 for pp in per_player if pp["d_ok"])
    total_pp = len(per_player)

    total_det_k = sum(pp["det_k"] for pp in per_player)
    total_truth_k = sum(pp["truth_k"] for pp in per_player)
    total_det_d = sum(pp["det_d"] for pp in per_player)
    total_truth_d = sum(pp["truth_d"] for pp in per_player)

    result = {
        "match_idx": match_idx + 1,
        "replay": replay_name,
        "frames": total_frames,
        "players_matched": total_pp,
        "kill_player_ok": k_ok,
        "death_player_ok": d_ok,
        "total_player": total_pp,
        "total_det_k": total_det_k,
        "total_truth_k": total_truth_k,
        "total_det_d": total_det_d,
        "total_truth_d": total_truth_d,
    }
    all_results.append(result)

    k_status = "PERFECT" if k_ok == total_pp else f"{k_ok}/{total_pp}"
    d_status = "PERFECT" if d_ok == total_pp else f"{d_ok}/{total_pp}"

    print(f"Match {match_idx+1}: frames={total_frames}, players={total_pp}")
    print(f"  KILLS:  det={total_det_k:3d} truth={total_truth_k:3d} "
          f"per-player={k_status}")
    print(f"  DEATHS: det={total_det_d:3d} truth={total_truth_d:3d} "
          f"per-player={d_status}")

    # Show mismatches
    mismatches = [pp for pp in per_player if not pp["k_ok"] or not pp["d_ok"]]
    if mismatches:
        for pp in sorted(mismatches, key=lambda x: x["hero"]):
            parts = []
            if not pp["k_ok"]:
                parts.append(f"K:{pp['det_k']}vs{pp['truth_k']}({pp['det_k']-pp['truth_k']:+d})")
            if not pp["d_ok"]:
                parts.append(f"D:{pp['det_d']}vs{pp['truth_d']}({pp['det_d']-pp['truth_d']:+d})")
            print(f"    {pp['hero']:15s} [{pp['team']}] {' '.join(parts)}")
    print()


# =========================================================================
# Grand Summary
# =========================================================================
print("=" * 80)
print("GRAND SUMMARY")
print("=" * 80)
print()

total_k_ok = sum(r["kill_player_ok"] for r in all_results)
total_d_ok = sum(r["death_player_ok"] for r in all_results)
total_pp = sum(r["total_player"] for r in all_results)
total_det_k = sum(r["total_det_k"] for r in all_results)
total_truth_k = sum(r["total_truth_k"] for r in all_results)
total_det_d = sum(r["total_det_d"] for r in all_results)
total_truth_d = sum(r["total_truth_d"] for r in all_results)

k_perfect = sum(1 for r in all_results if r["kill_player_ok"] == r["total_player"])
d_perfect = sum(1 for r in all_results if r["death_player_ok"] == r["total_player"])
total_matches = len(all_results)

print(f"Replays tested: {total_matches}")
print(f"Total players:  {total_pp}")
print()
print(f"KILLS:")
print(f"  Per-player accuracy:  {total_k_ok}/{total_pp} ({100*total_k_ok/total_pp:.1f}%)")
print(f"  Perfect matches:      {k_perfect}/{total_matches}")
print(f"  Total det vs truth:   {total_det_k} vs {total_truth_k} (diff={total_det_k-total_truth_k:+d})")
print()
print(f"DEATHS:")
print(f"  Per-player accuracy:  {total_d_ok}/{total_pp} ({100*total_d_ok/total_pp:.1f}%)")
print(f"  Perfect matches:      {d_perfect}/{total_matches}")
print(f"  Total det vs truth:   {total_det_d} vs {total_truth_d} (diff={total_det_d-total_truth_d:+d})")
print()
print(f"COMBINED K+D:")
print(f"  Per-player accuracy:  {total_k_ok+total_d_ok}/{total_pp*2} "
      f"({100*(total_k_ok+total_d_ok)/(total_pp*2):.1f}%)")

# Save
output = {
    "patterns": {
        "kill": "[18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]",
        "death": "[08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]",
    },
    "summary": {
        "replays_tested": total_matches,
        "total_players": total_pp,
        "kill_per_player_accuracy": f"{total_k_ok}/{total_pp}",
        "kill_perfect_matches": f"{k_perfect}/{total_matches}",
        "death_per_player_accuracy": f"{total_d_ok}/{total_pp}",
        "death_perfect_matches": f"{d_perfect}/{total_matches}",
    },
    "per_match": all_results,
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_cross_validation.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
