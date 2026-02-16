#!/usr/bin/env python3
"""
[OBJECTIVE] Detailed per-match gold breakdown to identify systematic errors

Analyze each match individually to find patterns in the gap between detected
gold and truth gold. Check if the gap is consistent or varies by match/player.
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


def scan_credits_detailed(data, valid_eids):
    """Scan ALL credit records without any filtering."""
    by_action = defaultdict(lambda: defaultdict(list))  # action -> eid -> [values]

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
            by_action[action][eid].append(value)

        pos += 3

    # Convert to sums and stats
    result = {}
    for action in by_action:
        result[action] = {}
        for eid in by_action[action]:
            values = by_action[action][eid]
            result[action][eid] = {
                'sum': sum(values),
                'count': len(values),
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
            }

    return result


def main():
    print("[STAGE:begin:data_loading]")

    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    all_match_data = []

    for match_idx, match in enumerate(truth['matches']):
        if match_idx == 8:  # Incomplete
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

        credit_data = scan_credits_detailed(all_data, valid_eids)

        all_match_data.append({
            'match_idx': match_idx,
            'match_name': p.parent.parent.name,
            'duration': match['match_info'].get('duration_seconds', 0),
            'truth_gold': truth_gold,
            'credit_data': credit_data,
            'name_by_eid': name_by_eid,
        })

    print(f"[DATA] Loaded {len(all_match_data)} matches")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:per_match_analysis]")
    print("PER-MATCH DETAILED BREAKDOWN")
    print("=" * 70)

    all_ratios = []

    for md in all_match_data:
        print(f"\n[DATA] Match {md['match_idx']+1}: {md['match_name']} ({md['duration']}s)")

        # Calculate best formula for this match (0x06 + 0x08)
        for eid in sorted(md['truth_gold'].keys()):
            truth = md['truth_gold'][eid]
            name = md['name_by_eid'][eid]

            sum_06 = md['credit_data'].get(0x06, {}).get(eid, {}).get('sum', 0)
            sum_08 = md['credit_data'].get(0x08, {}).get(eid, {}).get('sum', 0)
            sum_combined = sum_06 + sum_08

            count_06 = md['credit_data'].get(0x06, {}).get(eid, {}).get('count', 0)
            count_08 = md['credit_data'].get(0x08, {}).get(eid, {}).get('count', 0)

            ratio = truth / sum_combined if sum_combined > 0 else 0
            diff = truth - sum_combined

            all_ratios.append(ratio)

            print(f"  {name:20s}: truth={truth:5.0f}, "
                  f"0x06={sum_06:7.0f} (n={count_06:3d}), "
                  f"0x08={sum_08:6.0f} (n={count_08:2d}), "
                  f"sum={sum_combined:7.0f}, "
                  f"diff={diff:+6.0f}, ratio={ratio:.3f}")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:per_match_analysis]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:ratio_analysis]")
    print("RATIO STATISTICS")
    print("=" * 70)

    if all_ratios:
        valid_ratios = [r for r in all_ratios if r > 0]
        avg_ratio = sum(valid_ratios) / len(valid_ratios)
        min_ratio = min(valid_ratios)
        max_ratio = max(valid_ratios)

        print(f"[STAT:avg_ratio] {avg_ratio:.4f}")
        print(f"[STAT:min_ratio] {min_ratio:.4f}")
        print(f"[STAT:max_ratio] {max_ratio:.4f}")
        print(f"[STAT:ratio_range] {max_ratio - min_ratio:.4f}")

        # Test if fixed multiplier works
        print(f"\n[FINDING] Testing fixed multiplier = {avg_ratio:.4f}")

        ok_100 = 0
        ok_200 = 0
        ok_500 = 0
        total = 0

        for md in all_match_data:
            for eid in md['truth_gold'].keys():
                truth = md['truth_gold'][eid]
                sum_06 = md['credit_data'].get(0x06, {}).get(eid, {}).get('sum', 0)
                sum_08 = md['credit_data'].get(0x08, {}).get(eid, {}).get('sum', 0)
                sum_combined = sum_06 + sum_08

                est = round((sum_combined * avg_ratio) / 100) * 100
                diff = abs(est - truth)

                if diff <= 100: ok_100 += 1
                if diff <= 200: ok_200 += 1
                if diff <= 500: ok_500 += 1
                total += 1

        print(f"[STAT:acc_100] {ok_100}/{total} ({ok_100/total*100:.1f}%)")
        print(f"[STAT:acc_200] {ok_200}/{total} ({ok_200/total*100:.1f}%)")
        print(f"[STAT:acc_500] {ok_500}/{total} ({ok_500/total*100:.1f}%)")

        if ok_200 / total >= 0.8:
            print(f"\n[FINDING] ✓ TARGET ACHIEVED with fixed multiplier!")
        else:
            print(f"\n[LIMITATION] Fixed multiplier not sufficient")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:ratio_analysis]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:action_inventory]")
    print("ALL ACTION BYTES PRESENT")
    print("=" * 70)

    all_actions = set()
    for md in all_match_data:
        all_actions.update(md['credit_data'].keys())

    print(f"[FINDING] Found {len(all_actions)} unique action bytes:")
    for action in sorted(all_actions):
        # Count total records across all matches
        total_records = 0
        total_sum = 0
        for md in all_match_data:
            for eid_stats in md['credit_data'].get(action, {}).values():
                total_records += eid_stats['count']
                total_sum += eid_stats['sum']

        print(f"  0x{action:02X}: {total_records:5d} records, total_sum={total_sum:10.0f}")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:action_inventory]")


if __name__ == '__main__':
    main()
