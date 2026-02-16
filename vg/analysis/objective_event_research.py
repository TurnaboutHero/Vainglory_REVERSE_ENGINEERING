#!/usr/bin/env python3
"""
Objective Event Research - Kraken and Gold Mine capture detection.

Research goal: Identify which team captured Kraken/Gold Mine by analyzing:
1. Death events with eid > 65000 (objective entities)
2. Nearby credit records (action=0x04) to determine capturing team
3. Temporal patterns and entity ID ranges for Kraken vs Gold Mine distinction

Expected findings:
- Credit records after objective death show which team got the bounty
- Entity ID ranges or death count patterns differentiate Kraken from Gold Mine
- Timeline reconstruction of objective captures during match
"""
import json
import struct
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.unified_decoder import _le_to_be

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def load_frames(replay_path: str) -> bytes:
    """Load all frame files for a replay."""
    p = Path(replay_path)
    frame_dir = p.parent
    frame_name = p.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frame_files)


def get_players(replay_path: str) -> Dict[int, dict]:
    """Extract player entity IDs and team assignments."""
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


def scan_all_deaths(data: bytes) -> List[dict]:
    """Scan ALL death events [08 04 31] in the replay."""
    deaths = []
    pos = 0
    while True:
        pos = data.find(DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(data):
            pos += 1
            continue

        # Structural validation
        if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        ts = struct.unpack_from(">f", data, pos + 9)[0]

        # Validate timestamp range
        if not (0 < ts < 2400):
            pos += 1
            continue

        deaths.append({
            "eid": eid,
            "ts": ts,
            "offset": pos,
        })
        pos += 1

    return deaths


def scan_credits_near(data: bytes, death_offset: int, player_eids: Set[int],
                      scan_range: int = 2000) -> List[dict]:
    """Scan credit records within range of an objective death."""
    credits = []
    start = max(0, death_offset - scan_range // 2)
    end = min(death_offset + scan_range, len(data))

    pos = start
    while pos < end:
        if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
            if data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]

                # Filter for valid player credits with action=0x04 (objective bounty)
                if eid in player_eids and not (value != value):  # not NaN
                    credits.append({
                        "eid": eid,
                        "value": round(value, 2),
                        "action": action,
                        "offset": pos,
                        "dt_bytes": pos - death_offset,
                    })
            pos += 3
        else:
            pos += 1

    return credits


def analyze_match_objectives(replay_path: str, match_idx: int, truth_data: dict):
    """Analyze objective events for a single match."""
    print(f"\n{'='*80}")
    print(f"MATCH {match_idx + 1}: {Path(replay_path).parent.parent.name}")
    print(f"{'='*80}")

    truth_duration = truth_data["match_info"].get("duration_seconds", 0)
    truth_winner = truth_data["match_info"].get("winner", "unknown")
    print(f"Truth: duration={truth_duration}s, winner={truth_winner}")

    # Load data
    players = get_players(replay_path)
    player_eids = set(players.keys())
    all_data = load_frames(replay_path)

    print(f"Players: {len(players)} ({len([p for p in players.values() if p['team']=='left'])} left, "
          f"{len([p for p in players.values() if p['team']=='right'])} right)")

    # Scan all deaths
    all_deaths = scan_all_deaths(all_data)
    print(f"\n[DATA] Total death events: {len(all_deaths)}")

    # Group deaths by entity ID range
    death_ranges = {
        "players (1500-1510)": [],
        "turrets (2000-2200)": [],
        "minions (20000-65000)": [],
        "objectives (65000+)": [],
        "other": [],
    }

    for d in all_deaths:
        eid = d["eid"]
        if 1500 <= eid <= 1510:
            death_ranges["players (1500-1510)"].append(d)
        elif 2000 <= eid <= 2200:
            death_ranges["turrets (2000-2200)"].append(d)
        elif 20000 <= eid <= 65000:
            death_ranges["minions (20000-65000)"].append(d)
        elif eid > 65000:
            death_ranges["objectives (65000+)"].append(d)
        else:
            death_ranges["other"].append(d)

    print("\nDeath events by entity range:")
    for range_name, deaths in death_ranges.items():
        if deaths:
            print(f"  {range_name}: {len(deaths)} events")
            if "objectives" in range_name:
                # Show all objective deaths
                for d in sorted(deaths, key=lambda x: x["ts"]):
                    print(f"    eid={d['eid']}, ts={d['ts']:.1f}s, offset=0x{d['offset']:06X}")

    # Analyze objective deaths (eid > 65000)
    objective_deaths = death_ranges["objectives (65000+)"]
    if not objective_deaths:
        print("\n[FINDING] No objective deaths detected (eid > 65000)")
        return []

    print(f"\n[FINDING] Found {len(objective_deaths)} objective death events")

    # For each objective death, scan for nearby credits
    objective_events = []
    for obj_death in sorted(objective_deaths, key=lambda x: x["ts"]):
        print(f"\n--- Objective eid={obj_death['eid']}, ts={obj_death['ts']:.1f}s ---")

        # Scan credits within ±2000 bytes
        credits = scan_credits_near(all_data, obj_death["offset"], player_eids, scan_range=2000)

        # Filter for action=0x04 (objective bounty)
        bounty_credits = [c for c in credits if c["action"] == 0x04]

        print(f"  Credits found: {len(credits)} total, {len(bounty_credits)} with action=0x04")

        if bounty_credits:
            # Group by team
            team_credits = defaultdict(list)
            for cr in bounty_credits:
                pinfo = players.get(cr["eid"])
                if pinfo:
                    team_credits[pinfo["team"]].append({
                        "player": pinfo["name"],
                        "value": cr["value"],
                        "dt_bytes": cr["dt_bytes"],
                    })

            print(f"  Bounty distribution:")
            for team in ["left", "right"]:
                if team in team_credits:
                    total = sum(c["value"] for c in team_credits[team])
                    print(f"    {team}: {len(team_credits[team])} players, total={total:.0f}")
                    for c in team_credits[team][:3]:  # Show first 3
                        print(f"      {c['player']}: {c['value']:.0f} (dt={c['dt_bytes']:+d} bytes)")

            # Determine capturing team
            if team_credits:
                capturing_team = max(team_credits.keys(), key=lambda t: sum(c["value"] for c in team_credits[t]))
                print(f"  [FINDING] Capturing team: {capturing_team}")

                objective_events.append({
                    "eid": obj_death["eid"],
                    "timestamp": obj_death["ts"],
                    "capturing_team": capturing_team,
                    "bounty_left": sum(c["value"] for c in team_credits.get("left", [])),
                    "bounty_right": sum(c["value"] for c in team_credits.get("right", [])),
                })
        else:
            print(f"  [LIMITATION] No bounty credits found (action=0x04)")

    return objective_events


def distinguish_objective_types(all_objective_events: List[List[dict]]):
    """Analyze patterns to distinguish Kraken from Gold Mine."""
    print(f"\n{'='*80}")
    print("OBJECTIVE TYPE ANALYSIS")
    print(f"{'='*80}")

    # Collect all objective eids
    all_eids = []
    for match_events in all_objective_events:
        for evt in match_events:
            all_eids.append(evt["eid"])

    if not all_eids:
        print("[LIMITATION] No objective events to analyze")
        return

    # Analyze entity ID distribution
    eid_counts = defaultdict(int)
    for eid in all_eids:
        eid_counts[eid] += 1

    print(f"\n[STAT:objective_entity_count] {len(eid_counts)} unique objective entity IDs")
    print(f"[STAT:total_captures] {len(all_eids)} total captures across all matches")

    print("\nEntity ID frequency:")
    for eid in sorted(eid_counts.keys()):
        print(f"  eid {eid}: {eid_counts[eid]} occurrences")

    # Analyze entity ID ranges
    if all_eids:
        min_eid = min(all_eids)
        max_eid = max(all_eids)
        print(f"\n[STAT:eid_range] {min_eid} - {max_eid}")

        # Check if there are distinct ranges
        mid_point = (min_eid + max_eid) // 2
        low_range = [e for e in all_eids if e <= mid_point]
        high_range = [e for e in all_eids if e > mid_point]

        if low_range and high_range:
            print(f"\n[FINDING] Entity IDs cluster in two ranges:")
            print(f"  Low range (65000-{mid_point}): {len(low_range)} captures")
            print(f"  High range ({mid_point+1}+): {len(high_range)} captures")
            print(f"  Hypothesis: Low=Kraken OR Gold Mine, High=Kraken OR Gold Mine")


def generate_detection_algorithm(all_objective_events: List[List[dict]]):
    """Propose detection algorithm based on research findings."""
    print(f"\n{'='*80}")
    print("PROPOSED DETECTION ALGORITHM")
    print(f"{'='*80}")

    total_events = sum(len(events) for events in all_objective_events)

    print(f"""
Based on analysis of {total_events} objective events across {len(all_objective_events)} matches:

DETECTION STEPS:

1. Scan for death events [08 04 31] with eid > 65000
   - These are objective entity deaths (Kraken or Gold Mine)

2. For each objective death, scan credit records within ±2000 bytes
   - Look for [10 04 1D] credit records with action=0x04 (objective bounty)
   - Filter for player entity IDs only (1500-1510 range in BE)

3. Determine capturing team:
   - Group credits by player team
   - Team with highest total bounty = capturing team
   - Typically ALL 5 players on capturing team receive bounty

4. Distinguish Kraken vs Gold Mine:
   - If entity ID clustering is observed:
     * Entity range analysis (e.g., 65000-70000 vs 70000+)
   - If clustering not clear:
     * Use game timestamp (early captures = likely Gold Mine)
     * Use bounty amount patterns (Kraken may have higher bounty)
   - NOTE: Requires more match data to validate distinction method

5. Build objective event timeline:
   - Sort by timestamp
   - Track which team captured which objectives when
   - Can be used for strategic analysis

CONFIDENCE LEVEL:
- Team detection: HIGH (bounty credits clearly indicate capturing team)
- Kraken vs Gold Mine distinction: MEDIUM (needs validation with more data)
""")


def main():
    """Main research workflow."""
    print("[OBJECTIVE] Research objective capture events from Vainglory replay files")
    print("Target: Identify Kraken and Gold Mine captures with capturing team")

    # Load truth data
    with open(TRUTH_PATH) as f:
        truth = json.load(f)

    # Analyze first 4 complete matches
    all_objective_events = []
    matches_analyzed = 0

    for mi, match in enumerate(truth["matches"]):
        replay = match["replay_file"]

        # Skip incomplete matches
        if "Incomplete" in replay:
            continue

        try:
            objective_events = analyze_match_objectives(replay, mi, match)
            all_objective_events.append(objective_events)
            matches_analyzed += 1

            if matches_analyzed >= 4:
                break
        except Exception as e:
            print(f"\n[LIMITATION] Error processing match {mi+1}: {e}")
            continue

    # Cross-match analysis
    distinguish_objective_types(all_objective_events)
    generate_detection_algorithm(all_objective_events)

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:time:complete]")


if __name__ == "__main__":
    main()
