"""
KDA Cross-Validation v4: Selective post-game filter
=====================================================
v3 found: ts<=dur+10 best overall, but kills have reliable timestamps
only sometimes. Test applying filter ONLY to deaths (inline timestamps)
while keeping kills unfiltered.
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
            results.append({"eid": eid, "ts": ts, "frame": frame_idx})
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
            results.append({"eid": eid, "ts": ts, "frame": frame_idx})
        pos += 1
    return results


# Collect all events
match_data = []
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

    all_kills = []
    all_deaths = []
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
        all_kills.extend(find_kills(data, valid_eids, frame_idx))
        all_deaths.extend(find_deaths(data, valid_eids, frame_idx))

    match_data.append({
        "match_idx": match_idx, "match": match,
        "eid_be_to_player": eid_be_to_player,
        "player_to_truth": player_to_truth,
        "all_kills": all_kills, "all_deaths": all_deaths,
        "total_frames": total_frames,
        "duration": match["match_info"]["duration_seconds"],
    })

print(f"Loaded {len(match_data)} matches\n")

# =========================================================================
# Test strategies: filter kills/deaths independently
# =========================================================================
print("=" * 80)
print("SELECTIVE FILTER STRATEGIES")
print("=" * 80)
print()

configs = [
    ("raw K + raw D", None, None),
    ("raw K + D<=dur+0", None, 0),
    ("raw K + D<=dur+5", None, 5),
    ("raw K + D<=dur+10", None, 10),
    ("K<=dur+0 + D<=dur+0", 0, 0),
    ("K<=dur+10 + D<=dur+10", 10, 10),
    ("K<=dur+0 + raw D", 0, None),
    ("K<=dur+10 + raw D", 10, None),
]

best_name = None
best_score = 0
best_k_ok = 0
best_d_ok = 0

for name, k_buf, d_buf in configs:
    total_k_ok = 0
    total_d_ok = 0
    total_pp = 0

    for md in match_data:
        dur = md["duration"]

        kill_counts = Counter()
        for k in md["all_kills"]:
            if k_buf is not None:
                if k["ts"] is not None and k["ts"] > dur + k_buf:
                    continue
            kill_counts[k["eid"]] += 1

        death_counts = Counter()
        for d in md["all_deaths"]:
            if d_buf is not None:
                if d["ts"] > dur + d_buf:
                    continue
            death_counts[d["eid"]] += 1

        for eid_be in md["eid_be_to_player"]:
            truth_match = md["player_to_truth"].get(eid_be)
            if not truth_match:
                continue
            total_pp += 1
            if kill_counts.get(eid_be, 0) == truth_match["kills"]:
                total_k_ok += 1
            if death_counts.get(eid_be, 0) == truth_match["deaths"]:
                total_d_ok += 1

    combined = total_k_ok + total_d_ok
    pct_k = 100 * total_k_ok / total_pp
    pct_d = 100 * total_d_ok / total_pp
    pct_c = 100 * combined / (total_pp * 2)
    print(f"  {name:25s}: K={total_k_ok}/{total_pp} ({pct_k:.1f}%)  "
          f"D={total_d_ok}/{total_pp} ({pct_d:.1f}%)  "
          f"Comb={combined}/{total_pp*2} ({pct_c:.1f}%)")

    if combined > best_score or (combined == best_score and total_k_ok > best_k_ok):
        best_score = combined
        best_name = name
        best_k_ok = total_k_ok
        best_d_ok = total_d_ok

print()
print(f"Best: {best_name}")

# =========================================================================
# Detailed results with best strategy
# =========================================================================
# Parse the best config
if "raw K" in best_name:
    best_k_buf = None
else:
    for n, kb, db in configs:
        if n == best_name:
            best_k_buf = kb
            break

if "raw D" in best_name:
    best_d_buf = None
else:
    for n, kb, db in configs:
        if n == best_name:
            best_d_buf = db
            break

print()
print("=" * 80)
print(f"DETAILED: {best_name}")
print("=" * 80)
print()

total_k_ok = 0
total_d_ok = 0
total_pp = 0
all_per_match = []

for md in match_data:
    dur = md["duration"]

    kill_counts = Counter()
    for k in md["all_kills"]:
        if best_k_buf is not None:
            if k["ts"] is not None and k["ts"] > dur + best_k_buf:
                continue
        kill_counts[k["eid"]] += 1

    death_counts = Counter()
    for d in md["all_deaths"]:
        if best_d_buf is not None:
            if d["ts"] > dur + best_d_buf:
                continue
        death_counts[d["eid"]] += 1

    per_player = []
    for eid_be, p in md["eid_be_to_player"].items():
        truth_match = md["player_to_truth"].get(eid_be)
        if not truth_match:
            continue
        dk = kill_counts.get(eid_be, 0)
        dd = death_counts.get(eid_be, 0)
        tk = truth_match["kills"]
        td = truth_match["deaths"]
        per_player.append({
            "hero": truth_match["hero_name"], "team": p["team"],
            "det_k": dk, "truth_k": tk, "k_ok": dk == tk,
            "det_d": dd, "truth_d": td, "d_ok": dd == td,
        })

    k_ok = sum(1 for pp in per_player if pp["k_ok"])
    d_ok = sum(1 for pp in per_player if pp["d_ok"])
    pp_count = len(per_player)
    total_k_ok += k_ok
    total_d_ok += d_ok
    total_pp += pp_count

    k_perfect = k_ok == pp_count
    d_perfect = d_ok == pp_count

    all_per_match.append({
        "match": md["match_idx"] + 1,
        "k_ok": k_ok, "d_ok": d_ok, "total": pp_count,
        "k_perfect": k_perfect, "d_perfect": d_perfect,
    })

    k_status = "PERFECT" if k_perfect else f"{k_ok}/{pp_count}"
    d_status = "PERFECT" if d_perfect else f"{d_ok}/{pp_count}"
    print(f"Match {md['match_idx']+1}: K={k_status}  D={d_status}")

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
excl = [r for r in all_per_match if r["match"] != 9]
excl_k = sum(r["k_ok"] for r in excl)
excl_d = sum(r["d_ok"] for r in excl)
excl_pp = sum(r["total"] for r in excl)
excl_kp = sum(1 for r in excl if r["k_perfect"])
excl_dp = sum(1 for r in excl if r["d_perfect"])
excl_bp = sum(1 for r in excl if r["k_perfect"] and r["d_perfect"])

print(f"ALL REPLAYS:")
print(f"  K={total_k_ok}/{total_pp} ({100*total_k_ok/total_pp:.1f}%)  "
      f"D={total_d_ok}/{total_pp} ({100*total_d_ok/total_pp:.1f}%)  "
      f"Combined={total_k_ok+total_d_ok}/{total_pp*2} ({100*(total_k_ok+total_d_ok)/(total_pp*2):.1f}%)")

print(f"\nEXCL. MATCH 9 (incomplete):")
print(f"  K={excl_k}/{excl_pp} ({100*excl_k/excl_pp:.1f}%)  "
      f"D={excl_d}/{excl_pp} ({100*excl_d/excl_pp:.1f}%)  "
      f"Combined={excl_k+excl_d}/{excl_pp*2} ({100*(excl_k+excl_d)/(excl_pp*2):.1f}%)")
print(f"  K perfect: {excl_kp}/{len(excl)}, D perfect: {excl_dp}/{len(excl)}, Both: {excl_bp}/{len(excl)}")

# Save
output = {
    "version": "kda_cross_validation_v4",
    "best_strategy": best_name,
    "summary_excl_match9": {
        "kill_accuracy": f"{excl_k}/{excl_pp} ({100*excl_k/excl_pp:.1f}%)",
        "death_accuracy": f"{excl_d}/{excl_pp} ({100*excl_d/excl_pp:.1f}%)",
        "combined": f"{excl_k+excl_d}/{excl_pp*2} ({100*(excl_k+excl_d)/(excl_pp*2):.1f}%)",
    },
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_cross_validation_v4.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
