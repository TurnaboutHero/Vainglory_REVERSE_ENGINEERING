#!/usr/bin/env python3
"""
Gold Action 0x06 Verification - Validate gold detection across all matches.

Finding: Credit records [10 04 1D] with action byte 0x06 and value > 2.0
have r=1.000 correlation with truth gold across 3 matches. Sum ≈ 93% of truth.

Verify on all 11 matches and check if per-player ratio is consistent enough
to estimate gold within ±100 (truth rounding granularity).
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


def sum_gold_action06(data, valid_eids, min_value=2.0):
    """Sum credit record values with action byte 0x06 and value > min_value."""
    gold_sums = defaultdict(float)

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

        if action == 0x06 and not math.isnan(value) and not math.isinf(value):
            if value > min_value:
                gold_sums[eid] += value

        pos += 3

    return gold_sums


def main():
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    total_correct_100 = 0
    total_correct_200 = 0
    total_players = 0
    all_ratios = []

    for match_idx, match in enumerate(truth['matches']):
        print(f"\n{'='*70}")
        print(f"Match {match_idx + 1}")

        if match_idx == 8:
            print("  SKIPPED (incomplete)")
            continue

        p = Path(match['replay_file'])
        if not p.exists():
            print("  File not found!")
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
            print("  No gold truth data")
            continue

        gold_sums = sum_gold_action06(all_data, valid_eids)

        eids = sorted(truth_gold.keys())
        truth_vec = [truth_gold[e] for e in eids]
        detected_vec = [gold_sums.get(e, 0) for e in eids]

        corr = pearson_corr(truth_vec, detected_vec)
        match_ratio = sum(detected_vec) / sum(truth_vec) if sum(truth_vec) > 0 else 0

        print(f"  Correlation: {corr:.4f}, ratio: {match_ratio:.4f}")
        print(f"  {'Player':25s} {'Truth':>6s} {'Raw':>8s} {'Ratio':>6s} {'Est':>7s} {'Diff':>6s}")
        print(f"  {'-'*65}")

        match_ok_100 = 0
        match_ok_200 = 0

        for eid in eids:
            t = truth_gold[eid]
            raw = gold_sums.get(eid, 0)
            ratio = raw / t if t > 0 else 0
            all_ratios.append(ratio)

            # Estimate: raw / match_ratio, rounded to nearest 100
            if match_ratio > 0:
                estimated = round(raw / match_ratio / 100) * 100
            else:
                estimated = 0

            diff = estimated - t
            ok = abs(diff) <= 100
            if abs(diff) <= 100:
                match_ok_100 += 1
            if abs(diff) <= 200:
                match_ok_200 += 1
            total_players += 1

            name = name_by_eid[eid]
            status = "OK" if ok else f"MISS"
            print(f"  {name:25s} {t:6d} {raw:8.0f} {ratio:6.3f} {estimated:7d} {diff:+6d} {status}")

        total_correct_100 += match_ok_100
        total_correct_200 += match_ok_200
        pct = match_ok_100 / len(eids) * 100
        print(f"  Match accuracy (±100): {match_ok_100}/{len(eids)} ({pct:.0f}%)")

    print(f"\n{'='*70}")
    print(f"OVERALL RESULTS")
    print(f"{'='*70}")
    if total_players > 0:
        pct100 = total_correct_100 / total_players * 100
        pct200 = total_correct_200 / total_players * 100
        print(f"Accuracy (±100): {total_correct_100}/{total_players} ({pct100:.1f}%)")
        print(f"Accuracy (±200): {total_correct_200}/{total_players} ({pct200:.1f}%)")

    if all_ratios:
        avg_ratio = sum(all_ratios) / len(all_ratios)
        std_ratio = math.sqrt(sum((r - avg_ratio) ** 2 for r in all_ratios) / len(all_ratios))
        print(f"Average ratio: {avg_ratio:.4f} ± {std_ratio:.4f}")
        print(f"Min ratio: {min(all_ratios):.4f}, Max ratio: {max(all_ratios):.4f}")


if __name__ == '__main__':
    main()
