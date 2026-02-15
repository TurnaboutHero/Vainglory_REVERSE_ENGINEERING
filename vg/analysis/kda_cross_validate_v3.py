"""
KDA Cross-Validation v3: Kill + Death with post-game filter
=============================================================
v2 found that most overcounting comes from events AFTER game_duration.
These are "victory ceremony" kills/deaths after crystal is destroyed.

Fix: filter events where timestamp > game_duration.
Also test with small buffer (ts > duration + N seconds).
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


# =========================================================================
# Collect all events
# =========================================================================
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
        "match_idx": match_idx,
        "match": match,
        "players": players,
        "eid_be_to_player": eid_be_to_player,
        "player_to_truth": player_to_truth,
        "all_kills": all_kills,
        "all_deaths": all_deaths,
        "total_frames": total_frames,
        "duration": match["match_info"]["duration_seconds"],
    })

print(f"Loaded {len(match_data)} matches\n")

# =========================================================================
# Test filter strategies
# =========================================================================
print("=" * 80)
print("POST-GAME FILTER STRATEGIES")
print("=" * 80)
print()

# Buffers to test: no filter, duration+0, +5, +10, +30, +60
buffers = [None, 0, 5, 10, 30, 60]

best_buffer = None
best_combined = 0

for buf in buffers:
    total_k_ok = 0
    total_d_ok = 0
    total_pp = 0

    for md in match_data:
        duration = md["duration"]
        max_ts = (duration + buf) if buf is not None else 99999

        kill_counts = Counter()
        for k in md["all_kills"]:
            if k["ts"] is not None and k["ts"] <= max_ts:
                kill_counts[k["eid"]] += 1
            elif k["ts"] is None:
                kill_counts[k["eid"]] += 1  # keep events without timestamp

        death_counts = Counter()
        for d in md["all_deaths"]:
            if d["ts"] <= max_ts:
                death_counts[d["eid"]] += 1

        for eid_be, p in md["eid_be_to_player"].items():
            truth_match = md["player_to_truth"].get(eid_be)
            if not truth_match:
                continue
            total_pp += 1
            if kill_counts.get(eid_be, 0) == truth_match["kills"]:
                total_k_ok += 1
            if death_counts.get(eid_be, 0) == truth_match["deaths"]:
                total_d_ok += 1

    combined = total_k_ok + total_d_ok
    buf_str = "no filter" if buf is None else f"ts <= dur+{buf}s"
    pct = 100 * combined / (total_pp * 2) if total_pp else 0
    print(f"  {buf_str:18s}: K={total_k_ok}/{total_pp} ({100*total_k_ok/total_pp:.1f}%)  "
          f"D={total_d_ok}/{total_pp} ({100*total_d_ok/total_pp:.1f}%)  "
          f"Combined={combined}/{total_pp*2} ({pct:.1f}%)")

    if combined > best_combined:
        best_combined = combined
        best_buffer = buf

print()
print(f"Best: ts <= dur+{best_buffer}s")

# =========================================================================
# Detailed results with best filter
# =========================================================================
print()
print("=" * 80)
print(f"DETAILED RESULTS: ts <= duration+{best_buffer}s")
print("=" * 80)
print()

total_k_ok = 0
total_d_ok = 0
total_pp = 0
all_per_match = []

for md in match_data:
    duration = md["duration"]
    max_ts = duration + best_buffer

    kill_counts = Counter()
    for k in md["all_kills"]:
        if k["ts"] is not None and k["ts"] <= max_ts:
            kill_counts[k["eid"]] += 1
        elif k["ts"] is None:
            kill_counts[k["eid"]] += 1

    death_counts = Counter()
    for d in md["all_deaths"]:
        if d["ts"] <= max_ts:
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

    k_status = "PERFECT" if k_perfect else f"{k_ok}/{pp_count}"
    d_status = "PERFECT" if d_perfect else f"{d_ok}/{pp_count}"

    match_result = {
        "match": md["match_idx"] + 1,
        "k_ok": k_ok, "d_ok": d_ok, "total": pp_count,
        "k_perfect": k_perfect, "d_perfect": d_perfect,
    }
    all_per_match.append(match_result)

    print(f"Match {md['match_idx']+1}: K={k_status}  D={d_status}  frames={md['total_frames']}")

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
k_perfect_count = sum(1 for r in all_per_match if r["k_perfect"])
d_perfect_count = sum(1 for r in all_per_match if r["d_perfect"])
both_perfect = sum(1 for r in all_per_match if r["k_perfect"] and r["d_perfect"])

print(f"GRAND TOTAL:")
print(f"  Kill per-player:   {total_k_ok}/{total_pp} ({100*total_k_ok/total_pp:.1f}%)")
print(f"  Death per-player:  {total_d_ok}/{total_pp} ({100*total_d_ok/total_pp:.1f}%)")
print(f"  Combined:          {total_k_ok+total_d_ok}/{total_pp*2} "
      f"({100*(total_k_ok+total_d_ok)/(total_pp*2):.1f}%)")
print(f"  Kill perfect:      {k_perfect_count}/{len(all_per_match)}")
print(f"  Death perfect:     {d_perfect_count}/{len(all_per_match)}")
print(f"  Both perfect:      {both_perfect}/{len(all_per_match)}")

# Excluding Match 9 (incomplete)
print()
print("Excluding Match 9 (incomplete, 85 frames):")
excl = [r for r in all_per_match if r["match"] != 9]
excl_k = sum(r["k_ok"] for r in excl)
excl_d = sum(r["d_ok"] for r in excl)
excl_pp = sum(r["total"] for r in excl)
excl_kp = sum(1 for r in excl if r["k_perfect"])
excl_dp = sum(1 for r in excl if r["d_perfect"])
excl_bp = sum(1 for r in excl if r["k_perfect"] and r["d_perfect"])
print(f"  Kill per-player:   {excl_k}/{excl_pp} ({100*excl_k/excl_pp:.1f}%)")
print(f"  Death per-player:  {excl_d}/{excl_pp} ({100*excl_d/excl_pp:.1f}%)")
print(f"  Combined:          {excl_k+excl_d}/{excl_pp*2} ({100*(excl_k+excl_d)/(excl_pp*2):.1f}%)")
print(f"  Kill perfect:      {excl_kp}/{len(excl)}")
print(f"  Death perfect:     {excl_dp}/{len(excl)}")
print(f"  Both perfect:      {excl_bp}/{len(excl)}")

# Save
output = {
    "version": "kda_cross_validation_v3",
    "filter": f"ts <= duration + {best_buffer}s",
    "summary": {
        "all_replays": {
            "kill_accuracy": f"{total_k_ok}/{total_pp}",
            "death_accuracy": f"{total_d_ok}/{total_pp}",
            "combined": f"{total_k_ok+total_d_ok}/{total_pp*2}",
        },
        "excl_match9": {
            "kill_accuracy": f"{excl_k}/{excl_pp}",
            "death_accuracy": f"{excl_d}/{excl_pp}",
            "combined": f"{excl_k+excl_d}/{excl_pp*2}",
        },
    },
    "per_match": all_per_match,
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_cross_validation_v3.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
