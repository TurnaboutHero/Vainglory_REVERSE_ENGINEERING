"""
KDA Cross-Validation v2: Kill + Death with deduplication
=========================================================
v1 found +1 overcounting in some matches. This version adds:
1. Timestamp-based deduplication: same entity + same timestamp across frames = 1 event
2. Analysis of overcounting patterns

Kill: [18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
Death: [08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]
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


def find_kills(data, valid_eids_be):
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
            results.append({"eid": eid, "ts": ts, "pos": pos})
        pos += 1
    return results


def find_deaths(data, valid_eids_be):
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


def dedup_events(events_by_frame, ts_tolerance=0.01):
    """Deduplicate events across frames: same eid + similar timestamp = 1 event.
    Returns dict of eid -> count."""
    # Collect all events with their timestamps
    all_events = []  # (eid, ts, frame_idx)
    for frame_idx, events in sorted(events_by_frame.items()):
        for ev in events:
            all_events.append((ev["eid"], ev["ts"], frame_idx))

    # Group by eid, then merge close timestamps
    by_eid = defaultdict(list)
    for eid, ts, fidx in all_events:
        by_eid[eid].append((ts, fidx))

    counts = Counter()
    for eid, ts_list in by_eid.items():
        if not ts_list:
            continue
        # Sort by timestamp
        ts_list.sort()
        # Merge events with same timestamp (within tolerance)
        unique_ts = []
        for ts, fidx in ts_list:
            if ts is None:
                unique_ts.append(ts)
                continue
            # Check if this ts is close to any existing
            is_dup = False
            for uts in unique_ts:
                if uts is not None and abs(ts - uts) < ts_tolerance:
                    is_dup = True
                    break
            if not is_dup:
                unique_ts.append(ts)
        counts[eid] = len(unique_ts)

    return counts


# =========================================================================
# Test multiple dedup strategies
# =========================================================================
print("=" * 80)
print("KDA CROSS-VALIDATION v2: With Deduplication Strategies")
print("=" * 80)
print()

# Strategy configs: (name, kill_dedup, death_dedup, ts_tolerance)
strategies = [
    ("raw (no dedup)", False, False, 0),
    ("dedup ts<0.01", True, True, 0.01),
    ("dedup ts<0.1", True, True, 0.1),
    ("dedup ts<1.0", True, True, 1.0),
    ("dedup ts<5.0", True, True, 5.0),
    ("dedup ts<10.0", True, True, 10.0),
]

# First pass: collect raw events for all matches
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

    # Collect events per frame
    kill_events_by_frame = {}
    death_events_by_frame = {}
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

        kills = find_kills(data, valid_eids)
        if kills:
            kill_events_by_frame[frame_idx] = kills

        deaths = find_deaths(data, valid_eids)
        if deaths:
            death_events_by_frame[frame_idx] = deaths

    match_data.append({
        "match_idx": match_idx,
        "match": match,
        "players": players,
        "eid_be_to_player": eid_be_to_player,
        "player_to_truth": player_to_truth,
        "kill_events_by_frame": kill_events_by_frame,
        "death_events_by_frame": death_events_by_frame,
        "total_frames": total_frames,
    })

print(f"Loaded {len(match_data)} matches\n")

# Test each strategy
best_strat = None
best_score = 0

for strat_name, do_kill_dedup, do_death_dedup, tol in strategies:
    total_k_ok = 0
    total_d_ok = 0
    total_pp = 0

    for md in match_data:
        player_to_truth = md["player_to_truth"]
        eid_be_to_player = md["eid_be_to_player"]

        if do_kill_dedup:
            kill_counts = dedup_events(md["kill_events_by_frame"], tol)
        else:
            kill_counts = Counter()
            for frame_idx, events in md["kill_events_by_frame"].items():
                for ev in events:
                    kill_counts[ev["eid"]] += 1

        if do_death_dedup:
            death_counts = dedup_events(md["death_events_by_frame"], tol)
        else:
            death_counts = Counter()
            for frame_idx, events in md["death_events_by_frame"].items():
                for ev in events:
                    death_counts[ev["eid"]] += 1

        for eid_be, p in eid_be_to_player.items():
            truth_match = player_to_truth.get(eid_be)
            if not truth_match:
                continue
            total_pp += 1

            dk = kill_counts.get(eid_be, 0)
            dd = death_counts.get(eid_be, 0)
            tk = truth_match["kills"]
            td = truth_match["deaths"]

            if dk == tk:
                total_k_ok += 1
            if dd == td:
                total_d_ok += 1

    combined = total_k_ok + total_d_ok
    pct_k = 100 * total_k_ok / total_pp if total_pp else 0
    pct_d = 100 * total_d_ok / total_pp if total_pp else 0
    pct_c = 100 * combined / (total_pp * 2) if total_pp else 0

    print(f"  {strat_name:20s}: K={total_k_ok}/{total_pp} ({pct_k:.1f}%)  "
          f"D={total_d_ok}/{total_pp} ({pct_d:.1f}%)  "
          f"Combined={combined}/{total_pp*2} ({pct_c:.1f}%)")

    if combined > best_score:
        best_score = combined
        best_strat = strat_name

print()
print(f"Best strategy: {best_strat}")

# =========================================================================
# Detailed analysis with best strategy (dedup ts<5.0 expected)
# Try the top 2-3 and show per-match detail for the best
# =========================================================================
print()
print("=" * 80)
print("DETAILED RESULTS: dedup ts<5.0")
print("=" * 80)
print()

total_k_ok = 0
total_d_ok = 0
total_pp = 0

for md in match_data:
    match = md["match"]
    match_idx = md["match_idx"]
    player_to_truth = md["player_to_truth"]
    eid_be_to_player = md["eid_be_to_player"]

    kill_counts = dedup_events(md["kill_events_by_frame"], 5.0)
    death_counts = dedup_events(md["death_events_by_frame"], 5.0)

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

    mismatches = [pp for pp in per_player if not pp["k_ok"] or not pp["d_ok"]]

    k_status = "PERFECT" if k_ok == pp_count else f"{k_ok}/{pp_count}"
    d_status = "PERFECT" if d_ok == pp_count else f"{d_ok}/{pp_count}"

    print(f"Match {match_idx+1}: K={k_status}  D={d_status}  frames={md['total_frames']}")
    if mismatches:
        for pp in sorted(mismatches, key=lambda x: x["hero"]):
            parts = []
            if not pp["k_ok"]:
                parts.append(f"K:{pp['det_k']}vs{pp['truth_k']}({pp['det_k']-pp['truth_k']:+d})")
            if not pp["d_ok"]:
                parts.append(f"D:{pp['det_d']}vs{pp['truth_d']}({pp['det_d']-pp['truth_d']:+d})")
            print(f"    {pp['hero']:15s} [{pp['team']}] {' '.join(parts)}")

print()
print(f"TOTAL: K={total_k_ok}/{total_pp} ({100*total_k_ok/total_pp:.1f}%)  "
      f"D={total_d_ok}/{total_pp} ({100*total_d_ok/total_pp:.1f}%)  "
      f"Combined={total_k_ok+total_d_ok}/{total_pp*2} ({100*(total_k_ok+total_d_ok)/(total_pp*2):.1f}%)")

# Save
output = {
    "version": "kda_cross_validation_v2",
    "best_strategy": best_strat,
    "summary": {
        "kill_accuracy": f"{total_k_ok}/{total_pp}",
        "death_accuracy": f"{total_d_ok}/{total_pp}",
    },
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/kda_cross_validation_v2.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
