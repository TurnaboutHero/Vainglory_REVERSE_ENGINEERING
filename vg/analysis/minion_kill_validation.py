"""
Validate current minion kill detection accuracy and identify misses.
"""
import sys
sys.path.insert(0, 'D:/Documents/GitHub/VG_REVERSE_ENGINEERING')

from vg.core.vgr_parser import VGRParser
from vg.core.kda_detector import KDADetector
from vg.core.hero_matcher import identify_hero_mapping
import json

# Load truth
with open('vg/output/tournament_truth.json', 'r') as f:
    truth = json.load(f)

print("Validating current minion kill detection (action byte 0x0E)")
print("=" * 70)

total_perfect = 0
total_players = 0
all_errors = []

for match_idx, match in enumerate(truth['matches'][:9]):  # Skip match 9 (incomplete)
    if match_idx == 8:  # Match 9
        continue

    print(f"\nMatch {match_idx + 1}: {match['replay_name'][:40]}...")

    # Parse replay
    parser = VGRParser(match['replay_file'])
    parser.parse()

    # Get entity IDs
    hero_map, player_blocks = identify_hero_mapping(parser.frames[0])
    entity_ids = set(hero_map.keys())

    # Detect minion kills
    detector = KDADetector(entity_ids)
    for i, frame in enumerate(parser.frames):
        detector.process_frame(i, frame)

    results = detector.get_results()

    # Compare with truth
    match_errors = []
    for player, data in match['players'].items():
        truth_mk = data.get('minion_kills')
        if truth_mk is None:
            continue

        # Find entity ID for this player
        eid = None
        for e, hmap in hero_map.items():
            if hmap['player_name'] == player:
                eid = e
                break

        if eid:
            detected_mk = results[eid].minion_kills
            total_players += 1
            diff = detected_mk - truth_mk

            if diff == 0:
                total_perfect += 1
            else:
                match_errors.append({
                    'player': player,
                    'hero': data['hero_name'],
                    'truth': truth_mk,
                    'detected': detected_mk,
                    'diff': diff,
                    'match': match_idx + 1
                })
                all_errors.append(match_errors[-1])

    if match_errors:
        print(f"  Errors in this match:")
        for err in match_errors:
            print(f"    {err['player']:20s} ({err['hero']:12s}) Truth:{err['truth']:3d} Detected:{err['detected']:3d} Diff:{err['diff']:+3d}")
    else:
        print(f"  ✓ All players perfect")

print("\n" + "=" * 70)
print(f"Overall Accuracy: {total_perfect}/{total_players} ({100*total_perfect/total_players:.1f}%)")
print(f"Errors: {len(all_errors)}")

if all_errors:
    print("\nAll errors summary:")
    for err in all_errors:
        print(f"  Match {err['match']}: {err['player']:20s} ({err['hero']:12s}) Diff:{err['diff']:+3d} (Truth:{err['truth']:3d})")
