#!/usr/bin/env python3
"""
[OBJECTIVE] Search player blocks for gold state values

Hypothesis: Total gold might be stored in player block state, not just accumulated
from credit events. Check last frame player blocks for gold-like values.
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']


def extract_player_block_full(data, pos, marker_len):
    """Extract full player block data around marker."""
    block_start = max(0, pos - 50)
    block_end = min(len(data), pos + 500)
    block_data = data[block_start:block_end]

    eid_offset = pos - block_start + 0xA5
    if eid_offset + 2 > len(block_data):
        return None

    eid_le = struct.unpack('<H', block_data[eid_offset:eid_offset + 2])[0]
    eid_be = struct.unpack('>H', struct.pack('<H', eid_le))[0]

    # Extract name
    ns = pos - block_start + marker_len
    ne = ns
    while ne < len(block_data) and ne < ns + 30:
        if block_data[ne] < 32 or block_data[ne] > 126:
            break
        ne += 1
    name = block_data[ns:ne].decode('ascii', errors='replace')

    return {
        'eid_le': eid_le,
        'eid_be': eid_be,
        'name': name,
        'block_offset': block_start,
        'marker_pos': pos,
        'block_data': block_data,
    }


def scan_for_gold_candidates(block_data, truth_gold):
    """Scan player block for values near truth_gold."""
    candidates = []

    # Try different interpretations
    for offset in range(0, len(block_data) - 4, 1):
        try:
            # Float32 BE
            val_f32_be = struct.unpack_from(">f", block_data, offset)[0]
            if 100 <= val_f32_be <= 25000:
                diff = abs(val_f32_be - truth_gold)
                if diff <= 1000:
                    candidates.append({
                        'offset': offset,
                        'type': 'f32_be',
                        'value': val_f32_be,
                        'diff': diff,
                        'hex': block_data[offset:offset+4].hex(),
                    })

            # Float32 LE
            val_f32_le = struct.unpack_from("<f", block_data, offset)[0]
            if 100 <= val_f32_le <= 25000:
                diff = abs(val_f32_le - truth_gold)
                if diff <= 1000:
                    candidates.append({
                        'offset': offset,
                        'type': 'f32_le',
                        'value': val_f32_le,
                        'diff': diff,
                        'hex': block_data[offset:offset+4].hex(),
                    })

            # Uint32 BE
            if offset % 2 == 0:
                val_u32_be = struct.unpack_from(">I", block_data, offset)[0]
                if 100 <= val_u32_be <= 25000:
                    diff = abs(val_u32_be - truth_gold)
                    if diff <= 1000:
                        candidates.append({
                            'offset': offset,
                            'type': 'u32_be',
                            'value': val_u32_be,
                            'diff': diff,
                            'hex': block_data[offset:offset+4].hex(),
                        })

                # Uint32 LE
                val_u32_le = struct.unpack_from("<I", block_data, offset)[0]
                if 100 <= val_u32_le <= 25000:
                    diff = abs(val_u32_le - truth_gold)
                    if diff <= 1000:
                        candidates.append({
                            'offset': offset,
                            'type': 'u32_le',
                            'value': val_u32_le,
                            'diff': diff,
                            'hex': block_data[offset:offset+4].hex(),
                        })
        except:
            pass

    # Return top 5 closest matches
    candidates.sort(key=lambda x: x['diff'])
    return candidates[:5]


def main():
    print("[STAGE:begin:data_loading]")

    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    print(f"[DATA] Loaded {len(truth['matches'])} matches")

    # Analyze last frame of each match
    offset_votes = defaultdict(lambda: defaultdict(int))  # offset -> type -> count
    exact_matches = []

    for match_idx, match in enumerate(truth['matches'][:3]):  # First 3 for testing
        if match_idx == 8:
            continue

        p = Path(match['replay_file'])
        if not p.exists():
            continue

        d = p.parent
        base = p.stem.rsplit('.', 1)[0]
        frames = sorted(d.glob(f'{base}.*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))

        if not frames:
            continue

        last_frame = frames[-1].read_bytes()

        print(f"\n[DATA] Match {match_idx+1}: {p.parent.parent.name}")

        # Extract player blocks from last frame
        player_blocks = []
        for marker in PLAYER_MARKERS:
            pos = 0
            while True:
                pos = last_frame.find(marker, pos)
                if pos == -1:
                    break
                block = extract_player_block_full(last_frame, pos, len(marker))
                if block and len(block['name']) >= 3:
                    player_blocks.append(block)
                pos += 1

        print(f"[DATA] Found {len(player_blocks)} player blocks in last frame")

        # Match with truth
        for block in player_blocks:
            matched = False
            for tname, tdata in match['players'].items():
                if 'gold' not in tdata:
                    continue
                short = tname.split('_', 1)[-1] if '_' in tname else tname
                if block['name'] == short or tname.endswith(block['name']):
                    truth_gold = tdata['gold']
                    matched = True

                    print(f"\n  Player: {tname}, truth_gold={truth_gold}")

                    candidates = scan_for_gold_candidates(block['block_data'], truth_gold)

                    if candidates:
                        print(f"  [FINDING] Top gold candidates:")
                        for cand in candidates:
                            print(f"    Offset +0x{cand['offset']:03X}: {cand['type']:8s} = {cand['value']:7.0f}, "
                                  f"diff={cand['diff']:5.0f}, hex={cand['hex']}")

                            # Vote for this offset+type
                            if cand['diff'] <= 200:
                                offset_votes[cand['offset']][cand['type']] += 1

                            if cand['diff'] <= 50:
                                exact_matches.append({
                                    'match': match_idx + 1,
                                    'player': tname,
                                    'offset': cand['offset'],
                                    'type': cand['type'],
                                    'value': cand['value'],
                                    'truth': truth_gold,
                                    'diff': cand['diff'],
                                })
                    else:
                        print(f"  [LIMITATION] No gold candidates within ±1000")

                    break

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # ====================================================================
    print("\n" + "=" * 70)
    print("[STAGE:begin:analysis]")
    print("OFFSET VOTING RESULTS")
    print("=" * 70)

    if offset_votes:
        print(f"[FINDING] Offsets with multiple matches (±200 accuracy):")

        sorted_offsets = sorted(offset_votes.items(),
                               key=lambda x: sum(x[1].values()),
                               reverse=True)

        for offset, types in sorted_offsets[:10]:
            total_votes = sum(types.values())
            type_str = ', '.join(f"{t}:{c}" for t, c in sorted(types.items(),
                                key=lambda x: x[1], reverse=True))
            print(f"  +0x{offset:03X}: {total_votes} matches [{type_str}]")
    else:
        print(f"[LIMITATION] No consistent offsets found")

    if exact_matches:
        print(f"\n[FINDING] Exact matches (±50):")
        for em in exact_matches:
            print(f"  Match {em['match']}, {em['player']}: "
                  f"+0x{em['offset']:03X} {em['type']:8s} = {em['value']:.0f} "
                  f"(truth={em['truth']}, diff={em['diff']:.0f})")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:analysis]")


if __name__ == '__main__':
    main()
