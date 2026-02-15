#!/usr/bin/env python3
"""
Discover missing hero binary IDs by scanning all available replays.
For each unknown binary hero ID found at offset 0x0A9, record the value
so we can expand the BINARY_HERO_ID_MAP.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from vgr_mapping import BINARY_HERO_ID_MAP, HERO_ID_OFFSET

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])


def scan_replay(replay_path: Path) -> list:
    """Scan a single replay for player blocks and extract hero IDs."""
    data = replay_path.read_bytes()
    results = []
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    seen = set()

    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""

            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                seen.add(name)
                if pos + HERO_ID_OFFSET + 2 <= len(data):
                    hero_id = int.from_bytes(
                        data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little'
                    )
                    known = BINARY_HERO_ID_MAP.get(hero_id, None)
                    results.append({
                        "name": name,
                        "hero_id": hero_id,
                        "hero_hex": f"0x{hero_id:04X}",
                        "known_hero": known,
                    })

        search_start = pos + 1
    return results


def main():
    # Scan all available replay directories
    replay_base = Path("D:/Desktop/My Folder/Game/VG/vg replay")
    if not replay_base.exists():
        print(f"Replay base not found: {replay_base}")
        return

    print(f"Scanning replays under: {replay_base}")
    vgr_files = list(replay_base.rglob("*.0.vgr"))
    print(f"Found {len(vgr_files)} replay files")

    all_hero_ids = defaultdict(lambda: {"count": 0, "players": [], "known": None})
    total_players = 0

    for vgr in vgr_files:
        results = scan_replay(vgr)
        for r in results:
            hid = r["hero_id"]
            all_hero_ids[hid]["count"] += 1
            all_hero_ids[hid]["known"] = r["known_hero"]
            if len(all_hero_ids[hid]["players"]) < 3:
                all_hero_ids[hid]["players"].append(r["name"])
            total_players += 1

    print(f"\nTotal players scanned: {total_players}")
    print(f"Unique hero IDs found: {len(all_hero_ids)}")

    # Separate known and unknown
    known = {k: v for k, v in all_hero_ids.items() if v["known"]}
    unknown = {k: v for k, v in all_hero_ids.items() if not v["known"]}

    print(f"\n--- KNOWN HERO IDs ({len(known)}) ---")
    for hid in sorted(known.keys()):
        info = known[hid]
        print(f"  0x{hid:04X} = {info['known']:<20} (seen {info['count']}x)")

    print(f"\n--- UNKNOWN HERO IDs ({len(unknown)}) ---")
    for hid in sorted(unknown.keys()):
        info = unknown[hid]
        players = ", ".join(info["players"])
        print(f"  0x{hid:04X} ({hid:>5}) seen {info['count']:>3}x  players: {players}")

    # Save results
    output = {
        "total_players": total_players,
        "total_unique_ids": len(all_hero_ids),
        "known_ids": len(known),
        "unknown_ids": len(unknown),
        "known": {
            f"0x{k:04X}": {"hero": v["known"], "count": v["count"]}
            for k, v in sorted(known.items())
        },
        "unknown": {
            f"0x{k:04X}": {"count": v["count"], "players": v["players"]}
            for k, v in sorted(unknown.items())
        },
    }
    output_path = Path(__file__).parent.parent / "output" / "hero_id_discovery.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
