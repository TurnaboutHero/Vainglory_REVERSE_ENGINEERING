#!/usr/bin/env python3
"""
Kill-count heuristic for team label resolution.
Compare detected kills per team_byte group to truth scores.
"""
import sys
sys.path.insert(0, r'D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\core')

import json
import struct
from pathlib import Path
from collections import defaultdict
from kda_detector import KDADetector

TRUTH_PATH = r'D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_truth.json'

SWAP_STATUS = {
    1: False, 2: True, 3: True, 4: False, 5: True,
    6: False, 7: False, 8: True, 9: None, 10: True, 11: False,
}

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])


def parse_player_blocks_raw(data):
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
            except:
                name = ""
            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                eid_le = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little') if pos + 0xA7 <= len(data) else None
                team_id = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                players.append({'name': name, 'entity_id_le': eid_le, 'team_id': team_id})
                seen.add(name)
        search_start = pos + 1
    return players


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_all_frames(replay_file):
    frame_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]
    frames = sorted(frame_dir.glob(f"{replay_name}.*.vgr"),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return [(int(f.stem.split('.')[-1]), f.read_bytes()) for f in frames]


def main():
    print("=" * 80)
    print("KILL-COUNT HEURISTIC FOR TEAM LABEL RESOLUTION")
    print("=" * 80)

    with open(TRUTH_PATH, 'r') as f:
        truth_data = json.load(f)

    print(f"\n  {'M#':>3s}  {'b1_K':>5s}  {'b2_K':>5s}  {'b1_D':>5s}  {'b2_D':>5s}  "
          f"{'t_L':>5s}  {'t_R':>5s}  {'err_L':>6s}  {'err_R':>6s}  {'Predict':>8s}  {'Result':>8s}")
    print(f"  {'---':>3s}  {'----':>5s}  {'----':>5s}  {'----':>5s}  {'----':>5s}  "
          f"{'---':>5s}  {'---':>5s}  {'-----':>6s}  {'-----':>6s}  {'-------':>8s}  {'------':>8s}")

    correct_count = 0
    wrong_count = 0
    total = 0

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        byte1_eids_be = set()
        byte2_eids_be = set()
        all_eids_be = set()

        for p in players:
            eid_be = le_to_be(p['entity_id_le'])
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids_be.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids_be.add(eid_be)

        detector = KDADetector(valid_entity_ids=all_eids_be)
        frames = load_all_frames(replay_file)
        duration = match['match_info']['duration_seconds']

        for frame_idx, frame_data in frames:
            detector.process_frame(frame_idx, frame_data)

        results = detector.get_results(game_duration=duration)

        byte1_kills = sum(results[eid].kills for eid in byte1_eids_be if eid in results)
        byte2_kills = sum(results[eid].kills for eid in byte2_eids_be if eid in results)
        byte1_deaths = sum(results[eid].deaths for eid in byte1_eids_be if eid in results)
        byte2_deaths = sum(results[eid].deaths for eid in byte2_eids_be if eid in results)

        truth_score_left = match['match_info']['score_left']
        truth_score_right = match['match_info']['score_right']

        # Error if byte1=left assignment: |b1k-tl| + |b2k-tr|
        err_left = abs(byte1_kills - truth_score_left) + abs(byte2_kills - truth_score_right)
        # Error if byte1=right assignment: |b1k-tr| + |b2k-tl|
        err_right = abs(byte1_kills - truth_score_right) + abs(byte2_kills - truth_score_left)

        if err_left < err_right:
            predicted = 'b1=L'
            correct = not swapped
        elif err_right < err_left:
            predicted = 'b1=R'
            correct = swapped
        else:
            predicted = 'TIE'
            correct = None

        if correct is True:
            correct_count += 1
        elif correct is False:
            wrong_count += 1
        total += 1

        result = 'OK' if correct else ('WRONG' if correct is False else 'TIE')
        print(f"  M{match_num:2d}  {byte1_kills:5d}  {byte2_kills:5d}  {byte1_deaths:5d}  {byte2_deaths:5d}  "
              f"{truth_score_left:5d}  {truth_score_right:5d}  {err_left:6d}  {err_right:6d}  {predicted:>8s}  {result:>8s}")

    print(f"\n  Summary: {correct_count}/{total} correct, {wrong_count}/{total} wrong")
    if correct_count + wrong_count > 0:
        print(f"  Accuracy: {correct_count/(correct_count+wrong_count)*100:.1f}%")

    # Also test: use death counts instead (deaths of byte1 should match score of OTHER team)
    print(f"\n\n  DEATH-COUNT HEURISTIC (byte1_deaths should = score_right if byte1=right):")
    print(f"  {'M#':>3s}  {'b1_D':>5s}  {'b2_D':>5s}  {'t_L':>5s}  {'t_R':>5s}  "
          f"{'err_L':>6s}  {'err_R':>6s}  {'Predict':>8s}  {'Result':>8s}")

    dc_correct = 0
    dc_wrong = 0
    dc_total = 0

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)

        byte1_eids_be = set()
        byte2_eids_be = set()
        all_eids_be = set()

        for p in players:
            eid_be = le_to_be(p['entity_id_le'])
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids_be.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids_be.add(eid_be)

        detector = KDADetector(valid_entity_ids=all_eids_be)
        frames = load_all_frames(replay_file)
        duration = match['match_info']['duration_seconds']

        for frame_idx, frame_data in frames:
            detector.process_frame(frame_idx, frame_data)

        results = detector.get_results(game_duration=duration)

        byte1_deaths = sum(results[eid].deaths for eid in byte1_eids_be if eid in results)
        byte2_deaths = sum(results[eid].deaths for eid in byte2_eids_be if eid in results)

        truth_score_left = match['match_info']['score_left']
        truth_score_right = match['match_info']['score_right']

        # Deaths of left team = score_right (kills by right)
        # If byte1=left: byte1_deaths ~= score_right, byte2_deaths ~= score_left
        err_left = abs(byte1_deaths - truth_score_right) + abs(byte2_deaths - truth_score_left)
        err_right = abs(byte1_deaths - truth_score_left) + abs(byte2_deaths - truth_score_right)

        if err_left < err_right:
            predicted = 'b1=L'
            correct = not swapped
        elif err_right < err_left:
            predicted = 'b1=R'
            correct = swapped
        else:
            predicted = 'TIE'
            correct = None

        if correct is True:
            dc_correct += 1
        elif correct is False:
            dc_wrong += 1
        dc_total += 1

        result = 'OK' if correct else ('WRONG' if correct is False else 'TIE')
        print(f"  M{match_num:2d}  {byte1_deaths:5d}  {byte2_deaths:5d}  "
              f"{truth_score_left:5d}  {truth_score_right:5d}  {err_left:6d}  {err_right:6d}  {predicted:>8s}  {result:>8s}")

    print(f"\n  Death-count summary: {dc_correct}/{dc_total} correct, {dc_wrong}/{dc_total} wrong")
    if dc_correct + dc_wrong > 0:
        print(f"  Accuracy: {dc_correct/(dc_correct+dc_wrong)*100:.1f}%")

    # COMBINED: kills + deaths
    print(f"\n\n  COMBINED HEURISTIC (kills + deaths):")
    print(f"  {'M#':>3s}  {'b1K':>4s} {'b2K':>4s} {'b1D':>4s} {'b2D':>4s} "
          f"{'tL':>4s} {'tR':>4s} {'errL':>5s} {'errR':>5s} {'Pred':>5s} {'Res':>5s}")

    cb_correct = 0
    cb_wrong = 0
    cb_total = 0

    for match_idx, match in enumerate(truth_data['matches']):
        match_num = match_idx + 1
        swapped = SWAP_STATUS.get(match_num)
        if swapped is None:
            continue

        replay_file = match['replay_file']
        if not Path(replay_file).exists():
            continue

        with open(replay_file, 'rb') as f:
            frame0 = f.read()

        players = parse_player_blocks_raw(frame0)
        byte1_eids_be = set()
        byte2_eids_be = set()
        all_eids_be = set()
        for p in players:
            eid_be = le_to_be(p['entity_id_le'])
            all_eids_be.add(eid_be)
            if p['team_id'] == 1:
                byte1_eids_be.add(eid_be)
            elif p['team_id'] == 2:
                byte2_eids_be.add(eid_be)

        detector = KDADetector(valid_entity_ids=all_eids_be)
        frames = load_all_frames(replay_file)
        duration = match['match_info']['duration_seconds']
        for frame_idx, frame_data in frames:
            detector.process_frame(frame_idx, frame_data)
        results = detector.get_results(game_duration=duration)

        b1k = sum(results[eid].kills for eid in byte1_eids_be if eid in results)
        b2k = sum(results[eid].kills for eid in byte2_eids_be if eid in results)
        b1d = sum(results[eid].deaths for eid in byte1_eids_be if eid in results)
        b2d = sum(results[eid].deaths for eid in byte2_eids_be if eid in results)

        tl = match['match_info']['score_left']
        tr = match['match_info']['score_right']

        # If byte1=left: b1k~tl, b2k~tr, b1d~tr, b2d~tl
        err_left = abs(b1k-tl) + abs(b2k-tr) + abs(b1d-tr) + abs(b2d-tl)
        err_right = abs(b1k-tr) + abs(b2k-tl) + abs(b1d-tl) + abs(b2d-tr)

        if err_left < err_right:
            predicted = 'b1=L'
            correct = not swapped
        elif err_right < err_left:
            predicted = 'b1=R'
            correct = swapped
        else:
            predicted = 'TIE'
            correct = None

        if correct is True:
            cb_correct += 1
        elif correct is False:
            cb_wrong += 1
        cb_total += 1

        result = 'OK' if correct else ('WRONG' if correct is False else 'TIE')
        print(f"  M{match_num:2d} {b1k:4d} {b2k:4d} {b1d:4d} {b2d:4d} "
              f"{tl:4d} {tr:4d} {err_left:5d} {err_right:5d} {predicted:>5s} {result:>5s}")

    print(f"\n  Combined summary: {cb_correct}/{cb_total} correct, {cb_wrong}/{cb_total} wrong")
    if cb_correct + cb_wrong > 0:
        print(f"  Accuracy: {cb_correct/(cb_correct+cb_wrong)*100:.1f}%")


if __name__ == '__main__':
    main()
