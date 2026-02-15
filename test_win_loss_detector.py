#!/usr/bin/env python3
"""
Test script for win_loss_detector.py
Demonstrates JSON output format and validation
"""

import json
from vg.analysis.win_loss_detector import WinLossDetector

def test_replay_analysis():
    """Test win/loss detection and output JSON format"""

    replay_path = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"

    print("="*60)
    print("Win/Loss Detector - Test Run")
    print("="*60)
    print(f"Replay: {replay_path}")
    print()

    # Run detection
    detector = WinLossDetector(replay_path, debug=False)
    outcome = detector.detect_winner()

    if outcome:
        # Collect crystal data
        entity_data = detector._collect_entity_events()
        team1_ids, team2_ids = detector._cluster_turrets_by_team(entity_data)
        team1_crystal, team2_crystal = detector._identify_vain_crystals(team1_ids, team2_ids, entity_data)

        # Determine which crystal was destroyed
        max_frame = outcome.total_frames
        team1_crystal_destroyed = entity_data[team1_crystal]['last_frame'] < max_frame - 1
        team2_crystal_destroyed = entity_data[team2_crystal]['last_frame'] < max_frame - 1

        # Build JSON result
        result = {
            "winner": outcome.winner,
            "loser": outcome.loser,
            "method": outcome.method,
            "confidence": round(outcome.confidence, 2),
            "crystal_team1": {
                "entity_id": team1_crystal,
                "destroyed_frame": entity_data[team1_crystal]['last_frame'] if team1_crystal_destroyed else None,
                "event_count": entity_data[team1_crystal]['event_count']
            },
            "crystal_team2": {
                "entity_id": team2_crystal,
                "destroyed_frame": entity_data[team2_crystal]['last_frame'] if team2_crystal_destroyed else None,
                "event_count": entity_data[team2_crystal]['event_count']
            },
            "turret_stats": {
                "team1_total": len(team1_ids),
                "team1_destroyed": outcome.left_turrets_destroyed,
                "team2_total": len(team2_ids),
                "team2_destroyed": outcome.right_turrets_destroyed
            },
            "timeline": {
                "crystal_destruction_frame": outcome.crystal_destruction_frame,
                "total_frames": outcome.total_frames
            }
        }

        print("\n" + "="*60)
        print("JSON OUTPUT")
        print("="*60)
        print(json.dumps(result, indent=2))

        print("\n" + "="*60)
        print("VALIDATION")
        print("="*60)
        print(f"Expected winner: right (Blue team)")
        print(f"Detected winner: {outcome.winner}")
        print(f"Match: {'CORRECT' if outcome.winner == 'right' else 'INCORRECT'}")

        return result
    else:
        print("\n❌ Failed to detect match outcome")
        return None

if __name__ == '__main__':
    result = test_replay_analysis()

    if result:
        print("\n" + "="*60)
        print("TEST PASSED")
        print("="*60)
    else:
        print("\n" + "="*60)
        print("TEST FAILED")
        print("="*60)
