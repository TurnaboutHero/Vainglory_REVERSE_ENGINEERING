"""
Minion Kill Pattern Search - Brute Force Frequency Matching
============================================================
Search for 3-byte patterns where counting occurrences matches truth minion_kills.
This is the same technique that successfully found kill/death patterns.
"""
import os
import struct
import json
from collections import defaultdict
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

TRUTH_PATH = "vg/output/tournament_truth.json"

def find_player_entities(frame0_data):
    """Extract player entities from frame 0."""
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
                    "eid_le": eid_le,
                    "eid_be": eid_be,
                    "hero_id": hero_id,
                    "hero_name": hero_name,
                    "team": team_str,
                })
            pos += 1
    return players


def count_pattern_with_entity(all_frames_data, pattern, entity_offset, valid_eids):
    """
    Count occurrences of pattern where entity ID (BE) at offset matches valid_eids.

    Args:
        all_frames_data: concatenated bytes of all frames
        pattern: 3-byte pattern to search for
        entity_offset: offset from pattern start where 2-byte BE entity ID is
        valid_eids: set of valid entity IDs (Big Endian)

    Returns:
        dict: {eid: count}
    """
    counts = defaultdict(int)
    pos = 0

    while True:
        pos = all_frames_data.find(pattern, pos)
        if pos == -1:
            break

        eid_pos = pos + entity_offset
        if eid_pos + 2 <= len(all_frames_data):
            eid_be = struct.unpack_from(">H", all_frames_data, eid_pos)[0]
            if eid_be in valid_eids:
                counts[eid_be] += 1

        pos += 1

    return counts


def calculate_accuracy(detected_counts, truth_counts):
    """Calculate how many players have exact match."""
    perfect = 0
    total = len(truth_counts)

    for eid, truth_val in truth_counts.items():
        if detected_counts.get(eid, 0) == truth_val:
            perfect += 1

    return perfect, total, perfect / total if total > 0 else 0


print("[STAGE:begin:brute_force_search]")
print("=" * 80)
print("PHASE 2: Brute Force Pattern Search for Minion Kills")
print("=" * 80)

with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)

# Use matches 1-4 for search (they all had 100% accuracy with current method)
# Then validate on matches 5-8
search_matches = [0, 1, 2, 3]  # Match 1-4 (indices 0-3)

print("\nLoading search dataset (Matches 1-4)...")

search_data = []
for match_idx in search_matches:
    match = truth_data["matches"][match_idx]
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

    # Load frame 0 for entity IDs
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

    # Map entity IDs to truth data
    truth_players = match["players"]
    truth_by_hero = {pdata["hero_name"]: pdata for pname, pdata in truth_players.items()}

    truth_minion_kills = {}
    for p in players:
        if p["hero_name"] in truth_by_hero:
            mk = truth_by_hero[p["hero_name"]].get("minion_kills")
            if mk is not None:
                truth_minion_kills[p["eid_be"]] = mk

    valid_eids = set(truth_minion_kills.keys())

    # Load all frames and concatenate
    all_frames = []
    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and len(all_frames) > 0:
                break
            continue
        with open(fpath, "rb") as f:
            all_frames.append(f.read())

    concatenated = b''.join(all_frames)

    search_data.append({
        "match": match_idx + 1,
        "data": concatenated,
        "valid_eids": valid_eids,
        "truth": truth_minion_kills,
    })

    print(f"  Match {match_idx + 1}: {len(all_frames)} frames, {len(valid_eids)} players, {len(concatenated):,} bytes")

print(f"\n[DATA] Loaded {len(search_data)} matches for pattern search")

# Search for 3-byte patterns [XX 04 YY] with entity at various offsets
# This follows the common event structure we've seen
print("\n" + "=" * 80)
print("Searching for patterns [XX 04 YY] with entity ID at offsets +3 to +7...")
print("=" * 80)

best_patterns = []

# Try common second bytes first
for byte1 in [0x10, 0x18, 0x08, 0x0C, 0x14, 0x1C, 0x20]:
    for byte3 in range(0x00, 0x50):
        pattern = bytes([byte1, 0x04, byte3])

        # Try different entity offsets (common structure has [XX 04 YY] [00 00] [eid BE])
        for entity_offset in [3, 5, 7]:
            # Test on all search matches
            all_perfect = 0
            all_total = 0

            for match_data in search_data:
                counts = count_pattern_with_entity(
                    match_data["data"],
                    pattern,
                    entity_offset,
                    match_data["valid_eids"]
                )

                perfect, total, acc = calculate_accuracy(counts, match_data["truth"])
                all_perfect += perfect
                all_total += total

            overall_acc = all_perfect / all_total if all_total > 0 else 0

            # Keep patterns with >80% accuracy
            if overall_acc >= 0.80:
                best_patterns.append({
                    "pattern": pattern,
                    "offset": entity_offset,
                    "accuracy": overall_acc,
                    "perfect": all_perfect,
                    "total": all_total,
                })
                print(f"  Found: [{pattern.hex(' ')}] offset={entity_offset} -> {all_perfect}/{all_total} ({overall_acc*100:.1f}%)")

print(f"\n[STAT:patterns_found] {len(best_patterns)} patterns with >80% accuracy")

# Sort by accuracy
best_patterns.sort(key=lambda x: (-x["accuracy"], -x["perfect"]))

if best_patterns:
    print("\nTop 10 patterns:")
    for i, p in enumerate(best_patterns[:10], 1):
        print(f"  {i}. [{p['pattern'].hex(' ')}] offset={p['offset']} -> {p['perfect']}/{p['total']} ({p['accuracy']*100:.1f}%)")

print("\n[STAGE:status:success]")
print("[STAGE:end:brute_force_search]")

# Save results
os.makedirs(".omc/scientist", exist_ok=True)
with open(".omc/scientist/minion_pattern_search.json", "w") as f:
    json.dump({
        "search_matches": [m["match"] for m in search_data],
        "patterns_found": len(best_patterns),
        "top_patterns": [
            {
                "pattern": p["pattern"].hex(" "),
                "offset": p["offset"],
                "accuracy": p["accuracy"],
                "perfect": p["perfect"],
                "total": p["total"],
            }
            for p in best_patterns[:20]
        ]
    }, f, indent=2)

print("\n[FINDING] Pattern search results saved to .omc/scientist/minion_pattern_search.json")
