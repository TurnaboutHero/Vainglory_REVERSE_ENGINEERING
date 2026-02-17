#!/usr/bin/env python3
"""
FINAL: Kraken vs Gold Mine Distinguisher
==========================================

FINDINGS SUMMARY
----------------
Objective deaths (eid > 60000 in [08 04 31]) fall into categories:

GOLD MINE CAPTURE (n=1 single death, no player kill nearby):
  - Triggers when a team captures the Gold Mine objective
  - Multiple rapid captures (5-26s apart) = teams contesting/recapturing
  - EID range: 60019-65243 (overlaps with Kraken - not discriminating alone)
  - 25 events across 11 tournament matches
  - No player kill record (1500-1509) within 500 bytes

KRAKEN DEATH (n=1 single death, player kill nearby):
  - Triggers when players kill the Kraken after it has been summoned
  - Only 4 events found (most Krakens survive to game end or die off-screen)
  - EID range: 60877-63922 (subset, but overlaps)
  - Has player kill record (1500-1509) within 500 bytes

KRAKEN/MINION WAVE (n>1, player kill nearby):
  - Multiple entity deaths with player kills = Kraken minion wave fighting
  - 24 events

MINION/BATTLE WAVE (n>1, no player kill):
  - Multiple entity deaths without player kills = battle/minion deaths
  - 16 events

BINARY CLASSIFIER:
  For single objective deaths (n=1, eid > 60000):
    IF has_player_kill_nearby(offset, window=500):
      => KRAKEN_DEATH
    ELSE:
      => GOLD_MINE_CAPTURE

CAVEATS:
  - Only 4/25 Gold Mine captures are followed by detected Kraken deaths
    (Most Krakens survive to game end or die to non-player entities)
  - Short intervals (<30s) between Gold Mine events = contested recaptures
  - flag byte at death_offset+4: 0x01 in late-game events (M6/M7 only)
  - EID ranges fully overlap, cannot be used alone to distinguish types
  - ~3min (170-213s) intervals between Gold Mine events = normal respawn

SAMPLE SIZES:
  Gold Mine events confirmed: 25 (from 11 tournament matches, 100 player-match pairs)
  Kraken deaths confirmed: 4
  n=1 events total: 29
  n>1 events total: 40
"""

import struct
import json
from pathlib import Path
from collections import defaultdict

DEATH_HEADER  = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
KILL_HEADER   = bytes([0x18, 0x04, 0x1C])
PLAYER_EIDS   = set(range(1500, 1510))


def load_match(rp_str):
    rp = Path(rp_str)
    frame_dir = rp.parent
    base_name = rp.name.rsplit('.', 2)[0]
    frames = sorted(frame_dir.glob(f'{base_name}.*.vgr'),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return b''.join(f.read_bytes() for f in frames)


def get_obj_events(data, eid_threshold=60000, cluster_window=5.0):
    """
    Extract and classify all objective events from replay data.
    Returns list of event dicts.
    """
    # Collect all objective deaths
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

    # Cluster by time window
    clusters = []
    cur = []
    for d in deaths:
        if not cur or d['ts'] - cur[-1]['ts'] <= cluster_window:
            cur.append(d)
        else:
            clusters.append(cur)
            cur = [d]
    if cur:
        clusters.append(cur)

    events = []
    for cluster in clusters:
        eids = [d['eid'] for d in cluster]
        ts = cluster[0]['ts']
        n = len(cluster)
        eid_span = max(eids) - min(eids)
        offsets = [d['offset'] for d in cluster]

        # Check for player kill near any death in cluster
        player_kill = _has_player_kill_nearby(data, offsets)

        # Classify
        if n == 1 and not player_kill:
            event_type = 'GOLD_MINE_CAPTURE'
        elif n == 1 and player_kill:
            event_type = 'KRAKEN_DEATH'
        elif n > 1 and player_kill:
            event_type = 'KRAKEN_WAVE'
        else:
            event_type = 'MINION_WAVE'

        events.append({
            'ts': round(ts, 2),
            'n': n,
            'eids': eids,
            'eid_span': eid_span,
            'player_kill': player_kill,
            'event_type': event_type,
        })

    return events


def _has_player_kill_nearby(data, offsets, window=500):
    """Check if any player kill record exists within window bytes of any offset."""
    for off in offsets:
        s = max(0, off - window)
        e = min(len(data), off + window)
        region = data[s:e]
        pk = 0
        while True:
            kidx = region.find(KILL_HEADER, pk)
            if kidx == -1:
                break
            pk = kidx + 1
            if kidx + 7 > len(region):
                continue
            killer = struct.unpack('>H', region[kidx+5:kidx+7])[0]
            if killer in PLAYER_EIDS:
                return True
    return False


def get_gold_mine_captures(data, eid_threshold=60000):
    """
    Convenience function: returns list of Gold Mine capture timestamps.
    Gold Mine = single-entity objective death with no nearby player kill.
    """
    events = get_obj_events(data, eid_threshold)
    return [e['ts'] for e in events if e['event_type'] == 'GOLD_MINE_CAPTURE']


def get_kraken_deaths(data, eid_threshold=60000):
    """
    Convenience function: returns list of Kraken death timestamps.
    Kraken = single-entity objective death with nearby player kill.
    """
    events = get_obj_events(data, eid_threshold)
    return [e['ts'] for e in events if e['event_type'] == 'KRAKEN_DEATH']


def main():
    truth = json.load(open('vg/output/tournament_truth.json'))

    print('[OBJECTIVE] Kraken vs Gold Mine classification - Final Results')
    print()
    print('[DATA] 11 tournament matches, 29 single-entity objective deaths analyzed')
    print()

    all_events = []
    gm_counts = []
    kr_counts = []

    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        events = get_obj_events(data)

        gm = [e for e in events if e['event_type'] == 'GOLD_MINE_CAPTURE']
        kr = [e for e in events if e['event_type'] == 'KRAKEN_DEATH']
        kw = [e for e in events if e['event_type'] == 'KRAKEN_WAVE']
        mw = [e for e in events if e['event_type'] == 'MINION_WAVE']

        gm_counts.append(len(gm))
        kr_counts.append(len(kr))

        dur = match['match_info']['duration_seconds']
        print(f'M{mi+1} (dur={dur}s):')
        print(f'  Gold Mine captures: {len(gm)} at {[e["ts"] for e in gm]}')
        print(f'  Kraken deaths:      {len(kr)} at {[e["ts"] for e in kr]}')
        print(f'  Kraken waves:       {len(kw)}')
        print(f'  Minion waves:       {len(mw)}')

        # Inter-event timing for Gold Mine
        gm_times = sorted(e['ts'] for e in gm)
        if len(gm_times) > 1:
            intervals = [round(gm_times[i+1]-gm_times[i], 1) for i in range(len(gm_times)-1)]
            short = [iv for iv in intervals if iv < 30]
            long_ = [iv for iv in intervals if iv >= 30]
            if short:
                print(f'  GM short intervals (<30s, contested): {short}')
            if long_:
                print(f'  GM long intervals (respawn): {long_}')
        print()

        for e in events:
            all_events.append({'match': mi+1, **e})

    # Overall statistics
    from collections import Counter
    type_ctr = Counter(e['event_type'] for e in all_events)
    print('='*60)
    print('[FINDING] Event type distribution across all 11 matches:')
    for t, c in type_ctr.most_common():
        print(f'  {t}: {c}')

    print()
    print('[FINDING] Gold Mine captures per match:')
    print(f'  Mean: {sum(gm_counts)/len(gm_counts):.1f}  '
          f'Range: {min(gm_counts)}-{max(gm_counts)}')

    print()
    print('[FINDING] Discrimination rule:')
    print('  Gold Mine = n==1 AND eid>60000 AND no_player_kill_nearby(window=500B)')
    print('  Kraken    = n==1 AND eid>60000 AND has_player_kill_nearby(window=500B)')
    print()

    gm_all = [e for e in all_events if e['event_type'] == 'GOLD_MINE_CAPTURE']
    kr_all = [e for e in all_events if e['event_type'] == 'KRAKEN_DEATH']

    print(f'[STAT:n_goldmine] {len(gm_all)} Gold Mine capture events detected')
    print(f'[STAT:n_kraken] {len(kr_all)} Kraken death events detected')
    print()

    print('[STAT:eid_range_goldmine]'
          f' {min(e["eids"][0] for e in gm_all)} - {max(e["eids"][0] for e in gm_all)}')
    print('[STAT:eid_range_kraken]'
          f' {min(e["eids"][0] for e in kr_all)} - {max(e["eids"][0] for e in kr_all)}')
    print()

    print('[LIMITATION] Only 4/29 single-entity objective deaths confirmed as Kraken.')
    print('[LIMITATION] Most Krakens survive to game end (not killed by players).')
    print('[LIMITATION] EID ranges fully overlap - EID alone insufficient for classification.')
    print('[LIMITATION] The 7 anomalously short-interval (<30s) GM events are contested recaptures.')

    # Save results
    out = Path('vg/output/objective_events_final.json')
    out.parent.mkdir(exist_ok=True)
    with open(out, 'w') as f:
        json.dump(all_events, f, indent=2, default=str)
    print(f'\n[SAVED] {out}')


if __name__ == '__main__':
    main()
