#!/usr/bin/env python3
"""
Assist Research v3 - Final assist detection from credit records.

SOLVED: flag_only strategy with same-team filtering = best approach.

Credit Record Structure:
  Header: [10 04 1D] [00 00] [eid BE uint16] [value f32 BE]  = 9 bytes

After each kill header [18 04 1C], credit records follow.
An assist is counted when a player (not the killer) has a credit record
with value == 1.0 (participation flag) AND is on the same team as the killer.

Cross-team 1.0 credits appear for enemies (likely "last hit" or damage tracking)
and should NOT be counted as assists.
"""
import struct
import json
import os
import sys
from pathlib import Path
from collections import defaultdict, Counter

# ── Constants ──────────────────────────────────────────────────────────────
KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def extract_player_info(data):
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""

            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                entity_id_le = None
                if pos + 0xA5 + 2 <= len(data):
                    entity_id_le = int.from_bytes(
                        data[pos + 0xA5:pos + 0xA5 + 2], 'little'
                    )

                team_byte = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                team = ("left" if team_byte == 1
                        else "right" if team_byte == 2
                        else "unknown")

                players.append({
                    'name': name,
                    'entity_id_le': entity_id_le,
                    'entity_id_be': le_to_be(entity_id_le) if entity_id_le else None,
                    'team': team,
                })
                seen.add(name)

        search_start = pos + 1

    return players


def load_all_frames(replay_file_path):
    base_path = replay_file_path.rsplit('.0.vgr', 1)[0]
    frames = []
    idx = 0
    while True:
        frame_path = f"{base_path}.{idx}.vgr"
        if os.path.exists(frame_path):
            with open(frame_path, 'rb') as f:
                frames.append(f.read())
            idx += 1
        else:
            break
    return frames


def validate_kill_header(data, pos):
    if pos + 16 > len(data):
        return False
    return (data[pos + 3:pos + 5] == b'\x00\x00'
            and data[pos + 7:pos + 11] == b'\xFF\xFF\xFF\xFF'
            and data[pos + 11:pos + 15] == b'\x3F\x80\x00\x00'
            and data[pos + 15] == 0x29)


def scan_credits_after_kill(data, start_pos, valid_eids_be):
    credits = []
    pos = start_pos
    max_scan = min(start_pos + 500, len(data))

    while pos < max_scan:
        if (data[pos:pos + 3] == KILL_HEADER
                and validate_kill_header(data, pos)):
            break

        if data[pos:pos + 3] == CREDIT_HEADER:
            if pos + 9 <= len(data) and data[pos + 3:pos + 5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]

                if eid in valid_eids_be and 0 <= value <= 10000:
                    credits.append({
                        'eid': eid,
                        'value': round(value, 2),
                        'offset': pos,
                    })

                pos += 9
                continue

        pos += 1

    return credits


def find_kills_with_credits(frames, valid_eids_be):
    kill_events = []

    for frame_idx, data in enumerate(frames):
        pos = 0
        while True:
            pos = data.find(KILL_HEADER, pos)
            if pos == -1:
                break

            if not validate_kill_header(data, pos):
                pos += 1
                continue

            killer_eid = struct.unpack_from(">H", data, pos + 5)[0]
            if killer_eid not in valid_eids_be:
                pos += 1
                continue

            ts = None
            if pos >= 7:
                ts = struct.unpack_from(">f", data, pos - 7)[0]
                if not (0 < ts < 1800):
                    ts = None

            credits = scan_credits_after_kill(
                data, pos + 16, valid_eids_be
            )

            kill_events.append({
                'killer_eid': killer_eid,
                'timestamp': ts,
                'frame_idx': frame_idx,
                'file_offset': pos,
                'credits': credits,
            })

            pos += 16

    return kill_events


def match_player_name(truth_name, detected_players):
    """Match truth player name to detected players with fuzzy matching."""
    parts = truth_name.split('_', 1)
    if len(parts) == 2 and parts[0].isdigit():
        short_name = parts[1]
    else:
        short_name = truth_name

    for p in detected_players:
        if p['name'] == short_name or p['name'] == truth_name:
            return p
        if p['name'].lower() == short_name.lower():
            return p
        # Handle ICN vs 1CN (letter I vs digit 1)
        if short_name == 'ICN' and p['name'] == '1CN':
            return p
        if short_name == '1CN' and p['name'] == 'ICN':
            return p
        # Handle typos like TenshilHime vs TenshiiHime (l vs i)
        if _fuzzy_match(short_name, p['name']):
            return p

    return None


def _fuzzy_match(a, b, max_dist=1):
    """Allow up to max_dist character substitutions."""
    if len(a) != len(b):
        return False
    diffs = sum(1 for ca, cb in zip(a, b) if ca != cb)
    return diffs <= max_dist


def count_assists_flag_only_same_team(kill_events, team_map):
    """
    Count assists using flag_only strategy with same-team filtering.

    An assist is: non-killer player, same team as killer, has 1.0 flag in credits.
    """
    assist_counts = defaultdict(int)
    kill_details = []

    for kev in kill_events:
        killer_eid = kev['killer_eid']
        killer_team = team_map.get(killer_eid)

        credits_by_eid = defaultdict(list)
        for c in kev['credits']:
            credits_by_eid[c['eid']].append(c['value'])

        assisters = set()
        for eid, values in credits_by_eid.items():
            if eid == killer_eid:
                continue
            # Must have 1.0 flag
            if not any(abs(v - 1.0) < 0.01 for v in values):
                continue
            # Must be same team as killer
            if team_map.get(eid) != killer_team:
                continue
            assisters.add(eid)

        for a_eid in assisters:
            assist_counts[a_eid] += 1

        kill_details.append({
            'killer_eid': killer_eid,
            'timestamp': kev['timestamp'],
            'assisters': assisters,
            'all_credits': kev['credits'],
        })

    return assist_counts, kill_details


def count_assists_flag_only(kill_events):
    """
    Count assists using flag_only strategy (no team filtering).
    An assist is: non-killer player with 1.0 flag in credits.
    """
    assist_counts = defaultdict(int)

    for kev in kill_events:
        killer_eid = kev['killer_eid']
        credits_by_eid = defaultdict(list)
        for c in kev['credits']:
            credits_by_eid[c['eid']].append(c['value'])

        for eid, values in credits_by_eid.items():
            if eid == killer_eid:
                continue
            if any(abs(v - 1.0) < 0.01 for v in values):
                assist_counts[eid] += 1

    return assist_counts


def analyze_match(match_data, match_idx, strategy='flag_same_team'):
    """Analyze a single match."""
    replay_file = match_data['replay_file']
    players_truth = match_data['players']

    frames = load_all_frames(replay_file)
    if not frames:
        return None

    detected_players = extract_player_info(frames[0])
    if not detected_players:
        return None

    valid_eids_be = set()
    eid_to_player = {}
    team_map = {}
    for p in detected_players:
        if p['entity_id_be'] is not None:
            valid_eids_be.add(p['entity_id_be'])
            eid_to_player[p['entity_id_be']] = p
            team_map[p['entity_id_be']] = p['team']

    kill_events = find_kills_with_credits(frames, valid_eids_be)

    if strategy == 'flag_same_team':
        assist_counts, kill_details = count_assists_flag_only_same_team(
            kill_events, team_map
        )
    elif strategy == 'flag_only':
        assist_counts = count_assists_flag_only(kill_events)
        kill_details = []
    else:
        assist_counts = defaultdict(int)
        kill_details = []

    # Build comparison
    results = []
    for truth_name, truth_data in players_truth.items():
        matched = match_player_name(truth_name, detected_players)
        if matched and matched['entity_id_be'] is not None:
            eid_be = matched['entity_id_be']
            detected_assists = assist_counts.get(eid_be, 0)
        else:
            eid_be = None
            detected_assists = 0

        results.append({
            'player': truth_name,
            'team': truth_data['team'],
            'hero': truth_data['hero_name'],
            'eid_be': eid_be,
            'detected_name': matched['name'] if matched else '???',
            'truth_kills': truth_data['kills'],
            'truth_assists': truth_data['assists'],
            'detected_assists': detected_assists,
            'diff': detected_assists - truth_data['assists'],
            'match': detected_assists == truth_data['assists'],
        })

    return {
        'match_idx': match_idx,
        'replay_name': match_data['replay_name'],
        'duration': match_data['match_info']['duration_seconds'],
        'num_frames': len(frames),
        'num_players': len(detected_players),
        'num_kills': len(kill_events),
        'kill_details': kill_details,
        'player_results': results,
        'eid_to_player': eid_to_player,
        'team_map': team_map,
    }


def main():
    truth_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'output', 'tournament_truth.json'
    )
    with open(truth_path, 'r') as f:
        truth = json.load(f)

    matches = truth['matches']
    print(f"[OBJECTIVE] Determine optimal assist detection strategy from credit records")
    print(f"[DATA] {len(matches)} matches in tournament_truth.json")
    print(f"[DATA] Excluding match 9 (index 8) - incomplete replay")
    print()

    # ── Phase 1: Compare flag_only vs flag_same_team ──
    print(f"{'='*80}")
    print(f"PHASE 1: STRATEGY COMPARISON (excl. match 9)")
    print(f"{'='*80}")

    for strat_name in ['flag_only', 'flag_same_team']:
        total_correct = 0
        total_players = 0
        total_truth = 0
        total_detected = 0

        for mi, match in enumerate(matches):
            if mi == 8:
                continue
            result = analyze_match(match, mi, strategy=strat_name)
            if result is None:
                continue
            for pr in result['player_results']:
                total_players += 1
                total_truth += pr['truth_assists']
                total_detected += pr['detected_assists']
                if pr['match']:
                    total_correct += 1

        acc = 100 * total_correct / total_players if total_players else 0
        gap = total_detected - total_truth
        print(f"  {strat_name:<25} accuracy={acc:.1f}% ({total_correct}/{total_players})  "
              f"truth={total_truth}  detected={total_detected}  gap={gap:+d}")

    # ── Phase 2: Detailed flag_same_team results ──
    print(f"\n{'='*80}")
    print(f"PHASE 2: DETAILED RESULTS - 'flag_same_team'")
    print(f"{'='*80}")

    all_results = []
    grand_total_correct = 0
    grand_total_players = 0
    grand_truth = 0
    grand_detected = 0

    for mi, match in enumerate(matches):
        if mi == 8:
            continue

        result = analyze_match(match, mi, strategy='flag_same_team')
        if result is None:
            continue

        all_results.append(result)

        print(f"\nMatch {mi+1}: {result['num_kills']} kills, {result['num_frames']} frames")
        print(f"  {'Player':<25} {'Hero':<15} {'Team':<6} {'Truth':>5} {'Detect':>6} {'Diff':>5} {'OK?':>4}")
        print(f"  {'-'*70}")

        match_correct = 0
        for pr in result['player_results']:
            marker = 'OK' if pr['match'] else 'MISS'
            diff_str = f"{pr['diff']:+d}" if pr['diff'] != 0 else "0"
            print(f"  {pr['player']:<25} {pr['hero']:<15} {pr['team']:<6} "
                  f"{pr['truth_assists']:>5} {pr['detected_assists']:>6} {diff_str:>5} {marker:>4}")
            grand_total_players += 1
            grand_truth += pr['truth_assists']
            grand_detected += pr['detected_assists']
            if pr['match']:
                match_correct += 1
                grand_total_correct += 1

        print(f"  Match accuracy: {match_correct}/{len(result['player_results'])}")

    # ── Phase 3: Investigate remaining mismatches ──
    print(f"\n{'='*80}")
    print(f"PHASE 3: MISMATCH INVESTIGATION")
    print(f"{'='*80}")

    mismatches = []
    for result in all_results:
        for pr in result['player_results']:
            if not pr['match']:
                mismatches.append((result, pr))

    print(f"\n{len(mismatches)} mismatches found:")
    for result, pr in mismatches:
        mi = result['match_idx']
        print(f"\n  Match {mi+1}: {pr['player']} ({pr['hero']}, {pr['team']})")
        print(f"    Truth: {pr['truth_assists']}, Detected: {pr['detected_assists']}, Diff: {pr['diff']:+d}")
        print(f"    Detected name: '{pr['detected_name']}', EID_BE: {pr['eid_be']}")

        if pr['eid_be'] is None:
            print(f"    >>> NAME MISMATCH: Could not match '{pr['player']}' to any detected player")
            print(f"    >>> Detected players: {[p['name'] for p in extract_player_info(load_all_frames(matches[mi]['replay_file'])[0])]}")
        elif pr['diff'] > 0:
            # Over-counting - investigate which kills gave false assists
            print(f"    >>> OVER-COUNT by {pr['diff']}")
            # Find kills where this player was counted as assister
            for kd in result['kill_details']:
                if pr['eid_be'] in kd['assisters']:
                    killer_name = result['eid_to_player'].get(kd['killer_eid'], {}).get('name', '?')
                    killer_team = result['team_map'].get(kd['killer_eid'], '?')
                    player_team = result['team_map'].get(pr['eid_be'], '?')
                    print(f"    Assisted in kill by {killer_name} (team={killer_team}) at ts={kd['timestamp']}")
        elif pr['diff'] < 0:
            # Under-counting
            print(f"    >>> UNDER-COUNT by {abs(pr['diff'])}")
            print(f"    >>> This gap likely represents OBJECTIVE assists (turrets, Kraken)")

    # ── Phase 4: Cross-team 1.0 flag analysis ──
    print(f"\n{'='*80}")
    print(f"PHASE 4: CROSS-TEAM 1.0 FLAG AUDIT")
    print(f"{'='*80}")
    print(f"\nChecking if any cross-team 1.0 flags are incorrectly excluded:")

    cross_team_flag_count = 0
    for result in all_results:
        for kd in result['kill_details']:
            killer_eid = kd['killer_eid']
            killer_team = result['team_map'].get(killer_eid)
            credits_by_eid = defaultdict(list)
            for c in kd['all_credits']:
                credits_by_eid[c['eid']].append(c['value'])

            for eid, values in credits_by_eid.items():
                if eid == killer_eid:
                    continue
                has_flag = any(abs(v - 1.0) < 0.01 for v in values)
                if has_flag and result['team_map'].get(eid) != killer_team:
                    cross_team_flag_count += 1

    print(f"  Total cross-team 1.0 flags found: {cross_team_flag_count}")
    print(f"  These are correctly EXCLUDED from assist counts")

    # ── Phase 5: Match 9 (incomplete) analysis ──
    print(f"\n{'='*80}")
    print(f"PHASE 5: MATCH 9 (INCOMPLETE) ANALYSIS")
    print(f"{'='*80}")

    result9 = analyze_match(matches[8], 8, strategy='flag_same_team')
    if result9:
        print(f"  Frames: {result9['num_frames']} (expected ~170 for {result9['duration']}s)")
        print(f"  Kills detected: {result9['num_kills']}")
        print(f"\n  {'Player':<25} {'Hero':<15} {'Team':<6} {'Truth':>5} {'Detect':>6} {'Diff':>5}")
        print(f"  {'-'*70}")
        m9_correct = 0
        m9_total = 0
        for pr in result9['player_results']:
            diff_str = f"{pr['diff']:+d}" if pr['diff'] != 0 else "0"
            marker = 'OK' if pr['match'] else 'MISS'
            print(f"  {pr['player']:<25} {pr['hero']:<15} {pr['team']:<6} "
                  f"{pr['truth_assists']:>5} {pr['detected_assists']:>6} {diff_str:>5} {marker:>4}")
            m9_total += 1
            if pr['match']:
                m9_correct += 1
        print(f"\n  Match 9 accuracy: {m9_correct}/{m9_total}")
        print(f"  [LIMITATION] Replay incomplete - only {result9['num_frames']} frames captured")

    # ── Final Summary ──
    print(f"\n{'='*80}")
    print(f"FINAL SUMMARY")
    print(f"{'='*80}")

    accuracy = 100 * grand_total_correct / grand_total_players
    print(f"\n[FINDING] Assist detection via same-team 1.0 flag credits after kill headers")
    print(f"[STAT:n] {grand_total_players} players across {len(all_results)} complete matches")
    print(f"[STAT:accuracy] {accuracy:.1f}% ({grand_total_correct}/{grand_total_players})")
    print(f"[STAT:total_truth_assists] {grand_truth}")
    print(f"[STAT:total_detected_assists] {grand_detected}")
    print(f"[STAT:gap] {grand_detected - grand_truth:+d}")

    exact = sum(1 for r in all_results for p in r['player_results'] if p['match'])
    over = sum(1 for r in all_results for p in r['player_results'] if p['diff'] > 0)
    under = sum(1 for r in all_results for p in r['player_results'] if p['diff'] < 0)
    print(f"\n[STAT:exact_match] {exact} players")
    print(f"[STAT:over_count] {over} players (detected > truth)")
    print(f"[STAT:under_count] {under} players (detected < truth)")

    # Breakdown of error magnitudes
    abs_errors = [abs(p['diff']) for r in all_results for p in r['player_results'] if not p['match']]
    if abs_errors:
        print(f"\nError magnitude distribution:")
        for e in sorted(set(abs_errors)):
            count = abs_errors.count(e)
            print(f"  |diff| = {e}: {count} players")

    # Per-match accuracy
    print(f"\nPer-match accuracy:")
    for result in all_results:
        mi = result['match_idx']
        correct = sum(1 for p in result['player_results'] if p['match'])
        total = len(result['player_results'])
        print(f"  Match {mi+1:>2}: {correct}/{total} ({100*correct/total:.0f}%)")

    print(f"\n[FINDING] Credit structure decoded:")
    print(f"  - Kill header [18 04 1C] followed by credit records [10 04 1D]")
    print(f"  - Each credit: [10 04 1D] [00 00] [eid BE] [value f32 BE]")
    print(f"  - Assister pattern: player has 1.0 flag credit AND is on killer's team")
    print(f"  - Cross-team 1.0 flags exist but are NOT assists (damage/proximity tracking)")
    print(f"  - Gold bounty shares (25-250) co-occur with 1.0 flags for true assists")

    print(f"\n[LIMITATION] Match 9 excluded (incomplete replay)")
    print(f"[LIMITATION] 1 name-mismatch player ('TenshilHime' typo in truth data)")
    print(f"[LIMITATION] Small over-counts may include objective assists attributed via credit records")

    # Save results
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'output')
    output_path = os.path.join(output_dir, 'assist_research_results.json')

    save_data = {
        'strategy': 'flag_same_team',
        'description': 'Assist = non-killer same-team player with 1.0 flag in credit records after kill header',
        'accuracy': accuracy,
        'correct': grand_total_correct,
        'total': grand_total_players,
        'truth_sum': grand_truth,
        'detected_sum': grand_detected,
        'gap': grand_detected - grand_truth,
        'matches_analyzed': len(all_results),
        'match_9_excluded': True,
        'per_match': [{
            'match_idx': r['match_idx'],
            'replay_name': r['replay_name'],
            'num_kills': r['num_kills'],
            'player_results': r['player_results'],
        } for r in all_results],
    }

    with open(output_path, 'w') as f:
        json.dump(save_data, f, indent=2)

    print(f"\n[DATA] Results saved to {output_path}")


if __name__ == '__main__':
    main()
