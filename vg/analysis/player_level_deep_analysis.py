"""
Player Level Deep Analysis - Focus on Action 0x02 and 0x03

Key findings from initial research:
- Action 0x02: 1,353 occurrences, values range ~6-15 (sample: 9.3, 7.54, 8.78, 11.25, 15.15)
- Action 0x03: 336 occurrences, all values = 1.0
- Heartbeat byte 8 shows incrementing pattern: [13, 13, 13, 13, 14, 14, 14, 14, 14, 14]

Hypothesis:
- 0x02 = XP gain events (variable values match XP rewards)
- 0x03 = Level-up events (value=1.0 means +1 level)
- Heartbeat byte 8 = current player level (incrementing 13→14 = level up)
"""

import struct
import os
from collections import defaultdict, Counter
from pathlib import Path

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
HEARTBEAT_HEADER = bytes([0x18, 0x04, 0x3E])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
KILL_HEADER = bytes([0x18, 0x04, 0x1C])

def _le_to_be(eid_le):
    """Convert Little Endian entity ID to Big Endian"""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def find_player_blocks(data):
    """Find all player blocks"""
    players = []
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            try:
                eid_offset = pos + 0xA5
                hero_offset = pos + 0xA9
                team_offset = pos + 0xD5

                if eid_offset + 2 <= len(data) and hero_offset + 2 <= len(data) and team_offset + 1 <= len(data):
                    eid_le = struct.unpack('<H', data[eid_offset:eid_offset+2])[0]
                    hero_id = struct.unpack('<H', data[hero_offset:hero_offset+2])[0]
                    team = data[team_offset]

                    players.append({
                        'eid_le': eid_le,
                        'eid_be': _le_to_be(eid_le),
                        'hero_id': hero_id,
                        'team': team
                    })
            except:
                pass

            offset = pos + 1

    return players

def extract_all_credits(data):
    """Extract all credit records with timestamps"""
    credits = []
    offset = 0

    while True:
        pos = data.find(CREDIT_HEADER, offset)
        if pos == -1:
            break

        try:
            if pos + 12 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                value_f32 = struct.unpack('>f', data[pos+7:pos+11])[0]
                action = data[pos+11]

                # Try to find timestamp (7 bytes before credit header, as f32 BE)
                ts = None
                if pos >= 7:
                    try:
                        ts = struct.unpack('>f', data[pos-7:pos-3])[0]
                        if ts < 0 or ts > 10000:  # Sanity check
                            ts = None
                    except:
                        pass

                credits.append({
                    'pos': pos,
                    'eid': eid_be,
                    'value': value_f32,
                    'action': action,
                    'timestamp': ts
                })
        except:
            pass

        offset = pos + 1

    return credits

def extract_heartbeats(data, player_eids_be):
    """Extract heartbeat records for players"""
    heartbeats = defaultdict(list)
    offset = 0

    while True:
        pos = data.find(HEARTBEAT_HEADER, offset)
        if pos == -1:
            break

        try:
            if pos + 40 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                if eid_be in player_eids_be:
                    payload = data[pos+7:pos+37]

                    # Extract byte 8 (potential level)
                    level_byte = payload[8] if len(payload) > 8 else None

                    # Try to extract timestamp
                    ts = None
                    if pos >= 7:
                        try:
                            ts = struct.unpack('>f', data[pos-7:pos-3])[0]
                            if ts < 0 or ts > 10000:
                                ts = None
                        except:
                            pass

                    heartbeats[eid_be].append({
                        'pos': pos,
                        'timestamp': ts,
                        'level_byte': level_byte,
                        'payload': payload
                    })
        except:
            pass

        offset = pos + 1

    return heartbeats

def analyze_level_progression(credits, heartbeats, player_eid):
    """Analyze level progression for a single player"""
    print(f"\n{'='*80}")
    print(f"PLAYER ENTITY ID: {player_eid}")
    print(f"{'='*80}")

    # Filter credits for this player
    player_credits_0x02 = [c for c in credits if c['eid'] == player_eid and c['action'] == 0x02]
    player_credits_0x03 = [c for c in credits if c['eid'] == player_eid and c['action'] == 0x03]

    print(f"\n[DATA] Action 0x02 (XP gain?): {len(player_credits_0x02)} records")
    print(f"[DATA] Action 0x03 (Level up?): {len(player_credits_0x03)} records")

    # Show 0x03 events (level-ups?)
    if player_credits_0x03:
        print(f"\n[FINDING] Action 0x03 events (all value=1.0, potential level-ups):")
        for i, c in enumerate(player_credits_0x03[:15]):
            ts_str = f"{c['timestamp']:.2f}s" if c['timestamp'] else "unknown"
            print(f"  Level {i+2}? at {ts_str}")

    # Show 0x02 value distribution
    if player_credits_0x02:
        xp_values = [c['value'] for c in player_credits_0x02]
        xp_dist = Counter([round(v, 1) for v in xp_values])
        print(f"\n[FINDING] Action 0x02 value distribution (XP amounts?):")
        for val, count in sorted(xp_dist.items(), key=lambda x: -x[1])[:10]:
            print(f"  {val:6.1f}: {count:3d} times")

    # Analyze heartbeat level byte progression
    if player_eid in heartbeats:
        hb_records = heartbeats[player_eid]
        level_bytes = [h['level_byte'] for h in hb_records if h['level_byte'] is not None]

        if level_bytes:
            level_changes = []
            for i in range(1, len(level_bytes)):
                if level_bytes[i] != level_bytes[i-1]:
                    level_changes.append({
                        'from': level_bytes[i-1],
                        'to': level_bytes[i],
                        'at_record': i,
                        'timestamp': hb_records[i]['timestamp']
                    })

            print(f"\n[FINDING] Heartbeat byte 8 progression (n={len(level_bytes)} samples):")
            print(f"  Initial value: {level_bytes[0]}")
            print(f"  Final value: {level_bytes[-1]}")
            print(f"  Unique values: {sorted(set(level_bytes))}")

            if level_changes:
                print(f"\n[FINDING] Level transitions detected: {len(level_changes)}")
                for change in level_changes[:15]:
                    ts_str = f"{change['timestamp']:.2f}s" if change['timestamp'] else "unknown"
                    print(f"  {change['from']:3d} -> {change['to']:3d} at record {change['at_record']:4d} ({ts_str})")

            # Cross-reference with 0x03 events
            print(f"\n[STAT:level_up_events] Action 0x03 count: {len(player_credits_0x03)}")
            print(f"[STAT:heartbeat_transitions] Heartbeat transitions: {len(level_changes)}")

            if len(player_credits_0x03) > 0 and len(level_changes) > 0:
                ratio = len(level_changes) / len(player_credits_0x03)
                print(f"[STAT:correlation] Transition/0x03 ratio: {ratio:.2f}")

                if abs(ratio - 1.0) < 0.2:
                    print(f"[FINDING] STRONG CORRELATION - Heartbeat byte 8 likely encodes player level!")
                    print(f"[FINDING] Action 0x03 likely marks level-up events!")

def main():
    import time
    start_time = time.time()

    print("[OBJECTIVE] Deep analysis of player level encoding - focus on action 0x02, 0x03, and heartbeat byte 8")

    replay_file = r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1\d8736287-e35e-4c76-89b0-c78c76fd0b05-8c6e1a3e-68a0-4853-8786-44c899ff1e8a.0.vgr"

    if not os.path.exists(replay_file):
        print(f"[LIMITATION] File not found: {replay_file}")
        return

    print(f"\n[STAGE:begin:data_loading]")
    with open(replay_file, 'rb') as f:
        data = f.read()
    print(f"[DATA] Loaded {len(data):,} bytes")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # Find players
    print(f"\n[STAGE:begin:player_extraction]")
    players = find_player_blocks(data)
    player_eids_be = set([p['eid_be'] for p in players])
    print(f"[DATA] Found {len(players)} players")
    for p in players:
        print(f"  Entity {p['eid_be']:5d} (LE: {p['eid_le']:5d}), Hero {p['hero_id']:5d}, Team {p['team']}")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:player_extraction]")

    # Extract all credits
    print(f"\n[STAGE:begin:credit_extraction]")
    credits = extract_all_credits(data)
    print(f"[DATA] Extracted {len(credits):,} credit records")

    action_dist = Counter([c['action'] for c in credits])
    print(f"[FINDING] Action distribution:")
    for action, count in sorted(action_dist.items()):
        print(f"  0x{action:02X}: {count:4d}")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:credit_extraction]")

    # Extract heartbeats
    print(f"\n[STAGE:begin:heartbeat_extraction]")
    heartbeats = extract_heartbeats(data, player_eids_be)
    total_hb = sum(len(v) for v in heartbeats.values())
    print(f"[DATA] Extracted {total_hb:,} heartbeat records for {len(heartbeats)} players")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:heartbeat_extraction]")

    # Analyze first 3 players in detail
    print(f"\n[STAGE:begin:level_progression_analysis]")
    for i, player_eid in enumerate(list(player_eids_be)[:3]):
        analyze_level_progression(credits, heartbeats, player_eid)
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:level_progression_analysis]")

    # Summary statistics
    print(f"\n{'='*80}")
    print("SUMMARY STATISTICS")
    print(f"{'='*80}")

    total_0x03 = sum(1 for c in credits if c['action'] == 0x03)
    total_0x02 = sum(1 for c in credits if c['action'] == 0x02)

    print(f"\n[STAT:total_0x03_events] {total_0x03}")
    print(f"[STAT:total_0x02_events] {total_0x02}")
    print(f"[STAT:players] {len(players)}")
    print(f"[STAT:avg_0x03_per_player] {total_0x03 / len(players):.1f}")

    print(f"\n[FINDING] Expected level-ups per player in ~17min match: ~10-11 (start L1, end L11-12)")
    print(f"[FINDING] Observed 0x03 events per player: {total_0x03 / len(players):.1f}")

    if 9 <= total_0x03 / len(players) <= 12:
        print(f"[FINDING] ✓ STRONG EVIDENCE: 0x03 event frequency matches expected level-up count!")

    elapsed = time.time() - start_time
    print(f"\n[STAGE:time:{elapsed:.2f}]")

    print(f"\n[LIMITATION] Timestamp extraction unreliable - may need different offset")
    print(f"[LIMITATION] Need ground truth level data for final validation")

if __name__ == "__main__":
    main()
