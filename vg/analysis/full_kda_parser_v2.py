"""
Full KDA Parser v2 - Refined Kill/Death/Assist
================================================
Fixes from v1:
1. Deduplicate assists: count UNIQUE player names per kill event only
2. Only count killer's TEAMMATES as assisters
3. Match kills to deaths by TIMESTAMP (not position)
4. Use separate death record scan for death counting
"""
import os
import struct
import json
from collections import Counter, defaultdict

CACHE_DIR = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

entities_be = {
    0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
    0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
}

left_team = {"Phinn", "Petal", "Baron"}
right_team = {"Yates", "Caine", "Karas"}

truth_kills = {"Phinn": 2, "Yates": 1, "Caine": 3, "Karas": 0, "Petal": 3, "Baron": 6}
truth_deaths = {"Phinn": 0, "Yates": 4, "Caine": 4, "Karas": 3, "Petal": 2, "Baron": 2}
truth_assists = {"Phinn": 6, "Yates": 4, "Caine": 3, "Karas": 2, "Petal": 3, "Baron": 6}

print("Loading frames...")
frames = []
for i in range(200):
    path = os.path.join(CACHE_DIR, f"{PREFIX}.{i}.vgr")
    if not os.path.exists(path):
        continue
    with open(path, "rb") as f:
        frames.append((i, f.read()))
print(f"Loaded {len(frames)} frames")
print()

# =========================================================================
# Find all kill events [18 04 1C]
# =========================================================================
KILL_PATTERN = bytes([0x18, 0x04, 0x1C])
DEATH_PATTERN = bytes([0x08, 0x04, 0x31])
CREDIT_PATTERN = bytes([0x10, 0x04, 0x1D])

def get_team(name):
    return left_team if name in left_team else right_team

kill_events = []
for frame_idx, data in frames:
    pos = 0
    while True:
        pos = data.find(KILL_PATTERN, pos)
        if pos == -1:
            break
        if pos + 16 > len(data):
            pos += 1
            continue

        # Validate: [18 04 1C] [00 00] [eid BE] [FF FF FF FF] [3F 80 00 00] [29]
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue
        killer_eid = struct.unpack_from(">H", data, pos+5)[0]
        if killer_eid not in entities_be:
            pos += 1
            continue
        if data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF':
            pos += 1
            continue
        if data[pos+11:pos+15] != b'\x3F\x80\x00\x00':
            pos += 1
            continue
        if data[pos+15] != 0x29:
            pos += 1
            continue

        killer_name = entities_be[killer_eid]
        killer_team = get_team(killer_name)

        # Get timestamp from before the kill header
        ts = None
        if pos >= 7:
            ts_candidate = struct.unpack_from(">f", data, pos - 7)[0]
            if 0 < ts_candidate < 1800:
                ts = ts_candidate

        # Scan forward for [10 04 1D] credit records - but ONLY with same timestamp
        # and limit to 150 bytes
        ts_bytes = struct.pack(">f", ts) if ts else None
        unique_assisters = set()
        scan_pos = pos + 16
        scan_end = min(len(data), pos + 150)

        while scan_pos < scan_end:
            next_1d = data.find(CREDIT_PATTERN, scan_pos, scan_end)
            if next_1d == -1:
                break
            if next_1d + 11 > len(data):
                break

            # Verify [00 00] padding
            if data[next_1d+3:next_1d+5] == b'\x00\x00':
                credit_eid = struct.unpack_from(">H", data, next_1d+5)[0]
                credit_name = entities_be.get(credit_eid)
                credit_val = struct.unpack_from(">f", data, next_1d+7)[0]

                if credit_name and credit_name != killer_name:
                    # Must be same team as killer
                    if credit_name in killer_team:
                        # Only count gold bounty records (value > 2.0, not 1.0 or 0.5)
                        if credit_val > 2.0:
                            unique_assisters.add(credit_name)

            scan_pos = next_1d + 1

            # Stop if we hit another kill or death record
            if scan_pos + 3 <= len(data):
                next3 = data[scan_pos:scan_pos+3]
                if next3 in [KILL_PATTERN, DEATH_PATTERN]:
                    break

        kill_events.append({
            "frame": frame_idx,
            "killer": killer_name,
            "ts": ts,
            "assisters": sorted(unique_assisters),
            "pos": pos,
        })
        pos += 16

kill_events.sort(key=lambda e: (e["frame"], e.get("ts") or 0))

# =========================================================================
# Find all death events [08 04 31] separately
# =========================================================================
death_events = []
for frame_idx, data in frames:
    pos = 0
    while True:
        pos = data.find(DEATH_PATTERN, pos)
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
        if eid in entities_be and 0 < ts < 1800:
            death_events.append({
                "victim": entities_be[eid],
                "ts": ts,
                "frame": frame_idx,
            })
        pos += 1

death_events.sort(key=lambda e: e["ts"])

# =========================================================================
# Match kills to deaths by timestamp
# =========================================================================
print("=" * 70)
print("KILL-DEATH TIMESTAMP MATCHING")
print("=" * 70)
print()

for kev in kill_events:
    best_death = None
    best_dt = 999
    for dev in death_events:
        dt = abs(kev["ts"] - dev["ts"])
        victim_team = get_team(dev["victim"])
        killer_team = get_team(kev["killer"])
        # Victim must be on enemy team
        if victim_team != killer_team and dt < best_dt:
            best_dt = dt
            best_death = dev

    if best_death and best_dt < 5.0:
        kev["victim"] = best_death["victim"]
        kev["death_ts"] = best_death["ts"]
        kev["dt"] = best_dt
    else:
        kev["victim"] = None

# =========================================================================
# Display results
# =========================================================================
print(f"Kill events: {len(kill_events)}")
print(f"Death events: {len(death_events)}")
print()

kill_counts = Counter()
assist_counts = Counter()

for i, ev in enumerate(kill_events):
    killer = ev["killer"]
    victim = ev.get("victim", "?") or "?"
    ts = ev["ts"]
    assisters = ev["assisters"]

    kill_counts[killer] += 1
    for a in assisters:
        assist_counts[a] += 1

    assist_str = ", ".join(assisters) if assisters else "(solo)"
    dt_str = f"dt={ev.get('dt', '?'):.2f}s" if ev.get("victim") else "no match"

    print(f"  #{i+1:2d} ts={ts:8.2f} {killer:8s} -> {victim:8s} "
          f"assists=[{assist_str}] [{dt_str}]")

# Death counts from separate scan
death_counts = Counter(d["victim"] for d in death_events)

# =========================================================================
# KDA Validation
# =========================================================================
print()
print("=" * 70)
print("KDA VALIDATION (v2)")
print("=" * 70)
print()

print(f"  {'Player':8s} {'K':>3s} {'TK':>3s} {'':12s} {'D':>3s} {'TD':>3s} {'':12s} {'A':>3s} {'TA':>3s}")
total_k = total_d = total_a = 0
for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ck = kill_counts.get(name, 0)
    cd = death_counts.get(name, 0)
    ca = assist_counts.get(name, 0)
    tk = truth_kills[name]
    td = truth_deaths[name]
    ta = truth_assists[name]
    k_ok = "OK" if ck == tk else f"MISS({ck-tk:+d})"
    d_ok = "OK" if cd == td else f"MISS({cd-td:+d})"
    a_ok = "OK" if ca == ta else f"MISS({ca-ta:+d})"
    if ck == tk: total_k += 1
    if cd == td: total_d += 1
    if ca == ta: total_a += 1
    print(f"  {name:8s} {ck:3d} {tk:3d} [{k_ok:>10s}] {cd:3d} {td:3d} [{d_ok:>10s}] {ca:3d} {ta:3d} [{a_ok:>10s}]")

print()
print(f"  ACCURACY: K={total_k}/6  D={total_d}/6  A={total_a}/6")
print(f"  TOTAL: {total_k + total_d + total_a}/18")
print()

# =========================================================================
# Assist detail breakdown
# =========================================================================
print("=" * 70)
print("ASSIST BREAKDOWN (who assisted which kill)")
print("=" * 70)
print()

player_assist_detail = defaultdict(list)
for i, ev in enumerate(kill_events):
    for a in ev["assisters"]:
        victim = ev.get("victim") or "?"
        player_assist_detail[a].append(f"#{i+1} {ev['killer']} kills {victim}")

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    details = player_assist_detail.get(name, [])
    print(f"  {name:8s} ({len(details)} assists, truth={truth_assists[name]}):")
    for d in details:
        print(f"    {d}")

# Save
output = {
    "version": "full_kda_v2",
    "patterns": {
        "kill": "[18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]",
        "death": "[08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]",
        "credit": "[10 04 1D] [00 00] [eid BE] [gold f32 BE] (gold > 2.0 = assist bounty)",
    },
    "accuracy": {
        "kills": total_k, "deaths": total_d, "assists": total_a,
        "total": f"{total_k+total_d+total_a}/18",
    },
    "events": [
        {
            "killer": ev["killer"],
            "victim": ev.get("victim"),
            "assisters": ev["assisters"],
            "timestamp": ev["ts"],
            "frame": ev["frame"],
        }
        for ev in kill_events
    ],
    "counts": {
        "kills": dict(kill_counts),
        "deaths": dict(death_counts),
        "assists": dict(assist_counts),
    },
}

output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/full_kda_v2.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
print("DONE")
