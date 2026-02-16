#!/usr/bin/env python3
"""
Team Label Position Research
==============================
Search for X/Y coordinate data in player state events [18 04 3E]
that could distinguish left team from right team based on map position.

Approach:
1. Find [18 04 3E] events that reference known player entity IDs
2. Extract payload bytes at every possible offset
3. Interpret as float32 and check if any offset discriminates left vs right
4. Focus on early-game frames (first 30s) where teams are at spawn positions

Also tries:
- [18 04 1E] entity state events
- Turret death → credit correlation for team mapping
- Any float32 in player block that differs between teams
"""

import json
import struct
import sys
import math
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])

# Event headers
PLAYER_STATE_HEADER = bytes([0x18, 0x04, 0x3E])
ENTITY_STATE_HEADER = bytes([0x18, 0x04, 0x1E])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def parse_player_blocks(data):
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    while True:
        pos = -1
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
        if pos == -1:
            break
        name_start = pos + 3
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            if data[name_end] < 32 or data[name_end] > 126:
                break
            name_end += 1
        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""
            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                eid_le = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little') if pos + 0xA7 <= len(data) else None
                team_id = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                players.append({
                    'name': name,
                    'eid_le': eid_le,
                    'eid_be': le_to_be(eid_le) if eid_le else None,
                    'team_id': team_id,
                    'block_offset': pos,
                })
                seen.add(name)
        search_start = pos + 1
    return players


def load_frames(replay_file, max_frames=None):
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))
    if max_frames:
        frames = frames[:max_frames]
    return [(int(f.stem.split('.')[-1]), f.read_bytes()) for f in frames]


def find_header_events(data, header, valid_eids_be, max_events=100):
    """Find events with given header that reference valid player entity IDs.

    Tries multiple structures:
    A: [header 3B][00 00][eid_BE 2B][payload...]
    B: [header 3B][eid_BE 2B][payload...]
    """
    events = []
    pos = 0
    while len(events) < max_events:
        pos = data.find(header, pos)
        if pos == -1:
            break

        # Structure A: [header][00 00][eid_BE]
        if pos + 7 <= len(data) and data[pos+3:pos+5] == b'\x00\x00':
            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid in valid_eids_be:
                # Extract next 40 bytes as payload
                payload_start = pos + 3  # after header
                payload = data[payload_start:payload_start + 50] if payload_start + 50 <= len(data) else data[payload_start:]
                events.append({
                    'eid_be': eid,
                    'offset': pos,
                    'structure': 'A',
                    'payload': payload,
                })

        # Structure B: [header][eid_BE] (no 00 00 gap)
        if pos + 5 <= len(data):
            eid = struct.unpack_from(">H", data, pos + 3)[0]
            if eid in valid_eids_be and not any(e['offset'] == pos for e in events):
                payload_start = pos + 3
                payload = data[payload_start:payload_start + 50] if payload_start + 50 <= len(data) else data[payload_start:]
                events.append({
                    'eid_be': eid,
                    'offset': pos,
                    'structure': 'B',
                    'payload': payload,
                })

        pos += 1

    return events


def scan_float_offsets(events_by_team, payload_len=40):
    """For each byte offset, interpret as float32 and check left/right separation.

    Returns: list of (offset, avg_left, avg_right, separation) sorted by separation.
    """
    results = []

    for offset in range(0, payload_len - 3):
        left_vals = []
        right_vals = []

        for team, events in events_by_team.items():
            for ev in events:
                if offset + 4 <= len(ev['payload']):
                    val = struct.unpack_from(">f", ev['payload'], offset)[0]
                    if not math.isnan(val) and not math.isinf(val) and abs(val) < 10000:
                        if team == 'left':
                            left_vals.append(val)
                        else:
                            right_vals.append(val)

        if left_vals and right_vals:
            avg_l = sum(left_vals) / len(left_vals)
            avg_r = sum(right_vals) / len(right_vals)
            std_l = (sum((v - avg_l)**2 for v in left_vals) / len(left_vals)) ** 0.5 if len(left_vals) > 1 else 999
            std_r = (sum((v - avg_r)**2 for v in right_vals) / len(right_vals)) ** 0.5 if len(right_vals) > 1 else 999

            # Separation metric: |avg_l - avg_r| / max(std_l + std_r, 0.01)
            separation = abs(avg_l - avg_r) / max(std_l + std_r, 0.01) if (std_l + std_r) > 0 else 0

            results.append({
                'offset': offset,
                'avg_left': avg_l,
                'avg_right': avg_r,
                'std_left': std_l,
                'std_right': std_r,
                'separation': separation,
                'n_left': len(left_vals),
                'n_right': len(right_vals),
            })

    # Also try little-endian float
    for offset in range(0, payload_len - 3):
        left_vals = []
        right_vals = []

        for team, events in events_by_team.items():
            for ev in events:
                if offset + 4 <= len(ev['payload']):
                    val = struct.unpack_from("<f", ev['payload'], offset)[0]
                    if not math.isnan(val) and not math.isinf(val) and abs(val) < 10000:
                        if team == 'left':
                            left_vals.append(val)
                        else:
                            right_vals.append(val)

        if left_vals and right_vals:
            avg_l = sum(left_vals) / len(left_vals)
            avg_r = sum(right_vals) / len(right_vals)
            std_l = (sum((v - avg_l)**2 for v in left_vals) / len(left_vals)) ** 0.5 if len(left_vals) > 1 else 999
            std_r = (sum((v - avg_r)**2 for v in right_vals) / len(right_vals)) ** 0.5 if len(right_vals) > 1 else 999

            separation = abs(avg_l - avg_r) / max(std_l + std_r, 0.01) if (std_l + std_r) > 0 else 0

            results.append({
                'offset': offset,
                'avg_left': avg_l,
                'avg_right': avg_r,
                'std_left': std_l,
                'std_right': std_r,
                'separation': separation,
                'n_left': len(left_vals),
                'n_right': len(right_vals),
                'endian': 'LE',
            })

    results.sort(key=lambda x: -x['separation'])
    return results


def research_player_state_events(truth_data):
    """Research [18 04 3E] player state events for position data."""
    print("=" * 80)
    print("RESEARCH 1: [18 04 3E] Player State Events - Position Data")
    print("=" * 80)

    # Use first 3 matches for discovery
    for mi, match in enumerate(truth_data['matches'][:3]):
        match_num = mi + 1
        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)

        # Build truth team map
        eid_to_truth = {}
        for pname, pdata in match['players'].items():
            for p in players:
                short = pname.split('_', 1)[1] if '_' in pname else pname
                if p['name'] == short or p['name'] == pname:
                    eid_to_truth[p['eid_be']] = pdata['team']
                    break

        valid_eids = set(p['eid_be'] for p in players if p['eid_be'])

        # Load first 3 frames only (early game = spawn positions)
        frames = load_frames(replay_file, max_frames=3)

        print(f"\n  M{match_num}: {len(frames)} frames loaded")
        print(f"  Player eids (BE): {sorted(valid_eids)}")

        # Find [18 04 3E] events
        for fi, fdata in frames[:1]:  # Just first frame
            events = find_header_events(fdata, PLAYER_STATE_HEADER, valid_eids, max_events=200)

            if not events:
                print(f"    Frame {fi}: No [18 04 3E] events found with player eids")
                # Try broader search - check what eids appear after header
                pos = 0
                sample_eids = set()
                count = 0
                while count < 20:
                    pos = fdata.find(PLAYER_STATE_HEADER, pos)
                    if pos == -1:
                        break
                    if pos + 7 <= len(fdata):
                        # Try various offsets for eid
                        for eid_off in [3, 5, 7]:
                            if pos + eid_off + 2 <= len(fdata):
                                eid_be = struct.unpack_from(">H", fdata, pos + eid_off)[0]
                                eid_le = struct.unpack_from("<H", fdata, pos + eid_off)[0]
                                sample_eids.add((eid_off, eid_be, eid_le))
                    count += 1
                    pos += 1

                print(f"    Sample eids near header (first 20):")
                for eid_off, eid_be, eid_le in sorted(sample_eids)[:30]:
                    marker = " <-- PLAYER" if eid_be in valid_eids or eid_le in valid_eids else ""
                    print(f"      offset+{eid_off}: BE={eid_be}, LE={eid_le}{marker}")
                continue

            # Group events by truth team
            events_by_team = {'left': [], 'right': []}
            for ev in events:
                team = eid_to_truth.get(ev['eid_be'])
                if team:
                    events_by_team[team].append(ev)

            print(f"    Frame {fi}: {len(events)} [18 04 3E] events")
            print(f"    By team: left={len(events_by_team['left'])}, right={len(events_by_team['right'])}")

            if events_by_team['left'] and events_by_team['right']:
                # Scan for discriminating float offsets
                top_offsets = scan_float_offsets(events_by_team, payload_len=45)

                print(f"\n    Top 10 discriminating float offsets:")
                print(f"    {'Off':>4s} {'Endian':>6s} {'AvgL':>8s} {'AvgR':>8s} {'StdL':>8s} {'StdR':>8s} {'Sep':>6s} {'nL':>3s} {'nR':>3s}")
                for r in top_offsets[:10]:
                    endian = r.get('endian', 'BE')
                    print(f"    {r['offset']:4d} {endian:>6s} {r['avg_left']:8.1f} {r['avg_right']:8.1f} "
                          f"{r['std_left']:8.1f} {r['std_right']:8.1f} {r['separation']:6.2f} "
                          f"{r['n_left']:3d} {r['n_right']:3d}")

            # Also dump raw payload hex for first event of each team
            for team in ['left', 'right']:
                if events_by_team[team]:
                    ev = events_by_team[team][0]
                    hex_str = ' '.join(f'{b:02X}' for b in ev['payload'][:40])
                    print(f"\n    Sample {team} (eid={ev['eid_be']}, struct={ev['structure']}):")
                    print(f"    {hex_str}")


def research_entity_event_format(truth_data):
    """Research the general event format near [18 04 3E] headers."""
    print("\n" + "=" * 80)
    print("RESEARCH 2: Event Format Analysis near [18 04 3E]")
    print("=" * 80)

    match = truth_data['matches'][0]
    replay_file = match['replay_file']
    if not Path(replay_file).exists():
        return

    with open(replay_file, 'rb') as f:
        frame0 = f.read()
    players = parse_player_blocks(frame0)
    valid_eids_be = set(p['eid_be'] for p in players if p['eid_be'])

    frames = load_frames(replay_file, max_frames=2)

    # Count total occurrences
    for fi, fdata in frames[:1]:
        total_3e = fdata.count(PLAYER_STATE_HEADER)
        total_1e = fdata.count(ENTITY_STATE_HEADER)

        print(f"\n  Frame {fi}: [18 04 3E] x {total_3e}, [18 04 1E] x {total_1e}")

        # Dump context around first 5 occurrences
        pos = 0
        for i in range(5):
            pos = fdata.find(PLAYER_STATE_HEADER, pos)
            if pos == -1:
                break

            # Show 10 bytes before and 40 bytes after
            pre = max(0, pos - 10)
            post = min(len(fdata), pos + 50)
            context = fdata[pre:post]

            # Mark the header position
            header_rel = pos - pre
            hex_parts = []
            for j, b in enumerate(context):
                if j == header_rel:
                    hex_parts.append(f'[{b:02X}')
                elif j == header_rel + 2:
                    hex_parts.append(f'{b:02X}]')
                else:
                    hex_parts.append(f'{b:02X}')

            hex_str = ' '.join(hex_parts)

            # Check if any nearby bytes match player eids
            eid_notes = []
            for off in range(0, min(40, post - pos)):
                if pos + off + 2 <= len(fdata):
                    eid = struct.unpack_from(">H", fdata, pos + off)[0]
                    if eid in valid_eids_be:
                        eid_notes.append(f"+{off}:BE={eid}")
                    eid = struct.unpack_from("<H", fdata, pos + off)[0]
                    if eid in valid_eids_be:
                        eid_notes.append(f"+{off}:LE={eid}")

            print(f"\n    #{i+1} @{pos}: {hex_str}")
            if eid_notes:
                print(f"       Player eids: {', '.join(eid_notes)}")

            pos += 1


def research_turret_death_credits(truth_data):
    """Research turret death events and nearby credit records."""
    print("\n" + "=" * 80)
    print("RESEARCH 3: Turret Death → Credit Records → Team Mapping")
    print("=" * 80)

    match = truth_data['matches'][0]  # Use M1
    replay_file = match['replay_file']
    if not Path(replay_file).exists():
        return

    with open(replay_file, 'rb') as f:
        frame0 = f.read()
    players = parse_player_blocks(frame0)

    # Build truth team map
    eid_to_truth = {}
    eid_to_name = {}
    for p in players:
        for pname, pdata in match['players'].items():
            short = pname.split('_', 1)[1] if '_' in pname else pname
            if p['name'] == short or p['name'] == pname:
                eid_to_truth[p['eid_be']] = pdata['team']
                eid_to_name[p['eid_be']] = p['name']
                break

    valid_eids = set(p['eid_be'] for p in players if p['eid_be'])

    # Load ALL frames
    frames = load_frames(replay_file)
    all_data = b"".join(data for _, data in frames)

    # Find turret/structure death events (eid 2000-2200 range)
    turret_deaths = []
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
        if 2000 <= eid <= 2200 and 0 < ts < 2000:
            turret_deaths.append({'eid_be': eid, 'ts': ts, 'offset': pos})
        pos += 1

    print(f"\n  Turret/structure deaths (eid 2000-2200): {len(turret_deaths)}")

    # For each turret death, find nearby player credit records
    for td in turret_deaths[:10]:
        # Find credit records within ±500 bytes
        credits = []
        search_start = max(0, td['offset'] - 500)
        search_end = min(len(all_data), td['offset'] + 2000)

        cpos = search_start
        while cpos < search_end:
            cpos = all_data.find(CREDIT_HEADER, cpos)
            if cpos == -1 or cpos >= search_end:
                break
            if cpos + 12 <= len(all_data) and all_data[cpos+3:cpos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", all_data, cpos + 5)[0]
                value = struct.unpack_from(">f", all_data, cpos + 7)[0]
                action = all_data[cpos + 11]

                if eid in valid_eids:
                    credits.append({
                        'eid_be': eid,
                        'value': value,
                        'action': action,
                        'rel_offset': cpos - td['offset'],
                        'team': eid_to_truth.get(eid, '?'),
                        'name': eid_to_name.get(eid, '?'),
                    })
            cpos += 1

        # Filter to action=0x04 (turret bounty) credits that come AFTER the death
        after_bounty = [c for c in credits if c['action'] == 0x04 and c['rel_offset'] > 0]

        print(f"\n  Turret eid={td['eid_be']}, ts={td['ts']:.1f}s:")
        if after_bounty:
            teams = set(c['team'] for c in after_bounty)
            team_str = ', '.join(f"{c['name']}({c['team']}) val={c['value']:.0f}" for c in after_bounty[:5])
            print(f"    → Bounty credits ({len(after_bounty)}): {team_str}")
            print(f"    → Killing team: {teams}")
        else:
            # Show what credits ARE nearby
            nearby = [c for c in credits if abs(c['rel_offset']) < 500][:5]
            if nearby:
                for c in nearby:
                    print(f"    Credit: {c['name']}({c['team']}) val={c['value']:.1f} action=0x{c['action']:02X} @{c['rel_offset']:+d}")
            else:
                print(f"    No player credits within ±500 bytes")


def research_player_block_floats(truth_data):
    """Search for discriminating float values within player blocks."""
    print("\n" + "=" * 80)
    print("RESEARCH 4: Player Block Float Scan")
    print("=" * 80)
    print("  Scan every 4-byte window in player block for floats that")
    print("  consistently differ between left and right teams.")

    all_offsets = defaultdict(lambda: {'left': [], 'right': []})

    for mi, match in enumerate(truth_data['matches'][:5]):
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)

        for p in players:
            # Find truth team
            truth_team = None
            for pname, pdata in match['players'].items():
                short = pname.split('_', 1)[1] if '_' in pname else pname
                if p['name'] == short or p['name'] == pname:
                    truth_team = pdata['team']
                    break

            if not truth_team:
                continue

            # Scan player block for floats (300 bytes after marker)
            block_start = p['block_offset']
            for off in range(0, 300):
                abs_off = block_start + off
                if abs_off + 4 > len(frame0):
                    break

                # Big endian float
                val_be = struct.unpack_from(">f", frame0, abs_off)[0]
                if not math.isnan(val_be) and not math.isinf(val_be) and 0.1 < abs(val_be) < 5000:
                    all_offsets[(off, 'BE')][truth_team].append(val_be)

                # Little endian float
                val_le = struct.unpack_from("<f", frame0, abs_off)[0]
                if not math.isnan(val_le) and not math.isinf(val_le) and 0.1 < abs(val_le) < 5000:
                    all_offsets[(off, 'LE')][truth_team].append(val_le)

    # Find offsets with best separation
    scored = []
    for (off, endian), teams in all_offsets.items():
        if len(teams['left']) >= 5 and len(teams['right']) >= 5:
            avg_l = sum(teams['left']) / len(teams['left'])
            avg_r = sum(teams['right']) / len(teams['right'])
            std_l = (sum((v - avg_l)**2 for v in teams['left']) / len(teams['left'])) ** 0.5
            std_r = (sum((v - avg_r)**2 for v in teams['right']) / len(teams['right'])) ** 0.5

            sep = abs(avg_l - avg_r) / max(std_l + std_r, 0.01)
            scored.append({
                'offset': off,
                'endian': endian,
                'avg_left': avg_l,
                'avg_right': avg_r,
                'std_left': std_l,
                'std_right': std_r,
                'sep': sep,
                'n': len(teams['left']) + len(teams['right']),
            })

    scored.sort(key=lambda x: -x['sep'])

    print(f"\n  Scanned {len(all_offsets)} offset/endian combos")
    print(f"\n  Top 15 discriminating offsets:")
    print(f"  {'Off':>4s} {'End':>3s} {'AvgL':>8s} {'AvgR':>8s} {'StdL':>6s} {'StdR':>6s} {'Sep':>6s} {'N':>3s}")
    for r in scored[:15]:
        print(f"  {r['offset']:4d} {r['endian']:>3s} {r['avg_left']:8.1f} {r['avg_right']:8.1f} "
              f"{r['std_left']:6.1f} {r['std_right']:6.1f} {r['sep']:6.2f} {r['n']:3d}")


def main():
    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    research_entity_event_format(truth_data)
    research_player_state_events(truth_data)
    research_turret_death_credits(truth_data)
    research_player_block_floats(truth_data)

    print("\n" + "=" * 80)
    print("RESEARCH COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
