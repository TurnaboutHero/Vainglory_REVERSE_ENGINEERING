#!/usr/bin/env python3
"""
Deep dive into objective bounty mechanics.

Finding: action=0x04 is rare for objectives. Need to investigate:
1. What action bytes appear near objective deaths?
2. Clustered death pattern analysis (1-6 entities dying together)
3. Alternative bounty detection methods
"""
import json
import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Set, Dict

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
            players[eid_be] = {
                "name": p["name"],
                "team": team_name,
            }
    return players


def find_clustered_deaths(data: bytes, time_window: float = 2.0) -> List[List[dict]]:
    """Find deaths that occur in clusters (within time_window seconds)."""
    all_deaths = []
    pos = 0
    while True:
        pos = data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(data):
            pos += 1
            continue

        if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        ts = struct.unpack_from(">f", data, pos + 9)[0]

        if 0 < ts < 2400:
            all_deaths.append({
                "eid": eid,
                "ts": ts,
                "offset": pos,
            })
        pos += 1

    # Sort by timestamp
    all_deaths.sort(key=lambda d: d["ts"])

    # Cluster deaths within time_window
    clusters = []
    current_cluster = []

    for death in all_deaths:
        if not current_cluster:
            current_cluster.append(death)
        else:
            dt = death["ts"] - current_cluster[-1]["ts"]
            if dt <= time_window:
                current_cluster.append(death)
            else:
                if len(current_cluster) >= 1:
                    clusters.append(current_cluster)
                current_cluster = [death]

    if current_cluster:
        clusters.append(current_cluster)

    return clusters


def analyze_credits_all_actions(data: bytes, death_offset: int, player_eids: set,
                                scan_range: int = 3000) -> dict:
    """Scan ALL credit records (any action byte) near objective death."""
    credits_by_action = defaultdict(list)
    start = max(0, death_offset - scan_range // 2)
    end = min(death_offset + scan_range, len(data))

    pos = start
    while pos < end:
        if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
            if data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]

                if eid in player_eids and not (value != value):
                    credits_by_action[action].append({
                        "eid": eid,
                        "value": round(value, 2),
                        "dt_bytes": pos - death_offset,
                    })
            pos += 3
        else:
            pos += 1

    return credits_by_action


def main():
    print("[OBJECTIVE] Deep dive into objective bounty mechanics")
    print("[FINDING] Previous research: action=0x04 credits are RARE for objectives\n")

    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    # Analyze first match in detail
    match = truth["matches"][0]
    replay = match["replay_file"]

    print(f"Analyzing: {Path(replay).parent.parent.name}")
    print(f"Duration: {match['match_info']['duration_seconds']}s\n")

    players = get_players(replay)
    player_eids = set(players.keys())
    all_data = load_frames(replay)

    # Find clustered deaths (objective kills typically involve 1-6 entities)
    clusters = find_clustered_deaths(all_data, time_window=2.0)

    # Filter for clusters with eid > 65000
    objective_clusters = []
    for cluster in clusters:
        has_objective = any(d["eid"] > 65000 for d in cluster)
        if has_objective:
            objective_clusters.append(cluster)

    print(f"[DATA] Found {len(objective_clusters)} death clusters with eid > 65000")

    # Analyze each objective cluster
    all_action_stats = Counter()

    for ci, cluster in enumerate(objective_clusters[:5]):  # First 5 clusters
        print(f"\n{'='*70}")
        print(f"CLUSTER {ci+1}: {len(cluster)} deaths, ts={cluster[0]['ts']:.1f}s")
        print(f"{'='*70}")

        for death in cluster:
            print(f"  eid={death['eid']}, ts={death['ts']:.1f}s")

        # Pick the first objective death in cluster
        obj_death = next((d for d in cluster if d["eid"] > 65000), None)
        if not obj_death:
            continue

        # Scan ALL action bytes
        credits_by_action = analyze_credits_all_actions(
            all_data, obj_death["offset"], player_eids, scan_range=5000
        )

        print(f"\nCredit records by action byte (within ±5000 bytes):")
        for action in sorted(credits_by_action.keys()):
            credits = credits_by_action[action]
            total_value = sum(c["value"] for c in credits)
            all_action_stats[action] += len(credits)
            print(f"  0x{action:02X}: {len(credits)} records, total_value={total_value:.0f}")

        # Show team distribution for EACH action byte
        print(f"\nTeam distribution by action byte:")
        for action in sorted(credits_by_action.keys()):
            credits = credits_by_action[action]
            team_totals = defaultdict(float)
            for cr in credits:
                pinfo = players.get(cr["eid"])
                if pinfo:
                    team_totals[pinfo["team"]] += cr["value"]

            if team_totals:
                print(f"  0x{action:02X}: left={team_totals.get('left', 0):.0f}, "
                      f"right={team_totals.get('right', 0):.0f}")

    print(f"\n{'='*70}")
    print("ACTION BYTE FREQUENCY SUMMARY")
    print(f"{'='*70}")
    print("\nMost common action bytes near objective deaths:")
    for action, count in all_action_stats.most_common(10):
        print(f"  0x{action:02X}: {count} records")

    print(f"\n[FINDING] Action byte distribution analysis complete")
    print(f"[FINDING] If 0x06 dominates, objectives may use regular gold income mechanism")
    print(f"[FINDING] If other byte appears consistently, that's the objective bounty marker")


if __name__ == "__main__":
    main()
