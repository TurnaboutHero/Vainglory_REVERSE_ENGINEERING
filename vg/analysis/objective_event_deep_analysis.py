#!/usr/bin/env python3
"""
Objective Event Deep Analysis - Focus on turret credit records and high-range entities.

Findings from first pass (objective_event_detector.py):
1. Kill headers [18 04 1C] with full validation: ONLY player eids pass.
   Objective kills use a DIFFERENT structural pattern (no [3F 80 00 00] [29]).
2. Death headers [08 04 31]: Hundreds of non-player deaths (turrets, minions).
3. Credit headers [10 04 1D]: Turret-range eids (2000-2121) with value 150 and action 0x04.
4. High-range eids (65000+) in death events - possible Kraken/Gold Mine/special objectives.

This script investigates:
- Credit record eid ~2000-2121 patterns: are these turret/objective gold bounties?
- Relaxed kill pattern for non-players: [18 04 1C] [00 00] [eid] [FF FF FF FF] [value f32] [action]
- Death events for high-range entities (>65000): Kraken, Gold Mine candidates
- Groups of 6 turret deaths in same frame (crystal destruction correlation)
- Turret destruction timeline vs credit records
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

PLAYER_BLOCK_MARKER = b'\xDA\x03\xEE'
PLAYER_BLOCK_MARKER_ALT = b'\xE0\x03\xEE'


def load_truth():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def get_replay_frames(replay_file_path: str):
    first_frame = Path(replay_file_path)
    frame_dir = first_frame.parent
    replay_name = first_frame.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    frames.sort(key=lambda p: int(p.stem.split('.')[-1]))
    return frames


def extract_player_info(first_frame_data: bytes):
    """Extract player entity IDs and names."""
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


def scan_relaxed_kills_with_context(data: bytes, player_eids_be: set):
    """
    Scan for kill-like patterns [18 04 1C] [00 00] [eid BE] with wider context.
    Returns ALL matches regardless of entity range, with surrounding bytes for analysis.
    """
    events = []
    pos = 0
    while True:
        pos = data.find(KILL_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(data):
            pos += 1
            continue

        # Must have [00 00] separator
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]

        # Full validation check
        full_valid = False
        if pos + 16 <= len(data):
            full_valid = (data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF' and
                         data[pos+11:pos+15] == b'\x3F\x80\x00\x00' and
                         data[pos+15] == 0x29)

        # Extract timestamp
        ts = None
        if pos >= 7:
            ts = struct.unpack_from(">f", data, pos - 7)[0]
            if not (0 < ts < 1800):
                ts = None

        # Read next 4 bytes after eid for structural analysis
        after_eid = data[pos+7:pos+16]

        # Check for [FF FF FF FF] pattern after eid
        has_ffff = data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF'

        # If has FFFF, read the f32 value after it
        value_after_ffff = None
        if has_ffff and pos + 15 <= len(data):
            value_after_ffff = struct.unpack_from(">f", data, pos + 11)[0]

        # Action byte after the f32
        action_byte = data[pos+15] if pos + 15 < len(data) else None

        events.append({
            'eid': eid,
            'is_player': eid in player_eids_be,
            'full_valid': full_valid,
            'has_ffff': has_ffff,
            'value': value_after_ffff,
            'action_byte': action_byte,
            'timestamp': ts,
            'offset': pos,
            'after_eid_hex': after_eid.hex(' '),
        })
        pos += 1

    return events


def scan_deaths_per_frame(frames, player_eids_be: set):
    """
    Scan death events per frame to find simultaneous deaths (crystal destruction).
    """
    frame_deaths = {}
    for frame_path in frames:
        frame_idx = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        deaths = []
        pos = 0
        while True:
            pos = data.find(DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(data):
                pos += 1
                continue

            if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            ts = struct.unpack_from(">f", data, pos + 9)[0]

            if not (0 < ts < 1800):
                pos += 1
                continue

            is_player_eid = eid in player_eids_be
            deaths.append({
                'eid': eid,
                'ts': ts,
                'is_player': is_player_eid,
                'range': 'turret' if 1000 <= eid <= 19999 else
                         'minion' if 20000 <= eid <= 49999 else
                         'player' if 50000 <= eid <= 65000 else
                         'high' if eid > 65000 else 'low',
            })
            pos += 1

        if deaths:
            frame_deaths[frame_idx] = deaths

    return frame_deaths


def analyze_credit_turret_entities(data: bytes, player_eids_be: set):
    """
    Deep analysis of credit records for turret-range entities.
    Groups credits by entity ID and shows their temporal patterns.
    """
    credits = defaultdict(list)
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
        action = data[pos + 11] if pos + 11 < len(data) else None

        # Only turret/objective range
        if 1000 <= eid <= 20000 and eid not in player_eids_be:
            if 0 <= value <= 100000:
                credits[eid].append({
                    'value': round(value, 2),
                    'action': action,
                    'offset': pos,
                })

        pos += 3

    return credits


def find_nearby_player_credits(data: bytes, offset: int, window: int, player_eids_be: set):
    """Find player credit records near a given offset."""
    start = max(0, offset - window)
    end = min(len(data), offset + window)

    credits = []
    pos = start
    while pos < end:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1 or pos >= end:
            break
        if pos + 12 > len(data):
            pos += 1
            continue

        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 3
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11] if pos + 11 < len(data) else None

        if eid in player_eids_be and 0 <= value <= 100000:
            credits.append({
                'eid': eid,
                'value': round(value, 2),
                'action': f"0x{action:02X}" if action is not None else None,
                'offset': pos,
                'rel_offset': pos - offset,
            })

        pos += 3

    return credits


def analyze_match(match_data, match_idx):
    """Deep analysis of a single match."""
    replay_file = match_data['replay_file']
    match_info = match_data['match_info']
    duration = match_info['duration_seconds']

    print(f"\n{'='*80}")
    print(f"MATCH {match_idx + 1}: Duration={duration}s, Winner={match_info['winner']}")
    print(f"Score: left {match_info['score_left']} - {match_info['score_right']} right")
    print(f"{'='*80}")

    frames = get_replay_frames(replay_file)
    first_frame_data = frames[0].read_bytes()
    players = extract_player_info(first_frame_data)

    player_eids_be = set(p['eid_be'] for p in players.values())
    player_eid_to_name = {p['eid_be']: name for name, p in players.items()}

    print(f"\n  Players: {', '.join(f'{n}({p['eid_be']})' for n, p in players.items())}")

    # Read all data
    all_data = b""
    for frame_path in frames:
        all_data += frame_path.read_bytes()

    # =========================================================================
    # 1. RELAXED KILL ANALYSIS - Focus on non-player [18 04 1C] patterns
    # =========================================================================
    print(f"\n  === RELAXED KILL ANALYSIS ===")
    all_kills = scan_relaxed_kills_with_context(all_data, player_eids_be)

    # Separate by type
    player_full = [k for k in all_kills if k['is_player'] and k['full_valid']]
    player_partial = [k for k in all_kills if k['is_player'] and not k['full_valid']]
    nonplayer_ffff = [k for k in all_kills if not k['is_player'] and k['has_ffff']]
    nonplayer_other = [k for k in all_kills if not k['is_player'] and not k['has_ffff']]

    print(f"  Player kills (full valid):     {len(player_full)}")
    print(f"  Player kill-like (partial):    {len(player_partial)}")
    print(f"  Non-player with [FF FF FF FF]: {len(nonplayer_ffff)}")
    print(f"  Non-player other patterns:     {len(nonplayer_other)}")

    # Analyze the non-player [FF FF FF FF] pattern - what values appear?
    if nonplayer_ffff:
        print(f"\n  Non-player [18 04 1C][00 00][eid][FF FF FF FF][value f32][action]:")
        # Group by (value, action_byte) combination
        pattern_groups = defaultdict(list)
        for k in nonplayer_ffff:
            val_str = f"{k['value']:.2f}" if k['value'] is not None else "None"
            act_str = f"0x{k['action_byte']:02X}" if k['action_byte'] is not None else "None"
            pattern_groups[(val_str, act_str)].append(k)

        for (val, act), events in sorted(pattern_groups.items(), key=lambda x: -len(x[1])):
            eid_ranges = Counter()
            for e in events:
                eid = e['eid']
                if 1000 <= eid <= 19999:
                    eid_ranges['turret'] += 1
                elif 20000 <= eid <= 49999:
                    eid_ranges['minion'] += 1
                elif 50000 <= eid <= 65000:
                    eid_ranges['player_range'] += 1
                else:
                    eid_ranges['other'] += 1
            print(f"    value={val:>10s} action={act:>4s}  count={len(events):4d}  "
                  f"ranges={dict(eid_ranges)}")

        # Show unique (value, action) pairs for turret-range entities specifically
        turret_kills = [k for k in nonplayer_ffff if 1000 <= k['eid'] <= 19999]
        if turret_kills:
            print(f"\n  Turret-range entities with [FF FF FF FF] ({len(turret_kills)} events):")
            # Group by eid
            by_eid = defaultdict(list)
            for k in turret_kills:
                by_eid[k['eid']].append(k)

            for eid in sorted(by_eid.keys())[:30]:
                evs = by_eid[eid]
                vals = [(f"{e['value']:.2f}", f"0x{e['action_byte']:02X}") for e in evs
                        if e['value'] is not None and e['action_byte'] is not None]
                ts_list = [e['timestamp'] for e in evs if e['timestamp']]
                ts_str = f"ts=[{', '.join(f'{t:.0f}' for t in ts_list[:5])}]" if ts_list else ""
                print(f"      eid={eid:5d} ({eid:#06x})  count={len(evs):3d}  "
                      f"patterns={Counter(vals).most_common(5)}  {ts_str}")

    # =========================================================================
    # 2. HIGH-RANGE ENTITY DEATHS (>65000) - Kraken/Gold Mine candidates
    # =========================================================================
    print(f"\n  === HIGH-RANGE ENTITY DEATHS (eid > 65000) ===")
    all_deaths = []
    pos = 0
    while True:
        pos = all_data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00' or all_data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        ts = struct.unpack_from(">f", all_data, pos + 9)[0]

        if not (0 < ts < 1800):
            pos += 1
            continue

        if eid > 65000:
            # Read context around this death
            pre = all_data[max(0, pos-20):pos].hex(' ')
            post = all_data[pos+13:pos+30].hex(' ') if pos + 30 <= len(all_data) else ""
            all_deaths.append({
                'eid': eid,
                'ts': ts,
                'offset': pos,
                'pre': pre,
                'post': post,
            })

        pos += 1

    if all_deaths:
        print(f"  Found {len(all_deaths)} deaths with eid > 65000:")
        by_eid = defaultdict(list)
        for d in all_deaths:
            by_eid[d['eid']].append(d)

        for eid in sorted(by_eid.keys()):
            deaths = by_eid[eid]
            ts_list = [d['ts'] for d in deaths]
            print(f"    eid={eid:5d} ({eid:#06x})  deaths={len(deaths)}  "
                  f"ts={[round(t, 1) for t in ts_list]}")
            # Show context for first death
            if deaths:
                d = deaths[0]
                print(f"      pre: {d['pre']}")
                print(f"      [08 04 31] [00 00] [{eid:04X}] [00 00] [ts f32]")
                print(f"      post: {d['post']}")
    else:
        print("  No deaths found with eid > 65000")

    # =========================================================================
    # 3. TURRET CREDIT ENTITY ANALYSIS
    # =========================================================================
    print(f"\n  === TURRET CREDIT ENTITY ANALYSIS ===")
    turret_credits = analyze_credit_turret_entities(all_data, player_eids_be)

    if turret_credits:
        # Separate low-range (2000-2200) from higher turret range
        low_range = {k: v for k, v in turret_credits.items() if k < 2200}
        high_range = {k: v for k, v in turret_credits.items() if k >= 2200}

        print(f"  Low-range (2000-2199): {len(low_range)} entities, "
              f"{sum(len(v) for v in low_range.values())} records")
        print(f"  High-range (2200+): {len(high_range)} entities, "
              f"{sum(len(v) for v in high_range.values())} records")

        # Analyze low-range (likely turrets/objectives)
        print(f"\n  Low-range turret credit entities:")
        for eid in sorted(low_range.keys()):
            records = low_range[eid]
            value_counts = Counter(r['value'] for r in records)
            action_counts = Counter(r['action'] for r in records)
            print(f"    eid={eid:5d} ({eid:#06x})  records={len(records)}  "
                  f"values={dict(value_counts.most_common(5))}  "
                  f"actions={dict(action_counts.most_common(5))}")

        # For the entity with most records, look at nearby player credits
        if low_range:
            top_eid = max(low_range, key=lambda k: len(low_range[k]))
            top_records = low_range[top_eid]
            print(f"\n  Deep dive: eid={top_eid} ({len(top_records)} records)")
            print(f"  Checking player credits near turret credit records (window=200 bytes):")

            for i, rec in enumerate(top_records[:5]):
                nearby = find_nearby_player_credits(all_data, rec['offset'], 200, player_eids_be)
                if nearby:
                    print(f"    Record {i}: turret_credit at offset {rec['offset']} "
                          f"(val={rec['value']}, act=0x{rec['action']:02X})")
                    for nc in nearby[:5]:
                        pname = player_eid_to_name.get(nc['eid'], '?')
                        print(f"      {nc['rel_offset']:+5d}  player={pname}({nc['eid']})  "
                              f"val={nc['value']}  act={nc['action']}")

    # =========================================================================
    # 4. TURRET DEATH CLUSTERING (per-frame)
    # =========================================================================
    print(f"\n  === TURRET DEATH CLUSTERING ===")
    frame_deaths = scan_deaths_per_frame(frames, player_eids_be)

    # Find frames with multiple turret deaths
    turret_clusters = {}
    for frame_idx, deaths in frame_deaths.items():
        turret_deaths = [d for d in deaths if d['range'] == 'turret']
        if len(turret_deaths) >= 3:
            turret_clusters[frame_idx] = turret_deaths

    if turret_clusters:
        print(f"  Frames with 3+ turret deaths: {len(turret_clusters)}")
        for frame_idx in sorted(turret_clusters.keys()):
            deaths = turret_clusters[frame_idx]
            ts_range = (min(d['ts'] for d in deaths), max(d['ts'] for d in deaths))
            eids = sorted(d['eid'] for d in deaths)
            print(f"    Frame {frame_idx:3d}: {len(deaths)} turret deaths  "
                  f"ts={ts_range[0]:.1f}-{ts_range[1]:.1f}  "
                  f"eids=[{eids[0]}..{eids[-1]}]  "
                  f"range_span={eids[-1]-eids[0]}")

        # Show the biggest cluster (crystal destruction)
        biggest_frame = max(turret_clusters, key=lambda k: len(turret_clusters[k]))
        biggest = turret_clusters[biggest_frame]
        print(f"\n  Biggest cluster: Frame {biggest_frame} ({len(biggest)} turret deaths)")
        # Also check for high-range deaths in same frame
        all_frame_deaths = frame_deaths.get(biggest_frame, [])
        high_deaths = [d for d in all_frame_deaths if d['range'] == 'high']
        if high_deaths:
            print(f"  High-range deaths in same frame: {[(d['eid'], round(d['ts'], 1)) for d in high_deaths]}")
    else:
        print("  No frames with 3+ turret deaths found")

    # =========================================================================
    # 5. SPECIAL ENTITIES: eid 2001 and 2004 (seen across matches)
    # =========================================================================
    print(f"\n  === SPECIAL LOW-RANGE ENTITY DEATHS ===")
    special_deaths = []
    pos = 0
    while True:
        pos = all_data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00' or all_data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        ts = struct.unpack_from(">f", all_data, pos + 9)[0]

        if not (0 < ts < 1800) or eid not in player_eids_be:
            pass  # not filtering yet

        if 2000 <= eid <= 2200 and 0 < ts < 1800:
            special_deaths.append({
                'eid': eid,
                'ts': ts,
                'offset': pos,
            })

        pos += 1

    if special_deaths:
        by_eid = defaultdict(list)
        for d in special_deaths:
            by_eid[d['eid']].append(d)

        print(f"  Deaths in eid 2000-2200:")
        for eid in sorted(by_eid.keys()):
            deaths = by_eid[eid]
            ts_list = [round(d['ts'], 1) for d in deaths]
            print(f"    eid={eid:5d} ({eid:#06x})  deaths={len(deaths)}  ts={ts_list}")

            # Check credit records for this eid
            if eid in turret_credits:
                creds = turret_credits[eid]
                print(f"      Also has {len(creds)} credit records "
                      f"(values={Counter(r['value'] for r in creds).most_common(3)})")
    else:
        print("  No deaths in eid 2000-2200 found")

    # =========================================================================
    # 6. CORRELATE TRUTH DATA: Match score vs detected events
    # =========================================================================
    print(f"\n  === TRUTH CORRELATION ===")
    truth_score_left = match_info['score_left']
    truth_score_right = match_info['score_right']
    truth_total_kills = truth_score_left + truth_score_right

    # Count player kills and deaths
    player_kill_count = len(player_full)
    player_death_count = 0
    pos = 0
    while True:
        pos = all_data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00' or all_data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        ts = struct.unpack_from(">f", all_data, pos + 9)[0]
        if eid in player_eids_be and 0 < ts <= duration + 10:
            player_death_count += 1
        pos += 1

    print(f"  Truth total kills: {truth_total_kills} (left={truth_score_left}, right={truth_score_right})")
    print(f"  Detected player kills (full validation): {player_kill_count}")
    print(f"  Detected player deaths (filtered): {player_death_count}")
    total_turret_deaths = sum(
        1 for deaths_list in frame_deaths.values()
        for d in deaths_list if d.get('range') == 'turret'
    ) if frame_deaths else 0
    print(f"  Non-player turret deaths: {total_turret_deaths}")

    # Count turret credit records per player
    print(f"\n  Turret-related credit records near player entities:")
    for eid in sorted(low_range.keys()) if turret_credits else []:
        records = low_range.get(eid, [])
        if not records:
            continue
        # For each turret credit, find nearby player credits
        player_assoc = Counter()
        for rec in records[:20]:  # Sample
            nearby = find_nearby_player_credits(all_data, rec['offset'], 300, player_eids_be)
            for nc in nearby:
                player_assoc[nc['eid']] += 1
        if player_assoc:
            top_players = [(player_eid_to_name.get(eid, f'?{eid}'), cnt)
                          for eid, cnt in player_assoc.most_common(3)]
            # Not printing this anymore, it's too noisy


def main():
    truth = load_truth()
    matches = truth['matches']

    # Analyze first 3 matches
    num_matches = min(3, len(matches))
    print(f"Deep objective analysis of {num_matches} matches...")

    for i in range(num_matches):
        analyze_match(matches[i], i)


if __name__ == '__main__':
    main()
