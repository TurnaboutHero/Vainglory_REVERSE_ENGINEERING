"""
Death-Context Kill/Assist Search
=================================
Strategy: Since deaths are at known timestamps, scan bytes AROUND each
death record for other records containing enemy player entity IDs.

Death record: [08 04 31] [00 00] [victim_eid BE] [00 00] [ts f32 BE] [00 00 00]
                                                          ^-- 13 bytes total

Near each death record, there should be kill/assist records for enemies.
Scan +-200 bytes around each death for ALL player entity IDs (BE).
"""
import os
import struct
from collections import Counter, defaultdict

CACHE_DIR = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

entities = {
    0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
    0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
}
eid_to_name = {eid: name for eid, name in entities.items()}
name_to_eid = {name: eid for eid, name in entities.items()}

left_team = {"Phinn", "Petal", "Baron"}
right_team = {"Yates", "Caine", "Karas"}

truth_kills = {"Phinn": 2, "Yates": 1, "Caine": 3, "Karas": 0, "Petal": 3, "Baron": 6}
truth_deaths = {"Phinn": 0, "Yates": 4, "Caine": 4, "Karas": 3, "Petal": 2, "Baron": 2}
truth_assists = {"Phinn": 6, "Yates": 4, "Caine": 3, "Karas": 2, "Petal": 3, "Baron": 6}


def load_frame(idx):
    path = os.path.join(CACHE_DIR, f"{PREFIX}.{idx}.vgr")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def find_death_records(data, frame_idx):
    """Find all [08 04 31] death records."""
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
        if eid in eid_to_name and 0 < ts < 1800:
            results.append({
                "victim": eid_to_name[eid],
                "victim_eid": eid,
                "ts": ts,
                "pos": pos,
                "frame": frame_idx,
            })
        pos += 1
    return results


def find_all_player_refs_near(data, center_pos, window=200):
    """Find all player entity ID references (BE) near a position."""
    start = max(0, center_pos - window)
    end = min(len(data), center_pos + window)

    refs = []
    for eid, name in entities.items():
        eid_bytes = struct.pack(">H", eid)
        pos = start
        while pos < end:
            pos = data.find(eid_bytes, pos, end)
            if pos == -1:
                break
            # Record offset relative to the death record
            rel_offset = pos - center_pos
            # Check for nearby 3-byte record type header (look backwards)
            record_type = None
            for back in [2, 4, 5, 7, 9]:
                rpos = pos - back
                if rpos >= 0 and rpos + 3 <= len(data):
                    rt = data[rpos:rpos+3]
                    record_type = rt.hex()
                    break

            refs.append({
                "name": name,
                "eid": eid,
                "abs_pos": pos,
                "rel_offset": rel_offset,
                "nearby_bytes": data[max(0,pos-5):pos+7].hex(),
            })
            pos += 1
    return refs


# =========================================================================
# Phase 1: Collect all death records and surrounding context
# =========================================================================
print("Phase 1: Collecting death records and context...")
print()

all_deaths = []
for frame_idx in range(200):
    data = load_frame(frame_idx)
    if data is None:
        continue
    deaths = find_death_records(data, frame_idx)
    for d in deaths:
        d["data"] = data
    all_deaths.extend(deaths)

print(f"Found {len(all_deaths)} death records")
print()

# =========================================================================
# Phase 2: For each death, find ALL nearby player entity references
# =========================================================================
print("Phase 2: Analyzing context around each death...")
print()

# Track who appears near each death, categorized by team relationship
kill_candidates = Counter()  # enemy player -> count of appearances near victim deaths
assist_candidates = Counter()

for d in all_deaths:
    victim = d["victim"]
    victim_team = left_team if victim in left_team else right_team
    enemy_team = right_team if victim in left_team else left_team

    data = d["data"]
    refs = find_all_player_refs_near(data, d["pos"], window=150)

    # Filter: only ENEMY players (not the victim, not same team)
    enemy_refs = [r for r in refs if r["name"] in enemy_team]
    # Filter: not the death record itself (offset 0-13 region)
    enemy_refs = [r for r in enemy_refs if not (0 <= r["rel_offset"] <= 13)]

    # Group by relative offset to understand record structure
    print(f"  Death: {victim:8s} ts={d['ts']:8.2f} frame={d['frame']:3d} pos=0x{d['pos']:06X}")

    # Find unique enemies near this death
    unique_enemies = set()
    enemy_by_offset = defaultdict(list)
    for r in enemy_refs:
        unique_enemies.add(r["name"])
        enemy_by_offset[r["rel_offset"]].append(r["name"])

    for r in sorted(enemy_refs, key=lambda x: x["rel_offset"]):
        print(f"    offset={r['rel_offset']:+4d} {r['name']:8s} bytes={r['nearby_bytes']}")

    if not enemy_refs:
        print(f"    (no enemy references found)")
    print()

# =========================================================================
# Phase 3: Study the record structure around deaths more precisely
# =========================================================================
print("=" * 70)
print("Phase 3: Hex dump around each death record (+-50 bytes)")
print("=" * 70)
print()

for d in all_deaths:
    victim = d["victim"]
    pos = d["pos"]
    data = d["data"]

    start = max(0, pos - 50)
    end = min(len(data), pos + 60)
    chunk = data[start:end]

    print(f"Death: {victim:8s} ts={d['ts']:8.2f} frame={d['frame']:3d}")

    # Print hex with position markers
    for row_start in range(0, len(chunk), 16):
        abs_addr = start + row_start
        hex_bytes = []
        for j in range(16):
            if row_start + j < len(chunk):
                byte_pos = abs_addr + j
                # Mark death record bytes
                if pos <= byte_pos < pos + 13:
                    hex_bytes.append(f"\033[91m{chunk[row_start+j]:02X}\033[0m")
                # Mark player entity IDs
                elif byte_pos + 1 < len(data):
                    two_byte = struct.unpack_from(">H", data, byte_pos)[0]
                    if two_byte in eid_to_name:
                        hex_bytes.append(f"\033[92m{chunk[row_start+j]:02X}\033[0m")
                    else:
                        hex_bytes.append(f"{chunk[row_start+j]:02X}")
                else:
                    hex_bytes.append(f"{chunk[row_start+j]:02X}")
            else:
                hex_bytes.append("  ")

        # Plain hex for structured analysis
        plain_hex = " ".join(f"{chunk[row_start+j]:02X}" if row_start+j < len(chunk) else "  " for j in range(16))
        rel = abs_addr - pos
        print(f"  {abs_addr:06X} ({rel:+4d}): {plain_hex}")
    print()

# =========================================================================
# Phase 4: Pattern frequency near death records
# =========================================================================
print("=" * 70)
print("Phase 4: 3-byte pattern frequency at fixed offsets from death records")
print("=" * 70)
print()

# For each death, extract the 3 bytes at various offsets BEFORE and AFTER
offset_pattern_counts = defaultdict(Counter)
for d in all_deaths:
    pos = d["pos"]
    data = d["data"]
    for offset in range(-50, 60, 1):
        abs_pos = pos + offset
        if 0 <= abs_pos and abs_pos + 3 <= len(data):
            pat = data[abs_pos:abs_pos+3].hex()
            offset_pattern_counts[offset][pat] += 1

# Show offsets where ALL deaths share the same pattern (likely record structure)
print("Consistent patterns across all deaths:")
for offset in sorted(offset_pattern_counts.keys()):
    counts = offset_pattern_counts[offset]
    most_common = counts.most_common(1)[0]
    if most_common[1] == len(all_deaths):
        print(f"  offset {offset:+4d}: 0x{most_common[0]} (all {len(all_deaths)} deaths)")
    elif most_common[1] >= len(all_deaths) * 0.8:
        print(f"  offset {offset:+4d}: 0x{most_common[0]} ({most_common[1]}/{len(all_deaths)} deaths)")

print()

# =========================================================================
# Phase 5: Look at the SAME timestamp in nearby records
# =========================================================================
print("=" * 70)
print("Phase 5: Search for same timestamp as each death in surrounding +-500 bytes")
print("=" * 70)
print()

kill_by_timestamp = Counter()  # Tracks which enemies share timestamps with deaths

for d in all_deaths:
    victim = d["victim"]
    victim_team = left_team if victim in left_team else right_team
    enemy_team = right_team if victim in left_team else left_team
    ts = d["ts"]
    ts_bytes = struct.pack(">f", ts)
    pos = d["pos"]
    data = d["data"]

    # Search for the same timestamp bytes in +-500 range
    search_start = max(0, pos - 500)
    search_end = min(len(data), pos + 500)

    ts_positions = []
    spos = search_start
    while spos < search_end:
        spos = data.find(ts_bytes, spos, search_end)
        if spos == -1:
            break
        if spos != pos + 9:  # Skip the death record's own timestamp
            ts_positions.append(spos)
        spos += 1

    if ts_positions:
        print(f"Death: {victim:8s} ts={ts:8.2f} frame={d['frame']:3d}")
        for tp in ts_positions:
            rel = tp - pos
            # Check for player entity IDs near this timestamp occurrence
            context_start = max(0, tp - 10)
            context_end = min(len(data), tp + 10)
            context_hex = data[context_start:context_end].hex()

            # Look for player eids near this timestamp
            nearby_players = []
            for check_off in range(-8, 8):
                check_pos = tp + check_off
                if 0 <= check_pos and check_pos + 2 <= len(data):
                    check_eid = struct.unpack_from(">H", data, check_pos)[0]
                    if check_eid in eid_to_name:
                        pname = eid_to_name[check_eid]
                        nearby_players.append((check_off, pname))

            players_str = ", ".join(f"{p[1]}@{p[0]:+d}" for p in nearby_players)

            # Get the 3-byte header before this record region
            header_candidates = []
            for hoff in [4, 5, 7, 9]:
                hpos = tp - hoff
                if hpos >= 0:
                    header_candidates.append(f"@-{hoff}:0x{data[hpos:hpos+3].hex()}")

            print(f"  ts at {rel:+4d} (0x{tp:06X}): players=[{players_str}] headers=[{', '.join(header_candidates[:3])}]")

            # Track kill/assist candidates
            for _, pname in nearby_players:
                if pname in enemy_team:
                    kill_by_timestamp[pname] += 1
        print()

print()
print("=" * 70)
print("Enemy appearances near death timestamps (potential killers/assisters):")
print("=" * 70)
for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    count = kill_by_timestamp.get(name, 0)
    tk = truth_kills[name]
    ta = truth_assists[name]
    print(f"  {name:8s}: near-death={count:3d}  truth_K={tk}  truth_A={ta}  truth_K+A={tk+ta}")

print("\nDONE")
