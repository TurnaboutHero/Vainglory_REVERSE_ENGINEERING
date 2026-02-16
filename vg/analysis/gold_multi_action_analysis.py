#!/usr/bin/env python3
"""
Gold Multi-Action Analysis - Try combining multiple action bytes and
regression approaches to improve gold estimation accuracy.

Finding so far: Action 0x06 (val>2) has r≈0.99 but per-player ratio varies 0.88-1.24.
Match-level ratio correction yields only 25.5% accuracy at ±100.

Strategies to try:
1. Combine action bytes (0x06 + 0x08, etc.)
2. Per-action regression with intercept
3. Value threshold tuning
4. Include/exclude specific actions
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict
from itertools import combinations

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def extract_players(data):
    players = []
    seen = set()
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(data):
                eid_le = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                eid_be = struct.unpack('>H', struct.pack('<H', eid_le))[0]
                ns = pos + len(marker)
                ne = ns
                while ne < len(data) and ne < ns + 30:
                    if data[ne] < 32 or data[ne] > 126:
                        break
                    ne += 1
                name = data[ns:ne].decode('ascii', errors='replace')
                if eid_le not in seen and len(name) >= 3 and not name.startswith('GameMode'):
                    players.append({'name': name, 'eid_le': eid_le, 'eid_be': eid_be})
                    seen.add(eid_le)
            pos += 1
    return players


def pearson_corr(xs, ys):
    n = len(xs)
    if n < 3:
        return 0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0 or dy == 0:
        return 0
    return num / (dx * dy)


def linear_regression(xs, ys):
    """Returns (slope, intercept, r) for y = slope*x + intercept."""
    n = len(xs)
    if n < 2:
        return 1.0, 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    ss_xx = sum((x - mx)**2 for x in xs)
    ss_xy = sum((x - mx)*(y - my) for x, y in zip(xs, ys))
    if ss_xx == 0:
        return 1.0, 0.0, 0.0
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    r = pearson_corr(xs, ys)
    return slope, intercept, r


def scan_all_credits(data, valid_eids):
    """Scan all credit records, return dict of action -> {eid: total_sum}."""
    result = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))

    pos = 0
    while True:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in valid_eids:
            pos += 3
            continue
        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11]
        if not math.isnan(value) and not math.isinf(value):
            if value > 2.0:  # Filter flags (1.0, 0.5)
                result[action][eid] += value
            counts[action][eid] += 1
        pos += 3
    return result, counts


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Collect cross-match data for regression
    all_match_data = []  # List of (match_idx, eids, truth_vec, action_sums)

    for match_idx, match in enumerate(truth['matches']):
        if match_idx == 8:
            continue
        p = Path(match['replay_file'])
        if not p.exists():
            continue

        d = p.parent
        base = p.stem.rsplit('.', 1)[0]
        frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))

        all_data = b''
        for f_path in frames:
            all_data += f_path.read_bytes()

        f0 = frames[0].read_bytes()
        players = extract_players(f0)

        truth_gold = {}
        valid_eids = set()
        name_by_eid = {}
        for tname, tdata in match['players'].items():
            if 'gold' not in tdata:
                continue
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p_obj in players:
                if p_obj['name'] == short or tname.endswith(p_obj['name']):
                    truth_gold[p_obj['eid_be']] = tdata['gold']
                    valid_eids.add(p_obj['eid_be'])
                    name_by_eid[p_obj['eid_be']] = tname
                    break

        if not truth_gold:
            continue

        action_sums, action_counts = scan_all_credits(all_data, valid_eids)
        eids = sorted(truth_gold.keys())
        truth_vec = [truth_gold[e] for e in eids]

        all_match_data.append({
            'match_idx': match_idx,
            'eids': eids,
            'truth_vec': truth_vec,
            'truth_gold': truth_gold,
            'action_sums': action_sums,
            'action_counts': action_counts,
            'name_by_eid': name_by_eid,
        })

    print(f"Loaded {len(all_match_data)} matches with gold truth data\n")

    # Strategy 1: Find best single action byte
    print("=" * 70)
    print("Strategy 1: Best single action byte (val > 2.0)")
    print("=" * 70)
    all_actions = set()
    for md in all_match_data:
        all_actions.update(md['action_sums'].keys())

    for action in sorted(all_actions):
        all_truth = []
        all_detected = []
        for md in all_match_data:
            for e in md['eids']:
                all_truth.append(md['truth_gold'][e])
                all_detected.append(md['action_sums'].get(action, {}).get(e, 0))

        if not any(d > 0 for d in all_detected):
            continue

        corr = pearson_corr(all_truth, all_detected)
        slope, intercept, _ = linear_regression(all_detected, all_truth)

        # Estimate using global regression
        ok_100 = 0
        ok_200 = 0
        total = len(all_truth)
        for t, d in zip(all_truth, all_detected):
            est = round((slope * d + intercept) / 100) * 100
            if abs(est - t) <= 100:
                ok_100 += 1
            if abs(est - t) <= 200:
                ok_200 += 1

        if abs(corr) > 0.7:
            print(f"  0x{action:02X}: r={corr:.4f}, slope={slope:.4f}, intercept={intercept:.0f}, "
                  f"acc±100={ok_100}/{total} ({ok_100/total*100:.1f}%), "
                  f"acc±200={ok_200}/{total} ({ok_200/total*100:.1f}%)")

    # Strategy 2: Combine action bytes using global regression
    print(f"\n{'=' * 70}")
    print("Strategy 2: Combine action bytes with global regression")
    print("=" * 70)

    candidate_actions = []
    for action in sorted(all_actions):
        all_truth = []
        all_detected = []
        for md in all_match_data:
            for e in md['eids']:
                all_truth.append(md['truth_gold'][e])
                all_detected.append(md['action_sums'].get(action, {}).get(e, 0))
        corr = pearson_corr(all_truth, all_detected)
        if abs(corr) > 0.5:
            candidate_actions.append(action)

    best_combo = None
    best_acc = 0

    # Try all 1-4 action byte combinations
    for size in range(1, min(len(candidate_actions) + 1, 5)):
        for combo in combinations(candidate_actions, size):
            all_truth = []
            all_detected = []
            for md in all_match_data:
                for e in md['eids']:
                    all_truth.append(md['truth_gold'][e])
                    total_sum = sum(md['action_sums'].get(a, {}).get(e, 0) for a in combo)
                    all_detected.append(total_sum)

            corr = pearson_corr(all_truth, all_detected)
            if abs(corr) < 0.9:
                continue

            slope, intercept, _ = linear_regression(all_detected, all_truth)

            ok_100 = 0
            for t, d in zip(all_truth, all_detected):
                est = round((slope * d + intercept) / 100) * 100
                if abs(est - t) <= 100:
                    ok_100 += 1

            acc = ok_100 / len(all_truth) * 100
            if acc > best_acc:
                best_acc = acc
                best_combo = combo
                print(f"  [{'+'.join(f'0x{a:02X}' for a in combo)}]: "
                      f"r={corr:.4f}, slope={slope:.4f}, int={intercept:.0f}, "
                      f"acc±100={ok_100}/{len(all_truth)} ({acc:.1f}%)")

    # Strategy 3: Per-match linear regression (leave-one-out cross-validation)
    print(f"\n{'=' * 70}")
    print("Strategy 3: Per-match regression with action 0x06 (cross-validated)")
    print("=" * 70)

    total_ok_100 = 0
    total_ok_200 = 0
    total_players = 0

    for test_idx in range(len(all_match_data)):
        test_md = all_match_data[test_idx]

        # Train on other matches
        train_x = []
        train_y = []
        for train_idx in range(len(all_match_data)):
            if train_idx == test_idx:
                continue
            for e in all_match_data[train_idx]['eids']:
                train_x.append(all_match_data[train_idx]['action_sums'].get(0x06, {}).get(e, 0))
                train_y.append(all_match_data[train_idx]['truth_gold'][e])

        slope, intercept, _ = linear_regression(train_x, train_y)

        # Test on held-out match
        match_ok = 0
        match_ok_200 = 0
        for e in test_md['eids']:
            detected = test_md['action_sums'].get(0x06, {}).get(e, 0)
            truth = test_md['truth_gold'][e]
            est = round((slope * detected + intercept) / 100) * 100
            diff = est - truth
            if abs(diff) <= 100:
                match_ok += 1
            if abs(diff) <= 200:
                match_ok_200 += 1
            total_players += 1

        total_ok_100 += match_ok
        total_ok_200 += match_ok_200
        pct = match_ok / len(test_md['eids']) * 100
        print(f"  Match {test_md['match_idx']+1}: {match_ok}/{len(test_md['eids'])} "
              f"({pct:.0f}%) [slope={slope:.4f}, int={intercept:.0f}]")

    if total_players > 0:
        print(f"\n  Cross-validated accuracy (±100): {total_ok_100}/{total_players} ({total_ok_100/total_players*100:.1f}%)")
        print(f"  Cross-validated accuracy (±200): {total_ok_200}/{total_players} ({total_ok_200/total_players*100:.1f}%)")

    # Strategy 4: Use multiple features (action sums) in multivariate regression
    print(f"\n{'=' * 70}")
    print("Strategy 4: Best combo with cross-validated regression")
    print("=" * 70)

    if best_combo:
        total_ok_100 = 0
        total_ok_200 = 0
        total_players = 0

        for test_idx in range(len(all_match_data)):
            test_md = all_match_data[test_idx]

            train_x = []
            train_y = []
            for train_idx in range(len(all_match_data)):
                if train_idx == test_idx:
                    continue
                for e in all_match_data[train_idx]['eids']:
                    total_sum = sum(all_match_data[train_idx]['action_sums'].get(a, {}).get(e, 0) for a in best_combo)
                    train_x.append(total_sum)
                    train_y.append(all_match_data[train_idx]['truth_gold'][e])

            slope, intercept, _ = linear_regression(train_x, train_y)

            match_ok = 0
            match_ok_200 = 0
            for e in test_md['eids']:
                detected = sum(test_md['action_sums'].get(a, {}).get(e, 0) for a in best_combo)
                truth = test_md['truth_gold'][e]
                est = round((slope * detected + intercept) / 100) * 100
                diff = est - truth
                if abs(diff) <= 100:
                    match_ok += 1
                if abs(diff) <= 200:
                    match_ok_200 += 1
                total_players += 1

            total_ok_100 += match_ok
            total_ok_200 += match_ok_200

        combo_str = '+'.join(f'0x{a:02X}' for a in best_combo)
        print(f"  Best combo [{combo_str}]:")
        print(f"  Cross-validated accuracy (±100): {total_ok_100}/{total_players} ({total_ok_100/total_players*100:.1f}%)")
        print(f"  Cross-validated accuracy (±200): {total_ok_200}/{total_players} ({total_ok_200/total_players*100:.1f}%)")

    # Strategy 5: Raw sum of ALL credit values > 2.0 (no action filter)
    print(f"\n{'=' * 70}")
    print("Strategy 5: Raw sum of ALL credits (val>2.0, no action filter)")
    print("=" * 70)

    all_truth = []
    all_detected = []
    for md in all_match_data:
        for e in md['eids']:
            all_truth.append(md['truth_gold'][e])
            total_sum = sum(md['action_sums'].get(a, {}).get(e, 0) for a in md['action_sums'])
            all_detected.append(total_sum)

    corr = pearson_corr(all_truth, all_detected)
    slope, intercept, _ = linear_regression(all_detected, all_truth)

    ok_100 = 0
    ok_200 = 0
    for t, d in zip(all_truth, all_detected):
        est = round((slope * d + intercept) / 100) * 100
        if abs(est - t) <= 100:
            ok_100 += 1
        if abs(est - t) <= 200:
            ok_200 += 1

    print(f"  r={corr:.4f}, slope={slope:.4f}, intercept={intercept:.0f}")
    print(f"  Accuracy (±100): {ok_100}/{len(all_truth)} ({ok_100/len(all_truth)*100:.1f}%)")
    print(f"  Accuracy (±200): {ok_200}/{len(all_truth)} ({ok_200/len(all_truth)*100:.1f}%)")

    # Strategy 6: Action 0x06 direct (no regression, just round)
    print(f"\n{'=' * 70}")
    print("Strategy 6: Direct round to nearest 100 (no correction)")
    print("=" * 70)

    ok_100 = 0
    ok_200 = 0
    ok_500 = 0
    total = 0
    for md in all_match_data:
        for e in md['eids']:
            t = md['truth_gold'][e]
            raw = md['action_sums'].get(0x06, {}).get(e, 0)
            est = round(raw / 100) * 100
            diff = abs(est - t)
            if diff <= 100: ok_100 += 1
            if diff <= 200: ok_200 += 1
            if diff <= 500: ok_500 += 1
            total += 1

    print(f"  Accuracy (±100): {ok_100}/{total} ({ok_100/total*100:.1f}%)")
    print(f"  Accuracy (±200): {ok_200}/{total} ({ok_200/total*100:.1f}%)")
    print(f"  Accuracy (±500): {ok_500}/{total} ({ok_500/total*100:.1f}%)")


if __name__ == '__main__':
    main()
