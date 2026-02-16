#!/usr/bin/env python3
"""
Generate detailed event listings for error cases.
Shows ALL kill and death events in chronological order with context.
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder


def _le_to_be(eid_le: int) -> int:
    """Convert uint16 LE entity ID to Big Endian."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def analyze_match_10_deaths():
    """Deep dive into Match 10 death timestamps to understand the 20s offset."""
    print("[STAGE:begin:match10_analysis]")
    print("\n" + "="*80)
    print("MATCH 10: Buffalo vs RRONE (both death under-detections)")
    print("="*80 + "\n")

    replay_path = r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\Buffalo vs RRONE\1\f27505c4-1449-4e71-bd8a-134133e7f4b4-443dfc2c-bcf9-4791-be53-63c0f831d6f3.0.vgr"
    truth_duration = 1295

    decoder = UnifiedDecoder(replay_path)
    match = decoder.decode()

    print(f"[DATA] Match duration (truth): {truth_duration}s")
    print(f"[DATA] Crystal death timestamp: {match.crystal_death_ts:.2f}s" if match.crystal_death_ts else "[DATA] No crystal death detected")
    print(f"[DATA] Total players: {len(match.all_players)}")

    # Load frames and run KDA detector
    from vg.core.kda_detector import KDADetector

    replay_file = Path(replay_path)
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

    valid_eids = set()
    team_map = {}
    eid_to_player = {}
    for player in match.all_players:
        if player.entity_id:
            eid_be = _le_to_be(player.entity_id)
            valid_eids.add(eid_be)
            team_map[eid_be] = player.team
            eid_to_player[eid_be] = player

    detector = KDADetector(valid_eids)
    for frame_idx, data in frames:
        detector.process_frame(frame_idx, data)

    # Sort all deaths by timestamp
    all_deaths = sorted(detector.death_events, key=lambda d: d.timestamp)

    print(f"\n[FINDING] All death events (chronological):")
    print(f"  Total deaths detected: {len(all_deaths)}")
    print(f"  Death buffer thresholds:")
    print(f"    - 10s buffer: {truth_duration + 10}s")
    print(f"    - 15s buffer: {truth_duration + 15}s")
    print(f"    - 20s buffer: {truth_duration + 20}s")
    print(f"    - 25s buffer: {truth_duration + 25}s\n")

    for i, dev in enumerate(all_deaths, 1):
        player = eid_to_player.get(dev.victim_eid)
        pname = player.name if player else f"eid={dev.victim_eid:04X}"
        team = player.team if player else "unknown"
        hero = player.hero_name if player else "unknown"

        offset = dev.timestamp - truth_duration

        # Check which buffers would include this death
        buffer_10 = "Y" if offset <= 10 else "N"
        buffer_15 = "Y" if offset <= 15 else "N"
        buffer_20 = "Y" if offset <= 20 else "N"
        buffer_25 = "Y" if offset <= 25 else "N"

        # Highlight the two under-detected deaths
        highlight = ""
        if pname in ["3000_Synd", "2999_DrPawn"] and offset > 10:
            highlight = " ← FILTERED BY 10s BUFFER (truth confirms valid)"

        print(f"  Death #{i:2d}: {dev.timestamp:7.2f}s | {offset:+6.1f}s | "
              f"{pname:20s} ({team:5s}, {hero:12s}) | "
              f"10s:{buffer_10} 15s:{buffer_15} 20s:{buffer_20} 25s:{buffer_25}{highlight}")

    # Summary statistics
    deaths_within_10s = sum(1 for d in all_deaths if d.timestamp <= truth_duration + 10)
    deaths_within_15s = sum(1 for d in all_deaths if d.timestamp <= truth_duration + 15)
    deaths_within_20s = sum(1 for d in all_deaths if d.timestamp <= truth_duration + 20)
    deaths_within_25s = sum(1 for d in all_deaths if d.timestamp <= truth_duration + 25)
    deaths_total = len(all_deaths)

    print(f"\n[STAT:buffer_analysis]")
    print(f"  Buffer=10s: {deaths_within_10s}/{deaths_total} deaths counted")
    print(f"  Buffer=15s: {deaths_within_15s}/{deaths_total} deaths counted")
    print(f"  Buffer=20s: {deaths_within_20s}/{deaths_total} deaths counted")
    print(f"  Buffer=25s: {deaths_within_25s}/{deaths_total} deaths counted")

    # Truth comparison
    truth_deaths_left = 3 + 0 + 4 + 8 + 7  # From truth data
    truth_deaths_right = 4 + 2 + 1 + 0 + 1  # From truth data
    truth_total = truth_deaths_left + truth_deaths_right

    print(f"\n[STAT:truth_comparison]")
    print(f"  Truth total deaths: {truth_total}")
    print(f"  Detected (10s buffer): {deaths_within_10s} (diff: {deaths_within_10s - truth_total:+d})")
    print(f"  Detected (25s buffer): {deaths_within_25s} (diff: {deaths_within_25s - truth_total:+d})")

    # Check kills for comparison
    all_kills = sorted([k for k in detector.kill_events if k.timestamp], key=lambda k: k.timestamp)
    print(f"\n[FINDING] Kill timestamps for context:")
    print(f"  Total kills detected: {len(all_kills)}")

    recent_kills = [k for k in all_kills if k.timestamp > truth_duration - 60]
    print(f"  Kills in last 60s of game:")
    for kev in recent_kills:
        player = eid_to_player.get(kev.killer_eid)
        pname = player.name if player else f"eid={kev.killer_eid:04X}"
        offset = kev.timestamp - truth_duration
        print(f"    {kev.timestamp:7.2f}s ({offset:+5.1f}s) - {pname}")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:match10_analysis]")


def analyze_match_6_over_detections():
    """Analyze Match 6 where both kill and death have +1 over-detection."""
    print("\n[STAGE:begin:match6_analysis]")
    print("\n" + "="*80)
    print("MATCH 6: SFC vs Law Enforcers Finals 2 (kill +1, death +1)")
    print("="*80 + "\n")

    replay_path = r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73.0.vgr"
    truth_duration = 1551

    decoder = UnifiedDecoder(replay_path)
    match = decoder.decode()

    # Load frames and run KDA detector
    from vg.core.kda_detector import KDADetector

    replay_file = Path(replay_path)
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

    valid_eids = set()
    team_map = {}
    eid_to_player = {}
    for player in match.all_players:
        if player.entity_id:
            eid_be = _le_to_be(player.entity_id)
            valid_eids.add(eid_be)
            team_map[eid_be] = player.team
            eid_to_player[eid_be] = player

    detector = KDADetector(valid_eids)
    for frame_idx, data in frames:
        detector.process_frame(frame_idx, data)

    # Analyze staplers kills (truth=6, detected=7)
    staplers_eid = _le_to_be(0xE205)
    staplers_kills = [k for k in detector.kill_events if k.killer_eid == staplers_eid]

    print(f"[FINDING] 2600_staplers kills (detected=7, truth=6):")
    for i, kev in enumerate(staplers_kills, 1):
        credits_summary = f"{len(kev.credits)} credits"
        assisters = []
        for cr in kev.credits:
            if cr.eid != staplers_eid and abs(cr.value - 1.0) < 0.01:
                p = eid_to_player.get(cr.eid)
                if p:
                    assisters.append(p.name)

        assist_str = f" (assists: {', '.join(assisters)})" if assisters else ""
        print(f"  Kill #{i}: {kev.timestamp:.2f}s - {credits_summary}{assist_str}")

    # Analyze 123 deaths (truth=4, detected=5)
    lyra_eid = _le_to_be(0xE305)
    lyra_deaths = [d for d in detector.death_events if d.victim_eid == lyra_eid]

    print(f"\n[FINDING] 2599_123 (Lyra) deaths (detected=5, truth=4):")
    for i, dev in enumerate(lyra_deaths, 1):
        print(f"  Death #{i}: {dev.timestamp:.2f}s (frame {dev.frame_idx})")

    # Check for kill-death pairs around each death
    print(f"\n[FINDING] Kill-death pairing analysis:")
    for i, dev in enumerate(lyra_deaths, 1):
        # Find kills within ±3s
        nearby_kills = [k for k in detector.kill_events
                       if k.timestamp and abs(k.timestamp - dev.timestamp) < 3]

        print(f"  Death #{i} at {dev.timestamp:.2f}s:")
        if nearby_kills:
            for kev in nearby_kills:
                killer = eid_to_player.get(kev.killer_eid)
                kname = killer.name if killer else f"eid={kev.killer_eid:04X}"
                kteam = killer.team if killer else "unknown"
                dt = kev.timestamp - dev.timestamp
                print(f"    Kill by {kname} ({kteam}) at {kev.timestamp:.2f}s (Δt={dt:+.2f}s)")
        else:
            print(f"    No nearby kills (within ±3s)")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:match6_analysis]")


def main():
    print("[OBJECTIVE] Detailed event listing for error cases")

    import time
    start_time = time.time()

    try:
        analyze_match_10_deaths()
    except Exception as e:
        print(f"\n[LIMITATION] Error in Match 10 analysis: {e}")
        import traceback
        traceback.print_exc()

    try:
        analyze_match_6_over_detections()
    except Exception as e:
        print(f"\n[LIMITATION] Error in Match 6 analysis: {e}")
        import traceback
        traceback.print_exc()

    elapsed = time.time() - start_time
    print(f"\n[STAGE:time:{elapsed:.2f}]")


if __name__ == '__main__':
    main()
