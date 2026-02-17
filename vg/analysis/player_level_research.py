"""
Player Level/XP Research

Research plan:
1. Check player block bytes beyond +0xD5 for level-like values (1-12 range)
2. Search credit records for XP-related action bytes
3. Search [18 04 3E] heartbeat payloads for incrementing counters
4. Look for level-up event headers

Expected level progression in MOBA:
- Start: Level 1
- Max: Level 12
- XP from: minions, kills, assists, passive over time
- Level correlates with game duration and minion kills
"""

import struct
import os
from collections import defaultdict, Counter
from pathlib import Path

# Known event headers (Big Endian)
KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
ITEM_HEADER = bytes([0x10, 0x04, 0x3D])
HEARTBEAT_HEADER = bytes([0x18, 0x04, 0x3E])
ACTION_HEADER = bytes([0x28, 0x04, 0x3F])

# Known credit action bytes
KNOWN_ACTIONS = {
    0x06: "gold_income",
    0x08: "passive_gold",
    0x0E: "minion_kill_credit",
    0x0F: "minion_kill_gold",
    0x0D: "jungle_gold",
    0x04: "turret_bounty"
}

def find_player_blocks(data):
    """Find all player blocks (DA 03 EE or E0 03 EE markers)"""
    players = []
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            # Extract player data
            try:
                eid_offset = pos + 0xA5
                hero_offset = pos + 0xA9
                team_offset = pos + 0xD5

                if eid_offset + 2 <= len(data) and hero_offset + 2 <= len(data) and team_offset + 1 <= len(data):
                    eid_le = struct.unpack('<H', data[eid_offset:eid_offset+2])[0]
                    hero_id = struct.unpack('<H', data[hero_offset:hero_offset+2])[0]
                    team = data[team_offset]

                    # Read 50 bytes after team byte for exploration
                    extra_start = team_offset + 1
                    extra_end = min(extra_start + 50, len(data))
                    extra_bytes = data[extra_start:extra_end]

                    players.append({
                        'marker_pos': pos,
                        'eid_le': eid_le,
                        'hero_id': hero_id,
                        'team': team,
                        'extra_bytes': extra_bytes
                    })
            except:
                pass

            offset = pos + 1

    return players

def search_level_in_player_block(players):
    """Search for level values (1-12 range) in player block extra bytes"""
    print("\n[STAGE:begin:player_block_level_search]")

    level_candidates = defaultdict(list)

    for p in players:
        for i, byte_val in enumerate(p['extra_bytes']):
            if 1 <= byte_val <= 12:
                level_candidates[i].append({
                    'offset': i,
                    'value': byte_val,
                    'eid': p['eid_le'],
                    'hero': p['hero_id']
                })

    print(f"[DATA] Scanned {len(players)} player blocks")
    print(f"[FINDING] Found {len(level_candidates)} byte offsets with 1-12 range values:")

    for offset in sorted(level_candidates.keys()):
        values = [x['value'] for x in level_candidates[offset]]
        value_dist = Counter(values)
        print(f"  Offset +{offset} (from team byte): {dict(value_dist)} (n={len(values)})")

    print("[STAGE:status:success]")
    print("[STAGE:end:player_block_level_search]")

    return level_candidates

def find_unknown_credit_actions(data):
    """Find credit records with unknown action bytes (potential XP records)"""
    print("\n[STAGE:begin:unknown_credit_search]")

    offset = 0
    unknown_actions = []
    action_counter = Counter()

    while True:
        pos = data.find(CREDIT_HEADER, offset)
        if pos == -1:
            break

        try:
            # Credit structure: [10 04 1D][00 00][eid BE 2B][value f32 BE][action 1B]
            if pos + 12 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                value_f32 = struct.unpack('>f', data[pos+7:pos+11])[0]
                action = data[pos+11]

                action_counter[action] += 1

                if action not in KNOWN_ACTIONS:
                    unknown_actions.append({
                        'pos': pos,
                        'eid': eid_be,
                        'value': value_f32,
                        'action': action
                    })
        except:
            pass

        offset = pos + 1

    print(f"[DATA] Scanned {sum(action_counter.values())} credit records")
    print(f"[FINDING] Action byte distribution:")
    for action, count in sorted(action_counter.items(), key=lambda x: -x[1]):
        label = KNOWN_ACTIONS.get(action, "UNKNOWN")
        print(f"  0x{action:02X} ({label}): {count:,}")

    print(f"\n[FINDING] Found {len(unknown_actions)} records with unknown action bytes")
    if unknown_actions:
        print("Sample unknown records:")
        for rec in unknown_actions[:10]:
            print(f"  Action=0x{rec['action']:02X}, eid={rec['eid']}, value={rec['value']:.2f}")

    print("[STAGE:status:success]")
    print("[STAGE:end:unknown_credit_search]")

    return unknown_actions, action_counter

def analyze_heartbeat_payloads(data, player_eids):
    """Analyze [18 04 3E] heartbeat payloads for incrementing counters"""
    print("\n[STAGE:begin:heartbeat_payload_analysis]")

    # Convert player entity IDs from LE to BE
    player_eids_be = set()
    for eid_le in player_eids:
        eid_be = struct.unpack('>H', struct.pack('<H', eid_le))[0]
        player_eids_be.add(eid_be)

    offset = 0
    heartbeats = defaultdict(list)
    sample_count = 0
    max_samples = 1000  # Limit samples to avoid memory issues

    while sample_count < max_samples:
        pos = data.find(HEARTBEAT_HEADER, offset)
        if pos == -1:
            break

        try:
            # Heartbeat structure: [18 04 3E][00 00][eid BE 2B][payload ~32B]
            if pos + 37 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                if eid_be in player_eids_be:
                    payload = data[pos+7:pos+37]
                    heartbeats[eid_be].append({
                        'pos': pos,
                        'payload': payload
                    })
                    sample_count += 1
        except:
            pass

        offset = pos + 1

    print(f"[DATA] Collected {sample_count} heartbeat samples from {len(heartbeats)} players")

    # Analyze payload bytes for incrementing patterns
    for eid_be in list(heartbeats.keys())[:3]:  # Check first 3 players
        records = heartbeats[eid_be][:20]  # First 20 heartbeats

        print(f"\n[FINDING] Player eid={eid_be} heartbeat analysis (n={len(records)}):")

        # Check each byte position for variation
        for byte_idx in range(30):
            values = [r['payload'][byte_idx] for r in records]
            unique_vals = set(values)

            if len(unique_vals) > 1 and len(unique_vals) < 15:  # Shows variation but not random
                print(f"  Byte {byte_idx:2d}: {values[:10]} (unique={len(unique_vals)})")

    print("[STAGE:status:success]")
    print("[STAGE:end:heartbeat_payload_analysis]")

    return heartbeats

def search_new_event_headers(data):
    """Search for unknown event headers that might be level-up events"""
    print("\n[STAGE:begin:new_event_header_search]")

    known_headers = {
        KILL_HEADER, DEATH_HEADER, CREDIT_HEADER, ITEM_HEADER,
        HEARTBEAT_HEADER, ACTION_HEADER
    }

    # Search for 3-byte patterns starting with common prefixes
    event_prefixes = [
        bytes([0x08, 0x04]),  # Death family
        bytes([0x10, 0x04]),  # Credit/Item family
        bytes([0x18, 0x04]),  # Kill/Heartbeat family
        bytes([0x20, 0x04]),  # Unknown family
        bytes([0x28, 0x04]),  # Action family
    ]

    header_counter = Counter()

    for prefix in event_prefixes:
        offset = 0
        while True:
            pos = data.find(prefix, offset)
            if pos == -1:
                break

            if pos + 3 <= len(data):
                header = data[pos:pos+3]
                if header not in known_headers:
                    header_counter[header] += 1

            offset = pos + 1

    print(f"[DATA] Searched for event headers with known prefixes")
    print(f"[FINDING] Found {len(header_counter)} unknown header patterns:")

    for header, count in sorted(header_counter.items(), key=lambda x: -x[1])[:20]:
        hex_str = ' '.join(f'{b:02X}' for b in header)
        print(f"  [{hex_str}]: {count:,} occurrences")

    print("[STAGE:status:success]")
    print("[STAGE:end:new_event_header_search]")

    return header_counter

def main():
    import time
    start_time = time.time()

    print("[OBJECTIVE] Discover player level/XP encoding in Vainglory .vgr binary format")

    # Use first 3 tournament matches
    replay_files = [
        r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1\d8736287-e35e-4c76-89b0-c78c76fd0b05-8c6e1a3e-68a0-4853-8786-44c899ff1e8a.0.vgr",
        r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-20692443-e314-4ca5-934e-faa63d820d72.0.vgr",
        r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Maitun Gaming\1\d8736287-e35e-4c76-89b0-c78c76fd0b05-c2612bb7-c551-408f-bc75-c51ab6da604e.0.vgr"
    ]

    all_players = []
    all_level_candidates = {}
    all_unknown_credits = []
    all_action_counters = Counter()

    for i, replay_path in enumerate(replay_files, 1):
        if not os.path.exists(replay_path):
            print(f"[LIMITATION] File not found: {replay_path}")
            continue

        print(f"\n{'='*80}")
        print(f"MATCH {i}: {Path(replay_path).parent.parent.name} - {Path(replay_path).parent.name}")
        print(f"{'='*80}")

        with open(replay_path, 'rb') as f:
            data = f.read()

        print(f"[DATA] Loaded {len(data):,} bytes")

        # 1. Find player blocks and search for level values
        players = find_player_blocks(data)
        level_candidates = search_level_in_player_block(players)
        all_players.extend(players)

        # Merge level candidates
        for offset, values in level_candidates.items():
            if offset not in all_level_candidates:
                all_level_candidates[offset] = []
            all_level_candidates[offset].extend(values)

        # 2. Search for unknown credit action bytes
        unknown_credits, action_counter = find_unknown_credit_actions(data)
        all_unknown_credits.extend(unknown_credits)
        all_action_counters.update(action_counter)

        # 3. Analyze heartbeat payloads (only for first match to save time)
        if i == 1:
            player_eids = [p['eid_le'] for p in players]
            heartbeats = analyze_heartbeat_payloads(data, player_eids)

        # 4. Search for new event headers (only for first match)
        if i == 1:
            new_headers = search_new_event_headers(data)

    # Summary across all matches
    print(f"\n{'='*80}")
    print("CROSS-MATCH SUMMARY")
    print(f"{'='*80}")

    print(f"\n[FINDING] Level candidates across {len(all_players)} total player blocks:")
    for offset in sorted(all_level_candidates.keys()):
        values = [x['value'] for x in all_level_candidates[offset]]
        value_dist = Counter(values)
        variance = len(value_dist)
        print(f"  Offset +{offset}: {dict(value_dist)} (variance={variance})")

        # High variance (8-12 unique values) suggests level encoding
        if variance >= 8:
            print(f"    [STAT:high_variance] Offset +{offset} shows {variance} unique values - STRONG LEVEL CANDIDATE")

    print(f"\n[FINDING] Unknown credit action bytes across all matches:")
    unknown_action_set = set()
    for rec in all_unknown_credits:
        unknown_action_set.add(rec['action'])

    for action in sorted(unknown_action_set):
        count = all_action_counters[action]
        sample_values = [rec['value'] for rec in all_unknown_credits if rec['action'] == action][:10]
        print(f"  0x{action:02X}: {count:,} occurrences, sample values: {sample_values}")

    elapsed = time.time() - start_time
    print(f"\n[STAGE:time:{elapsed:.2f}]")
    print(f"\n[LIMITATION] Truth data does not include player level for validation")
    print(f"[LIMITATION] Need ground truth level data to confirm hypotheses")

if __name__ == "__main__":
    main()
