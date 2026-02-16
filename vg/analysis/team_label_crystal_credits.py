#!/usr/bin/env python3
"""
Team Label Resolution via Crystal Death Credits
=================================================
Hypothesis: When the Vain Crystal is destroyed, credit records (action=0x04)
near the crystal death timestamp identify the WINNING team's players.
Those players' team_byte → winner's team_byte.

Combined with KDA kill counts (winner has more kills), this gives us
a truth-free team label resolution.

Also tests: Does WinLossDetector's turret-based left/right match truth?
"""

import json
import struct
import sys
import io
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.kda_detector import KDADetector
from vg.analysis.win_loss_detector import WinLossDetector

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
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
                    'entity_id_le': eid_le,
                    'eid_be': le_to_be(eid_le) if eid_le else None,
                    'team_id': team_id,
                })
                seen.add(name)
        search_start = pos + 1
    return players


def load_all_frames(replay_file):
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return [(int(f.stem.split('.')[-1]), f.read_bytes()) for f in frames]


def find_crystal_death(all_data, duration_est=None):
    """Find crystal death event with highest timestamp (closest to game end)."""
    candidates = []
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
        if 2000 <= eid <= 2010 and 0 < ts < 3000:
            candidates.append({'eid_be': eid, 'timestamp': ts, 'offset': pos})
        pos += 1

    if not candidates:
        return None

    # Prefer the candidate closest to game end (highest timestamp)
    if duration_est:
        candidates.sort(key=lambda c: abs(c['timestamp'] - duration_est))
    else:
        candidates.sort(key=lambda c: -c['timestamp'])

    return candidates[0]


def find_credits_near_timestamp(all_data, target_ts, valid_eids_be, window=5.0):
    """Find credit records within ±window seconds of target_ts."""
    credits = []
    pos = 0
    while True:
        pos = all_data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        value = struct.unpack_from(">f", all_data, pos + 7)[0]
        action = all_data[pos + 11]

        if eid in valid_eids_be and action == 0x04:
            # Action 0x04 = turret/objective bounty
            # We don't have timestamp directly in credit records, but
            # they appear sequentially near the event that triggered them.
            # Just collect ALL 0x04 credits and filter later.
            credits.append({
                'eid_be': eid,
                'value': value,
                'action': action,
                'offset': pos,
            })
        pos += 1

    return credits


def find_credits_near_crystal_offset(all_data, crystal_offset, valid_eids_be, search_range=2000):
    """Find 0x04 credit records near the crystal death event offset."""
    credits = []
    start = max(0, crystal_offset - search_range)
    end = min(len(all_data), crystal_offset + search_range)

    pos = start
    while pos < end:
        pos = all_data.find(CREDIT_HEADER, pos)
        if pos == -1 or pos >= end:
            break
        if pos + 12 > len(all_data):
            pos += 1
            continue
        if all_data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        value = struct.unpack_from(">f", all_data, pos + 7)[0]
        action = all_data[pos + 11]

        if eid in valid_eids_be:
            credits.append({
                'eid_be': eid,
                'value': value,
                'action': action,
                'offset': pos,
                'rel_offset': pos - crystal_offset,
            })
        pos += 1

    return credits


def main():
    print("=" * 80)
    print("TEAM LABEL RESOLUTION - CRYSTAL DEATH CREDITS")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    # ===== TEST 1: WinLossDetector label vs truth (WITHOUT swap correction) =====
    print("\n[TEST 1] WinLossDetector winner label vs truth (no correction)")
    print(f"  {'M#':>3s}  {'WLD_winner':>12s}  {'truth_winner':>12s}  {'Match':>6s}")
    print("  " + "-" * 45)

    wld_correct = 0
    wld_total = 0

    for mi, match in enumerate(truth_data['matches']):
        match_num = mi + 1
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        truth_winner = match['match_info']['winner']

        # Run WinLossDetector silently
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            wld = WinLossDetector(replay_file)
            outcome = wld.detect_winner()
        finally:
            sys.stdout = old_stdout

        wld_winner = outcome.winner if outcome else None
        ok = wld_winner == truth_winner
        wld_total += 1
        if ok:
            wld_correct += 1

        print(f"  M{match_num:2d}  {str(wld_winner):>12s}  {truth_winner:>12s}  {'OK' if ok else 'FAIL':>6s}")

    print(f"\n  WinLossDetector accuracy: {wld_correct}/{wld_total} = {wld_correct/wld_total*100:.1f}%")

    # ===== TEST 2: Crystal death credits identify winning team_byte =====
    print("\n" + "=" * 80)
    print("[TEST 2] Credit records near crystal death → winning team_byte")
    print("=" * 80)

    crystal_correct = 0
    crystal_total = 0

    for mi, match in enumerate(truth_data['matches']):
        match_num = mi + 1
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        truth_winner = match['match_info']['winner']

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)

        # Build maps
        eid_to_player = {}
        byte1_eids = set()
        byte2_eids = set()
        all_eids_be = set()

        for p in players:
            eid_be = p['eid_be']
            eid_to_player[eid_be] = p
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids.add(eid_be)

        # Load all frames concatenated
        frames = load_all_frames(replay_file)
        all_data = b"".join(data for _, data in frames)

        # Get duration estimate from deaths
        detector = KDADetector(valid_entity_ids=all_eids_be)
        for fi, fdata in frames:
            detector.process_frame(fi, fdata)
        duration_est = max(d.timestamp for d in detector.death_events) if detector.death_events else None

        # Find crystal death
        crystal = find_crystal_death(all_data, duration_est)
        if not crystal:
            print(f"  M{match_num}: No crystal death found")
            continue

        # Find credits near crystal death offset
        credits = find_credits_near_crystal_offset(all_data, crystal['offset'], all_eids_be, search_range=3000)

        # Filter to action=0x04 credits only (turret/crystal bounty)
        bounty_credits = [c for c in credits if c['action'] == 0x04]

        # Also check action=0x06 credits near crystal
        gold_credits = [c for c in credits if c['action'] == 0x06]

        # Count team_byte occurrences in bounty credits AFTER crystal death
        after_crystal = [c for c in bounty_credits if c['rel_offset'] >= 0]
        byte1_bounty = sum(1 for c in after_crystal if c['eid_be'] in byte1_eids)
        byte2_bounty = sum(1 for c in after_crystal if c['eid_be'] in byte2_eids)

        # Determine winner team_byte from bounty credits
        if byte1_bounty > byte2_bounty:
            winner_byte = 1
        elif byte2_bounty > byte1_bounty:
            winner_byte = 2
        else:
            winner_byte = None

        # Cross-check: KDA kill counts
        results = detector.get_results(game_duration=duration_est)
        byte1_kills = sum(results[eid].kills for eid in byte1_eids if eid in results)
        byte2_kills = sum(results[eid].kills for eid in byte2_eids if eid in results)
        kda_winner_byte = 1 if byte1_kills > byte2_kills else (2 if byte2_kills > byte1_kills else None)

        # Determine truth mapping
        truth_mapping = {}
        for pname, pdata in match['players'].items():
            for p in players:
                if p['name'] == pname or (len(pname) > 5 and pname in p['name']):
                    truth_mapping[p['team_id']] = pdata['team']
                    break

        # What team_byte SHOULD map to the winner?
        expected_winner_byte = None
        for tb, side in truth_mapping.items():
            if side == truth_winner:
                expected_winner_byte = tb
                break

        crystal_total += 1
        ok = winner_byte == expected_winner_byte

        if ok:
            crystal_correct += 1

        print(f"\n  M{match_num}: crystal eid={crystal['eid_be']}, ts={crystal['timestamp']:.1f}s")
        print(f"    After-crystal 0x04 credits: byte1={byte1_bounty}, byte2={byte2_bounty}")
        print(f"    → Bounty winner_byte={winner_byte}")
        print(f"    KDA kills: byte1={byte1_kills}, byte2={byte2_kills} → kda_winner_byte={kda_winner_byte}")
        print(f"    Truth: winner={truth_winner}, expected_winner_byte={expected_winner_byte}")
        print(f"    → {'OK' if ok else 'FAIL'} (bounty) | {'OK' if kda_winner_byte == expected_winner_byte else 'FAIL'} (kda)")

    print(f"\n  Crystal bounty accuracy: {crystal_correct}/{crystal_total}")

    # ===== TEST 3: Combined approach =====
    print("\n" + "=" * 80)
    print("[TEST 3] Combined: KDA winner_byte + WinLossDetector winner_side → team label")
    print("=" * 80)
    print("  If WLD says winner=left, and KDA says byte1 has more kills (=winner),")
    print("  then byte1=left, byte2=right.")

    combined_correct = 0
    combined_total = 0

    for mi, match in enumerate(truth_data['matches']):
        match_num = mi + 1
        replay_file = match['replay_file']
        if not Path(replay_file).exists() or "Incomplete" in replay_file:
            continue

        truth_winner = match['match_info']['winner']

        with open(replay_file, 'rb') as f:
            frame0 = f.read()
        players = parse_player_blocks(frame0)

        byte1_eids = set()
        byte2_eids = set()
        all_eids_be = set()
        for p in players:
            eid_be = p['eid_be']
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids.add(eid_be)

        # KDA
        frames = load_all_frames(replay_file)
        detector = KDADetector(valid_entity_ids=all_eids_be)
        for fi, fdata in frames:
            detector.process_frame(fi, fdata)
        duration_est = max(d.timestamp for d in detector.death_events) if detector.death_events else None
        results = detector.get_results(game_duration=duration_est)

        byte1_kills = sum(results[eid].kills for eid in byte1_eids if eid in results)
        byte2_kills = sum(results[eid].kills for eid in byte2_eids if eid in results)
        kda_winner_byte = 1 if byte1_kills > byte2_kills else (2 if byte2_kills > byte1_kills else None)

        # WinLossDetector
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            wld = WinLossDetector(replay_file)
            outcome = wld.detect_winner()
        finally:
            sys.stdout = old_stdout

        wld_winner_side = outcome.winner if outcome else None

        if kda_winner_byte is None or wld_winner_side is None:
            print(f"  M{match_num}: Cannot determine (kda={kda_winner_byte}, wld={wld_winner_side})")
            continue

        # Combine: kda_winner_byte → wld_winner_side
        if kda_winner_byte == 1:
            byte1_label = wld_winner_side
            byte2_label = "right" if wld_winner_side == "left" else "left"
        else:
            byte2_label = wld_winner_side
            byte1_label = "right" if wld_winner_side == "left" else "left"

        # Validate against truth
        truth_mapping = {}
        for pname, pdata in match['players'].items():
            for p in players:
                short = pname.split('_', 1)[1] if '_' in pname else pname
                if p['name'] == short or p['name'] == pname:
                    truth_mapping[p['team_id']] = pdata['team']
                    break

        truth_byte1 = truth_mapping.get(1, '?')
        truth_byte2 = truth_mapping.get(2, '?')

        correct = (byte1_label == truth_byte1 and byte2_label == truth_byte2)
        combined_total += 1
        if correct:
            combined_correct += 1

        print(f"  M{match_num}: kda_winner=byte{kda_winner_byte} (b1k={byte1_kills}, b2k={byte2_kills}), "
              f"wld_winner={wld_winner_side}")
        print(f"    → byte1={byte1_label}, byte2={byte2_label} | "
              f"truth: byte1={truth_byte1}, byte2={truth_byte2} → {'OK' if correct else 'FAIL'}")

    print(f"\n  Combined accuracy: {combined_correct}/{combined_total} = "
          f"{combined_correct/combined_total*100:.1f}%" if combined_total else "N/A")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)


if __name__ == '__main__':
    main()
