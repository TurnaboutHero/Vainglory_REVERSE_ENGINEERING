"""
Gold Frame Analysis: Understand how gold credit records distribute across frames.

Key questions:
1. Are frames cumulative (each frame contains ALL events up to that point)?
2. Are frames independent (each frame has its own events)?
3. How does per-frame gold total relate to truth?
"""

import struct
import math
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def extract_gold_per_frame(replay_path: str):
    """Extract gold credit records per frame per player."""
    decoder = UnifiedDecoder(replay_path)
    replay_file_path = Path(replay_path)
    frame_dir = replay_file_path.parent
    frame_name = replay_file_path.stem.rsplit('.', 1)[0]

    # Get player info
    parsed = decoder.decode()
    players = parsed.all_players

    eid_map = {}
    for p in players:
        if p.entity_id:
            eid_be = _le_to_be(p.entity_id)
            eid_map[eid_be] = p.name

    valid_eids = set(eid_map.keys())

    # Load frames
    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))

    def _idx(p):
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0

    frame_files.sort(key=_idx)

    # Per-frame analysis
    frame_gold = {}  # frame_idx -> {eid: total_positive_gold}
    frame_record_counts = {}  # frame_idx -> {eid: count of 0x06 records}

    for fpath in frame_files:
        fidx = _idx(fpath)
        data = fpath.read_bytes()

        gold = defaultdict(float)
        counts = defaultdict(int)

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
                    gold[eid] += value
                    counts[eid] += 1

            pos += 3

        frame_gold[fidx] = dict(gold)
        frame_record_counts[fidx] = dict(counts)

    return eid_map, frame_gold, frame_record_counts


def analyze_frame_gold_pattern(replay_path: str, truth_gold: dict = None):
    """Analyze whether frame gold is cumulative or independent."""
    eid_map, frame_gold, frame_counts = extract_gold_per_frame(replay_path)

    frame_indices = sorted(frame_gold.keys())

    print(f"\nReplay: {Path(replay_path).name}")
    print(f"Total frames: {len(frame_indices)}")
    print(f"Players: {len(eid_map)}")

    # For each player, track gold across frames
    for eid in sorted(eid_map.keys()):
        pname = eid_map[eid]
        golds = [(fi, frame_gold.get(fi, {}).get(eid, 0)) for fi in frame_indices]
        counts = [(fi, frame_counts.get(fi, {}).get(eid, 0)) for fi in frame_indices]

        non_zero = [(fi, g) for fi, g in golds if g > 0]
        non_zero_counts = [(fi, c) for fi, c in counts if c > 0]

        if not non_zero:
            continue

        total_sum = sum(g for _, g in golds)
        max_single = max(g for _, g in golds) if golds else 0
        last_frame_gold = golds[-1][1] if golds else 0

        # Check if cumulative (monotonically increasing)
        values = [g for _, g in non_zero]
        is_increasing = all(values[i] <= values[i+1] * 1.01 for i in range(len(values)-1)) if len(values) > 1 else True

        truth_g = truth_gold.get(pname, 0) if truth_gold else 0

        print(f"\n  {pname} (eid={eid}):")
        print(f"    Frames with gold: {len(non_zero)}/{len(frame_indices)}")
        print(f"    Sum all frames: {total_sum:.0f}")
        print(f"    Max single frame: {max_single:.0f}")
        print(f"    Last frame gold: {last_frame_gold:.0f}")
        print(f"    Monotonically increasing: {is_increasing}")
        if truth_g:
            truth_minus_600 = truth_g - 600  # Remove starting gold
            print(f"    Truth (minus 600): {truth_minus_600}")
            print(f"    Sum/Truth: {total_sum/truth_minus_600:.2f}x" if truth_minus_600 > 0 else "")
            print(f"    Max/Truth: {max_single/truth_minus_600:.2f}x" if truth_minus_600 > 0 else "")
            print(f"    Last/Truth: {last_frame_gold/truth_minus_600:.2f}x" if truth_minus_600 > 0 else "")

        # Show first 5 and last 5 frame gold values
        if len(non_zero) > 10:
            print(f"    First 5 frames: {[(fi, f'{g:.0f}') for fi, g in non_zero[:5]]}")
            print(f"    Last 5 frames:  {[(fi, f'{g:.0f}') for fi, g in non_zero[-5:]]}")
        else:
            print(f"    All frames: {[(fi, f'{g:.0f}') for fi, g in non_zero]}")


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze first 3 complete matches
    for mi, match in enumerate(truth_data['matches'][:3]):
        replay_path = match['replay_file']
        truth_players = match.get('players', {})
        truth_gold = {pname: pdata.get('gold', 0) for pname, pdata in truth_players.items()}

        print(f"\n{'='*80}")
        print(f"MATCH {mi+1}: {Path(replay_path).parent.parent.name}/{Path(replay_path).parent.name}")
        print(f"{'='*80}")

        analyze_frame_gold_pattern(replay_path, truth_gold)


if __name__ == '__main__':
    main()
