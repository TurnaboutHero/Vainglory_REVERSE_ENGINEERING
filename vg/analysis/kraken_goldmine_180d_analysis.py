#!/usr/bin/env python3
"""
Analyze [18 04 0D] header records - appears near many Gold Mine objective deaths.

Payload structure observed:
  [18 04 0D][00][XX YY][ZZ][AA BB CC DD][EE FF GG][00][4F][HH HH][II]
  where HH HH are identical bytes.

Also investigate the [20 04 0E] header which appears near Kraken.

Goal: decode the structure to find entity type discriminator for Kraken vs Gold Mine.
"""

import struct
import json
from pathlib import Path
from collections import Counter, defaultdict

DEATH_HEADER  = bytes([0x08, 0x04, 0x31])
HDR_180D = bytes([0x18, 0x04, 0x0D])
HDR_200E = bytes([0x20, 0x04, 0x0E])
HDR_300F = bytes([0x30, 0x04, 0x0F])
PLAYER_EIDS = set(range(1500, 1510))


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


def main():
    truth = json.load(open('vg/output/tournament_truth.json'))

    print('=== [18 04 0D] Record Structure Analysis ===')
    print()

    # Load M1 and M7 for detailed study
    for mi in [0, 3, 5, 6]:  # M1, M4, M6, M7
        match = truth['matches'][mi]
        data = load_match(match['replay_file'])
        label = f'M{mi+1}'

        # Find all [18 04 0D] records
        offsets_180d = find_all(data, HDR_180D)
        print(f'{label}: {len(offsets_180d)} [18 04 0D] records')

        # Decode each
        # Guess structure from pattern:
        # [18 04 0D] [flags 1B] [eid BE 2B] [? 1B] [float 4B] [3B] [1B] [1B] [2B identical] [1B]
        # Total after header: ~15 bytes
        unique_eid_180d = set()
        float_vals = []
        pair_bytes = Counter()

        for off in offsets_180d:
            if off + 20 > len(data):
                continue
            raw = data[off:off+20]
            # Byte layout after [18 04 0D]:
            # +3: flags (1B)
            # +4,+5: eid (BE 2B)
            # +6: ?
            # +7..+10: float (4B)
            # +11: ?
            # +12: ?
            # +13: ?
            # +14,+15: pair bytes
            # +16: ?
            flags = raw[3]
            eid = struct.unpack('>H', raw[4:6])[0]
            try:
                fval = struct.unpack('>f', raw[7:11])[0]
            except Exception:
                fval = None
            byte14 = raw[14] if len(raw) > 14 else None
            byte15 = raw[15] if len(raw) > 15 else None
            byte13 = raw[13] if len(raw) > 13 else None

            unique_eid_180d.add(eid)
            if fval is not None:
                float_vals.append(round(fval, 2))
            if byte14 == byte15 and byte14 is not None:
                pair_bytes[byte14] += 1

        float_ctr = Counter(round(v) for v in float_vals)
        print(f'  Float values at +7: {dict(sorted(float_ctr.most_common(10)))}')
        print(f'  EID range at +4: {min(unique_eid_180d)} - {max(unique_eid_180d)}  n_unique={len(unique_eid_180d)}')
        print(f'  Pair bytes at +14,+15: {len(pair_bytes)} unique values')
        print()

    print()
    print('=== [20 04 0E] Record Structure Analysis ===')
    print()

    for mi in [0, 1, 3, 6]:  # M1, M2, M4, M7
        match = truth['matches'][mi]
        data = load_match(match['replay_file'])
        label = f'M{mi+1}'

        offsets_200e = find_all(data, HDR_200E)
        print(f'{label}: {len(offsets_200e)} [20 04 0E] records')

        # Find [20 04 0E] records that are within 20 bytes of an objective death
        obj_deaths = []
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
            if eid > 60000 and 0 < ts < 5000:
                obj_deaths.append({'eid': eid, 'ts': ts, 'offset': idx})

        near_obj = []
        for off_200e in offsets_200e:
            for d in obj_deaths:
                if abs(off_200e - d['offset'] - 12) <= 4:  # right after death
                    raw = data[off_200e:off_200e+24]
                    near_obj.append({
                        'off': off_200e,
                        'death_eid': d['eid'],
                        'death_ts': round(d['ts'], 1),
                        'raw': raw.hex(' ').upper()
                    })
                    break

        if near_obj:
            print(f'  [20 04 0E] immediately after objective death:')
            for r in near_obj:
                print(f'    ts={r["death_ts"]}s eid={r["death_eid"]}: {r["raw"]}')

        # Show structure of first 10 [20 04 0E] records
        print(f'  First 5 [20 04 0E] records:')
        for off in offsets_200e[:5]:
            raw = data[off:off+24]
            print(f'    0x{off:X}: {raw.hex(" ").upper()}')
        print()

    print()
    print('=== Focus: Which objective EIDs have [18 04 0D] vs [20 04 0E] after death ===')
    print()

    # The Gold Mine EIDs from classifier: 25 events across matches
    # Kraken EIDs: 4 events
    # Cross-check: what header follows each death?
    CONFIRMED_KRAKEN_TS = {(2, 922.8), (6, 821.7), (7, 744.6), (11, 961.4)}

    for mi, match in enumerate(truth['matches']):
        data = load_match(match['replay_file'])
        label = f'M{mi+1}'

        # Get single-death objective clusters
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
            if eid > 60000 and 0 < ts < 5000:
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
        singles = [c[0] for c in clusters if len(c) == 1]

        for d in singles:
            off = d['offset']
            ts = round(d['ts'], 1)
            is_kraken = any(abs(ts - kt) < 2.0 and mi + 1 == km
                            for km, kt in CONFIRMED_KRAKEN_TS)
            t = 'KRAKEN' if is_kraken else 'GOLDMINE?'

            # Check header at off+12 through off+15
            hdr_at_12 = data[off+12:off+15]

            # Check for [18 04 0D] within 5 bytes after death
            near_180d = data[off+12:off+20].find(HDR_180D) != -1
            near_200e = data[off+12:off+20].find(HDR_200E) != -1
            near_101d = data[off+12:off+20].find(bytes([0x10,0x04,0x1D])) != -1

            # Decode the immediate post-death record
            hdr_str = hdr_at_12.hex(' ').upper()

            print(f'{label} {t} ts={ts:>7.1f} eid={d["eid"]} hdr_at+12={hdr_str} '
                  f'180D={near_180d} 200E={near_200e} 101D={near_101d}')


if __name__ == '__main__':
    main()
