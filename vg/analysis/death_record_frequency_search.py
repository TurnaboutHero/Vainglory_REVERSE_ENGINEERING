"""
Death Record Frequency Search
==============================
New approach: Instead of analyzing individual events, look for a RECORD TYPE
where the total count per player MATCHES their death count.

Truth deaths: Phinn=0, Yates=4, Caine=4, Karas=3, Petal=2, Baron=2
If we find a record pattern where Phinn has 0 occurrences, Yates has 4, etc.,
that pattern IS the death record.

Search space: All [type sub action] 3-byte patterns where:
- The payload contains a player entity ID at some offset
- The count per player correlates with deaths
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
truth_deaths = {"Phinn": 0, "Yates": 4, "Caine": 4, "Karas": 3, "Petal": 2, "Baron": 2}
truth_kills = {"Phinn": 2, "Yates": 1, "Caine": 3, "Karas": 0, "Petal": 3, "Baron": 6}


def load_all_frames():
    """Load all frames concatenated."""
    all_data = bytearray()
    frame_count = 0
    for i in range(200):
        path = os.path.join(CACHE_DIR, f"{PREFIX}.{i}.vgr")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            all_data.extend(f.read())
        frame_count += 1
    return bytes(all_data), frame_count


print("Loading all frames...")
all_data, frame_count = load_all_frames()
print(f"Loaded {frame_count} frames, {len(all_data)} bytes total")
print()

# Strategy: For each 3-byte pattern [A B C], search the entire data.
# For each occurrence, check if a player entity ID appears at specific
# payload offsets (0, 2, 4, 6 bytes after the pattern).
# Count per player. Check if counts match truth_deaths or truth_kills.

# First, find all unique 3-byte patterns that have a player entity within 20 bytes
print("Phase 1: Scanning for 3-byte patterns with player entities nearby...")
print()

# Build index of all player entity positions
player_positions = defaultdict(list)  # name -> list of positions
for eid, name in entities.items():
    eid_be = struct.pack(">H", eid)
    pos = 0
    while True:
        pos = all_data.find(eid_be, pos)
        if pos == -1:
            break
        player_positions[name].append(pos)
        pos += 1

for name, positions in sorted(player_positions.items()):
    print(f"  {name}: {len(positions)} entity ID occurrences")
print()

# For each player entity occurrence, look at the 3-byte patterns at offsets
# -20 to -3 before the entity ID position. These would be [type sub action]
# patterns where the entity ID is in the payload.

pattern_player_counts = defaultdict(Counter)  # (pattern, offset) -> player -> count

for name, positions in player_positions.items():
    for pos in positions:
        # Look at 3-byte patterns before this position
        for offset in [3, 5, 7, 9, 11, 13, 15]:  # distance from pattern start to entity
            pat_pos = pos - offset
            if pat_pos < 0:
                continue
            pattern = all_data[pat_pos:pat_pos+3]
            if len(pattern) == 3:
                key = (pattern.hex(), offset)
                pattern_player_counts[key][name] += 1

print(f"Found {len(pattern_player_counts)} unique (pattern, offset) combinations")
print()

# Phase 2: Check which (pattern, offset) combinations match death or kill counts
print("Phase 2: Checking for death/kill count matches...")
print()

death_matches = []
kill_matches = []

for (pat_hex, offset), counts in pattern_player_counts.items():
    # Get counts for all players
    player_counts = {name: counts.get(name, 0) for name in entities.values()}

    # Check death match: exact match
    if player_counts == truth_deaths:
        death_matches.append((pat_hex, offset, player_counts))

    # Check kill match: exact match
    if player_counts == truth_kills:
        kill_matches.append((pat_hex, offset, player_counts))

    # Check proportional death match (scaled)
    # Maybe counts are N*deaths for some N
    if all(player_counts.get(name, 0) > 0 or truth_deaths[name] == 0
           for name in truth_deaths):
        if truth_deaths["Phinn"] == 0 and player_counts.get("Phinn", 0) == 0:
            # Phinn has 0, check if others are proportional
            ratios = set()
            valid = True
            for name in ["Yates", "Caine", "Karas", "Petal", "Baron"]:
                td = truth_deaths[name]
                pc = player_counts.get(name, 0)
                if td == 0:
                    if pc != 0:
                        valid = False
                        break
                elif pc % td != 0:
                    valid = False
                    break
                else:
                    ratios.add(pc // td)

            if valid and len(ratios) == 1 and ratios.pop() > 0:
                ratio = player_counts["Yates"] // truth_deaths["Yates"]
                if ratio <= 20 and ratio != 1:  # Skip exact match (already captured)
                    death_matches.append((pat_hex, offset, player_counts,
                                         f"proportional x{ratio}"))

print(f"  EXACT death matches: {sum(1 for m in death_matches if len(m) == 3)}")
print(f"  Proportional death matches: {sum(1 for m in death_matches if len(m) == 4)}")
print(f"  EXACT kill matches: {len(kill_matches)}")
print()

# Show matches
if death_matches:
    print("DEATH MATCHES:")
    for match in death_matches[:20]:
        pat_hex, offset, counts = match[0], match[1], match[2]
        extra = match[3] if len(match) > 3 else "EXACT"
        print(f"  Pattern=0x{pat_hex} offset={offset} [{extra}]")
        for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
            print(f"    {name:8s}: count={counts.get(name, 0):4d} truth_D={truth_deaths[name]}")
        print()

if kill_matches:
    print("KILL MATCHES:")
    for match in kill_matches[:20]:
        pat_hex, offset, counts = match[0], match[1], match[2]
        print(f"  Pattern=0x{pat_hex} offset={offset}")
        for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
            print(f"    {name:8s}: count={counts.get(name, 0):4d} truth_K={truth_kills[name]}")
        print()

if not death_matches and not kill_matches:
    print("  No exact or proportional matches found.")
    print()

    # Phase 3: Find CLOSEST matches using correlation
    print("Phase 3: Finding closest matches by correlation...")
    print()

    death_vec = [truth_deaths[name] for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]

    best_matches = []
    for (pat_hex, offset), counts in pattern_player_counts.items():
        count_vec = [counts.get(name, 0) for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]

        # Skip if all zeros or all same
        if sum(count_vec) == 0 or len(set(count_vec)) == 1:
            continue

        # Pearson correlation
        n = 6
        sum_x = sum(death_vec)
        sum_y = sum(count_vec)
        sum_xy = sum(a*b for a, b in zip(death_vec, count_vec))
        sum_x2 = sum(a*a for a in death_vec)
        sum_y2 = sum(b*b for b in count_vec)

        numer = n * sum_xy - sum_x * sum_y
        denom_sq = (n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2)
        if denom_sq <= 0:
            continue
        corr = numer / (denom_sq ** 0.5)

        # Also compute MAE (mean absolute error) normalized
        total = sum(count_vec)
        if total == 0:
            continue
        scale = sum(death_vec) / total
        scaled = [c * scale for c in count_vec]
        mae = sum(abs(a - b) for a, b in zip(death_vec, scaled)) / n

        best_matches.append((corr, mae, pat_hex, offset, count_vec))

    # Sort by correlation (descending)
    best_matches.sort(key=lambda x: -x[0])

    print("  Top 15 correlating patterns with DEATH counts:")
    print(f"  {'Pattern':12s} {'Off':>3s} {'Corr':>6s} {'MAE':>6s} {'Ph':>4s} {'Ya':>4s} {'Ca':>4s} {'Ka':>4s} {'Pe':>4s} {'Ba':>4s}")
    for corr, mae, pat_hex, offset, counts in best_matches[:15]:
        print(f"  0x{pat_hex:8s} {offset:3d} {corr:6.3f} {mae:6.3f} "
              f"{counts[0]:4d} {counts[1]:4d} {counts[2]:4d} {counts[3]:4d} {counts[4]:4d} {counts[5]:4d}")

    print(f"\n  Truth deaths:                          "
          f"{'':>19s} {truth_deaths['Phinn']:4d} {truth_deaths['Yates']:4d} "
          f"{truth_deaths['Caine']:4d} {truth_deaths['Karas']:4d} "
          f"{truth_deaths['Petal']:4d} {truth_deaths['Baron']:4d}")

    # Also check for KILL correlation
    kill_vec = [truth_kills[name] for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]

    kill_matches_corr = []
    for (pat_hex, offset), counts in pattern_player_counts.items():
        count_vec = [counts.get(name, 0) for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]
        if sum(count_vec) == 0 or len(set(count_vec)) == 1:
            continue

        n = 6
        sum_x = sum(kill_vec)
        sum_y = sum(count_vec)
        sum_xy = sum(a*b for a, b in zip(kill_vec, count_vec))
        sum_x2 = sum(a*a for a in kill_vec)
        sum_y2 = sum(b*b for b in count_vec)

        numer = n * sum_xy - sum_x * sum_y
        denom_sq = (n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2)
        if denom_sq <= 0:
            continue
        corr = numer / (denom_sq ** 0.5)
        kill_matches_corr.append((corr, pat_hex, offset, count_vec))

    kill_matches_corr.sort(key=lambda x: -x[0])

    print(f"\n  Top 15 correlating patterns with KILL counts:")
    print(f"  {'Pattern':12s} {'Off':>3s} {'Corr':>6s} {'Ph':>4s} {'Ya':>4s} {'Ca':>4s} {'Ka':>4s} {'Pe':>4s} {'Ba':>4s}")
    for corr, pat_hex, offset, counts in kill_matches_corr[:15]:
        print(f"  0x{pat_hex:8s} {offset:3d} {corr:6.3f} "
              f"{counts[0]:4d} {counts[1]:4d} {counts[2]:4d} {counts[3]:4d} {counts[4]:4d} {counts[5]:4d}")

    print(f"\n  Truth kills:                           "
          f"{'':>12s} {truth_kills['Phinn']:4d} {truth_kills['Yates']:4d} "
          f"{truth_kills['Caine']:4d} {truth_kills['Karas']:4d} "
          f"{truth_kills['Petal']:4d} {truth_kills['Baron']:4d}")

print("\nDONE")
