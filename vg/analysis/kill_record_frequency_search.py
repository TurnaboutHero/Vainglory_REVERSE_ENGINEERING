"""
Kill Record Frequency Search
=============================
Same brute-force approach that found death records [08 04 31].
Search ALL (pattern, offset) combos for frequency matching truth_kills.

Truth kills: Phinn=2, Yates=1, Caine=3, Karas=0, Petal=3, Baron=6
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
truth_kills = {"Phinn": 2, "Yates": 1, "Caine": 3, "Karas": 0, "Petal": 3, "Baron": 6}
truth_deaths = {"Phinn": 0, "Yates": 4, "Caine": 4, "Karas": 3, "Petal": 2, "Baron": 2}
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

# Build player entity position index
player_positions = defaultdict(list)
for eid, name in entities.items():
    eid_be = struct.pack(">H", eid)
    pos = 0
    while True:
        pos = all_data.find(eid_be, pos)
        if pos == -1:
            break
        player_positions[name].append(pos)
        pos += 1

# Build (pattern, offset) -> player -> count
pattern_player_counts = defaultdict(Counter)
for name, positions in player_positions.items():
    for pos in positions:
        for offset in [3, 5, 7, 9, 11, 13, 15]:
            pat_pos = pos - offset
            if pat_pos < 0:
                continue
            pattern = all_data[pat_pos:pat_pos+3]
            if len(pattern) == 3:
                key = (pattern.hex(), offset)
                pattern_player_counts[key][name] += 1

print(f"Found {len(pattern_player_counts)} unique (pattern, offset) combinations")
print()

# Search for EXACT matches with kills, deaths, assists
targets = {
    "KILLS": truth_kills,
    "DEATHS": truth_deaths,
    "ASSISTS": truth_assists,
}

for target_name, truth_values in targets.items():
    print(f"{'='*70}")
    print(f"Searching for {target_name} matches...")
    print(f"  Truth: {truth_values}")
    print(f"{'='*70}")
    print()

    exact_matches = []
    proportional_matches = []

    for (pat_hex, offset), counts in pattern_player_counts.items():
        player_counts = {name: counts.get(name, 0) for name in entities.values()}

        # Exact match
        if player_counts == truth_values:
            exact_matches.append((pat_hex, offset, player_counts))

        # Proportional match (all counts are N*truth for some N)
        zero_players = [n for n, v in truth_values.items() if v == 0]
        nonzero_players = [n for n, v in truth_values.items() if v > 0]

        if all(player_counts.get(n, 0) == 0 for n in zero_players):
            ratios = set()
            valid = True
            for name in nonzero_players:
                tv = truth_values[name]
                pc = player_counts.get(name, 0)
                if pc == 0 or pc % tv != 0:
                    valid = False
                    break
                ratios.add(pc // tv)

            if valid and len(ratios) == 1:
                ratio = ratios.pop()
                if 2 <= ratio <= 20:
                    proportional_matches.append((pat_hex, offset, player_counts, ratio))

    print(f"  EXACT matches: {len(exact_matches)}")
    print(f"  Proportional matches: {len(proportional_matches)}")
    print()

    if exact_matches:
        for pat_hex, offset, counts in exact_matches[:10]:
            print(f"  EXACT: Pattern=0x{pat_hex} offset={offset}")
            for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
                print(f"    {name:8s}: count={counts.get(name, 0):4d} truth={truth_values[name]}")
            print()

    if proportional_matches:
        for pat_hex, offset, counts, ratio in proportional_matches[:5]:
            print(f"  PROPORTIONAL (x{ratio}): Pattern=0x{pat_hex} offset={offset}")
            for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
                print(f"    {name:8s}: count={counts.get(name, 0):4d} truth={truth_values[name]} (x{ratio}={truth_values[name]*ratio})")
            print()

    # Also show top correlation matches
    truth_vec = [truth_values[n] for n in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]

    corr_matches = []
    for (pat_hex, offset), counts in pattern_player_counts.items():
        count_vec = [counts.get(n, 0) for n in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]]
        if sum(count_vec) == 0 or len(set(count_vec)) == 1:
            continue

        n = 6
        sx = sum(truth_vec)
        sy = sum(count_vec)
        sxy = sum(a*b for a, b in zip(truth_vec, count_vec))
        sx2 = sum(a*a for a in truth_vec)
        sy2 = sum(b*b for b in count_vec)

        numer = n * sxy - sx * sy
        denom_sq = (n * sx2 - sx**2) * (n * sy2 - sy**2)
        if denom_sq <= 0:
            continue
        corr = numer / (denom_sq ** 0.5)
        corr_matches.append((corr, pat_hex, offset, count_vec))

    corr_matches.sort(key=lambda x: -x[0])

    print(f"  Top 10 correlating patterns:")
    print(f"  {'Pattern':12s} {'Off':>3s} {'Corr':>6s} {'Ph':>4s} {'Ya':>4s} {'Ca':>4s} {'Ka':>4s} {'Pe':>4s} {'Ba':>4s}")
    for corr, pat_hex, offset, counts in corr_matches[:10]:
        print(f"  0x{pat_hex:8s} {offset:3d} {corr:6.3f} "
              f"{counts[0]:4d} {counts[1]:4d} {counts[2]:4d} {counts[3]:4d} {counts[4]:4d} {counts[5]:4d}")
    print(f"  {'Truth:':12s} {'':>3s} {'':>6s} "
          f"{truth_vec[0]:4d} {truth_vec[1]:4d} {truth_vec[2]:4d} {truth_vec[3]:4d} {truth_vec[4]:4d} {truth_vec[5]:4d}")
    print()

print("DONE")
