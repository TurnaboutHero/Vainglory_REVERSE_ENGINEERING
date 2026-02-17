#!/usr/bin/env python3
"""
Search for distinguishing byte patterns between Kraken and Gold Mine.

Key findings so far:
- Gold Mine (no player kill, n=1): 25 events
- Kraken (player kill, n=1): 4 events (M2/ts=923, M6/ts=822, M7/ts=745, M11/ts=961)

Both Kraken candidates M2 and M7 show [20 04 0E] immediately after the death record.
This analysis:
1. Counts [20 04 0E] occurrences and their proximity to objective deaths
2. Looks for patterns specific to Gold Mine vs Kraken in the 16 bytes after death
3. Checks the byte at death_offset+15 (last byte of death record)
4. Checks if [10 04 1D] credit record immediately follows (Gold Mine gives credit?)
"""

import struct
import json
from pathlib import Path
from collections import Counter, defaultdict

DEATH_HEADER  = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
KILL_HEADER   = bytes([0x18, 0x04, 0x1C])
PLAYER_EIDS   = set(range(1500, 1510))

HDR_200E = bytes([0x20, 0x04, 0x0E])
HDR_180D = bytes([0x18, 0x04, 0x0D])
HDR_181E = bytes([0x18, 0x04, 0x1E])
HDR_183E = bytes([0x18, 0x04, 0x3E])
HDR_101D = bytes([0x10, 0x04, 0x1D])


def load_match(rp_str):
    rp = Path(rp_str)
    frame_dir = rp.parent
    base_name = rp.name.rsplit('.', 2)[0]
    frames = sorted(frame_dir.glob(f'{base_name}.*.vgr'),
                    key=lambda p: int(p.stem.split('.')[-1]))
    return b''.join(f.read_bytes() for f in frames)


def find_all(data, pattern):
    offsets = []
    pos = 0
    while True:
        idx = data.find(pattern, pos)
        if idx == -1:
            break
        offsets.append(idx)
        pos = idx + 1
    return offsets


def get_obj_singles(data, thresh=60000):
    """Get single-death objective clusters."""
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

    deaths.sort(key=lambda x: x['ts'])
    clusters, cur = [], []
    for d in deaths:
        if not cur or d['ts'] - cur[-1]['ts'] <= 5.0:
            cur.append(d)
        else:
            clusters.append(cur)
            cur = [d]
    if cur:
        clusters.append(cur)
    return [c[0] for c in clusters if len(c) == 1]


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


def next_known_header(data, offset, window=200):
    """Find next known protocol header within window bytes after offset."""
    KNOWN = {
        bytes([0x08,0x04,0x31]): 'DEATH',
        bytes([0x18,0x04,0x1C]): 'KILL',
        bytes([0x10,0x04,0x1D]): 'CREDIT',
        bytes([0x18,0x04,0x3E]): 'PLAYER_STATE',
        bytes([0x18,0x04,0x1E]): 'ENTITY_STATE',
        bytes([0x28,0x04,0x3F]): 'UNK_28043F',
        bytes([0x10,0x04,0x4B]): 'ITEM_EQUIP',
        bytes([0x20,0x04,0x0E]): 'UNK_200E',
        bytes([0x18,0x04,0x0D]): 'UNK_180D',
        bytes([0x20,0x04,0x0F]): 'UNK_200F',
        bytes([0x30,0x04,0x0F]): 'UNK_300F',
    }
    for pos in range(offset, min(len(data) - 3, offset + window)):
        b3 = data[pos:pos+3]
        if b3 in KNOWN:
            return pos - offset, b3.hex(' ').upper(), KNOWN[b3]
    return None, None, None


def main():
    truth = json.load(open('vg/output/tournament_truth.json'))

    print('[OBJECTIVE] Distinguish Kraken from Gold Mine - Header Pattern Search')
    print()

    # Confirmed types from classifier:
    CONFIRMED_KRAKEN = {
        (2, 922.8), (6, 821.7), (7, 744.6), (11, 961.4)
    }

    # Collect all single-death events with full context
    all_events = []

    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        singles = get_obj_singles(data)

        for d in singles:
            off = d['offset']
            ts = round(d['ts'], 1)
            pk = has_player_kill(data, off)
            is_kraken = any(abs(ts - kt) < 2.0 and mi + 1 == km
                           for km, kt in CONFIRMED_KRAKEN)

            # Death record: 16 bytes total
            death_rec = data[off:off+16]
            # Bytes 12-15 (after death body): [XX 00 00 00] = frame/length?
            frame_byte = death_rec[12] if len(death_rec) >= 13 else None

            # Next known header after death record
            dist, hdr_hex, hdr_name = next_known_header(data, off + 12, 200)

            # Is [20 04 0E] within 200 bytes after?
            has_200e = data[off+12:off+212].find(HDR_200E) != -1
            dist_200e = data[off+12:off+212].find(HDR_200E)

            # Is [10 04 1D] (credit) the FIRST next header?
            first_hdr_is_credit = (hdr_name == 'CREDIT')
            first_hdr_is_200e = (hdr_name == 'UNK_200E')

            all_events.append({
                'match': mi + 1,
                'ts': ts,
                'eid': d['eid'],
                'pk': pk,
                'is_kraken': is_kraken,
                'frame_byte': frame_byte,
                'next_hdr': hdr_hex,
                'next_hdr_name': hdr_name,
                'next_hdr_dist': dist,
                'has_200e': has_200e,
                'dist_200e': dist_200e if dist_200e != -1 else None,
                'first_hdr_is_credit': first_hdr_is_credit,
                'first_hdr_is_200e': first_hdr_is_200e,
            })

    # Print all events with classification
    print(f'{"M":<3} {"ts":>7} {"eid":>6} {"pk":>5} {"type":<12} {"next_hdr":<20} {"dist":>5} {"has200E":>8} {"dist200E":>9}')
    print('-' * 85)
    for e in all_events:
        t = 'KRAKEN' if e['is_kraken'] else ('GOLDMINE?' if not e['pk'] else 'KRAKEN_UNK')
        print(f'M{e["match"]:<2} {e["ts"]:>7.1f} {e["eid"]:>6} {str(e["pk"]):>5} {t:<12} '
              f'{(e["next_hdr_name"] or "?"):<20} {str(e["next_hdr_dist"] or "?"):>5} '
              f'{str(e["has_200e"]):>8} {str(e["dist_200e"] or "-"):>9}')

    # ---- FINDING: Which header follows each type? ----
    print()
    print('[FINDING] Next header after death record - Gold Mine vs Kraken:')
    gm_hdrs = Counter(e['next_hdr_name'] for e in all_events if not e['is_kraken'] and not e['pk'])
    kr_hdrs = Counter(e['next_hdr_name'] for e in all_events if e['is_kraken'])
    print(f'  Gold Mine next headers: {dict(gm_hdrs)}')
    print(f'  Kraken next headers:    {dict(kr_hdrs)}')

    # ---- FINDING: [20 04 0E] presence ----
    print()
    print('[FINDING] [20 04 0E] header presence:')
    gm_200e = sum(1 for e in all_events if not e['is_kraken'] and not e['pk'] and e['has_200e'])
    kr_200e = sum(1 for e in all_events if e['is_kraken'] and e['has_200e'])
    gm_total = sum(1 for e in all_events if not e['is_kraken'] and not e['pk'])
    kr_total = sum(1 for e in all_events if e['is_kraken'])
    print(f'  Gold Mine: {gm_200e}/{gm_total} have [20 04 0E] within 200B after death')
    print(f'  Kraken:    {kr_200e}/{kr_total} have [20 04 0E] within 200B after death')

    # ---- FINDING: Frame byte at offset +12 ----
    print()
    print('[FINDING] Byte at death_offset+12 (frame separator):')
    gm_fb = Counter(e['frame_byte'] for e in all_events if not e['is_kraken'] and not e['pk'])
    kr_fb = Counter(e['frame_byte'] for e in all_events if e['is_kraken'])
    print(f'  Gold Mine byte+12: {dict(sorted(gm_fb.items()))}')
    print(f'  Kraken byte+12:    {dict(sorted(kr_fb.items()))}')

    # ---- [20 04 0E] global frequency ----
    print()
    print('[FINDING] [20 04 0E] global occurrences per match:')
    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        cnt = len(find_all(data, HDR_200E))
        print(f'  M{mi+1}: {cnt} occurrences')

    # ---- Examine raw 48 bytes after each Kraken/GoldMine death ----
    print()
    print('[FINDING] Full 48-byte context after confirmed events:')
    print()
    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        for e in all_events:
            if e['match'] != mi + 1:
                continue
            if not e['is_kraken'] and e['pk']:
                continue  # skip unknown pk events
            off = None
            # Re-find this specific death
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
                    ts2 = struct.unpack('>f', data[idx+9:idx+13])[0]
                except Exception:
                    continue
                if eid == e['eid'] and abs(ts2 - e['ts']) < 1.0:
                    off = idx
                    break

            if off is None:
                continue
            t = 'KRAKEN' if e['is_kraken'] else 'GOLDMINE?'
            full = data[off:off+48].hex(' ').upper()
            print(f'  M{e["match"]} {t} ts={e["ts"]}s eid={e["eid"]}:')
            print(f'    {full}')
            print()


if __name__ == '__main__':
    main()
