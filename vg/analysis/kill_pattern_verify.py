"""
Kill Pattern [00 29 00] Verification
======================================
Exhaustive search found: pattern 0x002900 at offset 23 from entity ID (BE)
matches kills EXACTLY: Phinn=2, Yates=1, Caine=3, Karas=0, Petal=3, Baron=6

This script:
1. Shows the actual byte context around each match
2. Determines the full record structure
3. Checks relationship to death records
"""
import os
import struct
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

# Load all frames individually (for frame identification)
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

# Also load concatenated for reference
all_data = bytearray()
for _, data in frames:
    all_data.extend(data)
all_data = bytes(all_data)

# =========================================================================
# Phase 1: Find all [00 29 00] ... [eid BE] matches (offset=23)
# =========================================================================
print("=" * 70)
print("Phase 1: Finding all [00 29 00] ... [eid BE at +23] matches")
print("=" * 70)
print()

kill_records = []

for frame_idx, data in frames:
    for eid, name in entities_be.items():
        eid_bytes = struct.pack(">H", eid)
        pos = 0
        while True:
            pos = data.find(eid_bytes, pos)
            if pos == -1:
                break

            # Check for [00 29 00] at position (pos - 23)
            pat_pos = pos - 23
            if pat_pos >= 0 and pat_pos + 3 <= len(data):
                if data[pat_pos:pat_pos+3] == bytes([0x00, 0x29, 0x00]):
                    # Found a match! Extract wide context
                    ctx_start = max(0, pat_pos - 30)
                    ctx_end = min(len(data), pos + 30)

                    # Look for timestamp (f32 BE) near the entity ID
                    timestamps = []
                    for ts_off in range(-10, 20):
                        ts_pos = pos + ts_off
                        if 0 <= ts_pos and ts_pos + 4 <= len(data):
                            ts_val = struct.unpack_from(">f", data, ts_pos)[0]
                            if 10 < ts_val < 1800:
                                timestamps.append((ts_off, ts_val))

                    # Look for other player entity IDs in nearby context
                    nearby_players = []
                    for check_pos in range(ctx_start, ctx_end - 1):
                        check_eid = struct.unpack_from(">H", data, check_pos)[0]
                        if check_eid in entities_be and check_pos != pos:
                            nearby_players.append((check_pos - pat_pos, entities_be[check_eid]))

                    # Check for death record [08 04 31] nearby
                    death_nearby = None
                    for death_off in range(-100, 100):
                        dpos = pat_pos + death_off
                        if 0 <= dpos and dpos + 13 <= len(data):
                            if data[dpos:dpos+3] == bytes([0x08, 0x04, 0x31]):
                                if data[dpos+3:dpos+5] == b'\x00\x00' and data[dpos+7:dpos+9] == b'\x00\x00':
                                    death_eid = struct.unpack_from(">H", data, dpos+5)[0]
                                    if death_eid in entities_be:
                                        death_ts = struct.unpack_from(">f", data, dpos+9)[0]
                                        if 0 < death_ts < 1800:
                                            death_nearby = {
                                                "offset": death_off,
                                                "victim": entities_be[death_eid],
                                                "ts": death_ts,
                                            }

                    kill_records.append({
                        "frame": frame_idx,
                        "killer": name,
                        "killer_eid": eid,
                        "pat_pos": pat_pos,
                        "eid_pos": pos,
                        "timestamps": timestamps,
                        "nearby_players": nearby_players,
                        "death_nearby": death_nearby,
                        "context": data[ctx_start:ctx_end],
                        "ctx_start": ctx_start,
                        "pat_offset_in_ctx": pat_pos - ctx_start,
                    })
            pos += 1

# Sort by frame and position
kill_records.sort(key=lambda r: (r["frame"], r["pat_pos"]))

print(f"Total kill records found: {len(kill_records)}")
print()

# Count per player
kill_counts = Counter(r["killer"] for r in kill_records)
print("Kill counts:")
for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    detected = kill_counts.get(name, 0)
    truth = truth_kills[name]
    ok = "OK" if detected == truth else "MISS"
    print(f"  {name:8s}: detected={detected}, truth={truth} [{ok}]")
print()

# =========================================================================
# Phase 2: Show detailed context for each kill record
# =========================================================================
print("=" * 70)
print("Phase 2: Detailed kill records")
print("=" * 70)
print()

for i, r in enumerate(kill_records):
    killer = r["killer"]
    killer_team = left_team if killer in left_team else right_team
    enemy_team = right_team if killer in left_team else left_team

    death_info = ""
    victim = "?"
    if r["death_nearby"]:
        dn = r["death_nearby"]
        death_info = f" | DEATH: {dn['victim']} at offset={dn['offset']:+d} ts={dn['ts']:.2f}"
        victim = dn["victim"]

    # Check if nearby players include enemies (potential victims)
    nearby_str = ", ".join(f"{p[1]}@{p[0]:+d}" for p in r["nearby_players"])

    # Find best timestamp candidate
    best_ts = None
    for ts_off, ts_val in r["timestamps"]:
        if best_ts is None or abs(ts_off) < abs(best_ts[0]):
            best_ts = (ts_off, ts_val)

    ts_str = f"ts={best_ts[1]:.2f}" if best_ts else "ts=?"

    print(f"#{i+1:2d} Frame={r['frame']:3d} KILLER={killer:8s} {ts_str}{death_info}")
    print(f"    Nearby players: [{nearby_str}]")

    # Hex dump of context
    ctx = r["context"]
    po = r["pat_offset_in_ctx"]
    eid_off = po + 23

    # Print hex with annotations
    hex_str = " ".join(f"{b:02X}" for b in ctx)
    # Show the bytes from pattern position to entity ID
    print(f"    Full context ({r['ctx_start']:06X}):")
    for row_start in range(0, len(ctx), 32):
        row_bytes = " ".join(f"{ctx[row_start+j]:02X}" if row_start+j < len(ctx) else "  " for j in range(32))
        abs_addr = r["ctx_start"] + row_start
        print(f"      {abs_addr:06X}: {row_bytes}")

    # Show the specific 25-byte region: pattern[3] + gap[20] + eid[2]
    if po >= 0 and eid_off + 2 <= len(ctx):
        region = ctx[po:eid_off+2]
        region_hex = " ".join(f"{b:02X}" for b in region)
        print(f"    Kill region (pat->eid): {region_hex}")
        print(f"    Structure: [00 29 00] [{' '.join(f'{b:02X}' for b in region[3:23])}] [{region[23]:02X} {region[24]:02X}]")
    print()

# =========================================================================
# Phase 3: Analyze the 20-byte gap between pattern and entity ID
# =========================================================================
print("=" * 70)
print("Phase 3: Structure of the 20-byte gap")
print("=" * 70)
print()

# Extract the 20 bytes between [00 29 00] and [eid] for each record
for i, r in enumerate(kill_records):
    ctx = r["context"]
    po = r["pat_offset_in_ctx"]
    if po < 0 or po + 25 > len(ctx):
        continue

    gap = ctx[po+3:po+23]  # 20 bytes between pattern and eid
    eid_bytes = ctx[po+23:po+25]

    # Try to parse the gap
    # Common patterns: 00 padding, timestamps, other entity IDs
    gap_hex = " ".join(f"{b:02X}" for b in gap)

    # Check for entity IDs in the gap
    gap_eids = []
    for j in range(len(gap) - 1):
        geid = struct.unpack_from(">H", gap, j)[0]
        if geid in entities_be:
            gap_eids.append((j, entities_be[geid]))

    # Check for timestamps in the gap
    gap_ts = []
    for j in range(len(gap) - 3):
        ts = struct.unpack_from(">f", gap, j)[0]
        if 10 < ts < 1800:
            gap_ts.append((j, ts))

    print(f"#{i+1} {r['killer']:8s} frame={r['frame']:3d}: {gap_hex} -> [{eid_bytes[0]:02X} {eid_bytes[1]:02X}]")
    if gap_eids:
        print(f"    Entity IDs in gap: {gap_eids}")
    if gap_ts:
        print(f"    Timestamps in gap: {[(off, f'{ts:.2f}') for off, ts in gap_ts]}")

print()
print("DONE")
