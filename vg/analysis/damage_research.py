"""
Damage Research: Search for damage dealt/taken patterns in VGR binary files

Research Strategy:
1. Analyze credit record action bytes for damage-related values
2. Search for new event headers with damage-like float values
3. Examine player heartbeat [18 04 3E] for stat fields
4. Look for damage bursts near kill events
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter
import json

# Import existing parsers
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

def find_pattern(data: bytes, pattern: bytes) -> list:
    """Find all occurrences of pattern in data"""
    positions = []
    start = 0
    while True:
        pos = data.find(pattern, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1
    return positions

def analyze_credit_action_bytes(replay_path: str):
    """Analyze all credit record [10 04 1D] action bytes"""
    print(f"\n=== Credit Action Byte Analysis: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])
    positions = find_pattern(data, credit_header)

    print(f"Found {len(positions)} credit records")

    # Structure: [10 04 1D][00 00][eid BE 2B][value f32 BE][action 1B]
    action_byte_counts = Counter()
    action_byte_examples = defaultdict(list)

    for pos in positions:
        if pos + 12 <= len(data):
            # Extract components
            eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
            value_bytes = data[pos+7:pos+11]
            value = struct.unpack('>f', value_bytes)[0]
            action_byte = data[pos+11]

            action_byte_counts[action_byte] += 1

            # Store examples (limit to 5 per action byte)
            if len(action_byte_examples[action_byte]) < 5:
                action_byte_examples[action_byte].append({
                    'eid': eid_be,
                    'value': value,
                    'pos': pos
                })

    # Print summary
    print(f"\nAction Byte Distribution:")
    for action_byte, count in sorted(action_byte_counts.items(), key=lambda x: -x[1]):
        print(f"  0x{action_byte:02X}: {count:5d} occurrences")

        # Show examples
        examples = action_byte_examples[action_byte][:3]
        for ex in examples:
            print(f"        eid={ex['eid']:5d}, value={ex['value']:8.2f}")

    return action_byte_counts, action_byte_examples

def search_damage_event_headers(replay_path: str):
    """Search for event headers with damage-like characteristics"""
    print(f"\n=== Damage Event Header Search: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()

    # Known headers to skip
    known_headers = [
        bytes([0x18, 0x04, 0x3E]),  # player heartbeat
        bytes([0x28, 0x04, 0x3F]),  # player action
        bytes([0x18, 0x04, 0x1E]),  # entity state
        bytes([0x18, 0x04, 0x1C]),  # kill
        bytes([0x08, 0x04, 0x31]),  # death
        bytes([0x10, 0x04, 0x1D]),  # credit
        bytes([0x10, 0x04, 0x3D]),  # item acquire
    ]

    # Search for 3-byte patterns [XX 04 YY] (common event header pattern)
    candidate_headers = Counter()

    for i in range(len(data) - 20):
        if data[i+1] == 0x04:  # Middle byte is 0x04
            header = bytes(data[i:i+3])
            if header not in known_headers:
                # Check if followed by player entity ID range (50000-60000 BE)
                if i + 7 <= len(data):
                    # Try reading entity ID at offset +5 (common pattern)
                    try:
                        eid_be = struct.unpack('>H', data[i+5:i+7])[0]
                        if 50000 <= eid_be <= 60000:
                            # Check for float value at +7
                            if i + 11 <= len(data):
                                value = struct.unpack('>f', data[i+7:i+11])[0]
                                # Damage-like: 10-2000 range
                                if 10 <= value <= 2000:
                                    candidate_headers[header] += 1
                    except:
                        pass

    print(f"\nCandidate damage event headers (with player eids + damage-like floats):")
    for header, count in sorted(candidate_headers.items(), key=lambda x: -x[1])[:10]:
        print(f"  {header.hex(' ').upper()}: {count:5d} occurrences")

    return candidate_headers

def analyze_player_heartbeat_stats(replay_path: str):
    """Analyze [18 04 3E] player heartbeat for stat fields"""
    print(f"\n=== Player Heartbeat Analysis: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    heartbeat_header = bytes([0x18, 0x04, 0x3E])
    positions = find_pattern(data, heartbeat_header)[:100]  # Sample first 100

    print(f"Analyzing {len(positions)} heartbeat samples (32-byte payload)")

    # Each heartbeat: [18 04 3E][00 00][eid BE 2B][payload 32B]
    # Look for accumulating float fields (damage dealt would increase over time)

    if len(positions) < 10:
        print("Not enough samples")
        return

    # Track float values at each offset
    float_sequences = defaultdict(list)

    for pos in positions[:50]:
        if pos + 37 <= len(data):
            eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

            # Scan payload for floats (4-byte aligned offsets)
            for offset in range(7, 37, 4):
                if pos + offset + 4 <= len(data):
                    try:
                        value = struct.unpack('>f', data[pos+offset:pos+offset+4])[0]
                        # Look for reasonable stat values (0-50000 range)
                        if 0 <= value <= 50000:
                            float_sequences[offset].append((eid_be, value))
                    except:
                        pass

    # Find fields that monotonically increase (stat accumulators)
    print("\nPotential stat accumulator fields (increasing over time):")
    for offset, values in sorted(float_sequences.items()):
        if len(values) >= 10:
            # Check if mostly increasing
            increasing_count = sum(1 for i in range(1, len(values)) if values[i][1] >= values[i-1][1])
            if increasing_count / len(values) > 0.7:
                print(f"  Offset +{offset}: {values[0][1]:.1f} -> {values[-1][1]:.1f} (range: {values[-1][1]-values[0][1]:.1f})")

    return float_sequences

def analyze_damage_near_kills(replay_path: str):
    """Look for damage burst patterns near kill events"""
    print(f"\n=== Damage Burst Near Kills: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    kill_header = bytes([0x18, 0x04, 0x1C])
    kill_positions = find_pattern(data, kill_header)

    print(f"Found {len(kill_positions)} kill events")

    # For each kill, scan -1000 to +500 bytes for high-frequency float patterns
    damage_candidates = Counter()

    for kill_pos in kill_positions[:20]:  # Sample first 20 kills
        # Scan window around kill
        start = max(0, kill_pos - 1000)
        end = min(len(data), kill_pos + 500)
        window = data[start:end]

        # Look for patterns with float values in damage range (10-500)
        for i in range(len(window) - 11):
            if window[i+1] == 0x04:  # Event header pattern
                header = bytes(window[i:i+3])
                try:
                    # Try reading float at various offsets
                    for float_offset in [7, 9, 11]:
                        if i + float_offset + 4 <= len(window):
                            value = struct.unpack('>f', window[i+float_offset:i+float_offset+4])[0]
                            if 10 <= value <= 500:  # Damage-like
                                damage_candidates[header] += 1
                except:
                    pass

    print(f"\nEvent headers with damage-like floats near kills:")
    for header, count in sorted(damage_candidates.items(), key=lambda x: -x[1])[:10]:
        print(f"  {header.hex(' ').upper()}: {count:5d} occurrences")

    return damage_candidates

def analyze_entity_state_events(replay_path: str):
    """Analyze [18 04 1E] entity state for health/damage fields"""
    print(f"\n=== Entity State Event Analysis: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    entity_state_header = bytes([0x18, 0x04, 0x1E])
    positions = find_pattern(data, entity_state_header)

    print(f"Found {len(positions)} entity state events")

    # Sample and look for health-like fields (decreasing over time)
    # Structure: [18 04 1E][00 00][eid BE 2B][payload ~32B]

    entity_sequences = defaultdict(list)

    for pos in positions[:500]:  # Sample
        if pos + 20 <= len(data):
            try:
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                # Only track player entities
                if 50000 <= eid_be <= 60000:
                    # Read float at offset +7 (common stat position)
                    if pos + 11 <= len(data):
                        value = struct.unpack('>f', data[pos+7:pos+11])[0]
                        if 0 <= value <= 10000:  # Health-like range
                            entity_sequences[eid_be].append(value)
            except:
                pass

    # Look for decreasing sequences (health loss)
    print("\nPlayer entities with decreasing values (potential health):")
    for eid, values in sorted(entity_sequences.items()):
        if len(values) >= 10:
            # Check variance
            if max(values) - min(values) > 100:  # Significant change
                print(f"  eid {eid}: {values[0]:.1f} -> {values[-1]:.1f} (min: {min(values):.1f}, max: {max(values):.1f})")

    return entity_sequences

def compare_credit_values_to_truth(replay_path: str, truth_data: dict):
    """Check if any credit action byte values correlate with expected damage"""
    print(f"\n=== Credit Value Correlation Check ===")

    # For now, we don't have damage truth data
    # But we can look for large credit values that might be damage

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])
    positions = find_pattern(data, credit_header)

    # Group by action byte and collect value statistics
    action_stats = defaultdict(list)

    for pos in positions:
        if pos + 12 <= len(data):
            value = struct.unpack('>f', data[pos+7:pos+11])[0]
            action_byte = data[pos+11]
            action_stats[action_byte].append(value)

    print("\nAction Byte Value Statistics:")
    for action_byte in sorted(action_stats.keys()):
        values = action_stats[action_byte]
        print(f"  0x{action_byte:02X}: count={len(values):5d}, "
              f"range=[{min(values):8.1f}, {max(values):8.1f}], "
              f"mean={sum(values)/len(values):8.1f}")

    return action_stats

def main():
    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze first 2 matches
    matches = truth_data['matches'][:2]

    for i, match in enumerate(matches):
        replay_path = match['replay_file']
        print(f"\n{'='*80}")
        print(f"MATCH {i+1}: {Path(replay_path).name}")
        print(f"Duration: {match['match_info']['duration_seconds']}s, "
              f"Score: {match['match_info']['score_left']}-{match['match_info']['score_right']}")
        print(f"{'='*80}")

        # Run all analyses
        action_byte_counts, action_byte_examples = analyze_credit_action_bytes(replay_path)
        candidate_headers = search_damage_event_headers(replay_path)
        float_sequences = analyze_player_heartbeat_stats(replay_path)
        damage_near_kills = analyze_damage_near_kills(replay_path)
        entity_sequences = analyze_entity_state_events(replay_path)
        action_stats = compare_credit_values_to_truth(replay_path, match)

        print(f"\n{'='*80}\n")

    print("\n[SUMMARY]")
    print("1. Credit action bytes: Analyzed all [10 04 1D] records for unexplored action bytes")
    print("2. New event headers: Searched for damage-like patterns with player eids")
    print("3. Player heartbeat: Checked [18 04 3E] for accumulating stat fields")
    print("4. Kill proximity: Scanned for damage bursts near kill events")
    print("5. Entity state: Analyzed [18 04 1E] for health/damage fields")

if __name__ == '__main__':
    main()
