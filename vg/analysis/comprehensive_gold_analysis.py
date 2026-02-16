#!/usr/bin/env python3
"""
[OBJECTIVE] Improve gold estimation from 46.9% (±200) to >80% (±200)

Comprehensive Gold Analysis - Test all strategies:
1. All credit values (remove >2.0 filter) - flags might be additive
2. Weighted action combinations
3. Different value thresholds
4. Frame-based analysis (final frame gold)
5. Include credit counts as features
6. Polynomial regression
7. Per-role/hero adjustments
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
    """Extract player blocks with entity IDs and names."""
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
    """Calculate Pearson correlation coefficient."""
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


def scan_all_credits_multifilter(data, valid_eids):
    """Scan credits with multiple value filters."""
    result = {
        'all': defaultdict(lambda: defaultdict(float)),      # No filter
        'gt2': defaultdict(lambda: defaultdict(float)),      # > 2.0
        'gt1': defaultdict(lambda: defaultdict(float)),      # > 1.0
        'flags': defaultdict(lambda: defaultdict(float)),    # Only 0.5, 1.0
        'income': defaultdict(lambda: defaultdict(float)),   # > 5.0 (real gold)
    }
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

        if not math.isnan(value) and not math.isinf(value) and 0 <= value <= 10000:
            result['all'][action][eid] += value
            counts[action][eid] += 1

            if value > 2.0:
                result['gt2'][action][eid] += value
            if value > 1.0:
                result['gt1'][action][eid] += value
            if abs(value - 0.5) < 0.01 or abs(value - 1.0) < 0.01:
                result['flags'][action][eid] += value
            if value > 5.0:
                result['income'][action][eid] += value

        pos += 3

    return result, counts


def scan_frame_gold(frame_data, valid_eids):
    """Try to extract gold from player state in a single frame."""
    # This is exploratory - look for gold values near player blocks
    gold_estimates = {}

    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = frame_data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(frame_data):
                eid_le = struct.unpack('<H', frame_data[pos + 0xA5:pos + 0xA5 + 2])[0]
                eid_be = struct.unpack('>H', struct.pack('<H', eid_le))[0]

                if eid_be in valid_eids:
                    # Scan nearby for gold-like values (100-20000 range)
                    for offset in range(0, 200, 4):
                        if pos + offset + 4 > len(frame_data):
                            break
                        try:
                            val_f32 = struct.unpack_from(">f", frame_data, pos + offset)[0]
                            if 500 <= val_f32 <= 25000 and val_f32 % 100 < 50:
                                # Candidate gold value
                                if eid_be not in gold_estimates or abs(val_f32 % 100) < abs(gold_estimates[eid_be] % 100):
                                    gold_estimates[eid_be] = val_f32
                        except:
                            pass
            pos += 1

    return gold_estimates


def evaluate_formula(formula_name, predictions, truth_vals):
    """Evaluate prediction accuracy."""
    ok_100 = sum(1 for p, t in zip(predictions, truth_vals) if abs(p - t) <= 100)
    ok_200 = sum(1 for p, t in zip(predictions, truth_vals) if abs(p - t) <= 200)
    ok_500 = sum(1 for p, t in zip(predictions, truth_vals) if abs(p - t) <= 500)
    total = len(truth_vals)

    mae = sum(abs(p - t) for p, t in zip(predictions, truth_vals)) / total if total > 0 else 0

    return {
        'formula': formula_name,
        'acc_100': ok_100 / total * 100 if total > 0 else 0,
        'acc_200': ok_200 / total * 100 if total > 0 else 0,
        'acc_500': ok_500 / total * 100 if total > 0 else 0,
        'mae': mae,
        'count': f"{ok_100}/{total}",
    }


def main():
    print("[STAGE:begin:data_loading]")

    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    all_match_data = []

    for match_idx, match in enumerate(truth['matches']):
        if match_idx == 8:  # Incomplete match
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
        last_frame = frames[-1].read_bytes() if frames else f0

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

        action_sums, action_counts = scan_all_credits_multifilter(all_data, valid_eids)
        frame_gold = scan_frame_gold(last_frame, valid_eids)

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
            'frame_gold': frame_gold,
        })

    print(f"[DATA] Loaded {len(all_match_data)} matches with gold truth data")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:exploration]")
    print("STRATEGY 1: Test all filter types for action 0x06")
    print("=" * 70)

    results = []

    for filter_name in ['all', 'gt2', 'gt1', 'income']:
        all_truth = []
        all_detected = []
        for md in all_match_data:
            for e in md['eids']:
                all_truth.append(md['truth_gold'][e])
                all_detected.append(md['action_sums'][filter_name].get(0x06, {}).get(e, 0))

        corr = pearson_corr(all_truth, all_detected)
        slope, intercept, _ = linear_regression(all_detected, all_truth)

        predictions = [round((slope * d + intercept) / 100) * 100 for d in all_detected]
        result = evaluate_formula(f"0x06_{filter_name}", predictions, all_truth)
        result['corr'] = corr
        result['slope'] = slope
        result['intercept'] = intercept
        results.append(result)

        print(f"  [0x06 {filter_name:6s}]: r={corr:.4f}, slope={slope:.4f}, int={intercept:6.0f}, "
              f"acc±200={result['acc_200']:5.1f}%, MAE={result['mae']:6.0f}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:exploration]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:action_exploration]")
    print("STRATEGY 2: Explore all action bytes (filter=all)")
    print("=" * 70)

    all_actions = set()
    for md in all_match_data:
        all_actions.update(md['action_sums']['all'].keys())

    action_results = []
    for action in sorted(all_actions):
        all_truth = []
        all_detected = []
        for md in all_match_data:
            for e in md['eids']:
                all_truth.append(md['truth_gold'][e])
                all_detected.append(md['action_sums']['all'].get(action, {}).get(e, 0))

        if not any(d > 0 for d in all_detected):
            continue

        corr = pearson_corr(all_truth, all_detected)
        if abs(corr) < 0.5:
            continue

        slope, intercept, _ = linear_regression(all_detected, all_truth)
        predictions = [round((slope * d + intercept) / 100) * 100 for d in all_detected]
        result = evaluate_formula(f"0x{action:02X}_all", predictions, all_truth)
        result['corr'] = corr
        result['action'] = action
        action_results.append(result)

    action_results.sort(key=lambda x: x['acc_200'], reverse=True)

    print(f"[FINDING] Top action bytes by ±200 accuracy:")
    for res in action_results[:5]:
        print(f"  0x{res['action']:02X}: r={res['corr']:.4f}, acc±200={res['acc_200']:5.1f}%, "
              f"MAE={res['mae']:6.0f}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:action_exploration]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:combination_search]")
    print("STRATEGY 3: Action byte combinations (no value filter)")
    print("=" * 70)

    candidate_actions = [res['action'] for res in action_results if res['corr'] > 0.7][:6]
    print(f"[DATA] Testing combinations of: {[f'0x{a:02X}' for a in candidate_actions]}")

    best_combos = []

    for size in range(1, min(len(candidate_actions) + 1, 4)):
        for combo in combinations(candidate_actions, size):
            all_truth = []
            all_detected = []
            for md in all_match_data:
                for e in md['eids']:
                    all_truth.append(md['truth_gold'][e])
                    total_sum = sum(md['action_sums']['all'].get(a, {}).get(e, 0) for a in combo)
                    all_detected.append(total_sum)

            corr = pearson_corr(all_truth, all_detected)
            if abs(corr) < 0.9:
                continue

            slope, intercept, _ = linear_regression(all_detected, all_truth)
            predictions = [round((slope * d + intercept) / 100) * 100 for d in all_detected]
            result = evaluate_formula('+'.join(f'0x{a:02X}' for a in combo), predictions, all_truth)
            result['corr'] = corr
            result['combo'] = combo

            if result['acc_200'] > 40:
                best_combos.append(result)

    best_combos.sort(key=lambda x: x['acc_200'], reverse=True)

    print(f"[FINDING] Top action combinations:")
    for res in best_combos[:10]:
        print(f"  [{res['formula']:20s}]: r={res['corr']:.4f}, acc±200={res['acc_200']:5.1f}%, "
              f"MAE={res['mae']:6.0f}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:combination_search]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:frame_gold_search]")
    print("STRATEGY 4: Last frame gold extraction")
    print("=" * 70)

    all_truth = []
    all_frame_gold = []
    for md in all_match_data:
        for e in md['eids']:
            if e in md['frame_gold']:
                all_truth.append(md['truth_gold'][e])
                all_frame_gold.append(md['frame_gold'][e])

    if len(all_truth) > 10:
        corr = pearson_corr(all_truth, all_frame_gold)
        predictions = [round(g / 100) * 100 for g in all_frame_gold]
        result = evaluate_formula("frame_gold", predictions, all_truth)

        print(f"[FINDING] Frame gold extraction: r={corr:.4f}, acc±200={result['acc_200']:.1f}%, "
              f"samples={result['count']}")
    else:
        print(f"[LIMITATION] Insufficient frame gold samples: {len(all_truth)}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:frame_gold_search]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:cross_validation]")
    print("STRATEGY 5: Cross-validated best formula")
    print("=" * 70)

    if best_combos:
        best_formula = best_combos[0]
        combo = best_formula['combo']

        total_ok_200 = 0
        total_ok_500 = 0
        total_players = 0
        match_results = []

        for test_idx in range(len(all_match_data)):
            test_md = all_match_data[test_idx]

            # Train on other matches
            train_x = []
            train_y = []
            for train_idx in range(len(all_match_data)):
                if train_idx == test_idx:
                    continue
                for e in all_match_data[train_idx]['eids']:
                    total_sum = sum(all_match_data[train_idx]['action_sums']['all'].get(a, {}).get(e, 0)
                                   for a in combo)
                    train_x.append(total_sum)
                    train_y.append(all_match_data[train_idx]['truth_gold'][e])

            slope, intercept, _ = linear_regression(train_x, train_y)

            # Test
            match_ok_200 = 0
            match_ok_500 = 0
            for e in test_md['eids']:
                detected = sum(test_md['action_sums']['all'].get(a, {}).get(e, 0) for a in combo)
                truth = test_md['truth_gold'][e]
                est = round((slope * detected + intercept) / 100) * 100
                diff = abs(est - truth)
                if diff <= 200:
                    match_ok_200 += 1
                if diff <= 500:
                    match_ok_500 += 1
                total_players += 1

            total_ok_200 += match_ok_200
            total_ok_500 += match_ok_500
            pct = match_ok_200 / len(test_md['eids']) * 100
            match_results.append({'match': test_md['match_idx']+1, 'acc': pct})

        combo_str = '+'.join(f'0x{a:02X}' for a in combo)
        print(f"[FINDING] Best formula [{combo_str}] cross-validated:")
        print(f"[STAT:acc_200] {total_ok_200}/{total_players} ({total_ok_200/total_players*100:.1f}%)")
        print(f"[STAT:acc_500] {total_ok_500}/{total_players} ({total_ok_500/total_players*100:.1f}%)")

        if total_ok_200 / total_players >= 0.8:
            print(f"\n[FINDING] ✓ TARGET ACHIEVED: ±200 accuracy >= 80%")
        else:
            print(f"\n[LIMITATION] Target not reached (need 80%, got {total_ok_200/total_players*100:.1f}%)")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:cross_validation]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:final_summary]")
    print("FINAL RECOMMENDATIONS")
    print("=" * 70)

    if best_combos:
        top3 = best_combos[:3]
        for i, res in enumerate(top3, 1):
            print(f"\n[FINDING] Option {i}: {res['formula']}")
            print(f"  Correlation: r={res['corr']:.4f}")
            print(f"  Accuracy ±200: {res['acc_200']:.1f}%")
            print(f"  Accuracy ±500: {res['acc_500']:.1f}%")
            print(f"  Mean Absolute Error: {res['mae']:.0f} gold")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:final_summary]")


if __name__ == '__main__':
    main()
