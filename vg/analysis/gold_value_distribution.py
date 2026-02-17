"""
Gold Value Distribution Analysis: Compare positive 0x06 record values
for overcounted vs accurate players to identify sell-back patterns.
"""

import struct, math, json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

# Known item costs for sell-back detection (sell = 50% of buy price)
# Common sell-back values would be: 150, 300, 250, 175, 350, 400, 500, 600, etc.


def extract_gold_records(replay_path: str):
    """Extract all positive 0x06 credit records per player."""
    decoder = UnifiedDecoder(replay_path)
    match = decoder.decode()

    eid_map = {}
    for p in match.all_players:
        if p.entity_id:
            eid_be = _le_to_be(p.entity_id)
            eid_map[eid_be] = p.name

    valid_eids = set(eid_map.keys())

    # Load all frames
    replay_file_path = Path(replay_path)
    frame_dir = replay_file_path.parent
    frame_name = replay_file_path.stem.rsplit('.', 1)[0]
    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))

    def _idx(p):
        try: return int(p.stem.split('.')[-1])
        except: return 0

    frame_files.sort(key=_idx)

    # Per-player: list of (value, frame_idx) for positive 0x06
    player_positive = defaultdict(list)
    player_negative = defaultdict(list)

    for fpath in frame_files:
        fidx = _idx(fpath)
        data = fpath.read_bytes()

        pos = 0
        while True:
            pos = data.find(_CREDIT_HEADER, pos)
            if pos == -1:
                break
            if pos + 12 > len(data):
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

            if action == 0x06 and not math.isnan(value) and not math.isinf(value):
                if value > 0:
                    player_positive[eid].append((value, fidx))
                elif value < 0:
                    player_negative[eid].append((value, fidx))

            pos += 3

    return eid_map, player_positive, player_negative


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze M7 (worst overcounting) and M1 (accurate)
    for mi in [0, 6]:  # M1 and M7 (0-indexed)
        match = truth_data['matches'][mi]
        replay_path = match['replay_file']
        truth_players = match.get('players', {})

        print(f"\n{'='*80}")
        print(f"MATCH {mi+1}: {Path(replay_path).parent.parent.name}/{Path(replay_path).parent.name}")
        print(f"{'='*80}")

        eid_map, pos_records, neg_records = extract_gold_records(replay_path)

        for eid in sorted(eid_map.keys()):
            pname = eid_map[eid]
            truth_gold = truth_players.get(pname, {}).get('gold', 0)

            positives = pos_records.get(eid, [])
            negatives = neg_records.get(eid, [])

            total_positive = sum(v for v, _ in positives)
            total_negative = sum(abs(v) for v, _ in negatives)
            detected = 600 + round(total_positive)
            err_pct = (detected - truth_gold) / truth_gold * 100 if truth_gold else 0

            # Value distribution
            value_counts = Counter(round(v) for v, _ in positives)
            neg_value_counts = Counter(round(abs(v)) for v, _ in negatives)

            # Check for sell-back candidates (positive values that are 50% of negative values)
            sell_back_candidates = 0
            sell_back_gold = 0
            for pos_val, count in value_counts.items():
                buy_val = pos_val * 2
                if buy_val in neg_value_counts:
                    # This positive value could be a sell-back of an item costing buy_val
                    sell_back_candidates += count
                    sell_back_gold += pos_val * count

            print(f"\n  {pname} (err={err_pct:+.1f}%):")
            print(f"    Positive 0x06: {len(positives)} records, total={total_positive:.0f}")
            print(f"    Negative 0x06: {len(negatives)} records, total={total_negative:.0f}")
            print(f"    Detected: {detected}, Truth: {truth_gold}")
            print(f"    Sell-back candidates: {sell_back_candidates} records, {sell_back_gold:.0f} gold")
            print(f"    Corrected (minus sell-back): {detected - sell_back_gold:.0f}, "
                  f"err={(detected - sell_back_gold - truth_gold)/truth_gold*100:.1f}%")

            # Top 10 positive values
            top_pos = value_counts.most_common(15)
            print(f"    Top positive values: {top_pos}")

            # Top negative values
            top_neg = neg_value_counts.most_common(10)
            print(f"    Top negative values (purchases): {top_neg}")


if __name__ == '__main__':
    main()
