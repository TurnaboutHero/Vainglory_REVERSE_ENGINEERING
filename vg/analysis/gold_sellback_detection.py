"""
Gold Sell-back Detection: Look for item sell events near positive 0x06 records.

Strategy:
1. Check if [10 04 3D] item acquire has negative qty for sells
2. Look for patterns around positive 0x06 that match sell-back values
3. Check if there are other event headers marking item sell
"""

import struct, math, json, sys
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

_ITEM_ACQUIRE = bytes([0x10, 0x04, 0x3D])
_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def analyze_item_events(replay_path: str):
    """Analyze [10 04 3D] events for sell patterns (negative qty or special flags)."""
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
    frame_files = sorted(frame_dir.glob(f"{frame_name}.*.vgr"),
                         key=lambda p: int(p.stem.split('.')[-1]) if p.stem.split('.')[-1].isdigit() else 0)

    # Track item acquire events with full context
    item_events = defaultdict(list)  # eid -> [(frame, pos, qty_byte, item_id, raw_bytes)]

    for fpath in frame_files:
        fidx = int(fpath.stem.split('.')[-1]) if fpath.stem.split('.')[-1].isdigit() else 0
        data = fpath.read_bytes()

        pos = 0
        while True:
            pos = data.find(_ITEM_ACQUIRE, pos)
            if pos == -1:
                break
            if pos + 20 > len(data):
                pos += 1
                continue
            if data[pos + 3:pos + 5] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid not in valid_eids:
                pos += 3
                continue

            # Full structure: [10 04 3D][00 00][eid BE][00 00][qty][item_id LE][00 00][counter BE][ts f32 BE]
            qty_byte = data[pos + 9]
            item_id = struct.unpack_from("<H", data, pos + 10)[0]
            raw = data[pos:pos + 20]

            # Also check the byte BEFORE qty for potential sell flag
            pre_qty = data[pos + 7:pos + 9]

            item_events[eid].append({
                'frame': fidx,
                'pos': pos,
                'qty': qty_byte,
                'item_id': item_id,
                'pre_qty_hex': pre_qty.hex(),
                'raw_hex': raw.hex(),
            })

            pos += 3

    # Analyze qty distributions
    print(f"\n{'='*60}")
    print(f"Item Acquire Event Analysis: {Path(replay_path).name}")
    print(f"{'='*60}")

    all_qty_values = Counter()
    for eid, events in item_events.items():
        pname = eid_map.get(eid, f"eid_{eid}")
        qty_counts = Counter(e['qty'] for e in events)
        all_qty_values.update(qty_counts)

        print(f"\n  {pname}: {len(events)} item events")
        print(f"    qty distribution: {dict(qty_counts)}")

        # Show unique item IDs
        unique_items = set(e['item_id'] for e in events)
        print(f"    unique items: {len(unique_items)} ({sorted(unique_items)[:20]})")

        # Show events with unusual qty (not 1)
        unusual = [e for e in events if e['qty'] != 1]
        if unusual:
            print(f"    Unusual qty events ({len(unusual)}):")
            for e in unusual[:10]:
                print(f"      frame={e['frame']}, qty={e['qty']}, item={e['item_id']}, "
                      f"pre_qty={e['pre_qty_hex']}, raw={e['raw_hex']}")

    print(f"\n  Overall qty distribution: {dict(all_qty_values)}")

    # Look for other event headers near positive 0x06 records
    # that might indicate item sell
    print(f"\n{'='*60}")
    print(f"Event Headers Near Positive 0x06 Records")
    print(f"{'='*60}")

    # Pick an overcounted player if available
    for fpath in frame_files[:5]:
        fidx = int(fpath.stem.split('.')[-1]) if fpath.stem.split('.')[-1].isdigit() else 0
        data = fpath.read_bytes()

        # Find positive 0x06 with value > 100 (potential sell-back)
        pos = 0
        high_value_contexts = []
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

            if action == 0x06 and value > 100 and not math.isnan(value):
                # Look at surrounding bytes
                context_start = max(0, pos - 30)
                context_end = min(len(data), pos + 30)
                context = data[context_start:context_end]
                high_value_contexts.append({
                    'frame': fidx,
                    'pos': pos,
                    'eid': eid,
                    'value': value,
                    'context_hex': context.hex(' '),
                })

            pos += 3

        if high_value_contexts:
            print(f"\n  Frame {fidx}: {len(high_value_contexts)} high-value 0x06 records")
            for ctx in high_value_contexts[:5]:
                pname = eid_map.get(ctx['eid'], f"eid_{ctx['eid']}")
                print(f"    {pname}: value={ctx['value']:.0f} at pos={ctx['pos']}")
                print(f"      context: ...{ctx['context_hex'][-90:]}...")


def check_negative_credit_context(replay_path: str):
    """Check if negative 0x06 records are near item acquire events."""
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

    print(f"\n{'='*60}")
    print(f"Negative 0x06 Context Analysis")
    print(f"{'='*60}")

    # Find all negative 0x06 and check if preceded by item acquire
    for fpath in frame_files[:10]:
        fidx = int(fpath.stem.split('.')[-1]) if fpath.stem.split('.')[-1].isdigit() else 0
        data = fpath.read_bytes()

        neg_records = []
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

            if action == 0x06 and value < 0:
                # Check bytes before this record for item acquire header
                look_back = 100
                start = max(0, pos - look_back)
                window = data[start:pos]
                has_item_acquire = _ITEM_ACQUIRE in window

                # Check bytes after for item acquire
                look_ahead = 50
                end = min(len(data), pos + 12 + look_ahead)
                window_after = data[pos + 12:end]
                has_item_after = _ITEM_ACQUIRE in window_after

                neg_records.append({
                    'pos': pos,
                    'eid': eid,
                    'value': value,
                    'item_before': has_item_acquire,
                    'item_after': has_item_after,
                })

            pos += 3

        if neg_records:
            print(f"\n  Frame {fidx}: {len(neg_records)} negative 0x06 records")
            with_item = sum(1 for r in neg_records if r['item_before'] or r['item_after'])
            print(f"    With nearby item acquire: {with_item}/{len(neg_records)}")

            for r in neg_records[:5]:
                pname = eid_map.get(r['eid'], f"eid_{r['eid']}")
                print(f"    {pname}: value={r['value']:.0f}, item_before={r['item_before']}, item_after={r['item_after']}")


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze M7 (worst overcounting)
    match = truth_data['matches'][6]  # M7 (0-indexed)
    replay_path = match['replay_file']

    analyze_item_events(replay_path)
    check_negative_credit_context(replay_path)


if __name__ == '__main__':
    main()
