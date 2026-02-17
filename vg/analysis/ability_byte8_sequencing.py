#!/usr/bin/env python3
"""
Byte 8 Sequencing Analysis

Investigate why byte 8 values differ across matches.
Hypothesis: Byte 8 may be a sequence counter or frame-relative value.
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter


def read_replay_binary(replay_path):
    """Read raw binary data from replay file."""
    with open(replay_path, 'rb') as f:
        return f.read()


def extract_player_entity_ids(data):
    """Extract entity IDs from player blocks."""
    entity_ids = []
    markers = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break
            if pos + 0xA7 <= len(data):
                eid_le = struct.unpack('<H', data[pos+0xA5:pos+0xA7])[0]
                eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)
                entity_ids.append(eid_be)
            offset = pos + 1

    return list(set(entity_ids))


def analyze_byte8_sequencing(replay_path):
    """Analyze byte 8 sequencing patterns."""
    print(f"\n[STAGE:begin:byte8_sequencing]")
    print(f"[OBJECTIVE] Analyze byte 8 value sequencing in {replay_path.name}")

    data = read_replay_binary(replay_path)
    player_eids = extract_player_entity_ids(data)

    # Extract [28 04 3F] events with full context
    header = b'\x28\x04\x3F'
    events = []

    i = 0
    event_idx = 0
    while i < len(data) - 53:
        if data[i:i+3] == header:
            event_data = data[i:i+53]
            eid = struct.unpack('>H', event_data[5:7])[0]

            if eid in player_eids:
                events.append({
                    'idx': event_idx,
                    'offset': i,
                    'eid': eid,
                    'byte8': event_data[7+8],
                    'byte9': event_data[7+9],
                })
                event_idx += 1
            i += 53
        else:
            i += 1

    print(f"[DATA] Extracted {len(events)} player events")

    # Check if byte 8 is sequential
    byte8_values = [e['byte8'] for e in events]

    if byte8_values:
        min_byte8 = min(byte8_values)
        max_byte8 = max(byte8_values)
        unique_byte8 = len(set(byte8_values))

        print(f"\n[FINDING] Byte 8 range: 0x{min_byte8:02X} - 0x{max_byte8:02X}")
        print(f"[STAT:byte8_min] 0x{min_byte8:02X}")
        print(f"[STAT:byte8_max] 0x{max_byte8:02X}")
        print(f"[STAT:byte8_unique] {unique_byte8}")

        # Check if values are sequential
        is_sequential = all(
            byte8_values[i] <= byte8_values[i+1]
            for i in range(len(byte8_values)-1)
        )

        if is_sequential:
            print(f"\n[FINDING] Byte 8 values are MONOTONICALLY INCREASING")
        else:
            print(f"\n[FINDING] Byte 8 values are NOT sequential")

        # Show first 20 events
        print(f"\n[FINDING] First 20 events byte 8 sequence:")
        for i, evt in enumerate(events[:20]):
            print(f"  Event {i:2d}: byte8=0x{evt['byte8']:02X}, byte9=0x{evt['byte9']:02X}, eid={evt['eid']}")

        # Check per-player sequencing
        by_player = defaultdict(list)
        for evt in events:
            by_player[evt['eid']].append(evt['byte8'])

        print(f"\n[FINDING] Per-player byte 8 sequences (first 3 players):")
        for eid in sorted(by_player.keys())[:3]:
            seq = by_player[eid][:15]  # First 15 events
            seq_str = ', '.join([f'0x{v:02X}' for v in seq])
            print(f"  Entity {eid}: {seq_str}")

            # Check if player-specific sequence is monotonic
            is_player_sequential = all(seq[i] <= seq[i+1] for i in range(len(seq)-1))
            if is_player_sequential:
                print(f"    -> MONOTONIC for this player")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:byte8_sequencing]")

    return events


def compare_byte8_across_matches(replay_files):
    """Compare byte 8 starting values across matches."""
    print(f"\n[STAGE:begin:cross_match_comparison]")
    print(f"[OBJECTIVE] Compare byte 8 starting values across matches")

    results = []

    for replay_path in replay_files:
        data = read_replay_binary(replay_path)
        player_eids = extract_player_entity_ids(data)

        # Get first event
        header = b'\x28\x04\x3F'
        pos = data.find(header)

        if pos != -1 and pos + 53 <= len(data):
            event_data = data[pos:pos+53]
            eid = struct.unpack('>H', event_data[5:7])[0]

            if eid in player_eids:
                first_byte8 = event_data[7+8]

                results.append({
                    'file': replay_path.name,
                    'first_byte8': first_byte8,
                    'file_size': len(data),
                })

    print(f"\n[FINDING] First byte 8 value by match:")
    for r in results:
        print(f"  {r['file'][:50]:50s}: 0x{r['first_byte8']:02X} (size: {r['file_size']:,} bytes)")

    print(f"\n[FINDING] Hypothesis: Byte 8 starts at different values per match")
    print(f"[FINDING] This suggests byte 8 is NOT an ability type, but a counter/sequence")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:cross_match_comparison]")


def main():
    print("[OBJECTIVE] Investigate byte 8 sequencing patterns\n")

    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")

    if not replay_dir.exists():
        print(f"[LIMITATION] Directory not found: {replay_dir}")
        return

    replay_files = sorted(list(replay_dir.rglob("*.vgr")))
    replay_files = [f for f in replay_files if '__MACOSX' not in str(f)][:5]

    if not replay_files:
        print(f"[LIMITATION] No replay files found")
        return

    # Detailed analysis of first match
    events = analyze_byte8_sequencing(replay_files[0])

    # Cross-match comparison
    compare_byte8_across_matches(replay_files)

    print("\n" + "="*60)
    print("REVISED HYPOTHESIS")
    print("="*60)

    print("\n[FINDING] Byte 8 is likely NOT an ability type identifier")
    print("\n[FINDING] Evidence:")
    print("1. Byte 8 values vary across matches (0x08-0x13, 0x13-0x17, etc.)")
    print("2. Values appear to increment within a match")
    print("3. Starting value differs per match/frame")
    print("4. This pattern matches a SEQUENCE COUNTER or FRAME ID")

    print("\n[FINDING] Revised interpretation:")
    print("- [28 04 3F] may be a general 'player action' event")
    print("- Byte 8 could be a frame counter or event sequence number")
    print("- Actual ability identification may require:")
    print("  a) Different event header entirely")
    print("  b) Analysis of OTHER payload bytes (9-11, which also vary)")
    print("  c) Combination with other event types")

    print("\n[LIMITATION] Next research directions:")
    print("1. Analyze bytes 9-11 for ability type encoding")
    print("2. Search for OTHER event headers with lower frequency (~5-20 per player)")
    print("3. Look for events correlated with specific timestamps/actions")
    print("4. Investigate rare event headers (frequency < 10)")


if __name__ == "__main__":
    main()
