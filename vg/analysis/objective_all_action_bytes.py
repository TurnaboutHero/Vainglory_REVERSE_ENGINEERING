#!/usr/bin/env python3
"""
Compare ALL action bytes to find which one correctly indicates capturing team.

Strategy: For each action byte, check if the team with MORE credits matches
the match winner (assuming winner captured more objectives).
"""
import json
import struct
import sys
from pathlib import Path
from collections import defaultdict

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


def get_players(replay_path: str) -> dict:
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()
    players = {}
    for team_name in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team_name, []):
            eid_be = _le_to_be(p.get("entity_id", 0))
            players[eid_be] = {"name": p["name"], "team": team_name}
    return players


def scan_all_action_bytes(data: bytes, obj_death_offset: int, player_eids: set) -> dict:
    """Scan ALL action bytes within range of objective death."""
    credits_by_action = defaultdict(list)
    start = max(0, obj_death_offset - 2000)
    end = min(obj_death_offset + 2000, len(data))

    pos = start
    while pos < end:
        if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
            if data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]

                if eid in player_eids and not (value != value):
                    credits_by_action[action].append({"eid": eid, "value": round(value, 2)})
            pos += 3
        else:
            pos += 1

    return credits_by_action


def main():
    print("[OBJECTIVE] Test ALL action bytes to find capturing team indicator\n")

    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    # Track prediction accuracy by action byte
    action_predictions = defaultdict(lambda: {"correct": 0, "total": 0})

    for mi, match in enumerate(truth["matches"][:6]):
        replay = match["replay_file"]
        if "Incomplete" in replay:
            continue

        match_name = Path(replay).parent.parent.name
        truth_winner = match["match_info"].get("winner")

        print(f"M{mi+1}: {match_name} | Winner: {truth_winner}")

        players = get_players(replay)
        player_eids = set(players.keys())
        all_data = load_frames(replay)

        # Find objective deaths
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
            print("  No objectives\n")
            continue

        # Aggregate credits by action byte across ALL objectives
        match_credits_by_action = defaultdict(lambda: {"left": 0.0, "right": 0.0})

        for obj in obj_deaths:
            credits_by_action = scan_all_action_bytes(all_data, obj["offset"], player_eids)

            for action, credits in credits_by_action.items():
                for cr in credits:
                    pinfo = players.get(cr["eid"])
                    if pinfo:
                        match_credits_by_action[action][pinfo["team"]] += cr["value"]

        # Test each action byte
        print(f"  Action byte predictions:")
        for action in sorted(match_credits_by_action.keys()):
            left_total = match_credits_by_action[action]["left"]
            right_total = match_credits_by_action[action]["right"]

            if left_total > right_total * 1.2:
                predicted = "left"
            elif right_total > left_total * 1.2:
                predicted = "right"
            else:
                predicted = "tie"

            correct = predicted == truth_winner
            action_predictions[action]["total"] += 1
            if correct:
                action_predictions[action]["correct"] += 1

            status = "OK" if correct else "WRONG"
            print(f"    0x{action:02X}: left={left_total:6.0f}, right={right_total:6.0f} "
                  f"-> {predicted:5s} {status}")

        print()

    # Summary
    print(f"{'='*70}")
    print("ACTION BYTE ACCURACY SUMMARY")
    print(f"{'='*70}\n")

    print("Action bytes ranked by prediction accuracy:")
    ranked = sorted(action_predictions.items(),
                   key=lambda x: (x[1]["correct"] / max(x[1]["total"], 1), x[1]["total"]),
                   reverse=True)

    for action, stats in ranked[:10]:
        if stats["total"] >= 3:  # Only show action bytes present in 3+ matches
            accuracy = 100 * stats["correct"] / stats["total"]
            print(f"  0x{action:02X}: {stats['correct']}/{stats['total']} = {accuracy:5.1f}%")

    print(f"\n[FINDING] Action byte with highest accuracy indicates capturing team")
    print(f"[FINDING] If no action byte achieves >50%, objectives may not have")
    print(f"          a direct capture bounty mechanism in the credit records")


if __name__ == "__main__":
    main()
