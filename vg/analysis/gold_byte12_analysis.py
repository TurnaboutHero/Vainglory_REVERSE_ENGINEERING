"""
Gold Byte-12 Analysis: Check if the byte AFTER the action byte (position +12)
differentiates sell-back gold from gameplay income.

If sell-back records have a different byte at +12 than income records,
we can filter them to improve gold accuracy.
"""

import struct, math, json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def analyze_byte12(replay_path: str, match_idx: int, truth_players: dict):
    """Analyze byte at position +12 for positive 0x06 records."""
    decoder = UnifiedDecoder(replay_path)
    match = decoder.decode()

    eid_map = {}
    for p in match.all_players:
        if p.entity_id:
            eid_be = _le_to_be(p.entity_id)
            eid_map[eid_be] = p.name
    valid_eids = set(eid_map.keys())

    replay_file_path = Path(replay_path)
    frame_dir = replay_file_path.parent
    frame_name = replay_file_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(frame_dir.glob(f"{frame_name}.*.vgr"),
                         key=lambda p: int(p.stem.split('.')[-1]) if p.stem.split('.')[-1].isdigit() else 0)

    # Per-player: group positive 0x06 by byte at +12
    player_byte12 = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'total': 0, 'values': []}))
    # Also track bytes at +12 to +15 for broader context
    player_extended = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'total': 0}))

    for fpath in frame_files:
        data = fpath.read_bytes()
        pos = 0
        while True:
            pos = data.find(_CREDIT_HEADER, pos)
            if pos == -1:
                break
            if pos + 16 > len(data):  # Need at least 4 extra bytes for context
                pos += 1
                continue
            if data[pos + 3:pos + 5] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid not in valid_eids:
                pos += 3
                continue

            value = struct.unpack_from(">f", data, pos + 7)[0]
            action = data[pos + 11]

            if action == 0x06 and not math.isnan(value) and not math.isinf(value) and value > 0:
                byte12 = data[pos + 12]
                player_byte12[eid][byte12]['count'] += 1
                player_byte12[eid][byte12]['total'] += value
                if len(player_byte12[eid][byte12]['values']) < 20:
                    player_byte12[eid][byte12]['values'].append(round(value))

                # Extended: 2-byte key at +12,+13
                ext_key = (data[pos + 12], data[pos + 13])
                player_extended[eid][ext_key]['count'] += 1
                player_extended[eid][ext_key]['total'] += value

            pos += 3

    print(f"\nM{match_idx}: {Path(replay_path).parent.parent.name}/{Path(replay_path).parent.name}")
    print(f"{'='*70}")

    for eid in sorted(eid_map.keys()):
        pname = eid_map[eid]
        truth_gold = truth_players.get(pname, {}).get('gold', 0)
        total_positive = sum(info['total'] for info in player_byte12[eid].values())
        detected = 600 + round(total_positive)
        err = (detected - truth_gold) / truth_gold * 100 if truth_gold else 0

        print(f"\n  {pname} (err={err:+.1f}%, detected={detected}, truth={truth_gold}):")

        # Show byte12 distribution
        for b12, info in sorted(player_byte12[eid].items()):
            sample_vals = info['values'][:10]
            print(f"    byte12=0x{b12:02X}: {info['count']:4d} records, "
                  f"total={info['total']:8.0f}, "
                  f"avg={info['total']/info['count']:6.1f}, "
                  f"samples={sample_vals}")

        # If there are multiple byte12 values, check if one group matches truth better
        if len(player_byte12[eid]) > 1 and truth_gold:
            for exclude_byte in player_byte12[eid]:
                remaining_total = sum(info['total'] for b, info in player_byte12[eid].items() if b != exclude_byte)
                adjusted = 600 + round(remaining_total)
                adj_err = (adjusted - truth_gold) / truth_gold * 100
                print(f"    → Excluding 0x{exclude_byte:02X}: {adjusted} (err={adj_err:+.1f}%)")


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze M1 (accurate) and M7 (overcounted)
    for mi in [0, 6]:
        match = truth_data['matches'][mi]
        replay_path = match['replay_file']
        truth_players = match.get('players', {})
        if "Incomplete" in replay_path:
            continue
        analyze_byte12(replay_path, mi + 1, truth_players)


if __name__ == '__main__':
    main()
