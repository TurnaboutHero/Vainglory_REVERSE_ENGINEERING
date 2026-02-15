"""
Full KDA Parser - Kill/Death/Assist Event Extraction
=====================================================
Based on discovered record structures:

KILL RECORD:
  [18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
  followed by padding and [10 04 1D] records for kill credit + assists

DEATH RECORD:
  [08 04 31] [00 00] [victim_eid BE] [00 00] [timestamp f32 BE] [00 00 00]

Strategy: Parse the full event stream around each kill/death event.
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
# Phase 1: Find all kill events [18 04 1C]
# =========================================================================
print("=" * 70)
print("Phase 1: Finding kill events [18 04 1C]")
print("=" * 70)
print()

kill_events = []
KILL_PATTERN = bytes([0x18, 0x04, 0x1C])

for frame_idx, data in frames:
    pos = 0
    while True:
        pos = data.find(KILL_PATTERN, pos)
        if pos == -1:
            break
        if pos + 16 > len(data):
            pos += 1
            continue

        # Validate structure: [18 04 1C] [00 00] [eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        killer_eid = struct.unpack_from(">H", data, pos+5)[0]

        if killer_eid not in entities_be:
            pos += 1
            continue

        # Check FF FF FF FF at +7
        if data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF':
            pos += 1
            continue

        # Check 3F 80 00 00 (= 1.0 float) at +11
        if data[pos+11:pos+15] != b'\x3F\x80\x00\x00':
            pos += 1
            continue

        # Check 29 at +15
        if data[pos+15] != 0x29:
            pos += 1
            continue

        killer_name = entities_be[killer_eid]

        # Find timestamp: look backwards for the timestamp pattern
        # Structure before: [?? ?? 00] [06 00 01 00 00 00] [ts f32 BE] [00 00 00] [18 04 1C]
        ts = None
        if pos >= 7:
            ts_pos = pos - 7  # timestamp is 7 bytes before the kill header
            ts_candidate = struct.unpack_from(">f", data, ts_pos)[0]
            if 0 < ts_candidate < 1800:
                ts = ts_candidate

        # Also check the embedded timestamp at +19 (after padding)
        if ts is None and pos + 27 <= len(data):
            ts_candidate = struct.unpack_from(">f", data, pos + 19)[0]
            if 0 < ts_candidate < 1800:
                ts = ts_candidate

        # Now scan forward for [10 04 1D] assist/credit records
        # After kill header: [29 00] [00 00 00 00 00 00 00 00] [ts] [00 00 00] [10 04 1D] ...
        assisters = []
        credit_records = []
        scan_pos = pos + 16  # After the [29 00] byte (pos+15 is 29, pos+16 is 00)

        # Scan up to 200 bytes forward for [10 04 1D] records
        scan_end = min(len(data), pos + 200)
        while scan_pos < scan_end:
            # Look for [10 04 1D]
            next_1d = data.find(bytes([0x10, 0x04, 0x1D]), scan_pos, scan_end)
            if next_1d == -1:
                break

            if next_1d + 7 > len(data):
                break

            # Check structure: [10 04 1D] [00 00] [eid BE]
            if data[next_1d+3:next_1d+5] == b'\x00\x00':
                credit_eid = struct.unpack_from(">H", data, next_1d+5)[0]
                credit_name = entities_be.get(credit_eid)

                if credit_name:
                    # Get the value after eid (f32 BE at +7)
                    value = None
                    if next_1d + 11 <= len(data):
                        value = struct.unpack_from(">f", data, next_1d+7)[0]

                    credit_records.append({
                        "name": credit_name,
                        "eid": credit_eid,
                        "value": value,
                        "offset_from_kill": next_1d - pos,
                    })

                    # If this is NOT the killer, it's an assister
                    if credit_name != killer_name:
                        assisters.append(credit_name)

            scan_pos = next_1d + 1

            # Stop if we hit another major record type (death, another kill, etc.)
            # Check for [08 04 31] or [18 04 1C] in the scan range
            if scan_pos + 3 <= len(data):
                next_3 = data[scan_pos:scan_pos+3]
                if next_3 in [bytes([0x08, 0x04, 0x31]), bytes([0x18, 0x04, 0x1C])]:
                    break

        # Find nearby death record
        death_victim = None
        death_ts = None
        for death_off in range(-50, 200):
            dpos = pos + death_off
            if 0 <= dpos and dpos + 13 <= len(data):
                if data[dpos:dpos+3] == bytes([0x08, 0x04, 0x31]):
                    if data[dpos+3:dpos+5] == b'\x00\x00' and data[dpos+7:dpos+9] == b'\x00\x00':
                        d_eid = struct.unpack_from(">H", data, dpos+5)[0]
                        d_ts = struct.unpack_from(">f", data, dpos+9)[0]
                        if d_eid in entities_be and 0 < d_ts < 1800:
                            death_victim = entities_be[d_eid]
                            death_ts = d_ts
                            break

        kill_events.append({
            "frame": frame_idx,
            "killer": killer_name,
            "ts": ts,
            "assisters": assisters,
            "credit_records": credit_records,
            "death_victim": death_victim,
            "death_ts": death_ts,
            "pos": pos,
        })

        pos += 16
    # end while

kill_events.sort(key=lambda e: (e["frame"], e.get("ts") or 0))

# =========================================================================
# Phase 2: Display and validate
# =========================================================================
print(f"Found {len(kill_events)} kill events")
print()

kill_counts = Counter()
assist_counts = Counter()
death_counts = Counter()

for i, ev in enumerate(kill_events):
    killer = ev["killer"]
    victim = ev["death_victim"] or "?"
    ts = ev["ts"]
    assisters = ev["assisters"]

    kill_counts[killer] += 1
    for a in assisters:
        assist_counts[a] += 1
    if ev["death_victim"]:
        death_counts[ev["death_victim"]] += 1

    assist_str = ", ".join(assisters) if assisters else "(solo)"
    credit_str = " | Credits: " + ", ".join(
        f"{c['name']}({c['value']:.1f})" if c['value'] else f"{c['name']}(?)"
        for c in ev["credit_records"]
    )

    ts_str = f"ts={ts:.2f}" if ts else "ts=?"
    print(f"  #{i+1:2d} {ts_str:14s} KILL: {killer:8s} -> {victim:8s} | Assists: {assist_str}{credit_str}")

print()

# =========================================================================
# Phase 3: KDA Validation
# =========================================================================
print("=" * 70)
print("KDA VALIDATION")
print("=" * 70)
print()

print(f"  {'Player':8s} {'K':>3s} {'TK':>3s} {'':5s} {'D':>3s} {'TD':>3s} {'':5s} {'A':>3s} {'TA':>3s}")
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
# Phase 4: Check kill-death timestamp pairing
# =========================================================================
print()
print("=" * 70)
print("Phase 4: Kill-Death timestamp pairing")
print("=" * 70)
print()

for ev in kill_events:
    killer = ev["killer"]
    victim = ev["death_victim"]
    kill_ts = ev["ts"]
    death_ts = ev["death_ts"]

    if kill_ts and death_ts:
        dt = abs(kill_ts - death_ts)
        pair_ok = "PAIRED" if dt < 5.0 else f"GAP={dt:.1f}s"
    else:
        pair_ok = "NO PAIR"

    victim_team = None
    if victim:
        killer_team = left_team if killer in left_team else right_team
        victim_in = left_team if victim in left_team else right_team
        cross_team = "CROSS" if killer_team != victim_in else "SAME TEAM!"
    else:
        cross_team = "?"

    ts_str = f"kill_ts={kill_ts:.2f}" if kill_ts else "kill_ts=?"
    dts_str = f"death_ts={death_ts:.2f}" if death_ts else "death_ts=?"
    print(f"  {killer:8s} -> {victim or '?':8s} [{cross_team:10s}] {ts_str} {dts_str} [{pair_ok}]")

# Save results
output = {
    "version": "full_kda_v1",
    "kill_record": "[18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]",
    "death_record": "[08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]",
    "credit_record": "[10 04 1D] [00 00] [eid BE] [value f32 BE]",
    "accuracy": {"kills": total_k, "deaths": total_d, "assists": total_a, "total": f"{total_k+total_d+total_a}/18"},
    "events": [
        {
            "killer": ev["killer"],
            "victim": ev["death_victim"],
            "assisters": ev["assisters"],
            "timestamp": ev["ts"],
            "frame": ev["frame"],
        }
        for ev in kill_events
    ],
    "kill_counts": dict(kill_counts),
    "death_counts": dict(death_counts),
    "assist_counts": dict(assist_counts),
}

output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/full_kda_v1.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
print("\nDONE")
