#!/usr/bin/env python3
"""
[OBJECTIVE] Calculate NET gold (income - spending) from credit records

KEY INSIGHT: Negative credit values exist! This means:
- Positive credits = gold EARNED
- Negative credits = gold SPENT
- Net = positive + negative (algebraic sum)

Test if NET gold from all actions matches truth gold better than just positive sums.
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


def scan_credits_net(data, valid_eids):
    """Scan credits and separate positive/negative by action."""
    result = {
        'net': defaultdict(lambda: defaultdict(float)),       # Algebraic sum
        'income': defaultdict(lambda: defaultdict(float)),    # Only positive
        'spending': defaultdict(lambda: defaultdict(float)),  # Only negative (abs)
    }

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

        if not math.isnan(value) and not math.isinf(value) and -10000 <= value <= 10000:
            result['net'][action][eid] += value

            if value > 0:
                result['income'][action][eid] += value
            elif value < 0:
                result['spending'][action][eid] += abs(value)

        pos += 3

    return result


def main():
    print("[STAGE:begin:data_loading]")

    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    all_match_data = []

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
        for tname, tdata in match['players'].items():
            if 'gold' not in tdata:
                continue
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p_obj in players:
                if p_obj['name'] == short or tname.endswith(p_obj['name']):
                    truth_gold[p_obj['eid_be']] = tdata['gold']
                    valid_eids.add(p_obj['eid_be'])
                    break

        if not truth_gold:
            continue

        credit_data = scan_credits_net(all_data, valid_eids)

        all_match_data.append({
            'match_idx': match_idx,
            'truth_gold': truth_gold,
            'credit_data': credit_data,
        })

    print(f"[DATA] Loaded {len(all_match_data)} matches")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:net_gold_test]")
    print("TEST NET GOLD (income - spending)")
    print("=" * 70)

    priority_actions = [0x02, 0x04, 0x05, 0x06, 0x08]

    print(f"[FINDING] Testing action combinations with NET calculation:")

    best_results = []

    for size in range(1, 4):
        for combo in combinations(priority_actions, size):
            all_truth = []
            all_net = []

            for md in all_match_data:
                for e in md['truth_gold'].keys():
                    all_truth.append(md['truth_gold'][e])
                    net_sum = sum(md['credit_data']['net'].get(a, {}).get(e, 0) for a in combo)
                    all_net.append(net_sum)

            corr = pearson_corr(all_truth, all_net)
            if abs(corr) < 0.95:
                continue

            slope, intercept, _ = linear_regression(all_net, all_truth)
            predictions = [round((slope * n + intercept) / 100) * 100 for n in all_net]

            ok_100 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 100)
            ok_200 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 200)
            ok_500 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 500)
            total = len(all_truth)

            mae = sum(abs(p - t) for p, t in zip(predictions, all_truth)) / total

            best_results.append({
                'combo': combo,
                'corr': corr,
                'slope': slope,
                'intercept': intercept,
                'acc_100': ok_100 / total * 100,
                'acc_200': ok_200 / total * 100,
                'acc_500': ok_500 / total * 100,
                'mae': mae,
            })

    best_results.sort(key=lambda x: x['acc_200'], reverse=True)

    if best_results:
        print(f"\n[FINDING] Top NET gold formulas:")
        for i, res in enumerate(best_results[:10], 1):
            combo_str = '+'.join(f'0x{a:02X}' for a in res['combo'])
            print(f"  {i:2d}. [{combo_str:20s}]: r={res['corr']:.4f}, "
                  f"acc±100={res['acc_100']:5.1f}%, acc±200={res['acc_200']:5.1f}%, "
                  f"acc±500={res['acc_500']:5.1f}%, MAE={res['mae']:5.0f}")
    else:
        print(f"[LIMITATION] No strong NET gold correlations found")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:net_gold_test]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:income_only_test]")
    print("TEST INCOME ONLY (positive values, all actions)")
    print("=" * 70)

    all_truth = []
    all_income_total = []

    for md in all_match_data:
        for e in md['truth_gold'].keys():
            all_truth.append(md['truth_gold'][e])
            # Sum ALL positive credits across ALL actions
            total_income = 0
            for action in md['credit_data']['income']:
                total_income += md['credit_data']['income'][action].get(e, 0)
            all_income_total.append(total_income)

    corr = pearson_corr(all_truth, all_income_total)
    slope, intercept, _ = linear_regression(all_income_total, all_truth)
    predictions = [round((slope * i + intercept) / 100) * 100 for i in all_income_total]

    ok_100 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 100)
    ok_200 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 200)
    ok_500 = sum(1 for p, t in zip(predictions, all_truth) if abs(p - t) <= 500)
    total = len(all_truth)
    mae = sum(abs(p - t) for p, t in zip(predictions, all_truth)) / total

    print(f"[FINDING] ALL positive credits (all actions):")
    print(f"  Correlation: r={corr:.4f}")
    print(f"  Regression: y = {slope:.4f}x + {intercept:.0f}")
    print(f"  Accuracy ±100: {ok_100}/{total} ({ok_100/total*100:.1f}%)")
    print(f"  Accuracy ±200: {ok_200}/{total} ({ok_200/total*100:.1f}%)")
    print(f"  Accuracy ±500: {ok_500}/{total} ({ok_500/total*100:.1f}%)")
    print(f"  MAE: {mae:.0f} gold")

    if ok_200 / total >= 0.8:
        print(f"\n[FINDING] ✓✓✓ TARGET ACHIEVED: {ok_200/total*100:.1f}% >= 80% ✓✓✓")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:income_only_test]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:cross_validation]")
    print("CROSS-VALIDATE BEST FORMULA")
    print("=" * 70)

    if best_results:
        best = best_results[0]
        combo = best['combo']
        combo_str = '+'.join(f'0x{a:02X}' for a in combo)

        print(f"[FINDING] Cross-validating: NET[{combo_str}]")

        total_ok_100 = 0
        total_ok_200 = 0
        total_ok_500 = 0
        total_players = 0

        for test_idx in range(len(all_match_data)):
            test_md = all_match_data[test_idx]

            train_x = []
            train_y = []
            for train_idx in range(len(all_match_data)):
                if train_idx == test_idx:
                    continue
                for e in all_match_data[train_idx]['truth_gold'].keys():
                    net_sum = sum(all_match_data[train_idx]['credit_data']['net'].get(a, {}).get(e, 0)
                                 for a in combo)
                    train_x.append(net_sum)
                    train_y.append(all_match_data[train_idx]['truth_gold'][e])

            slope, intercept, _ = linear_regression(train_x, train_y)

            for e in test_md['truth_gold'].keys():
                net = sum(test_md['credit_data']['net'].get(a, {}).get(e, 0) for a in combo)
                truth = test_md['truth_gold'][e]
                est = round((slope * net + intercept) / 100) * 100
                diff = abs(est - truth)
                if diff <= 100:
                    total_ok_100 += 1
                if diff <= 200:
                    total_ok_200 += 1
                if diff <= 500:
                    total_ok_500 += 1
                total_players += 1

        print(f"\n[STAT:formula] NET[{combo_str}]")
        print(f"[STAT:acc_100] {total_ok_100}/{total_players} ({total_ok_100/total_players*100:.1f}%)")
        print(f"[STAT:acc_200] {total_ok_200}/{total_players} ({total_ok_200/total_players*100:.1f}%)")
        print(f"[STAT:acc_500] {total_ok_500}/{total_players} ({total_ok_500/total_players*100:.1f}%)")

        if total_ok_200 / total_players >= 0.8:
            print(f"\n[FINDING] ✓✓✓ TARGET ACHIEVED ✓✓✓")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:cross_validation]")


if __name__ == '__main__':
    main()
