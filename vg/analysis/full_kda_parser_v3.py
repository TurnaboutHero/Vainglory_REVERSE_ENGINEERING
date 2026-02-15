"""
Full KDA Parser v3 - Timestamp-based Assist Matching
=====================================================
Key insight: Each sub-record in an event has [timestamp f32 BE] [00 00 00] prefix.
Find ALL [10 04 1D] records with the SAME timestamp as each kill event.
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

KILL_PATTERN = bytes([0x18, 0x04, 0x1C])
DEATH_PATTERN = bytes([0x08, 0x04, 0x31])
CREDIT_PATTERN = bytes([0x10, 0x04, 0x1D])

def get_team(name):
    return left_team if name in left_team else right_team

# =========================================================================
# Step 1: Find all kill events with their timestamps
# =========================================================================
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

        # Timestamp: 7 bytes before kill header
        ts = None
        ts_bytes = None
        if pos >= 7:
            ts_bytes = data[pos-7:pos-3]
            ts = struct.unpack_from(">f", ts_bytes, 0)[0]
            if not (0 < ts < 1800):
                ts = None
                ts_bytes = None

        kill_events.append({
            "frame": frame_idx,
            "killer": killer_name,
            "ts": ts,
            "ts_bytes": ts_bytes,
            "pos": pos,
        })
        pos += 16

kill_events.sort(key=lambda e: (e["frame"], e.get("ts") or 0))

# =========================================================================
# Step 2: For each kill, find ALL [10 04 1D] records in the same frame
#         with matching timestamp (ts_bytes appears 7 bytes before the record)
# =========================================================================
print("=" * 70)
print("KILL EVENTS WITH TIMESTAMP-MATCHED CREDITS")
print("=" * 70)
print()

for kev in kill_events:
    if not kev["ts_bytes"]:
        continue

    data = None
    for fidx, fdata in frames:
        if fidx == kev["frame"]:
            data = fdata
            break
    if not data:
        continue

    ts_bytes = kev["ts_bytes"]
    killer = kev["killer"]
    killer_team = get_team(killer)

    # Find ALL [10 04 1D] in this frame preceded by the same timestamp
    # Pattern: [ts_bytes] [00 00 00] [10 04 1D] [00 00] [eid BE] [value f32 BE]
    search_seq = ts_bytes + b'\x00\x00\x00' + CREDIT_PATTERN
    # That's 4 + 3 + 3 = 10 bytes

    credits = []
    spos = 0
    while True:
        spos = data.find(search_seq, spos)
        if spos == -1:
            break
        # [10 04 1D] starts at spos + 7
        rec_pos = spos + 7
        if rec_pos + 11 <= len(data):
            if data[rec_pos+3:rec_pos+5] == b'\x00\x00':
                credit_eid = struct.unpack_from(">H", data, rec_pos+5)[0]
                credit_name = entities_be.get(credit_eid)
                credit_val = struct.unpack_from(">f", data, rec_pos+7)[0]
                if credit_name:
                    credits.append({
                        "name": credit_name,
                        "value": credit_val,
                        "pos": rec_pos,
                    })
        spos += 1

    # Classify credits: killer vs assisters
    # Only count UNIQUE teammate names with gold bounty (value > 2.0)
    unique_assisters = set()
    all_credit_names = []
    for c in credits:
        all_credit_names.append(f"{c['name']}({c['value']:.1f})")
        if c["name"] != killer and c["name"] in killer_team and c["value"] > 2.0:
            unique_assisters.add(c["name"])

    kev["assisters"] = sorted(unique_assisters)
    kev["all_credits"] = all_credit_names

# =========================================================================
# Step 3: Find deaths separately
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
            death_events.append({"victim": entities_be[eid], "ts": ts, "frame": frame_idx})
        pos += 1

death_events.sort(key=lambda e: e["ts"])

# Match kills to deaths by timestamp
for kev in kill_events:
    best_death = None
    best_dt = 999
    killer_team = get_team(kev["killer"])
    for dev in death_events:
        victim_team = get_team(dev["victim"])
        if victim_team != killer_team:
            dt = abs(kev["ts"] - dev["ts"])
            if dt < best_dt:
                best_dt = dt
                best_death = dev
    kev["victim"] = best_death["victim"] if best_death and best_dt < 5.0 else None
    kev["death_ts"] = best_death["ts"] if best_death and best_dt < 5.0 else None

# =========================================================================
# Step 4: Display and validate
# =========================================================================
kill_counts = Counter()
assist_counts = Counter()

for i, ev in enumerate(kill_events):
    killer = ev["killer"]
    victim = ev.get("victim") or "?"
    assisters = ev.get("assisters", [])

    kill_counts[killer] += 1
    for a in assisters:
        assist_counts[a] += 1

    assist_str = ", ".join(assisters) if assisters else "(solo)"
    credits_str = ", ".join(ev.get("all_credits", []))
    dt_str = f"dt={abs(ev['ts'] - ev['death_ts']):.2f}s" if ev.get("death_ts") else "?"

    print(f"  #{i+1:2d} ts={ev['ts']:8.2f} {killer:8s} -> {victim:8s} | "
          f"assists=[{assist_str}] [{dt_str}]")
    print(f"       credits: [{credits_str}]")

death_counts = Counter(d["victim"] for d in death_events)

print()
print("=" * 70)
print("KDA VALIDATION (v3 - timestamp-matched)")
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

# =========================================================================
# Step 5: Try alternative assist counting strategies
# =========================================================================
print()
print("=" * 70)
print("ALTERNATIVE ASSIST STRATEGIES")
print("=" * 70)

# Strategy A: Count all unique teammates (including value <= 2.0)
print("\nStrategy A: All unique teammates from timestamp-matched credits")
assist_a = Counter()
for ev in kill_events:
    killer = ev["killer"]
    killer_team = get_team(killer)
    seen = set()
    for c_str in ev.get("all_credits", []):
        name = c_str.split("(")[0]
        if name != killer and name in killer_team and name not in seen:
            seen.add(name)
            assist_a[name] += 1

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ca = assist_a.get(name, 0)
    ta = truth_assists[name]
    ok = "OK" if ca == ta else f"({ca-ta:+d})"
    print(f"  {name:8s}: {ca:3d} truth={ta} {ok}")

# Strategy B: Count unique teammates including enemies
print("\nStrategy B: All unique players from timestamp-matched credits (any team)")
assist_b = Counter()
for ev in kill_events:
    killer = ev["killer"]
    seen = set()
    for c_str in ev.get("all_credits", []):
        name = c_str.split("(")[0]
        if name != killer and name not in seen:
            seen.add(name)
            assist_b[name] += 1

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ca = assist_b.get(name, 0)
    ta = truth_assists[name]
    ok = "OK" if ca == ta else f"({ca-ta:+d})"
    print(f"  {name:8s}: {ca:3d} truth={ta} {ok}")

# Strategy C: Count total credit occurrences (not unique) with gold > 2.0
print("\nStrategy C: Total gold bounty credits (value > 2.0, same team)")
assist_c = Counter()
for ev in kill_events:
    killer = ev["killer"]
    killer_team = get_team(killer)
    for c_str in ev.get("all_credits", []):
        name, val_str = c_str.split("(")
        val = float(val_str.rstrip(")"))
        if name != killer and name in killer_team and val > 2.0:
            assist_c[name] += 1

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ca = assist_c.get(name, 0)
    ta = truth_assists[name]
    ok = "OK" if ca == ta else f"({ca-ta:+d})"
    print(f"  {name:8s}: {ca:3d} truth={ta} {ok}")

# Strategy D: Count 10 04 1D with value=1.0 (participation flags, same team)
print("\nStrategy D: Participation flags (value == 1.0, same team)")
assist_d = Counter()
for ev in kill_events:
    killer = ev["killer"]
    killer_team = get_team(killer)
    for c_str in ev.get("all_credits", []):
        name, val_str = c_str.split("(")
        val = float(val_str.rstrip(")"))
        if name != killer and name in killer_team and val == 1.0:
            assist_d[name] += 1

for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    ca = assist_d.get(name, 0)
    ta = truth_assists[name]
    ok = "OK" if ca == ta else f"({ca-ta:+d})"
    print(f"  {name:8s}: {ca:3d} truth={ta} {ok}")

# Save
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/full_kda_v3.json"
output = {
    "version": "full_kda_v3",
    "accuracy": {"kills": total_k, "deaths": total_d, "assists": total_a},
    "events": [
        {
            "killer": ev["killer"],
            "victim": ev.get("victim"),
            "assisters": ev.get("assisters", []),
            "all_credits": ev.get("all_credits", []),
            "timestamp": ev["ts"],
            "frame": ev["frame"],
        }
        for ev in kill_events
    ],
}
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
print("DONE")
