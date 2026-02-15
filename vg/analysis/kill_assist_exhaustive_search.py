"""
Kill/Assist Exhaustive Pattern Search
======================================
Wider search than kill_record_frequency_search.py:
1. Offsets 1-30 (not just 3,5,7,9,11,13,15)
2. Both BE and LE entity IDs
3. 2-byte, 3-byte, and 4-byte patterns
4. Entity ID AFTER pattern (positive offsets)
"""
import os
import struct
from collections import Counter, defaultdict

CACHE_DIR = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

# Both BE and LE entity IDs
entities_be = {
    0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
    0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
}
entities_le = {
    0xDC05: "Phinn", 0xDD05: "Yates", 0xDE05: "Caine",
    0xDF05: "Petal", 0xE005: "Karas", 0xE105: "Baron",
}

truth_kills = {"Phinn": 2, "Yates": 1, "Caine": 3, "Karas": 0, "Petal": 3, "Baron": 6}
truth_assists = {"Phinn": 6, "Yates": 4, "Caine": 3, "Karas": 2, "Petal": 3, "Baron": 6}

print("Loading all frames...")
all_data = bytearray()
frame_count = 0
for i in range(200):
    path = os.path.join(CACHE_DIR, f"{PREFIX}.{i}.vgr")
    if not os.path.exists(path):
        continue
    with open(path, "rb") as f:
        all_data.extend(f.read())
    frame_count += 1
all_data = bytes(all_data)
print(f"Loaded {frame_count} frames, {len(all_data)} bytes")
print()

# Build entity position index for BOTH endianness
player_positions_be = defaultdict(list)
player_positions_le = defaultdict(list)

for eid, name in entities_be.items():
    eid_bytes = struct.pack(">H", eid)
    pos = 0
    while True:
        pos = all_data.find(eid_bytes, pos)
        if pos == -1:
            break
        player_positions_be[name].append(pos)
        pos += 1

for eid, name in entities_le.items():
    eid_bytes = struct.pack(">H", eid)  # Already in LE byte order
    pos = 0
    while True:
        pos = all_data.find(eid_bytes, pos)
        if pos == -1:
            break
        player_positions_le[name].append(pos)
        pos += 1

print(f"BE positions: {sum(len(v) for v in player_positions_be.values())} total")
print(f"LE positions: {sum(len(v) for v in player_positions_le.values())} total")
print()

targets = {
    "KILLS": truth_kills,
    "ASSISTS": truth_assists,
}

for endian_name, player_positions in [("BE", player_positions_be), ("LE", player_positions_le)]:
    for pat_len in [2, 3, 4]:
        for target_name, truth_values in targets.items():
            print(f"{'='*70}")
            print(f"Searching {target_name} | {endian_name} | pat_len={pat_len}")
            print(f"  Truth: {truth_values}")
            print(f"{'='*70}")

            # Build (pattern, offset) -> player -> count
            pattern_player_counts = defaultdict(Counter)
            for name, positions in player_positions.items():
                for pos in positions:
                    for offset in range(1, 31):
                        pat_pos = pos - offset
                        if pat_pos < 0:
                            continue
                        pattern = all_data[pat_pos:pat_pos+pat_len]
                        if len(pattern) == pat_len:
                            key = (pattern.hex(), offset)
                            pattern_player_counts[key][name] += 1

            # Search for exact matches
            exact_matches = []
            close_matches = []  # off by 1 total

            for (pat_hex, offset), counts in pattern_player_counts.items():
                player_counts = {name: counts.get(name, 0) for name in entities_be.values()}

                # Exact match
                if player_counts == truth_values:
                    exact_matches.append((pat_hex, offset, player_counts))

                # Close match (total difference <= 2, no single player off by more than 1)
                total_diff = sum(abs(player_counts[n] - truth_values[n]) for n in truth_values)
                max_single_diff = max(abs(player_counts[n] - truth_values[n]) for n in truth_values)
                if 0 < total_diff <= 2 and max_single_diff <= 1:
                    # Also check zero players are correct
                    zero_ok = all(player_counts[n] == 0 for n in truth_values if truth_values[n] == 0)
                    if zero_ok:
                        close_matches.append((pat_hex, offset, player_counts, total_diff))

            print(f"  EXACT matches: {len(exact_matches)}")
            print(f"  Close matches (off by <=2, max single <=1): {len(close_matches)}")

            if exact_matches:
                for pat_hex, offset, counts in exact_matches[:5]:
                    print(f"  EXACT: Pattern=0x{pat_hex} offset={offset}")
                    for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
                        print(f"    {name:8s}: {counts[name]:3d} truth={truth_values[name]}")

            if close_matches and not exact_matches:
                close_matches.sort(key=lambda x: x[3])
                for pat_hex, offset, counts, diff in close_matches[:5]:
                    print(f"  CLOSE (diff={diff}): Pattern=0x{pat_hex} offset={offset}")
                    for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
                        d = counts[name] - truth_values[name]
                        marker = "" if d == 0 else f" ({d:+d})"
                        print(f"    {name:8s}: {counts[name]:3d} truth={truth_values[name]}{marker}")
            print()

print("DONE")
