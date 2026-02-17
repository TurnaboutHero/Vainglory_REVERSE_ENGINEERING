#!/usr/bin/env python3
"""
Deep byte-level analysis of objective events (eid>60000, n=1 single deaths)
to distinguish Gold Mine from Kraken and other single-entity deaths.

Focus on:
1. Raw byte context around each event
2. EID sub-range analysis (do Gold Mine and Kraken use distinct EID ranges?)
3. Byte patterns at specific offsets relative to the death record
4. Credit record structure differences
5. Game timing validation vs VG spawn rules
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

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

def get_obj_single_deaths(data, thresh=60000):
    """Get all single-entity objective deaths (no clustering)."""
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
        if eid > thresh and 0 < ts < 5000:
            deaths.append({'eid': eid, 'ts': ts, 'offset': idx})
    return sorted(deaths, key=lambda x: x['ts'])

def has_player_kill(data, offset, window=500):
    s = max(0, offset - window)
    e = min(len(data), offset + window)
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

def get_first_credit_after(data, offset, window=300):
    """Get first credit record after offset."""
    p = offset + 12
    end = min(len(data), offset + window)
    while p < end - 12:
        if data[p:p+3] == CREDIT_HEADER:
            eid_cr = struct.unpack('>H', data[p+5:p+7])[0]
            try:
                val = struct.unpack('>f', data[p+7:p+11])[0]
            except Exception:
                val = None
            action = data[p+11]
            return {'eid': eid_cr, 'val': round(val, 2) if val else None, 'action': action}
        p += 1
    return None

def get_byte_at_offset(data, offset, rel_off):
    """Get byte at relative offset from death header."""
    idx = offset + rel_off
    if 0 <= idx < len(data):
        return data[idx]
    return None

def main():
    truth = json.load(open('vg/output/tournament_truth.json'))

    # Collect all single-death n=1 objective events across all matches
    all_singles = []

    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        duration = match['match_info']['duration_seconds']
        deaths = get_obj_single_deaths(data)

        # Cluster to find true singles (not part of multi-death burst)
        clusters = []
        cur = []
        for d in deaths:
            if not cur or d['ts'] - cur[-1]['ts'] <= 5.0:
                cur.append(d)
            else:
                clusters.append(cur)
                cur = [d]
        if cur:
            clusters.append(cur)

        # Only take clusters with exactly 1 death (true single events)
        single_clusters = [c for c in clusters if len(c) == 1]

        for cl in single_clusters:
            d = cl[0]
            off = d['offset']
            pk = has_player_kill(data, off)
            first_credit = get_first_credit_after(data, off)

            # Raw bytes: 16 before, death record itself (16b), 32 after
            pre16 = data[max(0, off-16):off].hex(' ').upper()
            death_rec = data[off:off+16].hex(' ').upper()
            post32 = data[off+12:off+44].hex(' ').upper()

            # Byte at off+12 (first byte after death record)
            byte_after = get_byte_at_offset(data, off, 12)
            # Byte at off-1 (last byte before death header)
            byte_before = get_byte_at_offset(data, off, -1)

            all_singles.append({
                'match': mi + 1,
                'ts': round(d['ts'], 1),
                'eid': d['eid'],
                'offset': off,
                'player_kill': pk,
                'duration': duration,
                'ts_frac': round(d['ts'] / duration, 3),
                'first_credit': first_credit,
                'pre16': pre16,
                'death_rec': death_rec,
                'post32': post32,
                'byte_after': byte_after,
                'byte_before': byte_before,
            })

    # ---- Analysis 1: Player kill separation ----
    goldmine_cands = [s for s in all_singles if not s['player_kill']]
    kraken_cands   = [s for s in all_singles if s['player_kill']]

    print(f'[OBJECTIVE] Distinguish Kraken from Gold Mine in VG replay binary')
    print(f'[DATA] Total single-death objective events: {len(all_singles)}')
    print(f'[DATA]   No player kill (Gold Mine cand): {len(goldmine_cands)}')
    print(f'[DATA]   Has player kill (Kraken cand):   {len(kraken_cands)}')
    print()

    # ---- Analysis 2: EID range breakdown ----
    print('=== EID ranges for each type ===')
    gm_eids = sorted(s['eid'] for s in goldmine_cands)
    kr_eids = sorted(s['eid'] for s in kraken_cands)
    print(f'Gold Mine EIDs: min={min(gm_eids)} max={max(gm_eids)} n={len(gm_eids)}')
    print(f'Kraken EIDs:    min={min(kr_eids)} max={max(kr_eids)} n={len(kr_eids)}')
    print(f'Gold Mine EIDs: {gm_eids}')
    print(f'Kraken EIDs:    {kr_eids}')
    print()

    # ---- Analysis 3: First credit record after each event ----
    print('=== First credit record after death ===')
    print('GOLD MINE candidates:')
    for s in goldmine_cands:
        cr = s['first_credit']
        cr_str = f"eid={cr['eid']} val={cr['val']} act=0x{cr['action']:02X}" if cr else 'None'
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s eid={s["eid"]} | {cr_str}')

    print()
    print('KRAKEN candidates:')
    for s in kraken_cands:
        cr = s['first_credit']
        cr_str = f"eid={cr['eid']} val={cr['val']} act=0x{cr['action']:02X}" if cr else 'None'
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s eid={s["eid"]} | {cr_str}')

    # ---- Analysis 4: Byte patterns ----
    print()
    print('=== Byte at offset +12 (first byte after death record) ===')
    print('Gold Mine cands:')
    ba_gm = Counter(s['byte_after'] for s in goldmine_cands if s['byte_after'] is not None)
    for v, c in sorted(ba_gm.items()):
        print(f'  0x{v:02X}: {c} times')
    print('Kraken cands:')
    ba_kr = Counter(s['byte_after'] for s in kraken_cands if s['byte_after'] is not None)
    for v, c in sorted(ba_kr.items()):
        print(f'  0x{v:02X}: {c} times')

    # ---- Analysis 5: Post-death 32 bytes patterns ----
    print()
    print('=== Raw death record + 32 bytes after ===')
    print('GOLD MINE candidates:')
    for s in goldmine_cands:
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s eid={s["eid"]} | {s["death_rec"]} || {s["post32"][:47]}')

    print()
    print('KRAKEN candidates:')
    for s in kraken_cands:
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s eid={s["eid"]} | {s["death_rec"]} || {s["post32"][:47]}')

    # ---- Analysis 6: Game timing ----
    print()
    print('=== Timing as fraction of game duration ===')
    print('Gold Mine (expected: ~4-6min into game, ~3min respawn):')
    for s in sorted(goldmine_cands, key=lambda x: x['ts']):
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s / {s["duration"]}s = {s["ts_frac"]:.2%}  eid={s["eid"]}')

    print()
    print('Kraken (expected: shortly after Gold Mine capture):')
    for s in sorted(kraken_cands, key=lambda x: x['ts']):
        print(f'  M{s["match"]} ts={s["ts"]:>7.1f}s / {s["duration"]}s = {s["ts_frac"]:.2%}  eid={s["eid"]}')

    # ---- Analysis 7: Post-death header type ----
    print()
    print('=== 3-byte header immediately after death record (at off+12) ===')
    KNOWN = {
        bytes([0x08,0x04,0x31]): 'DEATH',
        bytes([0x18,0x04,0x1C]): 'KILL',
        bytes([0x10,0x04,0x1D]): 'CREDIT',
        bytes([0x18,0x04,0x3E]): 'PLAYER_STATE',
        bytes([0x18,0x04,0x1E]): 'ENTITY_STATE',
        bytes([0x28,0x04,0x3F]): 'UNK_28043F',
        bytes([0x10,0x04,0x4B]): 'ITEM_EQUIP',
    }
    # Re-load data for M7 specifically (most singles)
    data_m7 = load_match(truth['matches'][6]['replay_file'])
    print('M7 singles - header at off+12:')
    for s in [x for x in all_singles if x['match'] == 7]:
        off = s['offset']
        hdr = data_m7[off+12:off+15] if off+15 <= len(data_m7) else b''
        hdr_name = KNOWN.get(hdr, hdr.hex(' ').upper())
        print(f'  ts={s["ts"]:>7.1f}s eid={s["eid"]} pk={s["player_kill"]} | next_hdr={hdr_name}')


if __name__ == '__main__':
    main()
