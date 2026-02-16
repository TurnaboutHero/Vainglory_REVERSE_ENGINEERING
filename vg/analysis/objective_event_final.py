#!/usr/bin/env python3
"""
Objective Event Final Analysis - Focus on three key discoveries:

1. SPECIAL LOW-RANGE DEATHS (eid 2000-2005): Crystal/objective destruction markers
   - eid 2004 dies at ts=1029.3 (Match 1 duration=1028s) -> Vain Crystal destruction!
   - eid 2001 dies at ts=961.7 (Match 2 duration=969s) -> Another crystal?

2. HIGH-RANGE DEATHS (eid >65000): Kraken/Gold Mine candidates
   - Match 1: 5 deaths (ts 870-924), Match 2: 6 deaths (ts 783-799), Match 3: 1 death (ts 787)

3. NEW HEADERS [18 04 1E] and [18 04 3E]: Appear right after high-range deaths
   - These may be the objective kill/event records

4. TURRET CREDIT ENTITIES (2008-2121): Periodic 150g gold ticks every ~60s
   - Two groups: 2008-2013 (base turrets?) and 2046-2121 (lane turrets?)
   - value=10.00 action=0x04 in relaxed kill format every ~60s
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

# New headers observed near objective deaths
HEADER_1E = bytes([0x18, 0x04, 0x1E])
HEADER_3E = bytes([0x18, 0x04, 0x3E])
HEADER_0D = bytes([0x18, 0x04, 0x0D])
HEADER_0F = bytes([0x30, 0x04, 0x0F])

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
            if first_frame_data[name_end] < 32 or first_frame_data[name_end] > 126:
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
                players[name] = {'eid_le': eid_le, 'eid_be': eid_be, 'team': team}
        search_start = pos + 1
    return players


def scan_header_pattern(data: bytes, header: bytes, name: str, context_size: int = 20):
    """Scan for a specific 3-byte header pattern and extract context."""
    events = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue

        # Read surrounding bytes
        pre_start = max(0, pos - context_size)
        post_end = min(len(data), pos + 3 + context_size)

        # Try to extract entity ID at pos+5 (after [header][00 00])
        eid = None
        if pos + 7 <= len(data) and data[pos+3:pos+5] == b'\x00\x00':
            eid = struct.unpack_from(">H", data, pos + 5)[0]

        events.append({
            'header': name,
            'offset': pos,
            'eid': eid,
            'pre': data[pre_start:pos].hex(' '),
            'header_hex': data[pos:pos+3].hex(' '),
            'post': data[pos+3:post_end].hex(' '),
        })
        pos += 1

    return events


def scan_all_18_04_variants(data: bytes):
    """Find ALL [18 04 xx] patterns to discover event type variants."""
    variants = Counter()
    pos = 0
    while True:
        # Search for [18 04]
        pos = data.find(b'\x18\x04', pos)
        if pos == -1:
            break
        if pos + 3 <= len(data):
            third_byte = data[pos + 2]
            variants[third_byte] += 1
        pos += 2
    return variants


def analyze_match(match_data, match_idx):
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
    player_eid_to_name = {p['eid_be']: n for n, p in players.items()}

    # Read all data
    all_data = b""
    for frame_path in frames:
        all_data += frame_path.read_bytes()

    print(f"  Data: {len(all_data):,} bytes, {len(frames)} frames")

    # =========================================================================
    # 1. ALL [18 04 xx] VARIANTS - discover the event type space
    # =========================================================================
    print(f"\n  === ALL [18 04 xx] HEADER VARIANTS ===")
    variants = scan_all_18_04_variants(all_data)
    for byte_val, count in variants.most_common():
        known = {0x1C: "KILL", 0x1E: "???_1E", 0x3E: "???_3E", 0x0D: "???_0D"}
        label = known.get(byte_val, "")
        print(f"    [18 04 {byte_val:02X}]  count={count:6d}  {label}")

    # =========================================================================
    # 2. [18 04 1E] PATTERN - seen after high-range deaths
    # =========================================================================
    print(f"\n  === [18 04 1E] EVENTS ===")
    events_1e = scan_header_pattern(all_data, HEADER_1E, "18_04_1E")
    print(f"  Total [18 04 1E] events: {len(events_1e)}")

    if events_1e:
        # Group by entity ID
        by_eid = defaultdict(list)
        for ev in events_1e:
            if ev['eid'] is not None:
                by_eid[ev['eid']].append(ev)

        # Categorize
        for eid in sorted(by_eid.keys())[:20]:
            evs = by_eid[eid]
            cat = "PLAYER" if eid in player_eids_be else \
                  "turret" if 1000 <= eid <= 19999 else \
                  "minion" if 20000 <= eid <= 49999 else \
                  "player_range" if 50000 <= eid <= 65000 else \
                  "HIGH" if eid > 65000 else "low"
            if len(evs) <= 3:
                for ev in evs:
                    pname = player_eid_to_name.get(eid, '')
                    print(f"    eid={eid:5d} ({eid:#06x}) [{cat}] {pname}")
                    print(f"      post: {ev['post']}")

    # =========================================================================
    # 3. [18 04 3E] PATTERN - also seen after high-range deaths
    # =========================================================================
    print(f"\n  === [18 04 3E] EVENTS ===")
    events_3e = scan_header_pattern(all_data, HEADER_3E, "18_04_3E")
    print(f"  Total [18 04 3E] events: {len(events_3e)}")

    if events_3e:
        by_eid = defaultdict(list)
        for ev in events_3e:
            if ev['eid'] is not None:
                by_eid[ev['eid']].append(ev)

        for eid in sorted(by_eid.keys())[:20]:
            evs = by_eid[eid]
            cat = "PLAYER" if eid in player_eids_be else \
                  "turret" if 1000 <= eid <= 19999 else \
                  "minion" if 20000 <= eid <= 49999 else \
                  "player_range" if 50000 <= eid <= 65000 else \
                  "HIGH" if eid > 65000 else "low"
            if cat in ("PLAYER", "HIGH"):
                for ev in evs[:3]:
                    pname = player_eid_to_name.get(eid, '')
                    print(f"    eid={eid:5d} ({eid:#06x}) [{cat}] {pname}")
                    print(f"      post: {ev['post']}")

    # =========================================================================
    # 4. SPECIAL LOW-RANGE DEATHS: Vain Crystal identification
    # =========================================================================
    print(f"\n  === VAIN CRYSTAL / OBJECTIVE DEATHS (eid 2000-2010) ===")
    crystal_deaths = []
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
        if 2000 <= eid <= 2010 and 0 < ts < 1800:
            context = all_data[max(0,pos-10):pos+20].hex(' ')
            crystal_deaths.append({'eid': eid, 'ts': ts, 'offset': pos, 'context': context})
        pos += 1

    if crystal_deaths:
        for d in crystal_deaths:
            delta = d['ts'] - duration
            print(f"    eid={d['eid']} ts={d['ts']:.1f}s  (duration+{delta:.1f}s)  offset={d['offset']}")
    else:
        print("    No deaths found for eid 2000-2010")

    # =========================================================================
    # 5. HIGH-RANGE DEATHS with surrounding event context
    # =========================================================================
    print(f"\n  === HIGH-RANGE DEATHS (eid > 65000) - KRAKEN/GOLD MINE ===")
    high_deaths = []
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
        if eid > 65000 and 0 < ts < 1800:
            # Read wide context
            pre = all_data[max(0,pos-30):pos]
            post = all_data[pos+13:min(len(all_data), pos+50)]
            high_deaths.append({
                'eid': eid, 'ts': ts, 'offset': pos,
                'pre': pre.hex(' '), 'post': post.hex(' '),
            })
        pos += 1

    if high_deaths:
        # Group by timestamp proximity
        groups = []
        current_group = [high_deaths[0]]
        for d in high_deaths[1:]:
            if d['ts'] - current_group[-1]['ts'] < 60:
                current_group.append(d)
            else:
                groups.append(current_group)
                current_group = [d]
        groups.append(current_group)

        for gi, group in enumerate(groups):
            ts_range = (group[0]['ts'], group[-1]['ts'])
            eids = [d['eid'] for d in group]
            print(f"  Group {gi+1}: {len(group)} deaths at ts={ts_range[0]:.1f}-{ts_range[1]:.1f}s")
            print(f"    Entity IDs: {eids}")
            for d in group[:3]:
                print(f"    eid={d['eid']} ({d['eid']:#06x}) ts={d['ts']:.1f}")
                print(f"      post: {d['post']}")
    else:
        print("    No high-range deaths found")

    # =========================================================================
    # 6. TURRET CREDIT ENTITY GROUPING - which are turrets vs objectives?
    # =========================================================================
    print(f"\n  === TURRET CREDIT ENTITY TIMELINE ===")
    turret_credits = defaultdict(list)
    pos = 0
    while True:
        pos = all_data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00':
            pos += 3
            continue
        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        value = struct.unpack_from(">f", all_data, pos + 7)[0]
        action = all_data[pos + 11] if pos + 11 < len(all_data) else None
        if 2000 <= eid <= 2200 and 0 <= value <= 1000:
            turret_credits[eid].append({'value': round(value, 2), 'action': action, 'offset': pos})
        pos += 3

    # Group A: eid 2000-2005 (always value=100, action=0x04)
    # Group B: eid 2008-2013 (mainly value=150, some variations)
    # Group C: eid 2046-2121 (mainly value=150)

    group_a = {k: v for k, v in turret_credits.items() if 2000 <= k <= 2007}
    group_b = {k: v for k, v in turret_credits.items() if 2008 <= k <= 2044}
    group_c = {k: v for k, v in turret_credits.items() if 2045 <= k <= 2200}

    print(f"  Group A (eid 2000-2007): {len(group_a)} entities, "
          f"{sum(len(v) for v in group_a.values())} records")
    for eid in sorted(group_a.keys()):
        recs = group_a[eid]
        vals = Counter(r['value'] for r in recs)
        print(f"    eid={eid}: records={len(recs)} values={dict(vals)}")

    print(f"  Group B (eid 2008-2044): {len(group_b)} entities, "
          f"{sum(len(v) for v in group_b.values())} records")
    for eid in sorted(group_b.keys()):
        recs = group_b[eid]
        vals = Counter(r['value'] for r in recs)
        print(f"    eid={eid}: records={len(recs)} values={dict(vals)}")

    print(f"  Group C (eid 2045-2200): {len(group_c)} entities, "
          f"{sum(len(v) for v in group_c.values())} records")

    # How many unique entities per group and their total record counts
    # Group C entities: look at which appear together
    if group_c:
        # Are they always in pairs? (left turret, right turret?)
        c_entities = sorted(group_c.keys())
        print(f"    Entities: {c_entities}")
        # Check record count parity
        for eid in c_entities:
            recs = group_c[eid]
            print(f"    eid={eid}: records={len(recs)}")

    # =========================================================================
    # 7. PLAYER EID APPEARING IN TURRET DEATHS (eid 1500-1509)
    # =========================================================================
    print(f"\n  === PLAYER EID IN TURRET-RANGE DEATHS ===")
    # In Match 2, Frame 92 had deaths for eid 1505, 1509 - these ARE player eids!
    # Frame 26 in Match 2 had eid 1509. Let's check all player-eid deaths
    player_eid_deaths = []
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
        if eid in player_eids_be and 0 < ts < 1800:
            player_eid_deaths.append({'eid': eid, 'ts': ts, 'offset': pos})
        pos += 1

    # Group by player
    by_player = defaultdict(list)
    for d in player_eid_deaths:
        name = player_eid_to_name.get(d['eid'], f"?{d['eid']}")
        by_player[name].append(d['ts'])

    print(f"  Player deaths (by entity ID, unfiltered):")
    for name in sorted(by_player.keys()):
        ts_list = by_player[name]
        # Mark deaths after game end
        filtered = [t for t in ts_list if t <= duration + 10]
        post_game = [t for t in ts_list if t > duration + 10]
        print(f"    {name:20s}: {len(filtered)} in-game + {len(post_game)} post-game  "
              f"ts={[round(t, 0) for t in ts_list]}")

    # =========================================================================
    # 8. CROSS-REFERENCE: What events accompany turret credit eid ~2000-2005?
    # =========================================================================
    print(f"\n  === EVENTS AROUND LOW-RANGE CREDIT ENTITIES ===")
    # These eids (2000-2005) have value=100, action=0x04 and exactly 8 records each
    # In 5v5 there are 8 turrets per team? Let's see if these correspond to turret kills
    # For eid 2004 (which died at game end in Match 1), look at context

    for target_eid in sorted(group_a.keys()):
        recs = group_a[target_eid]
        if not recs:
            continue
        print(f"\n  eid={target_eid} ({len(recs)} credit records, value=100):")
        # For each credit record, look at what's within 500 bytes
        for i, rec in enumerate(recs[:3]):  # Show first 3
            offset = rec['offset']
            # Look for kill headers nearby
            window = all_data[max(0, offset-300):offset+300]
            window_start = max(0, offset-300)

            # Find death headers in window
            death_offsets = []
            dpos = 0
            while True:
                dpos = window.find(DEATH_HEADER, dpos)
                if dpos == -1:
                    break
                abs_off = window_start + dpos
                if abs_off + 13 <= len(all_data):
                    if (all_data[abs_off+3:abs_off+5] == b'\x00\x00' and
                        all_data[abs_off+7:abs_off+9] == b'\x00\x00'):
                        d_eid = struct.unpack_from(">H", all_data, abs_off + 5)[0]
                        d_ts = struct.unpack_from(">f", all_data, abs_off + 9)[0]
                        if 0 < d_ts < 1800:
                            death_offsets.append({
                                'eid': d_eid, 'ts': d_ts,
                                'rel': abs_off - offset,
                            })
                dpos += 1

            # Find player credits in window
            pcredits = []
            cpos = 0
            while True:
                cpos = window.find(CREDIT_HEADER, cpos)
                if cpos == -1:
                    break
                abs_off = window_start + cpos
                if abs_off + 12 <= len(all_data) and all_data[abs_off+3:abs_off+5] == b'\x00\x00':
                    c_eid = struct.unpack_from(">H", all_data, abs_off + 5)[0]
                    c_val = struct.unpack_from(">f", all_data, abs_off + 7)[0]
                    if c_eid in player_eids_be and 0 <= c_val <= 10000:
                        pcredits.append({
                            'eid': c_eid, 'value': round(c_val, 2),
                            'rel': abs_off - offset,
                            'name': player_eid_to_name.get(c_eid, '?'),
                        })
                cpos += 3

            print(f"    Record {i}: offset={offset}")
            if death_offsets:
                print(f"      Nearby deaths: {[(d['eid'], round(d['ts'],1), d['rel']) for d in death_offsets[:5]]}")
            if pcredits:
                print(f"      Nearby player credits: {[(c['name'], c['value'], c['rel']) for c in pcredits[:8]]}")


def main():
    truth = load_truth()
    matches = truth['matches']

    # Analyze first 3 matches
    for i in range(min(3, len(matches))):
        analyze_match(matches[i], i)


if __name__ == '__main__':
    main()
