#!/usr/bin/env python3
"""
Kraken vs Gold Mine Distinguisher
==================================
Analyzes objective death events (eid > 65000 in [08 04 31]) across all tournament matches
to find binary patterns that separate Kraken from Gold Mine.

Strategy:
1. Extract all objective death clusters (within 5s window)
2. For each cluster: EID count, EID span, raw bytes after death
3. Credit records within 200 bytes after death (action 0x04, 0x06, 0x08)
4. Timing between consecutive objective events (respawn cadence)
5. Look for distinguishing headers immediately after death records

Game knowledge reference:
  Gold Mine  - gives ~150 gold/player, periodic income, team buff
  Kraken     - summoned pushing minion, gives gold on kill, destroys it early
"""

import json
import struct
import sys
from pathlib import Path
from collections import defaultdict

# ---- headers ----
DEATH_HEADER   = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER  = bytes([0x10, 0x04, 0x1D])
KILL_HEADER    = bytes([0x18, 0x04, 0x1C])

def read_f32_be(data, offset):
    try:
        return struct.unpack('>f', data[offset:offset+4])[0]
    except struct.error:
        return None

def read_u16_be(data, offset):
    try:
        return struct.unpack('>H', data[offset:offset+2])[0]
    except struct.error:
        return None

def read_u16_le(data, offset):
    try:
        return struct.unpack('<H', data[offset:offset+2])[0]
    except struct.error:
        return None

def find_all(data, pattern):
    """Find all offsets of pattern in data."""
    offsets = []
    start = 0
    while True:
        idx = data.find(pattern, start)
        if idx == -1:
            break
        offsets.append(idx)
        start = idx + 1
    return offsets

def parse_death_record(data, offset):
    """
    Parse a death record at offset (offset points to start of [08 04 31]).
    Death: [08 04 31] [00 00] [eid BE 2B] [00 00] [ts f32 BE] [00 00 00]
    Returns (eid, timestamp) or None.
    """
    try:
        hdr = data[offset:offset+3]
        if hdr != DEATH_HEADER:
            return None
        nul1 = data[offset+3:offset+5]
        if nul1 != b'\x00\x00':
            return None
        eid = read_u16_be(data, offset+5)
        nul2 = data[offset+7:offset+9]
        if nul2 != b'\x00\x00':
            return None
        ts = read_f32_be(data, offset+9)
        return (eid, ts)
    except Exception:
        return None

def parse_credit_record(data, offset):
    """
    Parse credit record at offset (offset points to [10 04 1D]).
    Credit: [10 04 1D] [00 00] [eid BE 2B] [value f32 BE] [action_byte]
    Returns (eid, value, action) or None.
    """
    try:
        hdr = data[offset:offset+3]
        if hdr != CREDIT_HEADER:
            return None
        nul1 = data[offset+3:offset+5]
        if nul1 != b'\x00\x00':
            return None
        eid = read_u16_be(data, offset+5)
        value = read_f32_be(data, offset+7)
        action = data[offset+11]
        return (eid, value, action)
    except Exception:
        return None

def get_header_at(data, offset):
    """Return 3-byte header as hex string."""
    if offset + 3 <= len(data):
        return data[offset:offset+3].hex(' ').upper()
    return '??'

def analyze_file(replay_path):
    """Full objective event analysis for one replay file."""
    path = Path(replay_path)
    if not path.exists():
        return None

    data = path.read_bytes()
    match_label = path.parent.name + '/' + path.name[:8]

    # 1. Find ALL death header offsets
    all_death_offsets = find_all(data, DEATH_HEADER)

    # 2. Parse only objective deaths (eid > 65000)
    obj_deaths = []
    for off in all_death_offsets:
        rec = parse_death_record(data, off)
        if rec is None:
            continue
        eid, ts = rec
        if eid is None or ts is None:
            continue
        if eid > 65000 and 0 < ts < 5000:
            obj_deaths.append({'offset': off, 'eid': eid, 'ts': ts})

    if not obj_deaths:
        return {'match': match_label, 'n_obj_deaths': 0, 'n_clusters': 0, 'clusters': [], 'intervals': []}

    # Sort by timestamp
    obj_deaths.sort(key=lambda x: x['ts'])

    # 3. Cluster deaths within 5 seconds
    clusters = []
    current = [obj_deaths[0]]
    for i in range(1, len(obj_deaths)):
        if obj_deaths[i]['ts'] - current[-1]['ts'] <= 5.0:
            current.append(obj_deaths[i])
        else:
            clusters.append(current)
            current = [obj_deaths[i]]
    clusters.append(current)

    # 4. Analyze each cluster
    result_clusters = []
    for cluster in clusters:
        eids = [d['eid'] for d in cluster]
        timestamps = [d['ts'] for d in cluster]
        offsets = [d['offset'] for d in cluster]
        eid_min, eid_max = min(eids), max(eids)
        eid_span = eid_max - eid_min
        ts_center = timestamps[0]
        n = len(cluster)

        # 5. For each death in cluster, extract 50 bytes after and credit records within 200 bytes
        post_bytes_all = []
        credit_records = []
        header_after_death = []

        for death in cluster:
            off = death['offset']
            death_end = off + 12  # death record is ~12 bytes

            # 50 raw bytes after this death record
            raw50 = data[death_end:death_end+50].hex(' ').upper()
            post_bytes_all.append(raw50)

            # Header immediately after death record
            hdr3 = get_header_at(data, death_end)
            header_after_death.append(hdr3)

            # Scan 200 bytes after death for credit records
            scan_end = min(death_end + 200, len(data))
            pos = death_end
            while pos < scan_end - 12:
                if data[pos:pos+3] == CREDIT_HEADER:
                    cr = parse_credit_record(data, pos)
                    if cr:
                        eid_cr, val, action = cr
                        credit_records.append({
                            'eid': eid_cr,
                            'value': round(val, 4) if val else None,
                            'action': f'0x{action:02X}',
                            'death_eid': death['eid'],
                        })
                    pos += 12
                else:
                    pos += 1

        # 6. Unique headers immediately after death records
        unique_headers = list(dict.fromkeys(header_after_death))

        # 7. Action byte distribution in credits
        action_counts = defaultdict(int)
        action_values = defaultdict(list)
        for cr in credit_records:
            action_counts[cr['action']] += 1
            if cr['value'] is not None:
                action_values[cr['action']].append(cr['value'])

        # 8. Gold paid out (action 0x04 = objective bounty based on prior research)
        gold_actions = {}
        for act, vals in action_values.items():
            gold_actions[act] = {
                'count': len(vals),
                'values': sorted(set(round(v, 1) for v in vals)),
                'total': round(sum(vals), 2),
            }

        result_clusters.append({
            'ts': round(ts_center, 2),
            'n_deaths': n,
            'eids': eids,
            'eid_min': eid_min,
            'eid_max': eid_max,
            'eid_span': eid_span,
            'headers_after': unique_headers,
            'first_post50': post_bytes_all[0] if post_bytes_all else '',
            'gold_actions': gold_actions,
            'n_credits': len(credit_records),
        })

    # 9. Compute inter-event timing (respawn cadence)
    times = [c['ts'] for c in result_clusters]
    intervals = [round(times[i+1] - times[i], 2) for i in range(len(times)-1)]

    return {
        'match': match_label,
        'n_obj_deaths': len(obj_deaths),
        'n_clusters': len(result_clusters),
        'clusters': result_clusters,
        'intervals': intervals,
    }


def main():
    truth_path = Path('vg/output/tournament_truth.json')
    with open(truth_path) as f:
        truth = json.load(f)

    replay_files = [m['replay_file'] for m in truth['matches']]

    all_results = []
    for rp in replay_files:
        print(f"\nAnalyzing: {Path(rp).parent.name} ...")
        result = analyze_file(rp)
        if result:
            all_results.append(result)

    # ---- Print summary ----
    print("\n" + "="*80)
    print("OBJECTIVE DEATH CLUSTER ANALYSIS")
    print("="*80)

    # Aggregate cluster stats for pattern finding
    cluster_summary = []

    for res in all_results:
        print(f"\n[MATCH] {res['match']}")
        print(f"  Obj deaths: {res['n_obj_deaths']}, Clusters: {res['n_clusters']}")
        print(f"  Inter-event intervals: {res['intervals']}")

        for i, cl in enumerate(res['clusters']):
            print(f"\n  [CLUSTER {i}] ts={cl['ts']:.1f}s  n={cl['n_deaths']}  "
                  f"eid_span={cl['eid_span']}  eids={cl['eids']}")
            print(f"    headers_after: {cl['headers_after']}")
            print(f"    n_credits={cl['n_credits']}  gold_actions={cl['gold_actions']}")
            print(f"    first_post50: {cl['first_post50'][:60]}...")

            cluster_summary.append({
                'match': res['match'],
                'ts': cl['ts'],
                'n': cl['n_deaths'],
                'eid_span': cl['eid_span'],
                'eid_min': cl['eid_min'],
                'eid_max': cl['eid_max'],
                'headers': cl['headers_after'],
                'gold_actions': cl['gold_actions'],
                'n_credits': cl['n_credits'],
            })

    # ---- Pattern analysis ----
    print("\n" + "="*80)
    print("PATTERN ANALYSIS: Candidate Distinguishers")
    print("="*80)

    # Group by cluster size
    by_size = defaultdict(list)
    for cl in cluster_summary:
        by_size[cl['n']].append(cl)

    print("\nCluster size distribution:")
    for size in sorted(by_size):
        entries = by_size[size]
        spans = [e['eid_span'] for e in entries]
        headers_flat = [h for e in entries for h in e['headers']]
        from collections import Counter
        hdr_ctr = Counter(headers_flat)
        print(f"  n={size}: {len(entries)} events, "
              f"eid_spans={sorted(set(spans))}, "
              f"headers={dict(hdr_ctr)}")

    # Unique header combos
    print("\nHeader-after-death combos by cluster size:")
    for size in sorted(by_size):
        hdr_sets = [tuple(sorted(set(e['headers']))) for e in by_size[size]]
        from collections import Counter
        print(f"  n={size}: {dict(Counter(hdr_sets))}")

    # Credit action patterns by cluster size
    print("\nCredit action patterns by cluster size:")
    for size in sorted(by_size):
        for e in by_size[size]:
            acts = {k: v['values'] for k, v in e['gold_actions'].items()}
            print(f"  n={size} ts={e['ts']:.0f}s: actions={acts}  n_credits={e['n_credits']}")

    # Save full results
    out_path = Path('vg/output/objective_cluster_analysis.json')
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\n[SAVED] Full results -> {out_path}")


if __name__ == '__main__':
    main()
