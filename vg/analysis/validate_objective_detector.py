#!/usr/bin/env python3
"""
Validate ObjectiveDetector module against tournament matches.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.objective_detector import ObjectiveDetector
from vg.core.unified_decoder import _le_to_be

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"


def load_frames(replay_path: str) -> bytes:
    p = Path(replay_path)
    frame_dir = p.parent
    frame_name = p.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frame_files)


def get_players_and_team_map(replay_path: str):
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()
    players = {}
    team_map = {}
    for team_name in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team_name, []):
            eid_be = _le_to_be(p.get("entity_id", 0))
            players[eid_be] = {"name": p["name"], "team": team_name}
            team_map[eid_be] = team_name
    return players, team_map


def main():
    print("[OBJECTIVE] Validate ObjectiveDetector production module\n")

    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    validation_results = []

    for mi, match in enumerate(truth["matches"][:6]):
        replay = match["replay_file"]
        if "Incomplete" in replay:
            continue

        match_name = Path(replay).parent.parent.name
        truth_winner = match["match_info"].get("winner")
        truth_duration = match["match_info"].get("duration_seconds")

        print(f"{'='*70}")
        print(f"M{mi+1}: {match_name}")
        print(f"Truth: winner={truth_winner}, duration={truth_duration}s")
        print(f"{'='*70}")

        # Setup
        players, team_map = get_players_and_team_map(replay)
        player_eids = set(players.keys())
        all_data = load_frames(replay)

        # Initialize detector
        detector = ObjectiveDetector(valid_entity_ids=player_eids)

        # Process all frames (simplified: just pass entire data as one frame)
        detector.process_frame(frame_idx=0, data=all_data)

        # Get summary
        summary = detector.get_summary()
        print(f"\nDetection summary:")
        print(f"  Objective deaths: {summary['objective_deaths_detected']}")
        if summary['objective_deaths_detected'] > 0:
            print(f"  Entity ID range: {summary['entity_id_range'][0]}-{summary['entity_id_range'][1]}")
            print(f"  Timestamp range: {summary['timestamp_range'][0]:.1f}s - {summary['timestamp_range'][1]:.1f}s")

        # Get captures with team identification
        captures = detector.get_captures(
            team_map=team_map,
            all_frame_data=all_data,
            confidence_threshold=0.5  # Only confident captures
        )

        print(f"\nCaptured objectives (confidence >= 0.5):")
        if not captures:
            print("  None detected")
        else:
            for i, cap in enumerate(captures, 1):
                print(f"  {i}. eid={cap.entity_id}, ts={cap.timestamp:.1f}s, "
                      f"team={cap.capturing_team}, confidence={cap.confidence:.0%}")
                print(f"     bounty: left={cap.bounty_left:.0f}, right={cap.bounty_right:.0f}")

        # Aggregate captures by team
        captures_by_team = {"left": 0, "right": 0, "unclear": 0}
        for cap in captures:
            if cap.capturing_team:
                captures_by_team[cap.capturing_team] += 1
            else:
                captures_by_team["unclear"] += 1

        print(f"\nCaptures by team: left={captures_by_team['left']}, "
              f"right={captures_by_team['right']}, unclear={captures_by_team['unclear']}")

        # Predict winner from objective captures
        if captures_by_team["left"] > captures_by_team["right"]:
            predicted_winner = "left"
        elif captures_by_team["right"] > captures_by_team["left"]:
            predicted_winner = "right"
        else:
            predicted_winner = "tie"

        match_correct = predicted_winner == truth_winner
        print(f"Predicted winner: {predicted_winner}")
        print(f"Match: {'CORRECT' if match_correct else 'WRONG'}")

        validation_results.append({
            "match": mi + 1,
            "truth_winner": truth_winner,
            "predicted": predicted_winner,
            "correct": match_correct,
            "captures": len(captures),
        })

        print()

    # Summary
    print(f"{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}\n")

    correct_count = sum(1 for r in validation_results if r["correct"])
    total_count = len([r for r in validation_results if r["predicted"] != "tie"])
    total_captures = sum(r["captures"] for r in validation_results)

    print(f"[STAT:accuracy] {correct_count}/{total_count} matches predicted correctly")
    print(f"[STAT:total_captures] {total_captures} objective captures detected")

    print(f"\nResults by match:")
    for r in validation_results:
        status = "OK" if r["correct"] else "WRONG"
        print(f"  M{r['match']}: truth={r['truth_winner']}, predicted={r['predicted']}, "
              f"captures={r['captures']} - {status}")

    if correct_count >= total_count * 0.7:
        print(f"\n[FINDING] ObjectiveDetector achieves {100*correct_count/total_count:.0f}% accuracy")
        print(f"[FINDING] Production-ready for deployment with confidence scores")
    else:
        print(f"\n[LIMITATION] Accuracy {100*correct_count/total_count:.0f}% below 70% threshold")
        print(f"[LIMITATION] Further refinement needed before production use")


if __name__ == "__main__":
    main()
