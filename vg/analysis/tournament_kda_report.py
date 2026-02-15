"""
Tournament KDA Report - Full KDA extraction using KDADetector module
=====================================================================
Processes all tournament replays, extracts kill/death counts,
matches kill-death pairs, and compares with truth data.
"""
import os
import struct
import json
from sys import path as sys_path
sys_path.insert(0, "D:/Documents/GitHub/VG_REVERSE_ENGINEERING")

from vg.core.kda_detector import KDADetector
from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

TRUTH_PATH = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json"
with open(TRUTH_PATH, "r") as f:
    truth_data = json.load(f)


def find_player_entities(frame0_data):
    players = []
    for marker_bytes in [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]:
        pos = 0
        while True:
            pos = frame0_data.find(marker_bytes, pos)
            if pos == -1:
                break
            if pos + 0xD6 <= len(frame0_data):
                eid_le = struct.unpack_from("<H", frame0_data, pos + 0xA5)[0]
                eid_be = ((eid_le & 0xFF) << 8) | ((eid_le >> 8) & 0xFF)
                hero_id = struct.unpack_from("<H", frame0_data, pos + 0xA9)[0]
                team = frame0_data[pos + 0xD5]
                team_str = "left" if team == 1 else "right" if team == 2 else f"unk_{team}"
                hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"Hero_{hero_id}")
                players.append({
                    "eid_le": eid_le, "eid_be": eid_be,
                    "hero_id": hero_id, "hero_name": hero_name, "team": team_str,
                })
            pos += 1
    return players


print("=" * 80)
print("TOURNAMENT KDA REPORT (using KDADetector module)")
print("=" * 80)
print()

report_matches = []
grand_k_ok = 0
grand_d_ok = 0
grand_pp = 0

for match_idx, match in enumerate(truth_data["matches"]):
    replay_file = match["replay_file"]
    if not os.path.exists(replay_file):
        continue

    replay_dir = os.path.dirname(replay_file)
    basename = os.path.basename(replay_file)
    if not basename.endswith(".0.vgr"):
        continue
    prefix = basename[:-6]

    cache_dir = os.path.join(replay_dir, "cache")
    if not os.path.exists(cache_dir):
        cache_dir = replay_dir

    frame0_path = os.path.join(cache_dir, f"{prefix}.0.vgr")
    if not os.path.exists(frame0_path):
        frame0_path = replay_file
    if not os.path.exists(frame0_path):
        continue

    with open(frame0_path, "rb") as f:
        frame0 = f.read()

    players = find_player_entities(frame0)
    if not players:
        continue

    eid_be_to_player = {p["eid_be"]: p for p in players}
    valid_eids = set(eid_be_to_player.keys())

    truth_players = match["players"]
    truth_heroes = {pdata["hero_name"]: pdata for pname, pdata in truth_players.items()}
    player_to_truth = {}
    for p in players:
        if p["hero_name"] in truth_heroes:
            player_to_truth[p["eid_be"]] = truth_heroes[p["hero_name"]]

    # Build team map
    team_map = {p["eid_be"]: p["team"] for p in players}

    # Run KDADetector
    detector = KDADetector(valid_entity_ids=valid_eids)
    total_frames = 0

    for frame_idx in range(500):
        fpath = os.path.join(cache_dir, f"{prefix}.{frame_idx}.vgr")
        if not os.path.exists(fpath):
            if frame_idx > 10 and total_frames > 0:
                break
            continue
        with open(fpath, "rb") as f:
            data = f.read()
        detector.process_frame(frame_idx, data)
        total_frames += 1

    duration = match["match_info"]["duration_seconds"]
    results = detector.get_results(game_duration=duration)
    pairs = detector.get_kill_death_pairs(team_map, game_duration=duration)

    # Build match report
    match_report = {
        "match": match_idx + 1,
        "replay": match.get("replay_name", "")[:50],
        "duration": duration,
        "frames": total_frames,
        "winner": match["match_info"]["winner"],
        "total_kills": len(detector.kill_events),
        "total_deaths": len(detector.death_events),
        "kill_death_pairs": len(pairs),
        "players": [],
    }

    k_ok = 0
    d_ok = 0
    pp_count = 0

    for eid_be, p in sorted(eid_be_to_player.items(), key=lambda x: x[1]["team"]):
        truth_match = player_to_truth.get(eid_be)
        if not truth_match:
            continue

        r = results[eid_be]
        tk = truth_match["kills"]
        td = truth_match["deaths"]
        pp_count += 1
        if r.kills == tk:
            k_ok += 1
        if r.deaths == td:
            d_ok += 1

        player_report = {
            "hero": truth_match["hero_name"],
            "team": p["team"],
            "detected_kills": r.kills,
            "truth_kills": tk,
            "kill_match": r.kills == tk,
            "detected_deaths": r.deaths,
            "truth_deaths": td,
            "death_match": r.deaths == td,
        }
        match_report["players"].append(player_report)

    match_report["kill_accuracy"] = f"{k_ok}/{pp_count}"
    match_report["death_accuracy"] = f"{d_ok}/{pp_count}"

    grand_k_ok += k_ok
    grand_d_ok += d_ok
    grand_pp += pp_count
    report_matches.append(match_report)

    # Print summary
    k_str = "PERFECT" if k_ok == pp_count else f"{k_ok}/{pp_count}"
    d_str = "PERFECT" if d_ok == pp_count else f"{d_ok}/{pp_count}"
    incomplete = " (INCOMPLETE)" if total_frames < 90 else ""

    print(f"Match {match_idx+1}: {match['match_info']['winner']} wins, "
          f"dur={duration}s, frames={total_frames}{incomplete}")
    print(f"  Kills: {k_str}   Deaths: {d_str}   "
          f"Events: {len(pairs)} kill-death pairs")

    # Show player details
    for pr in match_report["players"]:
        k_mark = "OK" if pr["kill_match"] else f"{pr['detected_kills']}vs{pr['truth_kills']}"
        d_mark = "OK" if pr["death_match"] else f"{pr['detected_deaths']}vs{pr['truth_deaths']}"
        team_mark = "L" if pr["team"] == "left" else "R"
        print(f"    [{team_mark}] {pr['hero']:15s} K={pr['detected_kills']:2d}({k_mark:>5s}) "
              f"D={pr['detected_deaths']:2d}({d_mark:>5s})")
    print()

# Grand summary
print("=" * 80)
print("GRAND SUMMARY")
print("=" * 80)
print()
print(f"Replays processed: {len(report_matches)}")
print(f"Total players:     {grand_pp}")
print(f"Kill accuracy:     {grand_k_ok}/{grand_pp} ({100*grand_k_ok/grand_pp:.1f}%)")
print(f"Death accuracy:    {grand_d_ok}/{grand_pp} ({100*grand_d_ok/grand_pp:.1f}%)")
print(f"Combined:          {grand_k_ok+grand_d_ok}/{grand_pp*2} "
      f"({100*(grand_k_ok+grand_d_ok)/(grand_pp*2):.1f}%)")

# Excluding incomplete
excl = [r for r in report_matches if r["frames"] >= 90]
if len(excl) < len(report_matches):
    excl_k = sum(int(r["kill_accuracy"].split("/")[0]) for r in excl)
    excl_d = sum(int(r["death_accuracy"].split("/")[0]) for r in excl)
    excl_pp = sum(int(r["kill_accuracy"].split("/")[1]) for r in excl)
    print(f"\nExcluding incomplete replays ({len(excl)}/{len(report_matches)}):")
    print(f"  Kill:     {excl_k}/{excl_pp} ({100*excl_k/excl_pp:.1f}%)")
    print(f"  Death:    {excl_d}/{excl_pp} ({100*excl_d/excl_pp:.1f}%)")
    print(f"  Combined: {excl_k+excl_d}/{excl_pp*2} ({100*(excl_k+excl_d)/(excl_pp*2):.1f}%)")

# Save report
output = {
    "version": "tournament_kda_report_v1",
    "module": "vg.core.kda_detector.KDADetector",
    "filter": "death ts <= duration + 10s",
    "summary": {
        "replays": len(report_matches),
        "total_players": grand_pp,
        "kill_accuracy": f"{grand_k_ok}/{grand_pp} ({100*grand_k_ok/grand_pp:.1f}%)",
        "death_accuracy": f"{grand_d_ok}/{grand_pp} ({100*grand_d_ok/grand_pp:.1f}%)",
        "combined": f"{grand_k_ok+grand_d_ok}/{grand_pp*2} ({100*(grand_k_ok+grand_d_ok)/(grand_pp*2):.1f}%)",
    },
    "matches": report_matches,
}
output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_kda_report.json"
with open(output_path, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to {output_path}")
