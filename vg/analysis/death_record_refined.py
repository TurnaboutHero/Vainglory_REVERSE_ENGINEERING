"""
Death Record [08 04 31] Refined Analysis
=========================================
Adds structural validation to reduce false positives:
- Bytes [3:5] must be 00 00
- Bytes [7:9] must be 00 00
- Bytes [9:13] must be valid game timestamp (float32 BE, 0-1200s)
- Entity ID must be BE (Big Endian only)

Also investigates:
- [08 04 24] records near deaths for KILLER identification
- The record immediately following [08 04 31] for additional info
"""
import os
import struct
import json
from collections import Counter, defaultdict

# =========================================================================
# Configuration
# =========================================================================
OUTPUT_DIR = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output"

# Replay configs
REPLAYS = {
    "21.11.04": {
        "cache_dir": "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache",
        "prefix": "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4",
        "entities": {
            0x05DC: "Phinn", 0x05DD: "Yates", 0x05DE: "Caine",
            0x05DF: "Petal", 0x05E0: "Karas", 0x05E1: "Baron",
        },
        "truth_kda": {
            "Phinn": {"K": 2, "D": 0, "A": 6},
            "Yates": {"K": 1, "D": 4, "A": 4},
            "Caine": {"K": 3, "D": 4, "A": 3},
            "Petal": {"K": 3, "D": 2, "A": 3},
            "Karas": {"K": 0, "D": 3, "A": 2},
            "Baron": {"K": 6, "D": 2, "A": 6},
        },
        "left_team": {"Phinn", "Petal", "Baron"},
        "right_team": {"Yates", "Caine", "Karas"},
    },
}


def load_frame(cache_dir, prefix, idx):
    path = os.path.join(cache_dir, f"{prefix}.{idx}.vgr")
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def find_death_records_strict(data, entities_map, frame_idx):
    """Find [08 04 31] records with strict structural validation."""
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

        # Structural validation
        b3_4 = data[pos+3:pos+5]
        b5_6_eid = struct.unpack_from(">H", data, pos+5)[0]
        b7_8 = data[pos+7:pos+9]
        b9_12_ts = struct.unpack_from(">f", data, pos+9)[0]

        # Check: bytes 3-4 must be 00 00
        if b3_4 != b'\x00\x00':
            pos += 1
            continue

        # Check: bytes 7-8 must be 00 00
        if b7_8 != b'\x00\x00':
            pos += 1
            continue

        # Check: timestamp must be valid game time
        if not (0 < b9_12_ts < 1200):
            pos += 1
            continue

        # Check: entity must be a known player
        name = entities_map.get(b5_6_eid)
        if not name:
            pos += 1
            continue

        # Extract the NEXT record after this one (starts at pos+16 typically)
        next_record = None
        next_pos = pos + 13  # After the 00 00 00 padding
        while next_pos < min(pos + 20, len(data)):
            if data[next_pos] == 0x00:
                next_pos += 1
            else:
                break

        if next_pos + 7 <= len(data):
            nr_type = data[next_pos:next_pos+3]
            nr_payload = data[next_pos+3:next_pos+20]
            nr_players = []
            for off in [2, 4]:
                if next_pos + 3 + off + 2 <= len(data):
                    nr_eid = struct.unpack_from(">H", data, next_pos + 3 + off)[0]
                    nr_name = entities_map.get(nr_eid)
                    if nr_name:
                        nr_players.append((off, nr_name))
            next_record = {
                "type_hex": nr_type.hex(),
                "players": nr_players,
            }

        results.append({
            "pos": pos,
            "frame": frame_idx,
            "ts": b9_12_ts,
            "victim": name,
            "eid": b5_6_eid,
            "next_record": next_record,
        })

        pos += 1
    return results


def find_0824_records(data, entities_map, target_ts, tolerance=1.0):
    """Find [08 04 24] records near a timestamp."""
    pattern = bytes([0x08, 0x04, 0x24])
    results = []
    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break

        if pos + 13 > len(data):
            pos += 1
            continue

        # Check structural validity (same as 0831)
        b3_4 = data[pos+3:pos+5]
        b5_6_eid = struct.unpack_from(">H", data, pos+5)[0]

        if b3_4 == b'\x00\x00':
            name = entities_map.get(b5_6_eid)
            if name:
                # Try to get timestamp
                ts_pos = pos - 7
                ts = None
                if ts_pos >= 0 and data[ts_pos+4:ts_pos+7] == b'\x00\x00\x00':
                    ts_val = struct.unpack_from(">f", data, ts_pos)[0]
                    if 0 <= ts_val < 1200 and abs(ts_val - target_ts) < tolerance:
                        ts = ts_val

                # Also check embedded timestamp at pos+9
                if ts is None:
                    b7_8 = data[pos+7:pos+9]
                    if b7_8 == b'\x00\x00':
                        ts_emb = struct.unpack_from(">f", data, pos+9)[0]
                        if 0 <= ts_emb < 1200 and abs(ts_emb - target_ts) < tolerance:
                            ts = ts_emb

                if ts is not None:
                    results.append({
                        "ts": ts,
                        "dt": ts - target_ts,
                        "player": name,
                    })

        pos += 1
    return results


# =========================================================================
# MAIN ANALYSIS
# =========================================================================
for replay_name, config in REPLAYS.items():
    print("=" * 70)
    print(f"Replay: {replay_name}")
    print("=" * 70)
    print()

    entities = config["entities"]
    truth = config["truth_kda"]
    left = config["left_team"]
    right = config["right_team"]

    # Collect all death records
    all_deaths = []
    for frame_idx in range(200):
        data = load_frame(config["cache_dir"], config["prefix"], frame_idx)
        if data is None:
            continue
        records = find_death_records_strict(data, entities, frame_idx)
        all_deaths.extend(records)

    # Verify death counts
    death_counts = Counter(d["victim"] for d in all_deaths)
    print(f"Total deaths detected: {len(all_deaths)}")
    print()
    print("Death verification:")
    all_match = True
    for name in sorted(entities.values()):
        detected = death_counts.get(name, 0)
        truth_d = truth[name]["D"]
        ok = "OK" if detected == truth_d else "MISS"
        if detected != truth_d:
            all_match = False
        print(f"  {name:8s}: detected={detected}, truth={truth_d} [{ok}]")
    print(f"  ALL MATCH: {'YES' if all_match else 'NO'}")
    print()

    # For each death, find killer candidates from [08 04 24] and next-record
    print("Death events with killer analysis:")
    print()

    kill_counts = Counter()
    assist_counts = Counter()

    for i, d in enumerate(all_deaths):
        victim = d["victim"]
        victim_team = left if victim in left else right
        enemy_team = right if victim in left else left

        # Get [08 04 24] records near this death
        frame_data = load_frame(config["cache_dir"], config["prefix"], d["frame"])
        recs_0824 = find_0824_records(frame_data, entities, d["ts"], tolerance=1.0) if frame_data else []

        # Enemy players from [08 04 24]
        enemy_0824 = [r for r in recs_0824 if r["player"] in enemy_team]
        friendly_0824 = [r for r in recs_0824 if r["player"] in victim_team and r["player"] != victim]

        # Next record player
        next_player = None
        next_type = None
        if d["next_record"]:
            nr = d["next_record"]
            next_type = nr["type_hex"]
            for off, pname in nr["players"]:
                if pname != victim:
                    next_player = pname
                    break

        # Determine killer: enemy player closest to death time in [08 04 24]
        killer = None
        if enemy_0824:
            enemy_0824.sort(key=lambda r: abs(r["dt"]))
            killer = enemy_0824[0]["player"]

        # If no killer from 0824, use next record player if enemy
        if not killer and next_player and next_player in enemy_team:
            killer = next_player

        # Assisters: other enemy players present
        assisters = set()
        for r in enemy_0824:
            if r["player"] != killer:
                assisters.add(r["player"])
        if next_player and next_player in enemy_team and next_player != killer:
            assisters.add(next_player)

        if killer:
            kill_counts[killer] += 1
        for a in assisters:
            assist_counts[a] += 1

        # Display
        enemy_str = ", ".join(f"{r['player']}(dt={r['dt']:+.2f})" for r in enemy_0824[:3])
        next_str = f" next=[{next_type}]→{next_player}" if next_player else ""
        print(f"  #{i+1:2d} t={d['ts']:8.2f} VICTIM={victim:8s} "
              f"KILLER={killer or '???':8s} "
              f"enemies_0824=[{enemy_str}]{next_str}")

    # KDA validation
    print()
    print("KDA Validation:")
    print(f"  {'Player':8s} {'K':>3s} {'TK':>3s} {'':5s} {'D':>3s} {'TD':>3s} {'':5s} {'A':>3s} {'TA':>3s}")
    total_k = total_d = total_a = 0
    for name in sorted(entities.values()):
        ck = kill_counts.get(name, 0)
        cd = death_counts.get(name, 0)
        ca = assist_counts.get(name, 0)
        tk = truth[name]["K"]
        td = truth[name]["D"]
        ta = truth[name]["A"]
        k_ok = "OK" if ck == tk else "MISS"
        d_ok = "OK" if cd == td else "MISS"
        a_ok = "OK" if ca == ta else "MISS"
        if ck == tk: total_k += 1
        if cd == td: total_d += 1
        if ca == ta: total_a += 1
        print(f"  {name:8s} {ck:3d} {tk:3d} [{k_ok:4s}] {cd:3d} {td:3d} [{d_ok:4s}] {ca:3d} {ta:3d} [{a_ok:4s}]")
    print(f"\n  ACCURACY: K={total_k}/6, D={total_d}/6, A={total_a}/6")
    print(f"  TOTAL: {total_k + total_d + total_a}/18")

    # Save
    output = {
        "version": "death_record_refined_v1",
        "pattern": "[08 04 31] [00 00] [victim_eid BE] [00 00] [timestamp f32 BE] [00 00 00]",
        "accuracy": {"kills": total_k, "deaths": total_d, "assists": total_a},
        "deaths": [
            {"victim": d["victim"], "ts": d["ts"], "frame": d["frame"]}
            for d in all_deaths
        ],
        "kills": dict(kill_counts),
        "death_counts": dict(death_counts),
    }
    output_path = os.path.join(OUTPUT_DIR, "death_record_refined.json")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved to {output_path}")

print("\nDONE")
