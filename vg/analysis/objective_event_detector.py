#!/usr/bin/env python3
"""
Objective Event Detector - Find turret, Kraken, Gold Mine kill/death/credit events.

Searches for kill [18 04 1C], death [08 04 31], and credit [10 04 1D] headers
where the entity ID is NOT a player (outside 50000-60000 range).

Entity ID ranges (from project docs):
  0       = system
  1-10    = infrastructure
  1000-20000 = turrets / objectives
  20000-50000 = minions
  50000-60000 = players

Goal: Discover what objective-related event patterns exist in the replay data.
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

# Headers from kda_detector.py
KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

# Player block markers
PLAYER_BLOCK_MARKER = b'\xDA\x03\xEE'
PLAYER_BLOCK_MARKER_ALT = b'\xE0\x03\xEE'

PLAYER_EID_MIN = 50000
PLAYER_EID_MAX = 65000


def load_truth():
    """Load tournament truth data."""
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def get_replay_frames(replay_file_path: str):
    """Get all frame file paths for a replay, sorted by frame index."""
    first_frame = Path(replay_file_path)
    frame_dir = first_frame.parent
    replay_name = first_frame.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    frames.sort(key=lambda p: int(p.stem.split('.')[-1]))
    return frames


def extract_player_eids(first_frame_data: bytes):
    """Extract player entity IDs (both LE and BE) from player blocks."""
    players = {}
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

    while True:
        pos = -1
        for candidate in markers:
            idx = first_frame_data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
        if pos == -1:
            break

        name_start = pos + 3
        name_end = name_start
        while name_end < len(first_frame_data) and name_end < name_start + 30:
            byte = first_frame_data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        name = ""
        if name_end > name_start:
            try:
                name = first_frame_data[name_start:name_end].decode('ascii')
            except Exception:
                pass

        if len(name) >= 3 and not name.startswith('GameMode'):
            eid_le = None
            team_id = None
            if pos + 0xA5 + 2 <= len(first_frame_data):
                eid_le = int.from_bytes(first_frame_data[pos + 0xA5:pos + 0xA5 + 2], 'little')
            if pos + 0xD5 < len(first_frame_data):
                team_id = first_frame_data[pos + 0xD5]

            if eid_le is not None:
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                team = "left" if team_id == 1 else "right" if team_id == 2 else "unknown"
                players[name] = {
                    'eid_le': eid_le,
                    'eid_be': eid_be,
                    'team': team,
                }

        search_start = pos + 1

    return players


def classify_entity(eid):
    """Classify an entity ID by range."""
    if eid == 0:
        return "system"
    elif 1 <= eid <= 10:
        return "infra"
    elif 11 <= eid <= 999:
        return "low_range"
    elif 1000 <= eid <= 19999:
        return "turret_objective"
    elif 20000 <= eid <= 49999:
        return "minion"
    elif 50000 <= eid <= 65000:
        return "player"
    else:
        return "unknown"


def scan_kill_headers_all(data: bytes, player_eids_be: set):
    """
    Scan for ALL kill headers [18 04 1C], including non-player entity IDs.
    Uses the same structural validation as kda_detector.py.
    """
    events = []
    pos = 0
    while True:
        pos = data.find(KILL_HEADER, pos)
        if pos == -1:
            break
        if pos + 16 > len(data):
            pos += 1
            continue

        # Structural validation (same as kda_detector)
        if (data[pos+3:pos+5] != b'\x00\x00' or
            data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF' or
            data[pos+11:pos+15] != b'\x3F\x80\x00\x00' or
            data[pos+15] != 0x29):
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        is_player = eid in player_eids_be

        # Extract timestamp
        ts = None
        if pos >= 7:
            ts = struct.unpack_from(">f", data, pos - 7)[0]
            if not (0 < ts < 1800):
                ts = None

        events.append({
            'header': 'kill',
            'eid': eid,
            'eid_class': classify_entity(eid),
            'is_player': is_player,
            'timestamp': ts,
            'offset': pos,
        })
        pos += 16

    return events


def scan_kill_headers_relaxed(data: bytes, player_eids_be: set):
    """
    Scan for kill headers [18 04 1C] with RELAXED validation.
    Only requires [00 00] after header and valid entity ID.
    This catches potential objective kills that might have different structural bytes.
    """
    events = []
    pos = 0
    while True:
        pos = data.find(KILL_HEADER, pos)
        if pos == -1:
            break
        if pos + 10 > len(data):
            pos += 1
            continue

        # Only check the [00 00] separator
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]

        # Check full structural validation
        full_valid = False
        if pos + 16 <= len(data):
            full_valid = (data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF' and
                         data[pos+11:pos+15] == b'\x3F\x80\x00\x00' and
                         data[pos+15] == 0x29)

        # Skip player entities (already well-analyzed)
        if eid in player_eids_be and full_valid:
            pos += 1
            continue

        # Extract timestamp
        ts = None
        if pos >= 7:
            ts = struct.unpack_from(">f", data, pos - 7)[0]
            if not (0 < ts < 1800):
                ts = None

        # Context bytes for analysis
        context_after = data[pos+5:pos+20].hex(' ') if pos + 20 <= len(data) else ""

        events.append({
            'eid': eid,
            'eid_class': classify_entity(eid),
            'full_valid': full_valid,
            'timestamp': ts,
            'offset': pos,
            'context_after': context_after,
        })
        pos += 1

    return events


def scan_death_headers_all(data: bytes, player_eids_be: set):
    """
    Scan for ALL death headers [08 04 31], including non-player entity IDs.
    Uses same structural validation as kda_detector.py.
    """
    events = []
    pos = 0
    while True:
        pos = data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(data):
            pos += 1
            continue

        # Structural validation
        if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        ts = struct.unpack_from(">f", data, pos + 9)[0]
        is_player = eid in player_eids_be

        if not (0 < ts < 1800):
            pos += 1
            continue

        events.append({
            'header': 'death',
            'eid': eid,
            'eid_class': classify_entity(eid),
            'is_player': is_player,
            'timestamp': ts,
            'offset': pos,
        })
        pos += 1

    return events


def scan_credit_headers_all(data: bytes, player_eids_be: set):
    """
    Scan for ALL credit headers [10 04 1D], including non-player entity IDs.
    """
    events = []
    pos = 0
    while True:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue

        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 3
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        value = struct.unpack_from(">f", data, pos + 7)[0]
        is_player = eid in player_eids_be

        action_byte = data[pos + 11] if pos + 11 < len(data) else None

        if 0 <= value <= 100000:  # Wide range for objectives
            events.append({
                'header': 'credit',
                'eid': eid,
                'eid_class': classify_entity(eid),
                'is_player': is_player,
                'value': round(value, 4),
                'action_byte': f"0x{action_byte:02X}" if action_byte is not None else None,
                'offset': pos,
            })

        pos += 3

    return events


def analyze_match(match_data, match_idx):
    """Analyze a single match for objective events."""
    replay_file = match_data['replay_file']
    match_info = match_data['match_info']
    print(f"\n{'='*80}")
    print(f"MATCH {match_idx + 1}: {match_data['replay_name'][:40]}...")
    print(f"Duration: {match_info['duration_seconds']}s, Winner: {match_info['winner']}")
    print(f"Score: left {match_info['score_left']} - {match_info['score_right']} right")
    print(f"{'='*80}")

    frames = get_replay_frames(replay_file)
    if not frames:
        print("  ERROR: No frame files found")
        return None

    # Read first frame for player data
    first_frame_data = frames[0].read_bytes()
    players = extract_player_eids(first_frame_data)

    player_eids_be = set()
    print(f"\n  Players ({len(players)}):")
    for name, pdata in players.items():
        eid_be = pdata['eid_be']
        player_eids_be.add(eid_be)
        print(f"    {name:20s}  eid_LE={pdata['eid_le']:5d}  eid_BE={eid_be:5d}  team={pdata['team']}")

    # Read ALL frames
    all_data = b""
    for frame_path in frames:
        all_data += frame_path.read_bytes()
    print(f"\n  Total data: {len(all_data):,} bytes across {len(frames)} frames")

    # =========================================================================
    # 1. KILL HEADERS - Full structural validation (same as kda_detector)
    # =========================================================================
    kill_events = scan_kill_headers_all(all_data, player_eids_be)
    player_kills = [e for e in kill_events if e['is_player']]
    nonplayer_kills = [e for e in kill_events if not e['is_player']]

    print(f"\n  --- KILL HEADERS [18 04 1C] (full validation) ---")
    print(f"  Player kills: {len(player_kills)}")
    print(f"  Non-player kills: {len(nonplayer_kills)}")

    if nonplayer_kills:
        # Categorize by entity range
        by_class = defaultdict(list)
        for ev in nonplayer_kills:
            by_class[ev['eid_class']].append(ev)
        for cls, evs in sorted(by_class.items()):
            eid_counter = Counter(e['eid'] for e in evs)
            print(f"\n    [{cls}] {len(evs)} events:")
            for eid, count in eid_counter.most_common(20):
                ts_list = [e['timestamp'] for e in evs if e['eid'] == eid and e['timestamp']]
                ts_str = f"  ts=[{', '.join(f'{t:.1f}' for t in ts_list[:5])}{'...' if len(ts_list) > 5 else ''}]" if ts_list else ""
                print(f"      eid={eid:5d} ({eid:#06x})  count={count}{ts_str}")

    # =========================================================================
    # 2. KILL HEADERS - Relaxed validation (catch different structural patterns)
    # =========================================================================
    relaxed_kills = scan_kill_headers_relaxed(all_data, player_eids_be)
    print(f"\n  --- KILL HEADERS [18 04 1C] (relaxed, non-player only) ---")
    print(f"  Non-standard kill-like patterns: {len(relaxed_kills)}")

    if relaxed_kills:
        by_class = defaultdict(list)
        for ev in relaxed_kills:
            by_class[ev['eid_class']].append(ev)
        for cls, evs in sorted(by_class.items()):
            eid_counter = Counter(e['eid'] for e in evs)
            print(f"\n    [{cls}] {len(evs)} events:")
            for eid, count in eid_counter.most_common(10):
                sample = [e for e in evs if e['eid'] == eid][:3]
                for s in sample:
                    print(f"      eid={eid:5d} ({eid:#06x})  valid={s['full_valid']}  "
                          f"ts={s['timestamp']}  ctx={s['context_after']}")

    # =========================================================================
    # 3. DEATH HEADERS - All entities
    # =========================================================================
    death_events = scan_death_headers_all(all_data, player_eids_be)
    player_deaths = [e for e in death_events if e['is_player']]
    nonplayer_deaths = [e for e in death_events if not e['is_player']]

    print(f"\n  --- DEATH HEADERS [08 04 31] (full validation) ---")
    print(f"  Player deaths: {len(player_deaths)}")
    print(f"  Non-player deaths: {len(nonplayer_deaths)}")

    if nonplayer_deaths:
        by_class = defaultdict(list)
        for ev in nonplayer_deaths:
            by_class[ev['eid_class']].append(ev)
        for cls, evs in sorted(by_class.items()):
            eid_counter = Counter(e['eid'] for e in evs)
            print(f"\n    [{cls}] {len(evs)} events:")
            for eid, count in eid_counter.most_common(20):
                ts_list = sorted(set(round(e['timestamp'], 1) for e in evs if e['eid'] == eid))
                ts_str = f"  ts=[{', '.join(f'{t:.1f}' for t in ts_list[:8])}{'...' if len(ts_list) > 8 else ''}]" if ts_list else ""
                print(f"      eid={eid:5d} ({eid:#06x})  count={count}{ts_str}")

    # =========================================================================
    # 4. CREDIT HEADERS - Non-player entities
    # =========================================================================
    credit_events = scan_credit_headers_all(all_data, player_eids_be)
    player_credits = [e for e in credit_events if e['is_player']]
    nonplayer_credits = [e for e in credit_events if not e['is_player']]

    print(f"\n  --- CREDIT HEADERS [10 04 1D] (all) ---")
    print(f"  Player credit records: {len(player_credits)}")
    print(f"  Non-player credit records: {len(nonplayer_credits)}")

    if nonplayer_credits:
        by_class = defaultdict(list)
        for ev in nonplayer_credits:
            by_class[ev['eid_class']].append(ev)
        for cls, evs in sorted(by_class.items()):
            eid_counter = Counter(e['eid'] for e in evs)
            print(f"\n    [{cls}] {len(evs)} events:")
            for eid, count in eid_counter.most_common(15):
                vals = [e['value'] for e in evs if e['eid'] == eid]
                actions = Counter(e['action_byte'] for e in evs if e['eid'] == eid)
                val_set = sorted(set(round(v, 2) for v in vals))[:10]
                print(f"      eid={eid:5d} ({eid:#06x})  count={count}  "
                      f"values={val_set}  actions={dict(actions.most_common(5))}")

    # =========================================================================
    # 5. CROSS-REFERENCE: Kill events near death events (turret kills)
    # =========================================================================
    print(f"\n  --- KILL-DEATH PROXIMITY ANALYSIS (non-player) ---")
    # For each non-player death, look for kill headers nearby in time
    if nonplayer_deaths:
        for dev in nonplayer_deaths[:20]:  # Sample
            # Find kills within 5 seconds
            nearby_kills = [
                k for k in kill_events
                if k['timestamp'] and dev['timestamp']
                and abs(k['timestamp'] - dev['timestamp']) < 5.0
            ]
            if nearby_kills:
                print(f"    Death: eid={dev['eid']} ({dev['eid_class']}) ts={dev['timestamp']:.1f}")
                for k in nearby_kills:
                    player_label = "PLAYER" if k['is_player'] else "NON-PLAYER"
                    dt = k['timestamp'] - dev['timestamp']
                    print(f"      -> Kill: eid={k['eid']} ({k['eid_class']}/{player_label}) "
                          f"ts={k['timestamp']:.1f} dt={dt:+.1f}s")

    # =========================================================================
    # 6. ENTITY LIFECYCLE: Track turret-range entities across frames
    # =========================================================================
    print(f"\n  --- TURRET-RANGE ENTITY LIFECYCLE ---")
    turret_deaths = [e for e in nonplayer_deaths if e['eid_class'] == 'turret_objective']
    if turret_deaths:
        unique_turret_eids = sorted(set(e['eid'] for e in turret_deaths))
        print(f"  Turret/objective entities with death events: {len(unique_turret_eids)}")
        for eid in unique_turret_eids:
            deaths_for_eid = [e for e in turret_deaths if e['eid'] == eid]
            ts_list = sorted(set(round(e['timestamp'], 1) for e in deaths_for_eid))
            print(f"    eid={eid:5d} ({eid:#06x})  deaths={len(deaths_for_eid)}  ts={ts_list}")
    else:
        print("  No turret-range entities found in death events")

    # =========================================================================
    # 7. SUMMARY STATISTICS
    # =========================================================================
    print(f"\n  --- SUMMARY ---")
    print(f"  Total kill events (all):    {len(kill_events)}")
    print(f"    Player:                   {len(player_kills)}")
    print(f"    Non-player:               {len(nonplayer_kills)}")
    print(f"  Total death events (all):   {len(death_events)}")
    print(f"    Player:                   {len(player_deaths)}")
    print(f"    Non-player:               {len(nonplayer_deaths)}")
    print(f"  Total credit records (all): {len(credit_events)}")
    print(f"    Player:                   {len(player_credits)}")
    print(f"    Non-player:               {len(nonplayer_credits)}")

    # Entity class distribution across all event types
    all_nonplayer = nonplayer_kills + nonplayer_deaths + nonplayer_credits
    class_counts = Counter(e['eid_class'] for e in all_nonplayer)
    print(f"\n  Non-player entity class distribution:")
    for cls, cnt in class_counts.most_common():
        print(f"    {cls:20s}: {cnt}")

    return {
        'match_idx': match_idx,
        'player_kills': len(player_kills),
        'nonplayer_kills': len(nonplayer_kills),
        'player_deaths': len(player_deaths),
        'nonplayer_deaths': len(nonplayer_deaths),
        'player_credits': len(player_credits),
        'nonplayer_credits': len(nonplayer_credits),
        'nonplayer_kill_eids': Counter(e['eid'] for e in nonplayer_kills),
        'nonplayer_death_eids': Counter(e['eid'] for e in nonplayer_deaths),
        'turret_death_eids': sorted(set(e['eid'] for e in turret_deaths)) if turret_deaths else [],
    }


def main():
    truth = load_truth()
    matches = truth['matches']

    # Analyze first 3 matches for initial investigation
    num_matches = min(3, len(matches))
    print(f"Analyzing {num_matches} matches for objective events...")

    results = []
    for i in range(num_matches):
        result = analyze_match(matches[i], i)
        if result:
            results.append(result)

    # Cross-match summary
    print(f"\n\n{'='*80}")
    print(f"CROSS-MATCH SUMMARY ({len(results)} matches)")
    print(f"{'='*80}")

    all_nonplayer_kill_eids = Counter()
    all_nonplayer_death_eids = Counter()
    all_turret_death_eids = set()

    for r in results:
        all_nonplayer_kill_eids.update(r['nonplayer_kill_eids'])
        all_nonplayer_death_eids.update(r['nonplayer_death_eids'])
        all_turret_death_eids.update(r['turret_death_eids'])

    print(f"\nNon-player kill entity IDs across matches:")
    for eid, count in all_nonplayer_kill_eids.most_common(20):
        print(f"  eid={eid:5d} ({eid:#06x}) [{classify_entity(eid)}]  total={count}")

    print(f"\nNon-player death entity IDs across matches:")
    for eid, count in all_nonplayer_death_eids.most_common(30):
        print(f"  eid={eid:5d} ({eid:#06x}) [{classify_entity(eid)}]  total={count}")

    print(f"\nTurret-range entity IDs with death events: {sorted(all_turret_death_eids)}")

    # Per-match totals
    print(f"\nPer-match breakdown:")
    print(f"  {'Match':>5s}  {'P_Kills':>8s}  {'NP_Kills':>8s}  {'P_Deaths':>8s}  {'NP_Deaths':>9s}  {'P_Credits':>9s}  {'NP_Credits':>10s}")
    for r in results:
        print(f"  {r['match_idx']+1:5d}  {r['player_kills']:8d}  {r['nonplayer_kills']:8d}  "
              f"{r['player_deaths']:8d}  {r['nonplayer_deaths']:9d}  "
              f"{r['player_credits']:9d}  {r['nonplayer_credits']:10d}")


if __name__ == '__main__':
    main()
