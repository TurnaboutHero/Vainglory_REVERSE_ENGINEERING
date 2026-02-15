"""
Death Record [08 04 31] Verification & Deep Analysis
=====================================================
BREAKTHROUGH: Pattern [08 04 31] with player entity at offset +5
matches death counts EXACTLY for all 6 players.

This script:
1. Shows full detail of each [08 04 31] death record
2. Checks timestamp alignment with BA events
3. Examines surrounding bytes for killer/assister info
4. Cross-validates on a SECOND replay
"""
import os
import struct
import json
from collections import Counter, defaultdict

# =========================================================================
# Replay 1: 21.11.04 (primary)
# =========================================================================
CACHE_DIR_1 = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
PREFIX_1 = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

entities_1 = {
    0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
    0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
}
truth_kda_1 = {
    "Phinn":  {"K": 2, "D": 0, "A": 6},
    "Yates":  {"K": 1, "D": 4, "A": 4},
    "Caine":  {"K": 3, "D": 4, "A": 3},
    "Petal":  {"K": 3, "D": 2, "A": 3},
    "Karas":  {"K": 0, "D": 3, "A": 2},
    "Baron":  {"K": 6, "D": 2, "A": 6},
}

left_team_1 = {"Phinn", "Petal", "Baron"}
right_team_1 = {"Yates", "Caine", "Karas"}

ba_timestamps_1 = [40.97, 67.37, 91.20, 113.97, 179.71, 229.85, 252.86,
                   303.57, 374.41, 406.04, 419.57, 461.97, 533.34, 559.51,
                   600.39, 653.92, 734.82, 854.24, 916.21]


def load_frame(cache_dir, prefix, frame_idx):
    path = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def find_death_records(data, entities_map):
    """Find all [08 04 31] records with player entity at offset +5."""
    pattern = bytes([0x08, 0x04, 0x31])
    results = []
    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break

        # Player entity at offset +5 from pattern start (offset +2 from pattern end)
        eid_pos = pos + 5
        if eid_pos + 2 <= len(data):
            eid = struct.unpack_from(">H", data, eid_pos)[0]
            name = entities_map.get(eid)

            if name:
                # Try to extract timestamp (usually 7 bytes before the pattern)
                ts = None
                ts_pos = pos - 7
                if ts_pos >= 0 and data[ts_pos+4:ts_pos+7] == b'\x00\x00\x00':
                    ts_val = struct.unpack_from(">f", data, ts_pos)[0]
                    if 0 <= ts_val < 1200:
                        ts = ts_val

                # Extract extended payload for analysis
                payload_start = pos
                payload = data[payload_start:payload_start+40]

                # Look for other player entities in the surrounding area
                nearby_players = []
                for check_offset in range(3, 30, 2):
                    if pos + check_offset + 2 <= len(data):
                        check_eid = struct.unpack_from(">H", data, pos + check_offset)[0]
                        check_name = entities_map.get(check_eid)
                        if check_name and check_name != name:
                            nearby_players.append((check_offset, check_name))

                results.append({
                    "pos": pos,
                    "ts": ts,
                    "victim": name,
                    "eid": eid,
                    "payload_hex": payload.hex(),
                    "nearby_players": nearby_players,
                })

        pos += 1
    return results


# =========================================================================
# PHASE 1: Detailed analysis of Replay 1
# =========================================================================
print("=" * 70)
print("PHASE 1: Detailed [08 04 31] death records in 21.11.04")
print("=" * 70)
print()

all_deaths = []
for frame_idx in range(200):
    data = load_frame(CACHE_DIR_1, PREFIX_1, frame_idx)
    if data is None:
        continue

    records = find_death_records(data, entities_1)
    for r in records:
        r["frame"] = frame_idx
        all_deaths.append(r)

# Count per player
death_counts = Counter()
for d in all_deaths:
    death_counts[d["victim"]] += 1

print(f"Total [08 04 31] death records: {len(all_deaths)}")
print()
print("Death counts vs truth:")
all_match = True
for name in ["Phinn", "Yates", "Caine", "Karas", "Petal", "Baron"]:
    count = death_counts.get(name, 0)
    truth = truth_kda_1[name]["D"]
    match = "OK" if count == truth else "MISMATCH"
    if count != truth:
        all_match = False
    print(f"  {name:8s}: detected={count}, truth={truth} [{match}]")
print(f"\n  ALL MATCH: {'YES' if all_match else 'NO'}")
print()

# Show each death record with details
print("Detailed death records:")
print()
for i, d in enumerate(all_deaths):
    # Find nearest BA event
    nearest_ba = None
    min_dt = float('inf')
    if d["ts"] is not None:
        for ba_idx, ba_ts in enumerate(ba_timestamps_1):
            dt = abs(d["ts"] - ba_ts)
            if dt < min_dt:
                min_dt = dt
                nearest_ba = ba_idx + 1

    ba_str = f" (nearest BA#{nearest_ba}, dt={min_dt:.2f}s)" if nearest_ba and min_dt < 5.0 else ""

    print(f"  Death #{i+1}: frame={d['frame']:3d} ts={d['ts'] or '???':>8} "
          f"VICTIM={d['victim']:8s}{ba_str}")

    # Show payload bytes
    payload = bytes.fromhex(d["payload_hex"])
    # Format: show first 30 bytes with annotations
    hex_str = " ".join(f"{b:02X}" for b in payload[:30])
    print(f"    Payload: {hex_str}")
    print(f"    Bytes [0:3]=[08 04 31], [3:5]={payload[3:5].hex()}, "
          f"[5:7]=VICTIM({payload[5:7].hex()}), [7:]={payload[7:12].hex()}")

    # Nearby players
    if d["nearby_players"]:
        for offset, pname in d["nearby_players"]:
            print(f"    Nearby player at +{offset}: {pname}")
    print()


# =========================================================================
# PHASE 2: Look for KILLER info in surrounding records
# =========================================================================
print("=" * 70)
print("PHASE 2: Searching for killer information near death records")
print("=" * 70)
print()

# For each death, look at ALL records within +/- 1 second
for d in all_deaths:
    if d["ts"] is None:
        continue

    frame_data = load_frame(CACHE_DIR_1, PREFIX_1, d["frame"])
    if frame_data is None:
        continue

    # Search for other [08 04 XX] patterns near the same timestamp
    nearby_records = []
    for action in range(0x100):
        pattern = bytes([0x08, 0x04, action])
        pos = 0
        while True:
            pos = frame_data.find(pattern, pos)
            if pos == -1:
                break
            ts_pos = pos - 7
            if ts_pos >= 0 and frame_data[ts_pos+4:ts_pos+7] == b'\x00\x00\x00':
                ts = struct.unpack_from(">f", frame_data, ts_pos)[0]
                if abs(ts - d["ts"]) < 0.5 and 0 <= ts < 1200:
                    payload = frame_data[pos:pos+20]
                    # Check for player entities
                    players_found = []
                    for off in [3, 5, 7, 9]:
                        if pos + off + 2 <= len(frame_data):
                            eid = struct.unpack_from(">H", frame_data, pos + off)[0]
                            name = entities_1.get(eid)
                            if name:
                                players_found.append((off, name))

                    if players_found or action == 0x31:
                        nearby_records.append({
                            "action": action,
                            "ts": ts,
                            "dt": ts - d["ts"],
                            "players": players_found,
                            "payload": payload.hex(),
                        })
            pos += 1

    victim = d["victim"]
    victim_team = left_team_1 if victim in left_team_1 else right_team_1
    enemy_team = right_team_1 if victim in left_team_1 else left_team_1

    print(f"  Death: {victim} at t={d['ts']:.2f}")
    print(f"    Nearby [08 04 XX] records (within 0.5s):")

    for nr in sorted(nearby_records, key=lambda x: x["ts"]):
        players_str = ", ".join(f"+{off}:{n}" for off, n in nr["players"])
        marker = " <<<DEATH" if nr["action"] == 0x31 else ""
        enemy_found = [n for _, n in nr["players"] if n in enemy_team]
        enemy_str = f" [ENEMY: {enemy_found}]" if enemy_found else ""
        print(f"      [08 04 {nr['action']:02X}] dt={nr['dt']:+.3f}s players=[{players_str}]{enemy_str}{marker}")
    print()


# =========================================================================
# PHASE 3: Cross-validation on second replay
# =========================================================================
print("=" * 70)
print("PHASE 3: Cross-replay validation")
print("=" * 70)
print()

# Load tournament truth
truth_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json"
with open(truth_path, "r") as f:
    tournament_truth = json.load(f)

# Try first tournament replay
validated = 0
total_replays = 0

for match in tournament_truth["matches"][:5]:
    replay_file = match["replay_file"]
    if not os.path.exists(replay_file):
        continue

    # For tournament replays, we need to find the cache directory
    # The replay file is the .0.vgr file
    replay_dir = os.path.dirname(replay_file)
    replay_name = os.path.basename(replay_file)

    # Extract prefix from filename (everything before .0.vgr)
    if replay_name.endswith(".0.vgr"):
        prefix = replay_name[:-6]
    else:
        continue

    # Check if cache exists or if frames are directly in the directory
    cache_dir = os.path.join(replay_dir, "cache")
    if not os.path.exists(cache_dir):
        cache_dir = replay_dir

    # Try to load frame 0 to get entity IDs
    frame0 = load_frame(cache_dir, prefix, 0)
    if frame0 is None:
        # Try without cache subfolder
        frame0_path = os.path.join(replay_dir, f"{prefix}.0.vgr")
        if os.path.exists(frame0_path):
            with open(frame0_path, "rb") as f:
                frame0 = f.read()
        else:
            continue

    total_replays += 1
    match_name = match.get("replay_name", "unknown")[:40]
    players = match["players"]

    print(f"Replay: {match_name}")

    # Get player entity IDs from player blocks (DA 03 EE markers)
    replay_entities = {}
    marker = bytes([0xDA, 0x03, 0xEE])
    mpos = 0
    block_idx = 0
    while True:
        mpos = frame0.find(marker, mpos)
        if mpos == -1:
            break
        # Entity ID at +0xA5 from marker
        if mpos + 0xA5 + 2 <= len(frame0):
            eid = struct.unpack_from("<H", frame0, mpos + 0xA5)[0]
            # Hero ID at +0xA9
            hero_id = struct.unpack_from("<H", frame0, mpos + 0xA9)[0]
            replay_entities[eid] = f"Player_{block_idx}"
            block_idx += 1
        mpos += 1

    if not replay_entities:
        # Try E0 03 EE marker
        marker2 = bytes([0xE0, 0x03, 0xEE])
        mpos = 0
        block_idx = 0
        while True:
            mpos = frame0.find(marker2, mpos)
            if mpos == -1:
                break
            if mpos + 0xA5 + 2 <= len(frame0):
                eid = struct.unpack_from("<H", frame0, mpos + 0xA5)[0]
                replay_entities[eid] = f"Player_{block_idx}"
                block_idx += 1
            mpos += 1

    if not replay_entities:
        print(f"  Could not find player entities, skipping")
        print()
        continue

    # Also build BE entity map (the protocol uses Big Endian)
    replay_entities_be = {}
    for eid, name in replay_entities.items():
        # Convert LE entity ID to BE for searching
        eid_be = ((eid & 0xFF) << 8) | ((eid >> 8) & 0xFF)
        replay_entities_be[eid_be] = name
        replay_entities_be[eid] = name  # Keep both just in case

    print(f"  Found {len(replay_entities)} player entities: {list(replay_entities.values())}")
    print(f"  Entity IDs (LE): {[hex(e) for e in replay_entities.keys()]}")

    # Count [08 04 31] death records across all frames
    frame_deaths = Counter()
    for frame_idx in range(300):
        data = load_frame(cache_dir, prefix, frame_idx)
        if data is None:
            if frame_idx > 10:
                break
            continue

        # Find [08 04 31] with player entity at +5
        pat = bytes([0x08, 0x04, 0x31])
        spos = 0
        while True:
            spos = data.find(pat, spos)
            if spos == -1:
                break
            if spos + 7 <= len(data):
                eid = struct.unpack_from(">H", data, spos + 5)[0]
                name = replay_entities_be.get(eid)
                if name:
                    frame_deaths[name] += 1
            spos += 1

    # Get truth deaths
    truth_deaths_replay = {}
    for pname, pdata in players.items():
        # Map to player index
        truth_deaths_replay[pname] = pdata["deaths"]

    total_detected = sum(frame_deaths.values())
    total_truth = sum(pdata["deaths"] for pdata in players.values())

    print(f"  Detected deaths: {total_detected}, Truth total: {total_truth}")
    print(f"  Per player: {dict(frame_deaths)}")
    print(f"  Truth deaths: ", end="")
    for pname, pdata in players.items():
        print(f"{pname[-8:]}={pdata['deaths']} ", end="")
    print()

    if total_detected == total_truth:
        validated += 1
        print(f"  TOTAL MATCH!")
    else:
        print(f"  MISMATCH (detected={total_detected} vs truth={total_truth})")
    print()

print(f"\nCross-validation: {validated}/{total_replays} replays matched")

# =========================================================================
# Save results
# =========================================================================
output = {
    "version": "death_record_discovery",
    "description": "BREAKTHROUGH: [08 04 31] pattern with player entity at +5 = death record",
    "pattern": {
        "bytes": "08 04 31",
        "entity_offset": 5,
        "entity_encoding": "Big Endian uint16",
    },
    "replay_1_accuracy": {
        "replay": "21.11.04",
        "match": all_match,
        "deaths": {name: {"detected": death_counts.get(name, 0),
                         "truth": truth_kda_1[name]["D"]}
                  for name in entities_1.values()},
    },
    "cross_validation": {
        "replays_tested": total_replays,
        "replays_matched": validated,
    },
    "death_records": [
        {"victim": d["victim"], "frame": d["frame"], "ts": d["ts"]}
        for d in all_deaths
    ],
}

output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/death_record_discovery.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nResults saved to {output_path}")
print("\nANALYSIS COMPLETE")
