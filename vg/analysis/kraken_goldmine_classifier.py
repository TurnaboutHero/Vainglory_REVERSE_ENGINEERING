#!/usr/bin/env python3
"""
Kraken vs Gold Mine Classifier
================================
Tests the hypothesis:
  - Gold Mine death: NO player kill record within 300 bytes
  - Kraken death:    HAS player kill record within 300 bytes

Also examines:
  - EID ranges for each type
  - Credit records (action 0x04 value=150 for Gold Mine income)
  - Cluster size (n=1 for objectives, n>1 for minion waves)
  - Timing between repeated events (respawn cadence)
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

DEATH_HEADER  = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
KILL_HEADER   = bytes([0x18, 0x04, 0x1C])


def load_match(rp_str):
    rp = Path(rp_str)
    frame_dir = rp.parent
    base_name = rp.name.rsplit('.', 2)[0]
    frames = sorted(frame_dir.glob(f'{base_name}.*.vgr'),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return b''.join(f.read_bytes() for f in frames)


def get_player_eids(data):
    """Extract all player EIDs from kill records (killers with eid < 60000)."""
    eids = set()
    pos = 0
    while True:
        idx = data.find(KILL_HEADER, pos)
        if idx == -1:
            break
        pos = idx + 1
        if idx + 7 > len(data):
            continue
        killer = struct.unpack('>H', data[idx+5:idx+7])[0]
        if 1400 < killer < 60000:
            eids.add(killer)
    return eids


def get_obj_clusters(data, eid_threshold=60000, cluster_window=5.0, max_cluster=15):
    """Get objective death clusters."""
    deaths = []
    pos = 0
    while True:
        idx = data.find(DEATH_HEADER, pos)
        if idx == -1:
            break
        pos = idx + 1
        if idx + 13 > len(data):
            continue
        eid = struct.unpack('>H', data[idx+5:idx+7])[0]
        try:
            ts = struct.unpack('>f', data[idx+9:idx+13])[0]
        except Exception:
            continue
        if eid > eid_threshold and 0 < ts < 5000:
            deaths.append({'eid': eid, 'ts': ts, 'offset': idx})

    deaths.sort(key=lambda x: x['ts'])
    clusters = []
    if not deaths:
        return clusters
    cur = [deaths[0]]
    for d in deaths[1:]:
        if d['ts'] - cur[-1]['ts'] <= cluster_window:
            cur.append(d)
        else:
            clusters.append(cur)
            cur = [d]
    clusters.append(cur)
    return [c for c in clusters if 1 <= len(c) <= max_cluster]


def has_player_kill_nearby(data, cluster, player_eids, window=400):
    """Check if a player kill record exists within window bytes of any death in cluster."""
    for d in cluster:
        search_start = max(0, d['offset'] - window)
        search_end = min(len(data), d['offset'] + window)
        region = data[search_start:search_end]
        pk = 0
        while True:
            kidx = region.find(KILL_HEADER, pk)
            if kidx == -1:
                break
            pk = kidx + 1
            if kidx + 7 > len(region):
                continue
            killer = struct.unpack('>H', region[kidx+5:kidx+7])[0]
            if killer in player_eids:
                return True
    return False


def get_credits_after(data, cluster, window=1500):
    """Scan for credit records within window bytes of first death."""
    off = cluster[0]['offset']
    end = min(len(data), off + window)
    credits = []
    p = off + 12
    while p < end - 12:
        if data[p:p+3] == CREDIT_HEADER:
            eid_cr = struct.unpack('>H', data[p+5:p+7])[0]
            try:
                val = struct.unpack('>f', data[p+7:p+11])[0]
            except Exception:
                val = None
            action = data[p+11]
            credits.append({'eid': eid_cr, 'val': round(val, 1) if val else None,
                             'action': action})
            p += 12
        else:
            p += 1
    return credits


def main():
    truth = json.load(open('vg/output/tournament_truth.json'))

    all_results = []

    # Per-match player eid sets printed for verification
    print('=== Player EID sets (from kill records) ===')
    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        player_eids = get_player_eids(data)
        print(f'M{mi+1}: player_eids={sorted(player_eids)}')

    print()
    print('=== Objective cluster classification ===')
    print(f'{"Match":<6} {"CL":<3} {"ts":>6} {"n":>3} {"span":>6} {"eid_min":>7} '
          f'{"player_kill":>12} {"type_guess":>12} {"notes"}')
    print('-' * 90)

    goldmine_eids = []
    kraken_eids = []
    unknown_eids = []

    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        player_eids = get_player_eids(data)
        clusters = get_obj_clusters(data)

        for ci, cl in enumerate(clusters):
            eids = [d['eid'] for d in cl]
            ts = cl[0]['ts']
            n = len(cl)
            span = max(eids) - min(eids)
            eid_min = min(eids)

            player_kill = has_player_kill_nearby(data, cl, player_eids)

            # Get 0x04 credits near this cluster
            credits = get_credits_after(data, cl)
            act04_vals = [c['val'] for c in credits if c['action'] == 0x04 and c['val']]
            has_150 = any(abs(v - 150.0) < 5 for v in act04_vals)

            # Classification logic
            if n == 1 and not player_kill:
                type_guess = 'GOLDMINE?'
                goldmine_eids.append(eid_min)
            elif n == 1 and player_kill:
                type_guess = 'KRAKEN?'
                kraken_eids.append(eid_min)
            elif n > 1 and player_kill:
                type_guess = 'KRAKEN_MULTI?'
                kraken_eids.extend(eids)
            else:
                type_guess = 'UNKNOWN'
                unknown_eids.extend(eids)

            notes = f'0x04={sorted(set(round(v) for v in act04_vals))[:4]}'
            if has_150:
                notes += ' [150!]'

            print(f'M{mi+1:<5} {ci:<3} {ts:>6.0f} {n:>3} {span:>6} {eid_min:>7} '
                  f'{str(player_kill):>12} {type_guess:>12} {notes}')

            all_results.append({
                'match': mi + 1,
                'cluster': ci,
                'ts': round(ts, 1),
                'n': n,
                'span': span,
                'eid_min': eid_min,
                'eid_max': max(eids),
                'player_kill': player_kill,
                'type_guess': type_guess,
                'act04_vals': sorted(set(round(v) for v in act04_vals))
            })

    # Summary statistics
    print()
    print('='*60)
    print('EID RANGE SUMMARY')
    print('='*60)
    print(f'\nGOLDMINE? EIDs ({len(goldmine_eids)} total):')
    if goldmine_eids:
        print(f'  Range: {min(goldmine_eids)} - {max(goldmine_eids)}')
        print(f'  Values: {sorted(goldmine_eids)[:20]}')

    print(f'\nKRAKEN? EIDs ({len(kraken_eids)} total):')
    if kraken_eids:
        print(f'  Range: {min(kraken_eids)} - {max(kraken_eids)}')

    print(f'\nUNKNOWN EIDs ({len(unknown_eids)} total):')
    if unknown_eids:
        print(f'  Range: {min(unknown_eids)} - {max(unknown_eids)}')

    # Timing analysis: respawn cadence
    print()
    print('='*60)
    print('TIMING: Intervals between same-type clusters per match')
    print('='*60)
    for mi in range(1, len(truth['matches']) + 1):
        match_res = [r for r in all_results if r['match'] == mi]
        gm_times = sorted(r['ts'] for r in match_res if r['type_guess'] == 'GOLDMINE?')
        kr_times = sorted(r['ts'] for r in match_res if 'KRAKEN' in r['type_guess'])
        if gm_times:
            intervals = [round(gm_times[i+1]-gm_times[i], 1) for i in range(len(gm_times)-1)]
            print(f'M{mi} GOLDMINE? times={gm_times}  intervals={intervals}')
        if kr_times:
            intervals = [round(kr_times[i+1]-kr_times[i], 1) for i in range(len(kr_times)-1)]
            print(f'M{mi} KRAKEN?   times={kr_times}  intervals={intervals}')

    # Save
    out = Path('vg/output/kraken_goldmine_classification.json')
    out.parent.mkdir(exist_ok=True)
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f'\n[SAVED] {out}')


if __name__ == '__main__':
    main()
