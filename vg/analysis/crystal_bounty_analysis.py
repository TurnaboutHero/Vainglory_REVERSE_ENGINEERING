#!/usr/bin/env python3
"""
Analyze crystal death bounty: which players receive gold when a crystal is destroyed?
This determines the winning team WITHOUT relying on kill count.
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


def load_frames(replay_path):
    p = Path(replay_path)
    frame_dir = p.parent
    frame_name = p.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frame_files)


def get_players(replay_path):
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()
    players = {}
    for team_name in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team_name, []):
            eid_be = _le_to_be(p.get("entity_id", 0))
            players[eid_be] = {
                "name": p["name"],
                "team": team_name,
                "team_byte": 1 if team_name == "left" else 2,  # from parser
            }
    return players


def find_crystal_death_and_bounty(all_data, player_eids):
    """Find crystal death events and scan credits nearby."""
    crystal_events = []

    pos = 0
    while True:
        pos = all_data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if (all_data[pos+3:pos+5] != b'\x00\x00' or
                all_data[pos+7:pos+9] != b'\x00\x00'):
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        ts = struct.unpack_from(">f", all_data, pos + 9)[0]

        if 2000 <= eid <= 2005 and 60 < ts < 2400:
            # Scan credit records within 1000 bytes after crystal death
            credits = scan_credits_near(all_data, pos, player_eids)
            crystal_events.append({
                "eid": eid,
                "ts": ts,
                "offset": pos,
                "credits": credits,
            })
        pos += 1

    return crystal_events


def scan_credits_near(data, death_offset, player_eids):
    """Scan credit records within 1000 bytes of crystal death."""
    credits = []
    start = death_offset
    end = min(death_offset + 1000, len(data))

    pos = start
    while pos < end:
        if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
            if data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]
                if eid in player_eids and not (value != value):  # not NaN
                    credits.append({
                        "eid": eid,
                        "value": round(value, 2),
                        "action": action,
                        "offset": pos,
                    })
            pos += 3
        else:
            pos += 1

    return credits


def main():
    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    print("Crystal Death Bounty Analysis")
    print("=" * 70)

    for mi, match in enumerate(truth["matches"]):
        replay = match["replay_file"]
        truth_winner = match["match_info"].get("winner")
        truth_duration = match["match_info"].get("duration_seconds")
        is_incomplete = "Incomplete" in replay

        if is_incomplete:
            continue

        print(f"\n--- M{mi+1} (truth_winner={truth_winner}, duration={truth_duration}s) ---")

        players = get_players(replay)
        player_eids = set(players.keys())
        all_data = load_frames(replay)

        crystal_events = find_crystal_death_and_bounty(all_data, player_eids)

        if not crystal_events:
            print("  No crystal death found!")
            continue

        # Use latest crystal death (closest to game end)
        crystal_events.sort(key=lambda x: x["ts"], reverse=True)

        for ce in crystal_events[:3]:  # Show top 3
            print(f"  Crystal eid={ce['eid']}, ts={ce['ts']:.1f}s, offset=0x{ce['offset']:06X}")

            # Group credits by player team
            team_credits = defaultdict(float)
            team_players = defaultdict(set)

            for cr in ce["credits"]:
                pinfo = players.get(cr["eid"])
                if pinfo:
                    team = pinfo["team"]
                    team_credits[team] += cr["value"]
                    team_players[team].add(pinfo["name"])
                    # Only show first few
                    if len(ce["credits"]) <= 20:
                        print(f"    credit: {pinfo['name']} ({team}) val={cr['value']} action=0x{cr['action']:02X}")

            for team in ["left", "right"]:
                total = team_credits.get(team, 0)
                n_players = len(team_players.get(team, set()))
                print(f"    {team}: {n_players} players, total_credit={total:.1f}")

            # Determine winner from crystal bounty
            if team_credits:
                bounty_winner = max(team_credits, key=team_credits.get)
                correct = "OK" if bounty_winner == truth_winner else "WRONG"
                print(f"    Crystal bounty winner: {bounty_winner} ({correct})")


if __name__ == "__main__":
    main()
