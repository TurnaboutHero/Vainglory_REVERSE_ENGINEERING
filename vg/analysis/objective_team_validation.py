#!/usr/bin/env python3
"""
Validate objective team detection against match outcomes.

Hypothesis: Action 0x03 may have inverted team logic or require
validation against actual match winner to determine correct assignment.

Strategy: Compare objective captures to match winner - winning team
should typically have more objective captures (or at minimum, equal).
"""
import json
import struct
import sys
from pathlib import Path
from collections import defaultdict
from typing import List, Dict, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.unified_decoder import _le_to_be

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def load_frames(replay_path: str) -> bytes:
    p = Path(replay_path)
    frame_dir = p.parent
    frame_name = p.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frame_files)


def get_players(replay_path: str) -> Dict[int, dict]:
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()
    players = {}
    for team_name in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team_name, []):
            eid_be = _le_to_be(p.get("entity_id", 0))
            players[eid_be] = {
                "name": p["name"],
                "team": team_name,
            }
    return players


def analyze_action_0x03_pattern(data: bytes, obj_death_offset: int,
                                player_eids: Set[int]) -> Dict[str, List[dict]]:
    """Scan action=0x03 credits near objective death."""
    credits = []
    start = max(0, obj_death_offset - 1500)
    end = min(obj_death_offset + 1500, len(data))

    pos = start
    while pos < end:
        if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
            if data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]

                if eid in player_eids and action == 0x03 and not (value != value):
                    credits.append({
                        "eid": eid,
                        "value": round(value, 2),
                        "dt_bytes": pos - obj_death_offset,
                    })
            pos += 3
        else:
            pos += 1

    return credits


def main():
    print("[OBJECTIVE] Validate action=0x03 team assignment against match winners\n")

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
        print(f"M{mi+1}: {match_name} | Winner: {truth_winner}")
        print(f"{'='*70}")

        players = get_players(replay)
        player_eids = set(players.keys())
        all_data = load_frames(replay)

        # Find objective deaths (eid > 65000)
        obj_deaths = []
        pos = 0
        while True:
            pos = all_data.find(DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(all_data):
                pos += 1
                continue
            if all_data[pos+3:pos+5] != b'\x00\x00' or all_data[pos+7:pos+9] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", all_data, pos + 5)[0]
            ts = struct.unpack_from(">f", all_data, pos + 9)[0]

            if eid > 65000 and 0 < ts < 2400:
                obj_deaths.append({"eid": eid, "ts": ts, "offset": pos})
            pos += 1

        if not obj_deaths:
            print("  No objective deaths found\n")
            continue

        print(f"  Found {len(obj_deaths)} objective deaths\n")

        # Analyze action=0x03 pattern for each
        team_0x03_totals = {"left": 0.0, "right": 0.0}
        all_0x03_credits = []

        for obj in obj_deaths:
            credits = analyze_action_0x03_pattern(all_data, obj["offset"], player_eids)

            if not credits:
                continue

            print(f"  Objective eid={obj['eid']}, ts={obj['ts']:.1f}s:")

            team_totals = {"left": 0.0, "right": 0.0}
            for cr in credits:
                pinfo = players.get(cr["eid"])
                if pinfo:
                    team_totals[pinfo["team"]] += cr["value"]
                    all_0x03_credits.append((pinfo["team"], cr["value"]))

            print(f"    Action 0x03: left={team_totals['left']:.0f}, right={team_totals['right']:.0f}")

            # Determine which team has HIGHER 0x03 credits
            if team_totals["left"] > team_totals["right"] * 1.5:
                detected_team = "left"
            elif team_totals["right"] > team_totals["left"] * 1.5:
                detected_team = "right"
            else:
                detected_team = "unclear"

            team_0x03_totals["left"] += team_totals["left"]
            team_0x03_totals["right"] += team_totals["right"]

            if detected_team != "unclear":
                print(f"    -> Detected capture: {detected_team}")

        # Match-level summary
        print(f"\n  Match total 0x03 credits: left={team_0x03_totals['left']:.0f}, "
              f"right={team_0x03_totals['right']:.0f}")

        if team_0x03_totals["left"] > team_0x03_totals["right"]:
            predicted_winner_0x03 = "left"
        elif team_0x03_totals["right"] > team_0x03_totals["left"]:
            predicted_winner_0x03 = "right"
        else:
            predicted_winner_0x03 = "tie"

        match_correct = predicted_winner_0x03 == truth_winner
        print(f"  0x03 predicted winner: {predicted_winner_0x03}")
        print(f"  Truth winner: {truth_winner}")
        print(f"  Match: {'CORRECT' if match_correct else 'WRONG'}")

        validation_results.append({
            "match": mi+1,
            "truth_winner": truth_winner,
            "predicted": predicted_winner_0x03,
            "correct": match_correct,
        })

        print()

    # Summary
    print(f"{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}\n")

    correct_count = sum(1 for r in validation_results if r["correct"])
    total_count = len(validation_results)

    print(f"[STAT:accuracy] {correct_count}/{total_count} = {100*correct_count/total_count:.1f}%")

    print(f"\nResults by match:")
    for r in validation_results:
        status = "OK" if r["correct"] else "WRONG"
        print(f"  M{r['match']}: truth={r['truth_winner']}, predicted={r['predicted']} {status}")

    if correct_count < total_count:
        print(f"\n[FINDING] Action 0x03 credits do NOT directly indicate capturing team")
        print(f"[FINDING] May indicate DEFENDING team or have inverted logic")
        print(f"[LIMITATION] Alternative detection method needed")
    else:
        print(f"\n[FINDING] Action 0x03 credits CORRECTLY indicate capturing team")
        print(f"[FINDING] Higher 0x03 total = more objectives captured = match winner")


if __name__ == "__main__":
    main()
