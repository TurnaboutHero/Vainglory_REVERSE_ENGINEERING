#!/usr/bin/env python3
"""
Detailed Ability Event Analysis

Focus on [28 04 3F] events - byte 8 shows 6 unique values (0x08-0x13)
which could correspond to different ability types (A, B, C, perk, items, etc.)
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter


def read_replay_binary(replay_path):
    """Read raw binary data from replay file."""
    with open(replay_path, 'rb') as f:
        return f.read()


def extract_player_entity_ids(data):
    """Extract entity IDs from player blocks and convert LE to BE."""
    entity_ids = []
    markers = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            # Entity ID at +0xA5 (Little Endian)
            if pos + 0xA7 <= len(data):
                eid_le = struct.unpack('<H', data[pos+0xA5:pos+0xA7])[0]
                # Convert LE to BE
                eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)
                entity_ids.append(eid_be)

            offset = pos + 1

    return list(set(entity_ids))  # Remove duplicates


def extract_28_04_3f_events(data, player_eids):
    """Extract all [28 04 3F] events with full payload."""
    print(f"[STAGE:begin:extract_events]")
    print(f"[OBJECTIVE] Extract all [28 04 3F] events")

    header = b'\x28\x04\x3F'
    events = []

    i = 0
    while i < len(data) - 53:
        if data[i:i+3] == header:
            # Event structure: [header 3B][00 00][eid 2B BE][payload 46B]
            event_data = data[i:i+53]
            eid = struct.unpack('>H', event_data[5:7])[0]

            events.append({
                'offset': i,
                'eid': eid,
                'payload': event_data[7:],
                'is_player': eid in player_eids
            })
            i += 53
        else:
            i += 1

    print(f"[FINDING] Extracted {len(events)} events")
    print(f"[STAT:total_events] {len(events)}")

    player_events = [e for e in events if e['is_player']]
    print(f"[STAT:player_events] {len(player_events)}")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:extract_events]")

    return events


def analyze_byte8_patterns(events):
    """Analyze byte 8 - potential ability type identifier."""
    print(f"\n[STAGE:begin:byte8_analysis]")
    print(f"[OBJECTIVE] Analyze byte 8 patterns (ability type hypothesis)")

    player_events = [e for e in events if e['is_player']]

    # Extract byte 8 values
    byte8_values = Counter()
    byte8_by_player = defaultdict(Counter)

    for evt in player_events:
        if len(evt['payload']) >= 9:
            byte8 = evt['payload'][8]
            byte8_values[byte8] += 1
            byte8_by_player[evt['eid']][byte8] += 1

    print(f"\n[FINDING] Byte 8 value distribution (all players):")
    for byte_val, count in sorted(byte8_values.items()):
        print(f"  0x{byte_val:02X}: {count:4d} occurrences")
        print(f"[STAT:byte8_0x{byte_val:02X}] {count}")

    # Check if byte 8 values correlate with specific players
    print(f"\n[FINDING] Byte 8 distribution by player:")
    for eid in sorted(byte8_by_player.keys())[:5]:  # Show first 5 players
        counts = byte8_by_player[eid]
        vals_str = ', '.join([f'0x{k:02X}:{v}' for k, v in sorted(counts.items())])
        print(f"  Entity {eid}: {vals_str}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:byte8_analysis]")

    return byte8_values, byte8_by_player


def analyze_byte16_17_patterns(events):
    """Analyze bytes 16-17 - potential action identifiers."""
    print(f"\n[STAGE:begin:byte16_17_analysis]")
    print(f"[OBJECTIVE] Analyze bytes 16-17 (action ID hypothesis)")

    player_events = [e for e in events if e['is_player']]

    # Extract 2-byte pattern at offset 16-17
    patterns = Counter()

    for evt in player_events:
        if len(evt['payload']) >= 18:
            pattern = (evt['payload'][16], evt['payload'][17])
            patterns[pattern] += 1

    print(f"\n[FINDING] Bytes 16-17 pattern distribution:")
    print(f"[STAT:unique_patterns] {len(patterns)}")

    for pattern, count in patterns.most_common(20):
        pattern_str = f"[{pattern[0]:02X} {pattern[1]:02X}]"
        print(f"  {pattern_str}: {count:4d} occurrences")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:byte16_17_analysis]")

    return patterns


def correlate_byte8_with_byte16_17(events):
    """Correlate byte 8 (type) with bytes 16-17 (action)."""
    print(f"\n[STAGE:begin:correlation_analysis]")
    print(f"[OBJECTIVE] Correlate byte 8 with bytes 16-17")

    player_events = [e for e in events if e['is_player']]

    # Build correlation map
    correlations = defaultdict(Counter)

    for evt in player_events:
        if len(evt['payload']) >= 18:
            byte8 = evt['payload'][8]
            pattern = (evt['payload'][16], evt['payload'][17])
            correlations[byte8][pattern] += 1

    print(f"\n[FINDING] Byte 8 -> Bytes 16-17 correlation:")
    for byte8 in sorted(correlations.keys()):
        print(f"\n  Byte 8 = 0x{byte8:02X}:")
        for pattern, count in correlations[byte8].most_common(10):
            pattern_str = f"[{pattern[0]:02X} {pattern[1]:02X}]"
            print(f"    {pattern_str}: {count:3d}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:correlation_analysis]")

    return correlations


def temporal_analysis(events):
    """Analyze temporal spacing between events (ability cooldowns)."""
    print(f"\n[STAGE:begin:temporal_analysis]")
    print(f"[OBJECTIVE] Analyze temporal patterns (cooldown hypothesis)")

    # Group by player and byte 8 value
    by_player_type = defaultdict(lambda: defaultdict(list))

    player_events = [e for e in events if e['is_player']]

    for evt in player_events:
        if len(evt['payload']) >= 9:
            byte8 = evt['payload'][8]
            by_player_type[evt['eid']][byte8].append(evt['offset'])

    # Calculate inter-event spacing for one player
    if by_player_type:
        sample_eid = list(by_player_type.keys())[0]
        print(f"\n[FINDING] Temporal spacing for entity {sample_eid}:")

        for byte8 in sorted(by_player_type[sample_eid].keys()):
            offsets = sorted(by_player_type[sample_eid][byte8])
            if len(offsets) > 1:
                spacings = [offsets[i+1] - offsets[i] for i in range(len(offsets)-1)]
                avg_spacing = sum(spacings) / len(spacings)
                min_spacing = min(spacings)
                max_spacing = max(spacings)

                print(f"  Byte 8 = 0x{byte8:02X}: {len(offsets):3d} events, "
                      f"avg spacing = {avg_spacing:.0f} bytes, "
                      f"min = {min_spacing}, max = {max_spacing}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:temporal_analysis]")


def extract_full_event_samples(events, byte8_value, max_samples=5):
    """Extract full event samples for a specific byte 8 value."""
    print(f"\n[STAGE:begin:sample_extraction]")
    print(f"[OBJECTIVE] Extract samples for byte 8 = 0x{byte8_value:02X}")

    samples = []
    for evt in events:
        if evt['is_player'] and len(evt['payload']) >= 9:
            if evt['payload'][8] == byte8_value:
                samples.append(evt)
                if len(samples) >= max_samples:
                    break

    print(f"\n[FINDING] Sample events (byte 8 = 0x{byte8_value:02X}):")
    for idx, evt in enumerate(samples):
        print(f"\n  Event {idx} - Entity {evt['eid']} @ offset 0x{evt['offset']:08X}:")
        # Print in 16-byte rows
        payload = evt['payload']
        for row_start in range(0, len(payload), 16):
            row_bytes = payload[row_start:row_start+16]
            hex_str = ' '.join([f'{b:02X}' for b in row_bytes])
            print(f"    {row_start:02d}: {hex_str}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:sample_extraction]")


def main():
    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")

    if not replay_dir.exists():
        print(f"[LIMITATION] Directory not found: {replay_dir}")
        return

    replay_files = sorted(list(replay_dir.rglob("*.vgr")))
    replay_files = [f for f in replay_files if '__MACOSX' not in str(f)]

    if not replay_files:
        print(f"[LIMITATION] No replay files found")
        return

    replay_path = replay_files[0]
    print(f"[OBJECTIVE] Detailed ability event analysis on {replay_path.name}")
    print(f"[DATA] File: {replay_path}\n")

    # Read data
    data = read_replay_binary(replay_path)
    player_eids = extract_player_entity_ids(data)
    print(f"[DATA] {len(player_eids)} unique players: {sorted(player_eids)}\n")

    # Extract events
    events = extract_28_04_3f_events(data, player_eids)

    # Analysis phases
    byte8_values, byte8_by_player = analyze_byte8_patterns(events)

    byte16_17_patterns = analyze_byte16_17_patterns(events)

    correlations = correlate_byte8_with_byte16_17(events)

    temporal_analysis(events)

    # Extract detailed samples for top byte 8 values
    for byte8_val, count in sorted(byte8_values.items())[:3]:
        extract_full_event_samples(events, byte8_val, max_samples=3)

    print("\n" + "="*60)
    print("ANALYSIS SUMMARY")
    print("="*60)

    print("\n[FINDING] Key insights:")
    print("1. Byte 8 has 6 unique values (0x08-0x13) - potential ability/action type")
    print("2. Bytes 16-17 show multiple patterns - potential action identifiers")
    print("3. Temporal spacing analysis can reveal cooldown patterns")
    print("4. Correlation between byte 8 and bytes 16-17 suggests structured encoding")

    print("\n[LIMITATION] Next steps:")
    print("- Compare events with known ability casts from gameplay video")
    print("- Validate byte 8 values against hero ability counts")
    print("- Cross-match analysis across multiple replays")
    print("- Investigate non-player events (entity IDs outside player range)")


if __name__ == "__main__":
    main()
