#!/usr/bin/env python3
"""
Verify parsed tournament output matches truth JSON.
"""

import argparse
import json
import sys
from pathlib import Path


def load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_truth_map(truth_data):
    matches = truth_data.get("matches", [])
    return {m.get("replay_name"): m for m in matches if m.get("replay_name")}


def build_parsed_map(parsed_data):
    parsed_map = {}
    duplicates = []
    for m in parsed_data:
        name = m.get("replay_name")
        if not name or name.startswith("._"):
            continue
        if name in parsed_map:
            duplicates.append(name)
            continue
        parsed_map[name] = m
    return parsed_map, duplicates


def compare(truth_map, parsed_map, max_details):
    truth_names = set(truth_map)
    parsed_names = set(parsed_map)

    missing = sorted(truth_names - parsed_names)
    extra = sorted(parsed_names - truth_names)
    field_mismatches = []
    player_mismatches = []

    for name in sorted(truth_names & parsed_names):
        t = truth_map[name]
        p = parsed_map[name]
        t_info = t.get("match_info", {})
        p_info = p.get("match_info", {})
        for key in ("duration_seconds", "winner", "score_left", "score_right"):
            tv = t_info.get(key)
            pv = p_info.get(key)
            if tv != pv:
                field_mismatches.append((name, key, tv, pv))

        p_players = {}
        for team in ("left", "right"):
            for pdata in p.get("teams", {}).get(team, []):
                pname = pdata.get("name")
                if pname:
                    p_players[pname] = pdata
        t_players = t.get("players", {})

        for pname, tdata in t_players.items():
            pdata = p_players.get(pname)
            if not pdata:
                player_mismatches.append((name, pname, "missing", None))
                continue
            for key in (
                "team",
                "hero_name",
                "kills",
                "deaths",
                "assists",
                "gold",
                "minion_kills",
                "bounty",
            ):
                tv = tdata.get(key)
                pv = pdata.get(key)
                if tv != pv:
                    player_mismatches.append((name, pname, key, tv, pv))

    def clip(items):
        return items[:max_details] if max_details > 0 else items

    return {
        "truth_count": len(truth_names),
        "parsed_count": len(parsed_names),
        "missing": missing,
        "extra": extra,
        "field_mismatches": field_mismatches,
        "player_mismatches": player_mismatches,
        "missing_preview": clip(missing),
        "extra_preview": clip(extra),
        "field_preview": clip(field_mismatches),
        "player_preview": clip(player_mismatches),
    }


def main():
    parser = argparse.ArgumentParser(description="Verify parsed output against truth JSON.")
    parser.add_argument("--truth", default="tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--parsed", default="tournament_parsed.json", help="Parsed JSON path")
    parser.add_argument("--max-details", type=int, default=20, help="Max mismatch details to show")
    args = parser.parse_args()

    truth_data = load_json(args.truth)
    parsed_data = load_json(args.parsed)

    truth_map = build_truth_map(truth_data)
    parsed_map, duplicates = build_parsed_map(parsed_data)

    result = compare(truth_map, parsed_map, args.max_details)

    print(f"truth matches: {result['truth_count']}")
    print(f"parsed matches: {result['parsed_count']}")
    print(f"missing in parsed: {len(result['missing'])}")
    print(f"extra in parsed: {len(result['extra'])}")
    print(f"match_info mismatches: {len(result['field_mismatches'])}")
    print(f"player mismatches: {len(result['player_mismatches'])}")
    if duplicates:
        print(f"duplicate parsed replays: {len(duplicates)}")

    if result["missing_preview"]:
        print("missing names (preview):")
        for name in result["missing_preview"]:
            print(f"  {name}")
    if result["extra_preview"]:
        print("extra names (preview):")
        for name in result["extra_preview"]:
            print(f"  {name}")
    if result["field_preview"]:
        print("match_info mismatches (preview):")
        for name, key, tv, pv in result["field_preview"]:
            print(f"  {name} {key}: truth={tv} parsed={pv}")
    if result["player_preview"]:
        print("player mismatches (preview):")
        for item in result["player_preview"]:
            if len(item) == 4:
                name, pname, key, _ = item
                print(f"  {name} {pname} {key}")
            else:
                name, pname, key, tv, pv = item
                print(f"  {name} {pname} {key}: truth={tv} parsed={pv}")

    has_errors = any(
        [
            result["missing"],
            result["extra"],
            result["field_mismatches"],
            result["player_mismatches"],
            duplicates,
        ]
    )
    return 1 if has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
