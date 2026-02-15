"""
Full KDA Parser v5 - Simple positional approach with wider window
=================================================================
What works:
- Kill: [18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
- Death: [08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]

After kill header, credit block structure:
1. [10 04 1D] [killer](1.0) + [09 00 01 00 00 00]  ← killer participation
2. [10 04 1D] [assister](gold>2.0)  ← assist bounty (repeated for each)
3. [10 04 1D] [assister](1.0)  ← assist flag
4. [10 04 1D] [assister](0.5)  ← assist sub-flag
5. Bonus section: small values for killer and assisters

Strategy: Skip first credit (killer), count unique teammates with gold > 2.0.
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

truth = {
    "Phinn": {"K": 2, "D": 0, "A": 6},
    "Yates": {"K": 1, "D": 4, "A": 4},
    "Caine": {"K": 3, "D": 4, "A": 3},
    "Karas": {"K": 0, "D": 3, "A": 2},
    "Petal": {"K": 3, "D": 2, "A": 3},
    "Baron": {"K": 6, "D": 2, "A": 6},
}

print("Loading frames...")
frames = {}
for i in range(200):
    path = os.path.join(CACHE_DIR, f"{PREFIX}.{i}.vgr")
    if not os.path.exists(path):
        continue
    with open(path, "rb") as f:
        frames[i] = f.read()
print(f"Loaded {len(frames)} frames")
print()

KILL_HDR = bytes([0x18, 0x04, 0x1C])
DEATH_HDR = bytes([0x08, 0x04, 0x31])
CREDIT_HDR = bytes([0x10, 0x04, 0x1D])

def get_team(name):
    return left_team if name in left_team else right_team

# =========================================================================
# Find kills
# =========================================================================
kill_events = []
for frame_idx in sorted(frames.keys()):
    data = frames[frame_idx]
    pos = 0
    while True:
        pos = data.find(KILL_HDR, pos)
        if pos == -1:
            break
        if pos + 16 > len(data):
            pos += 1
            continue
        if (data[pos+3:pos+5] != b'\x00\x00' or
            struct.unpack_from(">H", data, pos+5)[0] not in entities_be or
            data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF' or
            data[pos+11:pos+15] != b'\x3F\x80\x00\x00' or
            data[pos+15] != 0x29):
            pos += 1
            continue

        killer_eid = struct.unpack_from(">H", data, pos+5)[0]
        killer = entities_be[killer_eid]
        killer_team = get_team(killer)

        ts = struct.unpack_from(">f", data, pos - 7)[0] if pos >= 7 else None
        if ts and not (0 < ts < 1800):
            ts = None

        # Scan forward 300 bytes for [10 04 1D] credit records
        unique_assisters = set()
        credit_list = []
        scan_start = pos + 16
        scan_end = min(len(data), pos + 300)

        spos = scan_start
        is_first = True
        while spos < scan_end:
            next_pos = data.find(CREDIT_HDR, spos, scan_end)
            if next_pos == -1:
                break
            if next_pos + 11 > len(data):
                break

            if data[next_pos+3:next_pos+5] == b'\x00\x00':
                credit_eid = struct.unpack_from(">H", data, next_pos+5)[0]
                credit_name = entities_be.get(credit_eid)
                credit_val = struct.unpack_from(">f", data, next_pos+7)[0]

                if credit_name:
                    credit_list.append(f"{credit_name}({credit_val:.1f})")

                    if is_first:
                        is_first = False  # Skip first (killer participation)
                    elif credit_name != killer and credit_name in killer_team and credit_val > 2.0:
                        unique_assisters.add(credit_name)

            spos = next_pos + 1

        kill_events.append({
            "frame": frame_idx,
            "killer": killer,
            "ts": ts,
            "assisters": sorted(unique_assisters),
            "credits": credit_list,
            "pos": pos,
        })
        pos += 16

kill_events.sort(key=lambda e: (e["frame"], e.get("ts") or 0))

# =========================================================================
# Find deaths
# =========================================================================
death_events = []
for frame_idx in sorted(frames.keys()):
    data = frames[frame_idx]
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
        if eid in entities_be and 0 < ts < 1800:
            death_events.append({"victim": entities_be[eid], "ts": ts, "frame": frame_idx})
        pos += 1
death_events.sort(key=lambda e: e["ts"])

# Match kills to deaths by timestamp (1:1 matching)
used_deaths = set()
for kev in kill_events:
    killer_team = get_team(kev["killer"])
    best_death = None
    best_dt = 999
    best_di = -1
    for di, dev in enumerate(death_events):
        if di in used_deaths:
            continue
        if get_team(dev["victim"]) != killer_team:
            dt = abs(kev["ts"] - dev["ts"])
            if dt < best_dt and dt < 5.0:
                best_dt = dt
                best_death = dev
                best_di = di
    if best_death:
        kev["victim"] = best_death["victim"]
        kev["death_ts"] = best_death["ts"]
        used_deaths.add(best_di)
    else:
        kev["victim"] = None

# =========================================================================
# Display
# =========================================================================
print("=" * 70)
print("KILL EVENTS")
print("=" * 70)
print()

kill_counts = Counter()
assist_counts = Counter()

for i, ev in enumerate(kill_events):
    killer = ev["killer"]
    victim = ev.get("victim") or "?"
    assisters = ev["assisters"]

    kill_counts[killer] += 1
    for a in assisters:
        assist_counts[a] += 1

    assist_str = ", ".join(assisters) if assisters else "(solo)"
    dt_str = f"dt={abs(ev['ts'] - ev['death_ts']):.2f}s" if ev.get("death_ts") else ""
    cred_str = ", ".join(ev["credits"])

    print(f"  #{i+1:2d} ts={ev['ts']:8.2f} {killer:8s} -> {victim:8s} "
          f"assists=[{assist_str}] {dt_str}")
    print(f"      credits: [{cred_str}]")

death_counts = Counter(d["victim"] for d in death_events)

# =========================================================================
# KDA Validation
# =========================================================================
print()
print("=" * 70)
print("KDA VALIDATION (v5)")
print("=" * 70)
print()

print(f"  {'Player':8s} {'K':>3s} {'TK':>3s} {'':12s} {'D':>3s} {'TD':>3s} {'':12s} {'A':>3s} {'TA':>3s}")
total_k = total_d = total_a = 0
for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ck = kill_counts.get(name, 0)
    cd = death_counts.get(name, 0)
    ca = assist_counts.get(name, 0)
    tk = truth[name]["K"]
    td = truth[name]["D"]
    ta = truth[name]["A"]
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

# =========================================================================
# Assist analysis: check if truth_A > possible assists
# =========================================================================
print()
print("=" * 70)
print("ASSIST ANALYSIS: Possible vs Truth")
print("=" * 70)
print()

# Count how many kills each player could have assisted
possible_assists = Counter()
for ev in kill_events:
    killer = ev["killer"]
    killer_team = get_team(killer)
    for name in killer_team:
        if name != killer:
            possible_assists[name] += 1

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    pa = possible_assists.get(name, 0)
    ta = truth[name]["A"]
    ca = assist_counts.get(name, 0)
    feasible = "OK" if ta <= pa else f"IMPOSSIBLE (truth={ta} > possible={pa})"
    print(f"  {name:8s}: possible={pa:2d} detected={ca:2d} truth={ta:2d} [{feasible}]")

# Save
output = {
    "version": "full_kda_v5",
    "patterns": {
        "kill": "[18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]",
        "death": "[08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]",
        "assist": "[10 04 1D] [00 00] [teammate_eid BE] [gold f32 BE > 2.0] after kill header",
    },
    "accuracy": {"kills": total_k, "deaths": total_d, "assists": total_a,
                 "total": f"{total_k+total_d+total_a}/18"},
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
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/full_kda_v5.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
print("DONE")
