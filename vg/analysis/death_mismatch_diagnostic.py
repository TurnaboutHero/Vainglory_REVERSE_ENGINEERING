"""
Death [08 04 31] Mismatch Diagnostic
=====================================
For each replay where death counts don't match truth:
1. Which specific players are overcounted/undercounted?
2. Are deaths duplicated across consecutive frames?
3. Is the issue specific to certain heroes or universal?
"""
import os
import struct
import json
from collections import Counter, defaultdict

TRUTH_PATH = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json"
with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")
try:
    from vg.core.vgr_mapping import BINARY_HERO_ID_MAP
except:
    BINARY_HERO_ID_MAP = {}


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
                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")
                players.append({
                    "eid_le": eid_le, "eid_be": eid_be,
                    "hero_id": hero_id, "hero_name": hero_name,
                    "team": "left" if team == 1 else "right" if team == 2 else f"unk_{team}",
                })
            pos += 1
    return players


def find_deaths_with_frames(data, valid_eids_be, frame_idx):
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
        if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", data, pos+5)[0]
        ts = struct.unpack_from(">f", data, pos+9)[0]
        if eid in valid_eids_be and 0 < ts < 1800:
            results.append({"eid": eid, "ts": round(ts, 2), "frame": frame_idx, "pos": pos})
        pos += 1
    return results


print("=" * 70)
print("DEATH MISMATCH DIAGNOSTIC")
print("=" * 70)
print()

total_overcount = 0
total_undercount = 0
hero_mismatch_stats = Counter()  # hero_name -> net error
replay_errors = []

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

    # Collect ALL death records with frame info
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
        deaths = find_deaths_with_frames(data, valid_eids, frame_idx)
        all_deaths.extend(deaths)

    # Check for DUPLICATE deaths (same eid + same timestamp in different frames)
    death_by_eid_ts = defaultdict(list)
    for d in all_deaths:
        key = (d["eid"], d["ts"])
        death_by_eid_ts[key].append(d["frame"])

    duplicates = {k: v for k, v in death_by_eid_ts.items() if len(v) > 1}

    # Deduplicated count
    dedup_counts = Counter()
    for (eid, ts) in death_by_eid_ts:
        dedup_counts[eid] += 1

    raw_counts = Counter(d["eid"] for d in all_deaths)

    # Compare raw vs dedup vs truth
    total_detected_raw = sum(raw_counts.values())
    total_detected_dedup = sum(dedup_counts.values())
    total_truth = sum(pdata["deaths"] for pdata in truth_players.values())

    has_mismatch = total_detected_raw != total_truth
    has_duplicates = len(duplicates) > 0

    if has_mismatch or has_duplicates:
        replay_name = match.get("replay_name", "unknown")[:50]
        print(f"Match {match_idx+1}: {replay_name}")
        print(f"  Frames={total_frames}, Players={len(players)}")
        print(f"  Raw={total_detected_raw}, Dedup={total_detected_dedup}, Truth={total_truth}")

        if duplicates:
            print(f"  DUPLICATES found: {len(duplicates)} unique deaths appear in multiple frames")
            for (eid, ts), frames in sorted(duplicates.items()):
                pname = eid_be_to_player.get(eid, {}).get("hero_name", f"0x{eid:04X}")
                print(f"    {pname} ts={ts:.2f} in frames {frames}")

        # Per-player comparison (raw vs dedup vs truth)
        print(f"  Per-player:")
        for p in sorted(players, key=lambda x: x["hero_name"]):
            eid = p["eid_be"]
            hero = p["hero_name"]
            raw = raw_counts.get(eid, 0)
            dedup = dedup_counts.get(eid, 0)
            truth_match = player_to_truth.get(eid)
            if truth_match:
                td = truth_match["deaths"]
                raw_ok = "OK" if raw == td else f"{raw-td:+d}"
                dedup_ok = "OK" if dedup == td else f"{dedup-td:+d}"
                print(f"    {hero:15s}: raw={raw:2d} dedup={dedup:2d} truth={td:2d} [raw:{raw_ok:>4s} dedup:{dedup_ok:>4s}]")
                if dedup != td:
                    hero_mismatch_stats[hero] += (dedup - td)
            else:
                print(f"    {hero:15s}: raw={raw:2d} dedup={dedup:2d} (no truth match)")

        # Check if dedup fixes the issue
        dedup_player_ok = 0
        dedup_player_total = 0
        for eid, p in eid_be_to_player.items():
            truth_match = player_to_truth.get(eid)
            if truth_match:
                dedup_player_total += 1
                if dedup_counts.get(eid, 0) == truth_match["deaths"]:
                    dedup_player_ok += 1
        print(f"  Dedup accuracy: {dedup_player_ok}/{dedup_player_total}")
        print()

        if total_detected_raw > total_truth:
            total_overcount += (total_detected_raw - total_truth)
        else:
            total_undercount += (total_truth - total_detected_raw)

        replay_errors.append({
            "match": match_idx + 1,
            "raw": total_detected_raw,
            "dedup": total_detected_dedup,
            "truth": total_truth,
            "frames": total_frames,
            "players_detected": len(players),
            "duplicates": len(duplicates),
        })

print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"Total overcounted: +{total_overcount}")
print(f"Total undercounted: -{total_undercount}")
print()

if hero_mismatch_stats:
    print("Hero mismatch totals (after dedup):")
    for hero, net in sorted(hero_mismatch_stats.items(), key=lambda x: -abs(x[1])):
        print(f"  {hero:15s}: {net:+d}")
print()

print("Replay error details:")
for r in replay_errors:
    dup_str = f" ({r['duplicates']} dups)" if r["duplicates"] > 0 else ""
    print(f"  Match {r['match']:2d}: raw={r['raw']:2d} dedup={r['dedup']:2d} truth={r['truth']:2d} "
          f"frames={r['frames']:3d} players={r['players_detected']:2d}{dup_str}")
