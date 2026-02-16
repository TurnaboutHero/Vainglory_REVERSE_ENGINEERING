#!/usr/bin/env python3
"""
Gold Action Byte Analysis - Sum credit record values per (entity, action_byte)
and correlate each action byte's totals with truth gold.

Credit record: [10 04 1D] [00 00] [eid BE] [value f32 BE] [action_byte]
Different action bytes may represent different reward types.
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict

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


def scan_credits_by_action(data, valid_eids):
    """Scan all credit records, group values by (eid, action_byte).

    Returns: dict of action_byte -> {eid: [values]}
    """
    result = defaultdict(lambda: defaultdict(list))

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
            result[action][eid].append(value)

        pos += 3

    return result


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    # Analyze first 3 matches
    for match_idx in [0, 1, 2]:
        match = truth['matches'][match_idx]
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}")

        p = Path(match['replay_file'])
        d = p.parent
        base = p.stem.rsplit('.', 1)[0]
        frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))

        # Concatenate all frames
        all_data = b''
        for f_path in frames:
            all_data += f_path.read_bytes()

        f0 = frames[0].read_bytes()
        players = extract_players(f0)

        truth_gold = {}
        valid_eids = set()
        name_by_eid = {}
        for tname, tdata in match['players'].items():
            short = tname.split('_', 1)[-1] if '_' in tname else tname
            for p_obj in players:
                if p_obj['name'] == short or tname.endswith(p_obj['name']):
                    truth_gold[p_obj['eid_be']] = tdata['gold']
                    valid_eids.add(p_obj['eid_be'])
                    name_by_eid[p_obj['eid_be']] = tname
                    break

        print(f"  Frames: {len(frames)}, Data: {len(all_data):,} bytes")

        # Scan credits by action byte
        credits = scan_credits_by_action(all_data, valid_eids)

        eids = sorted(truth_gold.keys())
        truth_vec = [truth_gold[e] for e in eids]

        print(f"\n  Action byte analysis:")
        print(f"  {'Action':8s} {'TotalVal':>10s} {'Count':>7s} {'SumCorr':>8s} {'AvgCorr':>8s} {'CntCorr':>8s}")

        good_actions = []

        for action in sorted(credits.keys()):
            per_eid = credits[action]

            # Sum, avg, count per player
            sums = [sum(per_eid.get(e, [0])) for e in eids]
            counts = [len(per_eid.get(e, [])) for e in eids]
            avgs = [s/c if c > 0 else 0 for s, c in zip(sums, counts)]
            total_val = sum(sums)
            total_count = sum(counts)

            sum_corr = pearson_corr(truth_vec, sums)
            avg_corr = pearson_corr(truth_vec, avgs)
            cnt_corr = pearson_corr(truth_vec, counts)

            marker = ""
            if abs(sum_corr) > 0.8:
                marker = " ***"
                good_actions.append((action, sum_corr, sums))

            print(f"  0x{action:02X}     {total_val:10.0f} {total_count:7d} {sum_corr:8.3f} {avg_corr:8.3f} {cnt_corr:8.3f}{marker}")

        # Show details for high-correlation actions
        if good_actions:
            print(f"\n  High-correlation action bytes:")
            for action, corr, sums in good_actions:
                print(f"\n  Action 0x{action:02X} (r={corr:.3f}):")
                for i, eid in enumerate(eids):
                    name = name_by_eid[eid]
                    print(f"    {name:25s} truth={truth_gold[eid]:6d}, sum={sums[i]:10.1f}, ratio={sums[i]/truth_gold[eid]:.3f}")

        # Try combining action bytes
        print(f"\n  Combining action byte sums (top combos):")
        action_list = sorted(credits.keys())
        best_combos = []

        # Try all pairs
        for i, a1 in enumerate(action_list):
            sums1 = [sum(credits[a1].get(e, [0])) for e in eids]
            for a2 in action_list[i+1:]:
                sums2 = [sum(credits[a2].get(e, [0])) for e in eids]
                combined = [s1 + s2 for s1, s2 in zip(sums1, sums2)]
                corr = pearson_corr(truth_vec, combined)
                if abs(corr) > 0.85:
                    best_combos.append((f"0x{a1:02X}+0x{a2:02X}", corr, combined))

        # Try filtering by value range within each action
        print(f"\n  Filtering by value range within action bytes:")
        for action in sorted(credits.keys()):
            per_eid = credits[action]
            # Only sum values > 2 (exclude flags like 1.0, 0.5)
            gold_sums = []
            for eid in eids:
                vals = per_eid.get(eid, [])
                gold_vals = [v for v in vals if v > 2.0]
                gold_sums.append(sum(gold_vals))

            if any(s > 0 for s in gold_sums):
                corr = pearson_corr(truth_vec, gold_sums)
                if abs(corr) > 0.7:
                    total = sum(gold_sums)
                    truth_total = sum(truth_vec)
                    print(f"    0x{action:02X} (val>2): sum={total:.0f}, truth_sum={truth_total}, ratio={total/truth_total:.2f}, r={corr:.3f}")

        best_combos.sort(key=lambda x: -abs(x[1]))
        for name, corr, combined in best_combos[:5]:
            total = sum(combined)
            truth_total = sum(truth_vec)
            print(f"    {name}: r={corr:.3f}, sum={total:.0f}, truth_sum={truth_total}, ratio={total/truth_total:.2f}")


if __name__ == '__main__':
    main()
