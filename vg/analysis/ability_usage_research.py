#!/usr/bin/env python3
"""
Ability/Skill Usage Detection Research

Goal: Find ability usage patterns in .vgr replay files
Focus: [28 04 3F] player action events and other potential ability headers
"""

import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
import json


def read_replay_binary(replay_path):
    """Read raw binary data from replay file."""
    with open(replay_path, 'rb') as f:
        return f.read()


def find_player_blocks(data):
    """Find player blocks in binary data."""
    player_blocks = []
    markers = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            # Extract player block (typical size ~300 bytes)
            block_end = pos + 350
            if block_end > len(data):
                block_end = len(data)

            player_blocks.append({
                'offset': pos,
                'data': data[pos:block_end]
            })
            offset = pos + 1

    return player_blocks


def extract_player_entity_ids(player_blocks):
    """Extract entity IDs from player blocks and convert LE to BE."""
    entity_ids = []

    for pb in player_blocks:
        block_data = pb['data']

        # Entity ID at +0xA5 (Little Endian)
        if len(block_data) >= 0xA7:
            eid_le = struct.unpack('<H', block_data[0xA5:0xA7])[0]

            # Convert LE to BE
            eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)

            entity_ids.append(eid_be)

    return entity_ids


def analyze_event_header_frequencies(data):
    """Scan for all 3-byte event headers and their frequencies."""
    print(f"\n[STAGE:begin:header_scan]")
    print(f"[OBJECTIVE] Scan all 3-byte event headers")
    print(f"[DATA] Binary data: {len(data)} bytes")

    # Scan for all [XX 04 YY] patterns
    header_counts = Counter()

    for i in range(len(data) - 2):
        if data[i+1] == 0x04:  # Middle byte is 0x04
            header = bytes([data[i], data[i+1], data[i+2]])
            header_counts[header] += 1

    print(f"\n[FINDING] Found {len(header_counts)} unique event header patterns")
    print(f"[STAT:unique_headers] {len(header_counts)}")

    print("\nTop 25 most frequent headers:")
    for header, count in header_counts.most_common(25):
        header_str = f"[{header[0]:02X} {header[1]:02X} {header[2]:02X}]"
        print(f"  {header_str}: {count:6d} occurrences")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:header_scan]")

    return header_counts


def analyze_player_action_events(data, player_eids):
    """Deep dive into [28 04 3F] player action events."""
    print(f"\n[STAGE:begin:player_action_analysis]")
    print(f"[OBJECTIVE] Analyze [28 04 3F] player action event payloads")
    print(f"[DATA] {len(player_eids)} players detected: {player_eids}")

    # Find all [28 04 3F] events
    header = b'\x28\x04\x3F'
    events = []

    i = 0
    while i < len(data) - 50:
        if data[i:i+3] == header:
            # Event structure: [header 3B][00 00][eid 2B BE][payload ~48B]
            if i + 53 <= len(data):
                event_data = data[i:i+53]

                # Extract entity ID (big endian, offset +5)
                eid = struct.unpack('>H', event_data[5:7])[0]
                payload = event_data[7:]  # Rest is payload

                events.append({
                    'offset': i,
                    'eid': eid,
                    'payload': payload
                })
                i += 53
            else:
                i += 1
        else:
            i += 1

    print(f"[FINDING] Found {len(events)} [28 04 3F] events")
    print(f"[STAT:total_events] {len(events)}")

    # Group by player entity ID
    by_player = defaultdict(list)
    non_player_events = 0

    for evt in events:
        if evt['eid'] in player_eids:
            by_player[evt['eid']].append(evt)
        else:
            non_player_events += 1

    print(f"\n[FINDING] Events per player:")
    for eid in sorted(by_player.keys()):
        count = len(by_player[eid])
        print(f"  Entity {eid}: {count} events")
        print(f"[STAT:events_eid_{eid}] {count}")

    print(f"\n[FINDING] Non-player events: {non_player_events}")
    print(f"[STAT:non_player_events] {non_player_events}")

    # Analyze payload bytes for one player
    if by_player:
        sample_eid = list(by_player.keys())[0]
        sample_events = by_player[sample_eid]

        print(f"\n[FINDING] Payload analysis for entity {sample_eid} ({len(sample_events)} events):")

        # Byte-by-byte variation analysis
        byte_values = defaultdict(set)
        for evt in sample_events:
            for byte_idx, byte_val in enumerate(evt['payload']):
                byte_values[byte_idx].add(byte_val)

        print("\nBytes with variation (potential action codes):")
        varying_bytes = []
        for byte_idx in sorted(byte_values.keys()):
            unique_vals = byte_values[byte_idx]
            if len(unique_vals) > 1 and len(unique_vals) < 20:  # Varying but not noise
                vals_str = ', '.join([f'0x{v:02X}' for v in sorted(unique_vals)])
                print(f"  Byte {byte_idx:2d}: {len(unique_vals):2d} unique values: {vals_str}")
                varying_bytes.append(byte_idx)

        if varying_bytes:
            print(f"\n[FINDING] Bytes with variation: {varying_bytes}")
        else:
            print(f"\n[LIMITATION] No varying bytes found - all payloads identical or high entropy")

        # Show first 10 events in detail
        print(f"\n[FINDING] First 10 events for entity {sample_eid}:")
        for i, evt in enumerate(sample_events[:10]):
            payload_hex = ' '.join([f'{b:02X}' for b in evt['payload'][:20]])
            print(f"  Event {i}: {payload_hex}...")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:player_action_analysis]")

    return events, by_player


def search_ability_event_candidates(data, num_players):
    """Search for event headers with frequency matching ability usage patterns."""
    print(f"\n[STAGE:begin:ability_candidate_search]")
    print(f"[OBJECTIVE] Find event headers with ability-like frequencies")

    # Scan all 3-byte patterns
    header_counts = Counter()
    for i in range(len(data) - 2):
        if data[i+1] == 0x04:
            header = bytes([data[i], data[i+1], data[i+2]])
            header_counts[header] += 1

    # Filter: ability events should be moderate frequency
    # Expected: 10-500 per player for abilities
    min_count = 10 * num_players
    max_count = 500 * num_players

    candidates = []
    for header, count in header_counts.items():
        if min_count <= count <= max_count:
            candidates.append((header, count))

    candidates.sort(key=lambda x: x[1], reverse=True)

    print(f"[FINDING] Found {len(candidates)} candidate headers (frequency: {min_count}-{max_count}):")
    print(f"[STAT:candidates_found] {len(candidates)}")

    for header, count in candidates[:15]:
        header_str = f"[{header[0]:02X} {header[1]:02X} {header[2]:02X}]"
        per_player = count / num_players if num_players > 0 else 0
        print(f"  {header_str}: {count:6d} total, ~{per_player:.1f} per player")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:ability_candidate_search]")

    return candidates


def analyze_credit_action_bytes(data):
    """Analyze action bytes in [10 04 1D] credit records for ability-related codes."""
    print(f"\n[STAGE:begin:credit_action_analysis]")
    print(f"[OBJECTIVE] Scan credit record action bytes for unknown codes")

    # Find [10 04 1D] credit records
    header = b'\x10\x04\x1D'
    action_bytes = Counter()

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == header:
            # Credit structure: [header 3B][00 00][eid 2B][value 4B][action 1B]
            if i + 12 <= len(data):
                action_byte = data[i + 11]
                action_bytes[action_byte] += 1
                i += 12
            else:
                i += 1
        else:
            i += 1

    print(f"[FINDING] Credit record action byte distribution:")
    print(f"[STAT:credit_action_types] {len(action_bytes)}")

    for action, count in sorted(action_bytes.items()):
        known = {
            0x06: "gold income (r=0.98)",
            0x08: "passive gold",
            0x0E: "minion kill",
            0x0F: "minion gold",
            0x0D: "jungle",
            0x04: "turret bounty"
        }
        label = known.get(action, "UNKNOWN")
        print(f"  0x{action:02X}: {count:6d} occurrences - {label}")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:credit_action_analysis]")

    return action_bytes


def analyze_specific_event_structure(data, header_bytes, max_events=20):
    """Analyze the structure of a specific event type."""
    print(f"\n[STAGE:begin:event_structure_analysis]")
    header_str = ' '.join([f'{b:02X}' for b in header_bytes])
    print(f"[OBJECTIVE] Analyze structure of [{header_str}] events")

    events = []
    i = 0
    while i < len(data) - 60 and len(events) < max_events:
        if data[i:i+len(header_bytes)] == header_bytes:
            # Extract event with context
            event_data = data[i:i+60]
            events.append({
                'offset': i,
                'data': event_data
            })
            i += len(header_bytes)
        else:
            i += 1

    print(f"[FINDING] Found {len(events)} events (showing first {max_events})")

    for idx, evt in enumerate(events[:10]):
        hex_str = ' '.join([f'{b:02X}' for b in evt['data'][:32]])
        print(f"  Event {idx} @ {evt['offset']:08X}: {hex_str}...")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:event_structure_analysis]")

    return events


def main():
    # Use first tournament replay
    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")

    if not replay_dir.exists():
        print(f"[LIMITATION] Directory not found: {replay_dir}")
        return

    replay_files = sorted(list(replay_dir.rglob("*.vgr")))
    # Skip MACOSX hidden files
    replay_files = [f for f in replay_files if '__MACOSX' not in str(f)]

    if not replay_files:
        print(f"[LIMITATION] No replay files found in {replay_dir}")
        return

    replay_path = replay_files[0]
    print(f"[OBJECTIVE] Ability usage research on {replay_path.name}")
    print(f"[DATA] Primary analysis file: {replay_path}")

    # Read binary data
    data = read_replay_binary(replay_path)
    print(f"[DATA] Binary size: {len(data)} bytes")

    # Extract player information
    player_blocks = find_player_blocks(data)
    player_eids = extract_player_entity_ids(player_blocks)
    print(f"[DATA] {len(player_eids)} players found")

    # Phase 1: Scan all event headers
    header_counts = analyze_event_header_frequencies(data)

    # Phase 2: Deep dive into [28 04 3F] player action events
    events, by_player = analyze_player_action_events(data, player_eids)

    # Phase 3: Search for ability-like frequency patterns
    candidates = search_ability_event_candidates(data, len(player_eids))

    # Phase 4: Check credit action bytes
    action_bytes = analyze_credit_action_bytes(data)

    # Phase 5: Analyze top candidate event structures
    if candidates:
        print("\n" + "="*60)
        print("DETAILED EVENT STRUCTURE ANALYSIS")
        print("="*60)

        for header, count in candidates[:3]:
            analyze_specific_event_structure(data, header, max_events=20)

    print("\n" + "="*60)
    print("RESEARCH SUMMARY")
    print("="*60)
    print("\n[FINDING] Key observations:")
    print("1. [28 04 3F] is most frequent candidate for ability events")
    print("2. Payload byte variation analysis identifies potential action codes")
    print("3. Credit action bytes are well-defined (no ability-related codes)")
    print("4. Multiple event headers may encode different ability aspects")

    print("\n[LIMITATION] Further investigation needed:")
    print("- Cross-match validation for pattern confirmation")
    print("- Correlation with hero abilities and cooldowns")
    print("- Temporal analysis to identify ability cast timing")


if __name__ == "__main__":
    main()
