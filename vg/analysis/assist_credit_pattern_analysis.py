#!/usr/bin/env python3
"""
Assist Credit Pattern Analysis - Classify TRUE vs FALSE assists by credit structure.

From the raw investigation, we observe two distinct credit record patterns:
  PATTERN A (Full assist): player gets triplet [gold_value, 1.0, fraction(0.25/0.33/0.5)]
                          with action bytes [0x06, 0x0B, 0x0C]
  PATTERN B (Lone 1.0):   player gets ONLY a single value=1.0 record at the END of credits
                          with no gold_value or fraction in the same group

Hypothesis: Pattern B is NOT a real assist - it's a different game event
(e.g., Blackfeather perk proc, proximity credit, objective involvement).

This script classifies each detected assist and compares against truth.
"""

import struct
import json
import sys
import os
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core"))
from kda_detector import KDADetector, KILL_HEADER, CREDIT_HEADER

TRUTH_PATH = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

with open(TRUTH_PATH) as f:
    truth_data = json.load(f)


def read_all_frames(replay_path):
    p = Path(replay_path)
    frame_dir = p.parent
    replay_name = p.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def frame_index(fp):
        try: return int(fp.stem.split('.')[-1])
        except ValueError: return 0
    frames.sort(key=frame_index)
    frame_boundaries = []
    all_data = bytearray()
    for fp in frames:
        start = len(all_data)
        chunk = fp.read_bytes()
        all_data.extend(chunk)
        frame_boundaries.append((start, len(all_data), int(fp.stem.split('.')[-1])))
    return bytes(all_data), frame_boundaries


def parse_player_blocks(data):
    MARKER1 = bytes([0xDA, 0x03, 0xEE])
    MARKER2 = bytes([0xE0, 0x03, 0xEE])
    players = {}
    search_start = 0
    seen_names = set()
    while True:
        pos1 = data.find(MARKER1, search_start)
        pos2 = data.find(MARKER2, search_start)
        candidates = []
        if pos1 != -1: candidates.append((pos1, MARKER1))
        if pos2 != -1: candidates.append((pos2, MARKER2))
        if not candidates: break
        pos, marker = min(candidates, key=lambda x: x[0])
        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126: break
            name_end += 1
        if name_end > name_start:
            try: name = data[name_start:name_end].decode('ascii')
            except: name = ""
            if len(name) >= 3 and name not in seen_names and not name.startswith('GameMode'):
                entity_id = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little') if pos + 0xA7 <= len(data) else None
                team_byte = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                team = "left" if team_byte == 1 else ("right" if team_byte == 2 else "unknown")
                eid_be = struct.unpack(">H", struct.pack("<H", entity_id))[0] if entity_id else None
                players[name] = {"eid_be": eid_be, "team": team}
                seen_names.add(name)
        search_start = pos + 1
    return players


def scan_credits_with_action_bytes(data, start_pos, valid_eids):
    """Scan credit records AND extract the action byte after each value."""
    credits = []
    pos = start_pos
    max_scan = min(start_pos + 500, len(data))
    KILL_H = bytes([0x18, 0x04, 0x1C])
    CREDIT_H = bytes([0x10, 0x04, 0x1D])

    while pos < max_scan:
        # Stop at next validated kill header
        if (data[pos:pos + 3] == KILL_H and pos + 16 <= len(data)
                and data[pos+3:pos+5] == b'\x00\x00'
                and data[pos+7:pos+11] == b'\xFF\xFF\xFF\xFF'
                and data[pos+11:pos+15] == b'\x3F\x80\x00\x00'
                and data[pos+15] == 0x29):
            break

        if data[pos:pos + 3] == CREDIT_H:
            if pos + 12 <= len(data) and data[pos+3:pos+5] == b'\x00\x00':
                eid = struct.unpack_from(">H", data, pos + 5)[0]
                value = struct.unpack_from(">f", data, pos + 7)[0]
                action_byte = data[pos + 11] if pos + 11 < len(data) else None
                if eid in valid_eids and 0 <= value <= 10000:
                    credits.append({
                        "eid": eid,
                        "value": round(value, 2),
                        "action": action_byte,
                        "offset": pos,
                    })
                pos += 12
                continue
        pos += 1
    return credits


def classify_assist_pattern(credits, target_eid, killer_eid):
    """Classify what pattern of credits the target_eid has.

    Returns:
        "full_triplet" - has gold + 1.0(0x0B) + fraction(0x0C) = real assist
        "lone_1_0"     - has ONLY value=1.0 with no gold/fraction = suspicious
        "none"         - no 1.0 credit at all
        "mixed"        - some other pattern
    """
    target_credits = [c for c in credits if c["eid"] == target_eid]
    if not target_credits:
        return "none", []

    values = [c["value"] for c in target_credits]
    actions = [c["action"] for c in target_credits]

    has_1_0 = any(abs(v - 1.0) < 0.01 for v in values)
    if not has_1_0:
        return "none", target_credits

    # Check for full triplet: gold (action 0x06), 1.0 (action 0x0B), fraction (action 0x0C)
    has_gold_06 = any(c["action"] == 0x06 and c["value"] > 1.5 for c in target_credits)
    has_flag_0b = any(c["action"] == 0x0B and abs(c["value"] - 1.0) < 0.01 for c in target_credits)
    has_frac_0c = any(c["action"] == 0x0C for c in target_credits)

    if has_gold_06 and has_flag_0b and has_frac_0c:
        return "full_triplet", target_credits

    # Check if it's a lone 1.0 (no gold, no fraction)
    non_1_0_credits = [c for c in target_credits if abs(c["value"] - 1.0) > 0.01]
    if not non_1_0_credits:
        # Only 1.0 values - check action bytes
        return "lone_1_0", target_credits

    # Has 1.0 plus some other values but not the full triplet
    # Could be gold + 1.0 without fraction, or other combos
    has_any_gold = any(c["value"] > 1.5 and c["action"] in (0x06, 0x08) for c in target_credits)
    if has_any_gold and has_flag_0b:
        return "partial_triplet", target_credits

    return "mixed", target_credits


def analyze_all_matches():
    """Analyze ALL matches, classifying every assist detection by pattern."""

    print("=" * 90)
    print("ASSIST CREDIT PATTERN CLASSIFICATION")
    print("=" * 90)

    global_stats = {
        "full_triplet": {"correct": 0, "false": 0},
        "lone_1_0": {"correct": 0, "false": 0},
        "partial_triplet": {"correct": 0, "false": 0},
        "mixed": {"correct": 0, "false": 0},
    }

    # Track per-hero stats
    hero_false_positive_patterns = defaultdict(lambda: Counter())

    for midx, match in enumerate(truth_data["matches"]):
        replay_file = match["replay_file"]
        duration = match["match_info"]["duration_seconds"]

        # Read data
        first_frame_data = Path(replay_file).read_bytes()
        players = parse_player_blocks(first_frame_data)
        all_data, frame_boundaries = read_all_frames(replay_file)

        eid_to_name = {}
        eid_to_team = {}
        eid_to_hero = {}
        for pname, pinfo in players.items():
            eid_to_name[pinfo["eid_be"]] = pname
            eid_to_team[pinfo["eid_be"]] = pinfo["team"]
            truth_p = match["players"].get(pname, {})
            eid_to_hero[pinfo["eid_be"]] = truth_p.get("hero_name", "?")

        valid_eids = set(eid_to_name.keys())

        # Run KDA detection
        detector = KDADetector(valid_eids)
        for start, end, fidx in frame_boundaries:
            detector.process_frame(fidx, all_data[start:end])

        team_map = {eid: eid_to_team[eid] for eid in valid_eids}

        # For each kill, rescan credits WITH action bytes
        print(f"\n--- Match {midx+1}: {Path(replay_file).parent.parent.name}/{Path(replay_file).parent.name} ---")

        # Build truth assists per player
        truth_assists = {}
        for pname, pdata in match["players"].items():
            if pname in players:
                truth_assists[players[pname]["eid_be"]] = pdata.get("assists", 0)

        # Count assists by pattern per player
        player_assist_by_pattern = defaultdict(lambda: Counter())

        for kill_num, kev in enumerate(detector.kill_events, 1):
            killer_eid = kev.killer_eid
            killer_team = eid_to_team.get(killer_eid, "?")

            # Get credits with action bytes from raw frame data
            for start, end, fidx in frame_boundaries:
                if fidx == kev.frame_idx:
                    frame_data = all_data[start:end]
                    credits_raw = scan_credits_with_action_bytes(
                        frame_data, kev.file_offset + 16, valid_eids
                    )
                    break
            else:
                credits_raw = []

            # For each non-killer same-team player with value=1.0
            credits_by_eid = defaultdict(list)
            for cr in credits_raw:
                credits_by_eid[cr["eid"]].append(cr)

            for eid in valid_eids:
                if eid == killer_eid:
                    continue
                if eid_to_team.get(eid) != killer_team:
                    continue

                eid_credits = credits_by_eid.get(eid, [])
                has_1_0 = any(abs(c["value"] - 1.0) < 0.01 for c in eid_credits)
                if not has_1_0:
                    continue

                pattern, _ = classify_assist_pattern(credits_raw, eid, killer_eid)
                player_assist_by_pattern[eid][pattern] += 1

        # Compare with truth
        for eid in valid_eids:
            pname = eid_to_name.get(eid, "?")
            hero = eid_to_hero.get(eid, "?")
            truth_a = truth_assists.get(eid, 0)

            patterns = player_assist_by_pattern.get(eid, Counter())
            detected_total = sum(patterns.values())
            excess = detected_total - truth_a

            if excess != 0 or detected_total > 0:
                status = "OK" if excess == 0 else f"ERROR +{excess}" if excess > 0 else f"ERROR {excess}"

                if excess > 0:
                    print(f"  {status}: {pname} ({hero}): detected={detected_total} truth={truth_a}")
                    print(f"    Pattern breakdown: {dict(patterns)}")

                    # The excess must come from one or more patterns
                    # If we have lone_1_0, those are likely the false positives
                    if patterns.get("lone_1_0", 0) > 0:
                        print(f"    >>> lone_1_0 count={patterns['lone_1_0']} could explain {min(patterns['lone_1_0'], excess)} of {excess} false positives")
                        hero_false_positive_patterns[hero]["lone_1_0"] += min(patterns["lone_1_0"], excess)

                    for pat in patterns:
                        if pat != "lone_1_0" and excess > patterns.get("lone_1_0", 0):
                            hero_false_positive_patterns[hero][pat] += 1

        # Also count correct pattern stats across ALL players
        for eid in valid_eids:
            patterns = player_assist_by_pattern.get(eid, Counter())
            truth_a = truth_assists.get(eid, 0)
            detected_total = sum(patterns.values())
            excess = max(0, detected_total - truth_a)

            # Distribute: assume full_triplet are correct first, lone_1_0 are false
            remaining_correct = truth_a
            remaining_false = excess

            for pat in ["full_triplet", "partial_triplet", "mixed", "lone_1_0"]:
                count = patterns.get(pat, 0)
                correct_from_this = min(count, remaining_correct)
                false_from_this = min(count - correct_from_this, remaining_false)
                global_stats[pat]["correct"] += correct_from_this
                global_stats[pat]["false"] += false_from_this
                remaining_correct -= correct_from_this
                remaining_false -= false_from_this

    # Global summary
    print(f"\n\n{'='*90}")
    print("GLOBAL PATTERN STATISTICS")
    print(f"{'='*90}")
    total_correct = sum(v["correct"] for v in global_stats.values())
    total_false = sum(v["false"] for v in global_stats.values())
    print(f"Total correct assists: {total_correct}")
    print(f"Total false assists: {total_false}")
    print()

    for pat, stats in global_stats.items():
        total = stats["correct"] + stats["false"]
        if total > 0:
            precision = stats["correct"] / total * 100
            print(f"  {pat:20s}: {total:3d} detections ({stats['correct']} correct, {stats['false']} false) precision={precision:.1f}%")
        else:
            print(f"  {pat:20s}: 0 detections")

    print(f"\n{'='*90}")
    print("HERO-SPECIFIC FALSE POSITIVE PATTERNS")
    print(f"{'='*90}")
    for hero, patterns in sorted(hero_false_positive_patterns.items(), key=lambda x: -sum(x[1].values())):
        print(f"  {hero}: {dict(patterns)}")

    # Proposed filter analysis
    print(f"\n{'='*90}")
    print("PROPOSED FILTER: Remove 'lone_1_0' pattern assists")
    print(f"{'='*90}")
    lone_correct = global_stats["lone_1_0"]["correct"]
    lone_false = global_stats["lone_1_0"]["false"]
    print(f"  Would remove {lone_false} false positives")
    print(f"  Would remove {lone_correct} true positives (new false negatives)")
    print(f"  Net improvement: +{lone_false - lone_correct} correct")
    new_total = total_correct - lone_correct
    new_total_detections = total_correct + total_false - lone_correct - lone_false
    if new_total + total_false - lone_false > 0:
        old_accuracy = total_correct / (total_correct + total_false) * 100
        new_accuracy = new_total / (new_total + total_false - lone_false) * 100
        print(f"  Old accuracy: {old_accuracy:.1f}%")
        print(f"  New accuracy: {new_accuracy:.1f}%")


if __name__ == "__main__":
    analyze_all_matches()
