#!/usr/bin/env python3
"""
Death Frame Forensics - Analyze ALL events at death/respawn boundaries

Approach:
1. Parse ALL 103 frames and extract ALL events (not just player events)
2. Track player entity disappearance/reappearance (death/respawn boundaries)
3. For each death frame, collect ALL events from ALL entities
4. Identify unique event signatures that occur at death frames but not normal frames

Truth Data (21.11.04 replay - 15 total deaths):
- Baron (57605): 6 kills, 2 deaths
- Petal (57093): 3 kills, 2 deaths
- Phinn (56325): 2 kills, 0 deaths
- Caine (56837): 3 kills, 4 deaths
- Yates (56581): 1 kill, 4 deaths
- Amael (57349): 0 kills, 3 deaths
"""

import sys
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_parser import VGRParser

# Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]
EVENT_SIZE = 37

# Player entity IDs (from truth data)
PLAYER_ENTITIES = {
    56325: "Phinn",
    56581: "Yates",
    56837: "Caine",
    57093: "Petal",
    57349: "Amael",
    57605: "Baron"
}

# Known death counts (truth)
TRUTH_DEATHS = {
    "Phinn": 0,
    "Yates": 4,
    "Caine": 4,
    "Petal": 2,
    "Amael": 3,
    "Baron": 2
}

def parse_events_from_frame(frame_data: bytes) -> List[Dict[str, Any]]:
    """
    Parse all events from a frame.
    Event format: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B]
    """
    events = []
    offset = 0

    while offset + EVENT_SIZE <= len(frame_data):
        # Extract event components
        entity_id = int.from_bytes(frame_data[offset:offset+2], 'little')
        zero_bytes = frame_data[offset+2:offset+4]
        action_code = frame_data[offset+4]
        payload = frame_data[offset+5:offset+EVENT_SIZE]

        events.append({
            'entity_id': entity_id,
            'action_code': action_code,
            'action_hex': f"0x{action_code:02X}",
            'payload': payload.hex(),
            'zero_check': zero_bytes == b'\x00\x00'
        })

        offset += EVENT_SIZE

    return events

def load_all_frames(replay_dir: Path, replay_name: str) -> Dict[int, bytes]:
    """Load all frame files into memory."""
    frames = {}
    for i in range(200):  # Try up to frame 200
        frame_path = replay_dir / f"{replay_name}.{i}.vgr"
        if not frame_path.exists():
            break
        frames[i] = frame_path.read_bytes()
    return frames

def track_player_presence(all_frames: Dict[int, bytes]) -> Dict[int, List[int]]:
    """
    Track which frames each player entity appears in.
    Returns: {entity_id: [list of frame numbers where entity has events]}
    """
    player_presence = defaultdict(list)

    for frame_num, frame_data in sorted(all_frames.items()):
        events = parse_events_from_frame(frame_data)
        entities_in_frame = set(e['entity_id'] for e in events)

        for entity_id in PLAYER_ENTITIES.keys():
            if entity_id in entities_in_frame:
                player_presence[entity_id].append(frame_num)

    return player_presence

def find_disappearance_gaps(presence_frames: List[int], min_gap: int = 3) -> List[Tuple[int, int]]:
    """
    Find gaps in player presence (death periods).
    Returns: [(last_frame_before_gap, first_frame_after_gap), ...]
    """
    if not presence_frames:
        return []

    gaps = []
    for i in range(len(presence_frames) - 1):
        current_frame = presence_frames[i]
        next_frame = presence_frames[i + 1]
        gap_size = next_frame - current_frame

        if gap_size >= min_gap:  # Significant gap (likely death/respawn)
            gaps.append((current_frame, next_frame))

    return gaps

def analyze_death_frame_events(
    all_frames: Dict[int, bytes],
    death_frame: int,
    context_frames: int = 2
) -> Dict[str, Any]:
    """
    Analyze ALL events around a death frame.
    Returns events from death frame and context frames before/after.
    """
    analysis = {
        'death_frame': death_frame,
        'events_at_death': [],
        'events_before': [],
        'events_after': []
    }

    # Death frame events
    if death_frame in all_frames:
        analysis['events_at_death'] = parse_events_from_frame(all_frames[death_frame])

    # Context before
    for i in range(1, context_frames + 1):
        frame_num = death_frame - i
        if frame_num in all_frames:
            events = parse_events_from_frame(all_frames[frame_num])
            analysis['events_before'].append({
                'frame': frame_num,
                'events': events
            })

    # Context after
    for i in range(1, context_frames + 1):
        frame_num = death_frame + i
        if frame_num in all_frames:
            events = parse_events_from_frame(all_frames[frame_num])
            analysis['events_after'].append({
                'frame': frame_num,
                'events': events
            })

    return analysis

def find_unique_death_signatures(
    death_events: List[Dict[str, Any]],
    normal_events: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Identify event patterns unique to death frames.
    """
    # Count entity-action combinations in death frames
    death_signatures = Counter()
    for event in death_events:
        signature = (event['entity_id'], event['action_code'])
        death_signatures[signature] += 1

    # Count same combinations in normal frames
    normal_signatures = Counter()
    for event in normal_events:
        signature = (event['entity_id'], event['action_code'])
        normal_signatures[signature] += 1

    # Find signatures that are MUCH more common in death frames
    unique_to_death = {}
    for (entity_id, action_code), death_count in death_signatures.items():
        normal_count = normal_signatures.get((entity_id, action_code), 0)

        # Calculate enrichment ratio
        if normal_count == 0:
            enrichment = float('inf')
        else:
            enrichment = death_count / normal_count

        if enrichment > 2.0 or (death_count > 5 and normal_count == 0):
            unique_to_death[(entity_id, action_code)] = {
                'entity_id': entity_id,
                'entity_name': PLAYER_ENTITIES.get(entity_id, f"Entity_{entity_id}"),
                'action_code': f"0x{action_code:02X}",
                'death_count': death_count,
                'normal_count': normal_count,
                'enrichment': enrichment if enrichment != float('inf') else 'infinite'
            }

    return unique_to_death

def main():
    print("[STAGE:begin:data_loading]")

    # Replay path
    replay_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/")
    replay_name = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

    # Load player metadata
    parser = VGRParser(str(replay_dir / f"{replay_name}.0.vgr"))
    parsed_data = parser.parse()

    print(f"[DATA] Replay: {replay_name}")
    print(f"[DATA] Total frames: {parsed_data['match_info']['total_frames']}")

    # Load all frames
    all_frames = load_all_frames(replay_dir, replay_name)
    print(f"[DATA] Loaded {len(all_frames)} frames into memory")

    print("[STAGE:status:success]")
    print("[STAGE:end:data_loading]")

    print("\n[STAGE:begin:presence_tracking]")

    # Track player presence across frames
    player_presence = track_player_presence(all_frames)

    print("[FINDING] Player presence tracking:")
    for entity_id, frames in sorted(player_presence.items()):
        player_name = PLAYER_ENTITIES[entity_id]
        print(f"  {player_name} ({entity_id}): appears in {len(frames)} frames")
        print(f"    First: {frames[0]}, Last: {frames[-1]}")

    print("[STAGE:status:success]")
    print("[STAGE:end:presence_tracking]")

    print("\n[STAGE:begin:gap_detection]")

    # Find disappearance gaps (deaths)
    all_death_data = []
    total_detected_deaths = 0

    for entity_id, frames in sorted(player_presence.items()):
        player_name = PLAYER_ENTITIES[entity_id]
        gaps = find_disappearance_gaps(frames, min_gap=3)

        print(f"\n[FINDING] {player_name} disappearance gaps: {len(gaps)} detected")
        print(f"  Truth deaths: {TRUTH_DEATHS[player_name]}")

        for last_frame, first_frame in gaps:
            gap_size = first_frame - last_frame
            print(f"    Gap: frame {last_frame} -> {first_frame} (gap size: {gap_size})")

            all_death_data.append({
                'player_name': player_name,
                'entity_id': entity_id,
                'last_frame_before_death': last_frame,
                'first_frame_after_respawn': first_frame,
                'gap_size': gap_size
            })
            total_detected_deaths += 1

    print(f"\n[STAT:total_detected_deaths] {total_detected_deaths}")
    print(f"[STAT:truth_deaths] {sum(TRUTH_DEATHS.values())}")

    print("[STAGE:status:success]")
    print("[STAGE:end:gap_detection]")

    print("\n[STAGE:begin:death_frame_analysis]")

    # Analyze events at each death frame
    death_frame_events = []
    normal_frame_events = []

    death_frames = set()
    for death in all_death_data:
        death_frames.add(death['last_frame_before_death'])

    print(f"[DATA] Analyzing {len(death_frames)} unique death frames")

    # Collect all death frame events
    detailed_death_analysis = []
    for death in all_death_data:
        analysis = analyze_death_frame_events(
            all_frames,
            death['last_frame_before_death'],
            context_frames=2
        )

        death['event_analysis'] = analysis
        detailed_death_analysis.append(death)

        # Collect death frame events for signature analysis
        death_frame_events.extend(analysis['events_at_death'])

    # Collect normal frame events (not death frames)
    normal_frame_sample = []
    for frame_num in sorted(all_frames.keys()):
        if frame_num not in death_frames and len(normal_frame_sample) < 30:
            normal_frame_sample.append(frame_num)

    print(f"[DATA] Sampling {len(normal_frame_sample)} normal frames for comparison")

    for frame_num in normal_frame_sample:
        events = parse_events_from_frame(all_frames[frame_num])
        normal_frame_events.extend(events)

    print(f"[STAT:death_frame_events] {len(death_frame_events)}")
    print(f"[STAT:normal_frame_events] {len(normal_frame_events)}")

    print("[STAGE:status:success]")
    print("[STAGE:end:death_frame_analysis]")

    print("\n[STAGE:begin:signature_detection]")

    # Find unique death signatures
    unique_signatures = find_unique_death_signatures(death_frame_events, normal_frame_events)

    print(f"[FINDING] Found {len(unique_signatures)} unique death signatures")
    print("\nTop death signatures (entity-action pairs enriched at death):")

    sorted_sigs = sorted(
        unique_signatures.values(),
        key=lambda x: x['death_count'],
        reverse=True
    )

    for sig in sorted_sigs[:20]:
        enrichment_str = f"{sig['enrichment']:.1f}x" if sig['enrichment'] != 'infinite' else 'INF'
        print(f"  Entity {sig['entity_id']} ({sig['entity_name']}) Action {sig['action_code']}: "
              f"{sig['death_count']} death / {sig['normal_count']} normal = {enrichment_str}")

    # Entity-level analysis
    print("\n[FINDING] Low-ID entity activity at death frames:")
    low_id_entities = set()
    for event in death_frame_events:
        if event['entity_id'] < 1000:
            low_id_entities.add(event['entity_id'])

    print(f"  Found {len(low_id_entities)} unique low-ID entities at death frames")
    print(f"  Entity IDs: {sorted(low_id_entities)}")

    # System entity (ID=0) analysis
    system_events = [e for e in death_frame_events if e['entity_id'] == 0]
    print(f"\n[FINDING] Entity 0 (System) at death frames: {len(system_events)} events")
    if system_events:
        system_actions = Counter(e['action_code'] for e in system_events)
        print("  Action codes:")
        for action, count in system_actions.most_common(10):
            print(f"    0x{action:02X}: {count} times")

    # Entity 128 analysis
    entity_128_events = [e for e in death_frame_events if e['entity_id'] == 128]
    print(f"\n[FINDING] Entity 128 at death frames: {len(entity_128_events)} events")
    if entity_128_events:
        e128_actions = Counter(e['action_code'] for e in entity_128_events)
        print("  Action codes:")
        for action, count in e128_actions.most_common(10):
            print(f"    0x{action:02X}: {count} times")

    print("\n[STAGE:status:success]")
    print("[STAGE:end:signature_detection]")

    print("\n[STAGE:begin:output_generation]")

    # Build comprehensive output
    output = {
        'replay_name': replay_name,
        'analysis_summary': {
            'total_frames': len(all_frames),
            'detected_deaths': total_detected_deaths,
            'truth_deaths': sum(TRUTH_DEATHS.values()),
            'death_frames_analyzed': len(death_frames),
            'normal_frames_sampled': len(normal_frame_sample),
            'unique_death_signatures': len(unique_signatures)
        },
        'player_presence': {
            PLAYER_ENTITIES[eid]: {
                'entity_id': eid,
                'frames_with_events': len(frames),
                'first_frame': frames[0],
                'last_frame': frames[-1]
            }
            for eid, frames in player_presence.items()
        },
        'death_detections': detailed_death_analysis,
        'death_signatures': sorted_sigs,
        'low_id_entities_at_death': sorted(low_id_entities),
        'system_entity_events': {
            'entity_0': {
                'count': len(system_events),
                'actions': dict(Counter(e['action_code'] for e in system_events))
            },
            'entity_128': {
                'count': len(entity_128_events),
                'actions': dict(Counter(e['action_code'] for e in entity_128_events))
            }
        }
    }

    # Save to JSON
    output_path = Path("vg/output/death_frame_forensics.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[FINDING] Results saved to {output_path}")

    print("[STAGE:status:success]")
    print("[STAGE:end:output_generation]")

    print("\n" + "="*80)
    print("DEATH FRAME FORENSICS COMPLETE")
    print("="*80)
    print(f"Detected {total_detected_deaths} death gaps vs {sum(TRUTH_DEATHS.values())} truth deaths")
    print(f"Found {len(unique_signatures)} unique death event signatures")
    print(f"Low-ID entities at death: {sorted(low_id_entities)}")
    print("="*80)

if __name__ == '__main__':
    main()
