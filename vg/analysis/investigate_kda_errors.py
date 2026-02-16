#!/usr/bin/env python3
"""
Investigate KDA detection errors in VGR replays.

Kill errors (2 cases, both +1 over-detection):
- M5 2600_IcyBang (Kestrel): detected=1, truth=0 (diff=+1)
- M6 2600_staplers (Samuel): detected=7, truth=6 (diff=+1)

Death errors (4 cases):
- M2 2599_FengLin (Tony): detected=3, truth=2 (diff=+1)
- M6 2599_123 (Lyra): detected=5, truth=4 (diff=+1)
- M10 3000_Synd (Magnus): detected=2, truth=3 (diff=-1)
- M10 2999_DrPawn (Caine): detected=3, truth=4 (diff=-1)
"""

import struct
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder

# Error cases
ERROR_CASES = {
    "M5_IcyBang_Kill": {
        "replay_name": "d8736287-e35e-4c76-89b0-c78c76fd0b05-e76f857f-218a-45bf-8982-292c7671c902",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\1\d8736287-e35e-4c76-89b0-c78c76fd0b05-e76f857f-218a-45bf-8982-292c7671c902.0.vgr",
        "player": "2600_IcyBang",
        "hero": "Kestrel",
        "type": "kill",
        "detected": 1,
        "truth": 0,
        "truth_duration": 1135,
    },
    "M6_staplers_Kill": {
        "replay_name": "d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73.0.vgr",
        "player": "2600_staplers",
        "hero": "Samuel",
        "type": "kill",
        "detected": 7,
        "truth": 6,
        "truth_duration": 1551,
    },
    "M2_FengLin_Death": {
        "replay_name": "d8736287-e35e-4c76-89b0-c78c76fd0b05-20692443-e314-4ca5-934e-faa63d820d72",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-20692443-e314-4ca5-934e-faa63d820d72.0.vgr",
        "player": "2599_FengLin",
        "hero": "Tony",
        "type": "death",
        "detected": 3,
        "truth": 2,
        "truth_duration": 969,
    },
    "M6_123_Death": {
        "replay_name": "d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73.0.vgr",
        "player": "2599_123",
        "hero": "Lyra",
        "type": "death",
        "detected": 5,
        "truth": 4,
        "truth_duration": 1551,
    },
    "M10_Synd_Death": {
        "replay_name": "f27505c4-1449-4e71-bd8a-134133e7f4b4-443dfc2c-bcf9-4791-be53-63c0f831d6f3",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\Buffalo vs RRONE\1\f27505c4-1449-4e71-bd8a-134133e7f4b4-443dfc2c-bcf9-4791-be53-63c0f831d6f3.0.vgr",
        "player": "3000_Synd",
        "hero": "Magnus",
        "type": "death",
        "detected": 2,
        "truth": 3,
        "truth_duration": 1295,
    },
    "M10_DrPawn_Death": {
        "replay_name": "f27505c4-1449-4e71-bd8a-134133e7f4b4-443dfc2c-bcf9-4791-be53-63c0f831d6f3",
        "replay_path": r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\Buffalo vs RRONE\1\f27505c4-1449-4e71-bd8a-134133e7f4b4-443dfc2c-bcf9-4791-be53-63c0f831d6f3.0.vgr",
        "player": "2999_DrPawn",
        "hero": "Caine",
        "type": "death",
        "detected": 3,
        "truth": 4,
        "truth_duration": 1295,
    },
}


def _le_to_be(eid_le: int) -> int:
    """Convert uint16 LE entity ID to Big Endian."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def investigate_case(case_name: str, case_info: dict):
    """Investigate a single error case."""
    print(f"\n{'='*80}")
    print(f"CASE: {case_name}")
    print(f"  Player: {case_info['player']} ({case_info['hero']})")
    print(f"  Error: {case_info['type'].upper()} detected={case_info['detected']}, truth={case_info['truth']}")
    print(f"  Game duration: {case_info['truth_duration']}s")
    print(f"{'='*80}\n")

    # Decode replay
    decoder = UnifiedDecoder(case_info['replay_path'])
    match = decoder.decode()

    # Find player
    target_player = None
    for player in match.all_players:
        if player.name == case_info['player']:
            target_player = player
            break

    if not target_player:
        print(f"ERROR: Player {case_info['player']} not found in decoded match")
        return

    print(f"[DATA] Player entity_id (LE): 0x{target_player.entity_id:04X}")
    eid_be = _le_to_be(target_player.entity_id)
    print(f"[DATA] Player entity_id (BE): 0x{eid_be:04X}")
    print(f"[DATA] Team: {target_player.team}")

    # Re-run KDA detection to get event details
    from vg.core.kda_detector import KDADetector

    # Load frames
    replay_file = Path(case_info['replay_path'])
    frame_dir = replay_file.parent
    frame_name = replay_file.stem.rsplit('.', 1)[0]
    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))

    def _idx(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0

    frame_files.sort(key=_idx)
    frames = [(_idx(f), f.read_bytes()) for f in frame_files]

    print(f"[DATA] Loaded {len(frames)} frames")

    # Build entity ID set and team map
    valid_eids = set()
    team_map = {}
    eid_to_player = {}
    for player in match.all_players:
        if player.entity_id:
            eid_be_local = _le_to_be(player.entity_id)
            valid_eids.add(eid_be_local)
            team_map[eid_be_local] = player.team
            eid_to_player[eid_be_local] = player

    # Run detector
    detector = KDADetector(valid_eids)
    for frame_idx, data in frames:
        detector.process_frame(frame_idx, data)

    print(f"\n[FINDING] Total events detected:")
    print(f"  Kills: {len(detector.kill_events)}")
    print(f"  Deaths: {len(detector.death_events)}")

    if case_info['type'] == 'kill':
        # Analyze kill events for this player
        player_kills = [k for k in detector.kill_events if k.killer_eid == eid_be]
        print(f"\n[FINDING] Kill events for {case_info['player']}:")
        print(f"  Count: {len(player_kills)}")

        for i, kev in enumerate(player_kills, 1):
            print(f"\n  Kill #{i}:")
            print(f"    Timestamp: {kev.timestamp:.2f}s" if kev.timestamp else "    Timestamp: None")
            print(f"    Frame: {kev.frame_idx}")
            print(f"    File offset: 0x{kev.file_offset:X}")

            # Check if post-game (after duration + buffer)
            if kev.timestamp:
                post_game = kev.timestamp > case_info['truth_duration'] + 10
                print(f"    Post-game: {post_game} (>{case_info['truth_duration']+10}s)")
                if post_game:
                    print(f"    [STAT:post_game_kill] Kill #{i} is {kev.timestamp - case_info['truth_duration']:.1f}s after game end")

            # Show credit records
            if kev.credits:
                print(f"    Credits ({len(kev.credits)}):")
                for cr in kev.credits[:5]:  # Show first 5
                    credit_player = eid_to_player.get(cr.eid)
                    pname = credit_player.name if credit_player else f"eid={cr.eid:04X}"
                    print(f"      {pname}: {cr.value:.2f}")

    elif case_info['type'] == 'death':
        # Analyze death events for this player
        player_deaths = [d for d in detector.death_events if d.victim_eid == eid_be]
        print(f"\n[FINDING] Death events for {case_info['player']}:")
        print(f"  Count (raw): {len(player_deaths)}")

        # Apply filter
        death_buffer = 10.0
        filtered_deaths = [d for d in player_deaths if d.timestamp <= case_info['truth_duration'] + death_buffer]
        print(f"  Count (filtered, ts<={case_info['truth_duration']+death_buffer}s): {len(filtered_deaths)}")

        for i, dev in enumerate(player_deaths, 1):
            filtered = dev.timestamp <= case_info['truth_duration'] + death_buffer
            print(f"\n  Death #{i}:")
            print(f"    Timestamp: {dev.timestamp:.2f}s")
            print(f"    Frame: {dev.frame_idx}")
            print(f"    File offset: 0x{dev.file_offset:X}")
            print(f"    Filtered: {'COUNTED' if filtered else 'EXCLUDED (post-game)'}")

            if not filtered:
                print(f"    [STAT:post_game_death] Death #{i} is {dev.timestamp - case_info['truth_duration']:.1f}s after game end")

    # Summary
    print(f"\n[FINDING] Summary for {case_info['player']}:")
    if case_info['type'] == 'kill':
        post_game_kills = [k for k in player_kills if k.timestamp and k.timestamp > case_info['truth_duration'] + 10]
        print(f"  Total kills detected: {len(player_kills)}")
        print(f"  Post-game kills (>{case_info['truth_duration']+10}s): {len(post_game_kills)}")
        print(f"  Truth kills: {case_info['truth']}")
        print(f"  Expected fix: filter kills with ts > duration+10s would give {len(player_kills) - len(post_game_kills)}")
    else:
        post_game_deaths = [d for d in player_deaths if d.timestamp > case_info['truth_duration'] + 10]
        print(f"  Total deaths detected: {len(player_deaths)}")
        print(f"  Filtered deaths (ts<={case_info['truth_duration']+10}s): {len(filtered_deaths)}")
        print(f"  Post-game deaths (>{case_info['truth_duration']+10}s): {len(post_game_deaths)}")
        print(f"  Truth deaths: {case_info['truth']}")
        if len(filtered_deaths) != case_info['truth']:
            print(f"  [LIMITATION] Current filter (10s buffer) does NOT fix this case")
            print(f"    Detected: {len(filtered_deaths)}, Truth: {case_info['truth']}, Diff: {len(filtered_deaths) - case_info['truth']}")


def main():
    print("[OBJECTIVE] Investigate KDA detection errors in VGR replays")
    print("[STAGE:begin:investigation]")

    import time
    start_time = time.time()

    for case_name, case_info in ERROR_CASES.items():
        try:
            investigate_case(case_name, case_info)
        except Exception as e:
            print(f"\n[LIMITATION] Error investigating {case_name}: {e}")
            import traceback
            traceback.print_exc()

    elapsed = time.time() - start_time
    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:time:{elapsed:.2f}]")
    print(f"[STAGE:end:investigation]")


if __name__ == '__main__':
    main()
