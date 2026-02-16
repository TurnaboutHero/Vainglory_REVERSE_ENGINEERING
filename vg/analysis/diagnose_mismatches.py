#!/usr/bin/env python3
"""
Diagnose specific K/D/A mismatches between detected and truth values.
Examines timestamps, credit records, and event details for each error case.
"""
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.kda_detector import KDADetector, KILL_HEADER, DEATH_HEADER, CREDIT_HEADER
from vg.core.unified_decoder import _le_to_be

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

# Known mismatches to investigate
MISMATCHES = {
    # (match_idx 0-based, player_name, field, detected, truth)
    "kill_fps": [
        (4, "2600_IcyBang", "kill", 1, 0),
        (5, "2600_staplers", "kill", 7, 6),
    ],
    "death_fps": [
        (1, "2599_FengLin", "death", 3, 2),
        (5, "2599_123", "death", 5, 4),
    ],
    "death_fns": [
        (9, "3000_Synd", "death", 2, 3),
        (9, "2999_DrPawn", "death", 3, 4),
    ],
    "assist_fps": [
        (0, "2604_Ray", "assist", 2, 0),
        (2, "3004_TenshiiHime", "assist", 9, 8),
        (3, "3004_TenshiiHime", "assist", 11, 7),
        (4, "2600_Acex", "assist", 1, 0),
        (5, "2600_Acex", "assist", 12, 11),
        (5, "2600_TenshiiHime", "assist", 10, 6),
    ],
}


def load_truth():
    with open(TRUTH_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_replay_path(truth_match):
    return truth_match["replay_file"]


def load_all_frames(replay_path):
    """Load all frame data concatenated."""
    p = Path(replay_path)
    frame_dir = p.parent
    frame_name = p.stem.rsplit('.', 1)[0]

    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    frames = []
    for f in frame_files:
        idx = int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
        frames.append((idx, f.read_bytes()))
    return frames


def get_player_eids(replay_path):
    """Get player name -> (eid_le, eid_be) mapping."""
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()

    result = {}
    for team_name in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team_name, []):
            eid_le = p.get("entity_id", 0)
            eid_be = _le_to_be(eid_le)
            result[p["name"]] = {
                "eid_le": eid_le,
                "eid_be": eid_be,
                "team": team_name,
                "hero": p.get("hero_name", "?"),
            }
    return result


def diagnose_kills(truth_data):
    """Analyze false positive kills - check timestamps relative to game duration."""
    print("\n" + "=" * 70)
    print("KILL FALSE POSITIVES ANALYSIS")
    print("=" * 70)

    for mi, pname, _, detected, truth in MISMATCHES["kill_fps"]:
        match = truth_data["matches"][mi]
        replay_path = get_replay_path(match)
        duration = match["match_info"]["duration_seconds"]

        print(f"\n--- M{mi+1} {pname} (detected={detected}, truth={truth}, duration={duration}s) ---")

        players = get_player_eids(replay_path)
        if pname not in players:
            # Try fuzzy match
            for k in players:
                if k.lower() == pname.lower() or (len(k) > 5 and sum(a!=b for a,b in zip(k,pname)) <= 2):
                    pname = k
                    break

        pinfo = players.get(pname)
        if not pinfo:
            print(f"  Player not found: {pname}")
            continue

        eid_be = pinfo["eid_be"]
        print(f"  Player: {pname} ({pinfo['hero']}), EID_BE=0x{eid_be:04X}, team={pinfo['team']}")

        # Scan all frames for kill events for this player
        frames = load_all_frames(replay_path)
        all_eids = set(p["eid_be"] for p in players.values())

        detector = KDADetector(all_eids)
        for fidx, fdata in frames:
            detector.process_frame(fidx, fdata)

        kill_events = [k for k in detector.kill_events if k.killer_eid == eid_be]
        print(f"  Total kill events: {len(kill_events)}")

        for i, kev in enumerate(kill_events):
            ts_str = f"{kev.timestamp:.1f}s" if kev.timestamp else "no_ts"
            near_end = ""
            if kev.timestamp and kev.timestamp > duration:
                near_end = " ** POST-GAME **"
            elif kev.timestamp and kev.timestamp > duration - 10:
                near_end = " (near game end)"

            # Check credit records for victim info
            victim_info = ""
            for cr in kev.credits:
                if cr.eid != eid_be and cr.eid in all_eids:
                    p_team = [n for n, p in players.items() if p["eid_be"] == cr.eid]
                    victim_info += f" credit: eid=0x{cr.eid:04X}({p_team[0] if p_team else '?'}) val={cr.value}"

            print(f"  Kill #{i+1}: ts={ts_str}, frame={kev.frame_idx}{near_end}{victim_info}")


def diagnose_deaths(truth_data):
    """Analyze death mismatches - check timestamps."""
    print("\n" + "=" * 70)
    print("DEATH MISMATCHES ANALYSIS")
    print("=" * 70)

    all_cases = MISMATCHES["death_fps"] + MISMATCHES["death_fns"]

    for mi, pname, _, detected, truth in all_cases:
        match = truth_data["matches"][mi]
        replay_path = get_replay_path(match)
        duration = match["match_info"]["duration_seconds"]
        diff = detected - truth
        label = "FALSE POSITIVE" if diff > 0 else "MISSED"

        print(f"\n--- M{mi+1} {pname} ({label}, detected={detected}, truth={truth}, duration={duration}s) ---")

        players = get_player_eids(replay_path)
        # Fuzzy match
        for k in players:
            if k.lower() == pname.lower() or (len(k) > 5 and sum(a!=b for a,b in zip(k,pname)) <= 2):
                pname = k
                break

        pinfo = players.get(pname)
        if not pinfo:
            print(f"  Player not found: {pname}")
            continue

        eid_be = pinfo["eid_be"]
        print(f"  Player: {pname} ({pinfo['hero']}), EID_BE=0x{eid_be:04X}, team={pinfo['team']}")

        # Scan for deaths
        frames = load_all_frames(replay_path)
        all_eids = set(p["eid_be"] for p in players.values())

        detector = KDADetector(all_eids)
        for fidx, fdata in frames:
            detector.process_frame(fidx, fdata)

        death_events = [d for d in detector.death_events if d.victim_eid == eid_be]
        death_events.sort(key=lambda d: d.timestamp)

        print(f"  Total death events (unfiltered): {len(death_events)}")

        # Check which deaths pass/fail the duration+10s filter
        max_ts = duration + 10.0
        for i, dev in enumerate(death_events):
            filtered = " ** FILTERED (post-game) **" if dev.timestamp > max_ts else ""
            near_end = " (near game end)" if dev.timestamp > duration - 10 and not filtered else ""
            print(f"  Death #{i+1}: ts={dev.timestamp:.1f}s, frame={dev.frame_idx}{near_end}{filtered}")

        # For missed deaths, also scan raw binary for any death patterns we might be missing
        if diff < 0:
            print(f"\n  Scanning raw data for ALL death headers with this EID...")
            all_data = b"".join(d for _, d in frames)
            eid_bytes = struct.pack(">H", eid_be)

            raw_deaths = []
            pos = 0
            while True:
                pos = all_data.find(DEATH_HEADER, pos)
                if pos == -1:
                    break
                if pos + 13 <= len(all_data):
                    # Check structural bytes loosely
                    eid = struct.unpack_from(">H", all_data, pos + 5)[0]
                    if eid == eid_be:
                        ts = struct.unpack_from(">f", all_data, pos + 9)[0]
                        valid_struct = (all_data[pos+3:pos+5] == b'\x00\x00' and
                                       all_data[pos+7:pos+9] == b'\x00\x00')
                        raw_deaths.append((pos, ts, valid_struct))
                pos += 1

            print(f"  Raw death headers for this EID: {len(raw_deaths)}")
            for off, ts, valid in raw_deaths:
                v_str = "VALID" if valid else "INVALID_STRUCT"
                ts_valid = "OK" if 0 < ts < 1800 else "BAD_TS"
                print(f"    offset=0x{off:06X}, ts={ts:.1f}s, struct={v_str}, ts_range={ts_valid}")


def diagnose_assists(truth_data):
    """Analyze assist over-detection - examine credit records for each kill."""
    print("\n" + "=" * 70)
    print("ASSIST OVER-DETECTION ANALYSIS")
    print("=" * 70)

    for mi, pname, _, detected, truth in MISMATCHES["assist_fps"]:
        match = truth_data["matches"][mi]
        replay_path = get_replay_path(match)
        duration = match["match_info"]["duration_seconds"]
        diff = detected - truth

        print(f"\n--- M{mi+1} {pname} (detected={detected}, truth={truth}, diff=+{diff}, duration={duration}s) ---")

        players = get_player_eids(replay_path)
        # Fuzzy match
        orig_pname = pname
        for k in players:
            if k.lower() == pname.lower() or (len(k) > 5 and sum(a!=b for a,b in zip(k,pname)) <= 2):
                pname = k
                break

        pinfo = players.get(pname)
        if not pinfo:
            print(f"  Player not found: {orig_pname}")
            continue

        eid_be = pinfo["eid_be"]
        player_team = pinfo["team"]
        print(f"  Player: {pname} ({pinfo['hero']}), EID_BE=0x{eid_be:04X}, team={player_team}")

        # Run full KDA to get assist details
        frames = load_all_frames(replay_path)
        all_eids = set(p["eid_be"] for p in players.values())
        team_map = {p["eid_be"]: p["team"] for p in players.values()}
        eid_to_name = {p["eid_be"]: n for n, p in players.items()}
        eid_to_hero = {p["eid_be"]: p["hero"] for p in players.values()}

        detector = KDADetector(all_eids)
        for fidx, fdata in frames:
            detector.process_frame(fidx, fdata)

        # Find all kills where this player got an assist
        assist_kills = []
        for kev in detector.kill_events:
            killer_team = team_map.get(kev.killer_eid)
            if killer_team != player_team:
                continue
            if kev.killer_eid == eid_be:
                continue

            # Check if this player has a 1.0 credit
            credits_by_eid = defaultdict(list)
            for cr in kev.credits:
                credits_by_eid[cr.eid].append(cr.value)

            if eid_be in credits_by_eid:
                values = credits_by_eid[eid_be]
                has_1_0 = any(abs(v - 1.0) < 0.01 for v in values)
                if has_1_0:
                    assist_kills.append((kev, values))

        print(f"  Assists counted: {len(assist_kills)}")

        # Show details of each assist
        for i, (kev, values) in enumerate(assist_kills):
            killer_name = eid_to_name.get(kev.killer_eid, f"0x{kev.killer_eid:04X}")
            killer_hero = eid_to_hero.get(kev.killer_eid, "?")
            ts_str = f"{kev.timestamp:.1f}s" if kev.timestamp else "no_ts"
            post_game = " ** POST-GAME **" if kev.timestamp and kev.timestamp > duration else ""

            # Show all credit records for context
            all_creds = []
            for cr in kev.credits:
                cr_name = eid_to_name.get(cr.eid, f"0x{cr.eid:04X}")
                cr_hero = eid_to_hero.get(cr.eid, "?")
                all_creds.append(f"{cr_name}({cr_hero})={cr.value}")

            print(f"  Assist #{i+1}: kill by {killer_name}({killer_hero}) at ts={ts_str}{post_game}")
            print(f"    This player's credits: {values}")
            print(f"    All credits: {', '.join(all_creds)}")


if __name__ == "__main__":
    truth = load_truth()
    diagnose_kills(truth)
    diagnose_deaths(truth)
    diagnose_assists(truth)
