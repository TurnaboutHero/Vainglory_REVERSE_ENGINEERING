"""
Event Header Survey - Comprehensive catalog of ALL [XX 04 YY] event types.

Systematically identifies and classifies all event headers in VGR binary format:
- Frequency analysis across multiple matches
- Entity ID presence detection (player vs non-player)
- Payload size estimation
- Data pattern classification
"""

import struct
import sys
from collections import defaultdict
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be


def find_all_headers(data: bytes) -> dict:
    """
    Scan entire byte array for [XX 04 YY] patterns.
    Returns: {header_tuple: [list of offsets]}
    """
    headers = defaultdict(list)
    for i in range(len(data) - 2):
        if data[i + 1] == 0x04:
            header = (data[i], data[i + 1], data[i + 2])
            headers[header].append(i)
    return dict(headers)


def extract_entity_id(data: bytes, offset: int) -> int | None:
    """Extract entity ID at offset+5 (BE uint16), if valid range."""
    try:
        if offset + 7 > len(data):
            return None
        # Skip header[3] + 00 00[2] = 5 bytes, then read 2-byte BE eid
        eid = struct.unpack('>H', data[offset + 5:offset + 7])[0]
        # Valid entity ranges: 0-10 (system), 1000-60000 (entities)
        if eid <= 10 or (1000 <= eid <= 60000):
            return eid
        return None
    except:
        return None


def estimate_payload_size(offsets: list) -> int | None:
    """Estimate payload size from distance between consecutive events."""
    if len(offsets) < 10:
        return None
    distances = [offsets[i + 1] - offsets[i] for i in range(min(20, len(offsets) - 1))]
    # Most common distance
    from collections import Counter
    counts = Counter(distances)
    if counts:
        return counts.most_common(1)[0][0]
    return None


def classify_entity_type(eid: int) -> str:
    """Classify entity ID into known ranges."""
    if eid == 0:
        return "system"
    if 1 <= eid <= 10:
        return "infrastructure"
    if 1000 <= eid <= 20000:
        return "structures"
    if 20000 <= eid <= 50000:
        return "minions"
    if 50000 <= eid <= 60000:
        return "players"
    return "unknown"


def extract_payload_sample(data: bytes, offset: int, size: int) -> str:
    """Extract hex dump of payload (up to 64 bytes)."""
    end = min(offset + size, offset + 64, len(data))
    chunk = data[offset:end]
    return ' '.join(f'{b:02X}' for b in chunk)


def analyze_payload_patterns(data: bytes, offsets: list, size: int) -> dict:
    """
    Analyze payload data patterns:
    - Float32 presence (check for normal float values)
    - Uint16 patterns
    - Byte value distribution
    """
    if size is None or size < 8:
        return {}

    # Sample first 10 events
    float_values = []
    uint16_values = []
    byte_histogram = defaultdict(int)

    for offset in offsets[:10]:
        if offset + size > len(data):
            continue
        payload = data[offset:offset + size]

        # Try reading floats at various positions (BE)
        for i in range(0, min(len(payload) - 4, 32), 4):
            try:
                f = struct.unpack('>f', payload[i:i + 4])[0]
                if -1e6 < f < 1e6 and not (f == 0):  # Reasonable float range
                    float_values.append((i, f))
            except:
                pass

        # Uint16 values (BE)
        for i in range(0, min(len(payload) - 2, 32), 2):
            try:
                u = struct.unpack('>H', payload[i:i + 2])[0]
                if u != 0:
                    uint16_values.append((i, u))
            except:
                pass

        # Byte distribution
        for b in payload[:32]:
            byte_histogram[b] += 1

    return {
        'float_samples': float_values[:5],
        'uint16_samples': uint16_values[:5],
        'common_bytes': sorted(byte_histogram.items(), key=lambda x: -x[1])[:5]
    }


def survey_match(replay_path: Path, player_eids: set) -> dict:
    """Survey all headers in a single match."""
    print(f"\n[STAGE:begin:survey_{replay_path.stem}]")

    # Read raw binary data directly
    frame_data = replay_path.read_bytes()

    if not frame_data:
        print(f"[LIMITATION] No data from {replay_path.name}")
        return {}

    # Find all headers
    all_headers = find_all_headers(frame_data)
    print(f"[DATA] Found {len(all_headers)} unique header types in frame 0")

    results = {}

    for header, offsets in sorted(all_headers.items(), key=lambda x: -len(x[1])):
        header_hex = f"{header[0]:02X} {header[1]:02X} {header[2]:02X}"
        count = len(offsets)

        # Extract entity IDs from first 20 events
        entity_ids = []
        for offset in offsets[:20]:
            eid = extract_entity_id(frame_data, offset)
            if eid is not None:
                entity_ids.append(eid)

        # Check if player-related
        player_related = any(eid in player_eids for eid in entity_ids)

        # Classify entities
        entity_types = [classify_entity_type(eid) for eid in entity_ids if eid is not None]
        entity_summary = {}
        if entity_types:
            from collections import Counter
            entity_summary = dict(Counter(entity_types))

        # Estimate payload size
        payload_size = estimate_payload_size(offsets)

        # Sample payloads
        samples = []
        for offset in offsets[:3]:
            if payload_size:
                samples.append(extract_payload_sample(frame_data, offset, payload_size))

        # Payload patterns
        patterns = {}
        if payload_size and payload_size >= 8:
            patterns = analyze_payload_patterns(frame_data, offsets, payload_size)

        results[header_hex] = {
            'count': count,
            'player_related': player_related,
            'payload_size': payload_size,
            'entity_ids_sample': entity_ids[:10],
            'entity_types': entity_summary,
            'payload_samples': samples,
            'patterns': patterns
        }

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:survey_{replay_path.stem}]")

    return results


def classify_header_purpose(header: str, info: dict) -> str:
    """Classify header into known categories."""
    known = {
        '18 04 3E': 'player_heartbeat',
        '28 04 3F': 'player_action',
        '18 04 1E': 'entity_state',
        '18 04 1C': 'kill_header',
        '08 04 31': 'death_header',
        '10 04 1D': 'credit_record',
        '10 04 3D': 'item_acquire',
        '10 04 4B': 'item_equip'
    }

    if header in known:
        return known[header]

    # Classify unknown
    if info['player_related']:
        return 'unknown_player_event'
    elif info['entity_types']:
        dominant = max(info['entity_types'].items(), key=lambda x: x[1])[0]
        return f'unknown_{dominant}_event'
    else:
        return 'unknown_system_event'


def cross_match_validation(match_results: dict) -> dict:
    """Validate header consistency across matches."""
    # Find headers present in ALL matches
    all_headers = set()
    for match_name, headers in match_results.items():
        all_headers.update(headers.keys())

    consistency = {}
    for header in all_headers:
        counts = [match_results[m][header]['count'] for m in match_results if header in match_results[m]]
        present_in = len([m for m in match_results if header in match_results[m]])

        consistency[header] = {
            'present_in_matches': f"{present_in}/{len(match_results)}",
            'count_range': f"{min(counts) if counts else 0}-{max(counts) if counts else 0}",
            'avg_count': sum(counts) // len(counts) if counts else 0
        }

    return consistency


def main():
    print("[OBJECTIVE] Systematically catalog ALL event header types in VGR binary format")

    # Load truth data to get replay file paths
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path, 'r') as f:
        truth = json.load(f)

    # Use first 3 matches from truth data
    replays = []
    for match in truth['matches'][:3]:
        replay_path = Path(match['replay_file'])
        if replay_path.exists():
            replays.append(replay_path)
        else:
            print(f"[LIMITATION] Replay not found: {replay_path}")

    if not replays:
        print("[LIMITATION] No accessible replay files from truth data")
        return

    print(f"[DATA] Analyzing {len(replays)} matches: {[r.stem.split('-')[0] for r in replays]}")

    all_match_results = {}

    for replay in replays:
        match_name = replay.stem

        # Get player entity IDs for this match
        decoder = UnifiedDecoder(str(replay))
        decoded = decoder.decode()
        players = decoded.all_players

        player_eids_le = {p.entity_id for p in players}
        player_eids_be = {_le_to_be(eid) for eid in player_eids_le if eid}

        print(f"\n[DATA] Match: {match_name}, Player entity IDs (BE): {sorted(player_eids_be)}")

        # Survey
        results = survey_match(replay, player_eids_be)
        all_match_results[match_name] = results

    # Cross-match validation
    print("\n[STAGE:begin:cross_validation]")
    consistency = cross_match_validation(all_match_results)

    # Aggregate report
    print("\n" + "="*80)
    print("COMPLETE EVENT HEADER CATALOG")
    print("="*80)

    # Get headers from first match for detailed reporting
    first_match = list(all_match_results.keys())[0]
    reference_results = all_match_results[first_match]

    # Sort by frequency
    sorted_headers = sorted(reference_results.items(), key=lambda x: -x[1]['count'])

    for header, info in sorted_headers:
        purpose = classify_header_purpose(header, info)

        print(f"\n[{header}] - {purpose.upper()}")
        print(f"  Frequency: ~{info['count']} events/frame")
        print(f"  Consistency: {consistency[header]['present_in_matches']}")
        print(f"  Payload Size: {info['payload_size']} bytes" if info['payload_size'] else "  Payload Size: VARIABLE")
        print(f"  Player-Related: {'YES' if info['player_related'] else 'NO'}")

        if info['entity_types']:
            print(f"  Entity Types: {info['entity_types']}")

        if info['entity_ids_sample']:
            print(f"  Entity ID Sample: {info['entity_ids_sample'][:5]}")

        if info['payload_samples']:
            print(f"  Payload Sample (hex): {info['payload_samples'][0][:60]}...")

        if info['patterns']:
            patterns = info['patterns']
            if patterns.get('float_samples'):
                print(f"  Float32 detected: {patterns['float_samples'][:3]}")
            if patterns.get('uint16_samples'):
                print(f"  Uint16 values: {patterns['uint16_samples'][:3]}")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:cross_validation]")

    # Save detailed JSON report
    output_path = Path("vg/output/event_header_catalog.json")
    output_path.parent.mkdir(exist_ok=True)

    catalog = {
        'matches_analyzed': list(all_match_results.keys()),
        'headers': {}
    }

    for header in sorted_headers:
        header_hex = header[0]
        info = header[1]
        catalog['headers'][header_hex] = {
            'purpose': classify_header_purpose(header_hex, info),
            'frequency': info['count'],
            'payload_size': info['payload_size'],
            'player_related': info['player_related'],
            'entity_types': info['entity_types'],
            'consistency': consistency[header_hex],
            'sample_payloads': info['payload_samples'][:2]
        }

    with open(output_path, 'w') as f:
        json.dump(catalog, f, indent=2)

    print(f"\n[FINDING] Detailed catalog saved to {output_path}")
    print(f"[STAT:total_unique_headers] {len(sorted_headers)}")
    print(f"[STAT:known_headers] {sum(1 for h, i in sorted_headers if 'unknown' not in classify_header_purpose(h, i))}")
    print(f"[STAT:unknown_headers] {sum(1 for h, i in sorted_headers if 'unknown' in classify_header_purpose(h, i))}")


if __name__ == '__main__':
    main()
