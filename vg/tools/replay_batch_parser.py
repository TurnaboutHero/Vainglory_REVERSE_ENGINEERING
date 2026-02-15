#!/usr/bin/env python3
"""
Batch Replay Parser - Parse all VGR replays in a directory.
Usage: python replay_batch_parser.py <replay_dir> [--output results.json]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from vgr_parser import VGRParser


def parse_replay(vgr_path: Path) -> dict:
    """Parse a single replay and return summary."""
    try:
        parser = VGRParser(str(vgr_path), auto_truth=False)
        parsed = parser.parse()
        players = []
        for team_label in ("left", "right"):
            for p in parsed["teams"].get(team_label, []):
                players.append({
                    "name": p.get("name", ""),
                    "hero_name": p.get("hero_name", "Unknown"),
                    "hero_id": p.get("hero_id"),
                    "team": team_label,
                    "entity_id": p.get("entity_id"),
                })
        return {
            "file": str(vgr_path),
            "game_mode": parsed.get("game_mode", "unknown"),
            "map_mode": parsed.get("map_mode", "unknown"),
            "players": players,
            "player_count": len(players),
            "success": True,
        }
    except Exception as e:
        return {
            "file": str(vgr_path),
            "error": str(e),
            "success": False,
        }


def batch_parse(replay_dir: Path) -> dict:
    """Parse all replays in directory."""
    vgr_files = sorted(replay_dir.rglob("*.0.vgr"))
    print(f"Found {len(vgr_files)} replay files")

    results = []
    hero_counter = Counter()
    mode_counter = Counter()
    player_set = set()
    total_success = 0

    for i, vgr in enumerate(vgr_files):
        result = parse_replay(vgr)
        results.append(result)
        if result["success"]:
            total_success += 1
            mode_counter[result["game_mode"]] += 1
            for p in result["players"]:
                hero_counter[p["hero_name"]] += 1
                player_set.add(p["name"])
        if (i + 1) % 10 == 0:
            print(f"  Parsed {i+1}/{len(vgr_files)}...")

    summary = {
        "total_replays": len(vgr_files),
        "successful": total_success,
        "failed": len(vgr_files) - total_success,
        "unique_players": len(player_set),
        "game_modes": dict(mode_counter.most_common()),
        "hero_picks": dict(hero_counter.most_common()),
        "replays": results,
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Batch parse VGR replay files")
    parser.add_argument("replay_dir", help="Directory containing replay files")
    parser.add_argument("--output", "-o", default=None, help="Output JSON path")
    args = parser.parse_args()

    replay_dir = Path(args.replay_dir)
    if not replay_dir.exists():
        print(f"Error: {replay_dir} not found")
        sys.exit(1)

    summary = batch_parse(replay_dir)

    print(f"\n{'='*50}")
    print(f"Total replays: {summary['total_replays']}")
    print(f"Successful: {summary['successful']}")
    print(f"Unique players: {summary['unique_players']}")
    print(f"Hero picks: {len(summary['hero_picks'])} unique heroes")
    print(f"Top heroes: {dict(list(summary['hero_picks'].items())[:10])}")

    output_path = args.output or str(Path(__file__).parent.parent / "output" / "batch_parse_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
