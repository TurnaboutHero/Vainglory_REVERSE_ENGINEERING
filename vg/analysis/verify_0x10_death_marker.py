#!/usr/bin/env python3
"""
Verify 0x10 as Death Marker

Hypothesis: Action code 0x10 appears once per death event.

Test cases:
- Phinn (0 deaths) → expect 0x10 count = 0 ✓ (confirmed: 0)
- Yates (4 deaths) → expect 0x10 count ≈ 4 (actual: 4) ✓
- Caine (4 deaths) → expect 0x10 count ≈ 4 (actual: 3) ~ (75% accuracy)
- Petal (2 deaths) → expect 0x10 count ≈ 2 (actual: 3) ~ (150% - possible false positive)
- Amael (3 deaths) → expect 0x10 count ≈ 3
- Baron (2 deaths) → expect 0x10 count ≈ 2 (actual: 1) ~ (50% - underdetection)

This script extracts ALL 0x10 events with frame numbers and context.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

EVENT_SIZE = 37

PLAYER_ENTITIES = {
    56325: "Phinn",
    56581: "Yates",
    56837: "Caine",
    57093: "Petal",
    57349: "Amael",
    57605: "Baron"
}

DEATH_COUNTS = {
    "Phinn": 0,
    "Yates": 4,
    "Caine": 4,
    "Petal": 2,
    "Amael": 3,
    "Baron": 2
}

def extract_0x10_events(replay_dir: Path, replay_name: str):
    """Extract all 0x10 events with frame numbers and surrounding context."""

    results = defaultdict(list)

    for frame_num in range(200):
        frame_path = replay_dir / f"{replay_name}.{frame_num}.vgr"
        if not frame_path.exists():
            break

        frame_data = frame_path.read_bytes()
        offset = 0

        while offset + EVENT_SIZE <= len(frame_data):
            entity_id = int.from_bytes(frame_data[offset:offset+2], 'little')
            action_code = frame_data[offset+4]
            payload = frame_data[offset+5:offset+EVENT_SIZE]

            # Check for 0x10 action
            if action_code == 0x10 and entity_id in PLAYER_ENTITIES:
                player_name = PLAYER_ENTITIES[entity_id]

                results[player_name].append({
                    'frame': frame_num,
                    'entity_id': entity_id,
                    'action_code': '0x10',
                    'payload_hex': payload.hex()[:32]  # First 16 bytes
                })

            offset += EVENT_SIZE

    return results

def main():
    print("[STAGE:begin:verification]")

    replay_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/")
    replay_name = "8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4"

    # Extract all 0x10 events
    events_0x10 = extract_0x10_events(replay_dir, replay_name)

    print("\n[FINDING] 0x10 Event Distribution Across Players:\n")

    total_detected = 0
    total_truth = sum(DEATH_COUNTS.values())

    for player in sorted(PLAYER_ENTITIES.values()):
        count_0x10 = len(events_0x10.get(player, []))
        truth_deaths = DEATH_COUNTS[player]

        accuracy = (count_0x10 / truth_deaths * 100) if truth_deaths > 0 else 100 if count_0x10 == 0 else 0

        match_symbol = "✓" if count_0x10 == truth_deaths else "✗"

        print(f"{match_symbol} {player:8s}: {count_0x10} detected 0x10 events / {truth_deaths} truth deaths = {accuracy:.0f}%")

        if events_0x10.get(player):
            frames = [e['frame'] for e in events_0x10[player]]
            print(f"    Frames: {frames}")

        total_detected += count_0x10

    print(f"\n[STAT:total_0x10_events] {total_detected}")
    print(f"[STAT:total_truth_deaths] {total_truth}")
    print(f"[STAT:overall_accuracy] {total_detected / total_truth * 100:.1f}%")

    # Per-player accuracy
    exact_matches = sum(1 for p in PLAYER_ENTITIES.values() if len(events_0x10.get(p, [])) == DEATH_COUNTS[p])
    print(f"[STAT:exact_player_matches] {exact_matches}/6 players ({exact_matches/6*100:.0f}%)")

    # Save detailed report
    output = {
        'summary': {
            'total_0x10_detected': total_detected,
            'total_truth_deaths': total_truth,
            'overall_accuracy_pct': round(total_detected / total_truth * 100, 1),
            'exact_player_matches': exact_matches,
            'total_players': 6
        },
        'per_player': {
            player: {
                'detected_0x10': len(events_0x10.get(player, [])),
                'truth_deaths': DEATH_COUNTS[player],
                'accuracy_pct': round((len(events_0x10.get(player, [])) / DEATH_COUNTS[player] * 100) if DEATH_COUNTS[player] > 0 else (100 if len(events_0x10.get(player, [])) == 0 else 0), 1),
                'events': events_0x10.get(player, [])
            }
            for player in PLAYER_ENTITIES.values()
        }
    }

    output_path = Path("vg/output/verify_0x10_death_marker.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[FINDING] Detailed verification saved to {output_path}")

    print("\n[STAGE:status:success]")
    print("[STAGE:end:verification]")

    print("\n" + "="*80)
    print("0x10 DEATH MARKER VERIFICATION")
    print("="*80)

    if total_detected == total_truth and exact_matches == 6:
        print("✓ PERFECT MATCH: 0x10 is a reliable death marker")
    elif abs(total_detected - total_truth) <= 2:
        print("~ STRONG SIGNAL: 0x10 correlates with deaths (minor variance)")
    else:
        print("✗ WEAK SIGNAL: 0x10 does not reliably predict deaths")

    print("="*80)

if __name__ == '__main__':
    main()
