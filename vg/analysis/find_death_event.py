#!/usr/bin/env python3
"""
Find death event by comparing frames before and after death in Ringo test.
The death occurred somewhere in the 5 frames.
"""

from pathlib import Path
from collections import Counter


def analyze_ringo_death_test():
    """Analyze the Ringo Death Test replay to find the death event."""
    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\replay-test")

    # Entity ID for Ringo player
    entity_id = 56325
    entity_bytes = entity_id.to_bytes(2, 'little')  # 0x05DC in little endian

    print(f"Entity ID: {entity_id} (0x{entity_id:04X})")
    print(f"Entity bytes (LE): {entity_bytes.hex()}")
    print()

    # Load all frames
    frames = {}
    frame_files = sorted(replay_dir.glob("*.vgr"), key=lambda p: int(p.stem.split('.')[-1]))

    for f in frame_files:
        frame_num = int(f.stem.split('.')[-1])
        frames[frame_num] = f.read_bytes()
        print(f"Frame {frame_num}: {len(frames[frame_num])} bytes")

    print()

    # Find all unique action codes per frame for this entity
    print("=== Action Codes per Frame ===")
    frame_actions = {}
    for frame_num, data in sorted(frames.items()):
        pattern = entity_bytes + b'\x00\x00'
        actions = []
        idx = 0
        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break
            if idx + 5 <= len(data):
                action = data[idx + 4]
                actions.append(action)
            idx += 1

        action_counts = Counter(actions)
        frame_actions[frame_num] = action_counts
        print(f"Frame {frame_num}: {dict(action_counts)}")

    print()

    # Find actions that appear in only one frame (potential death event)
    print("=== Actions Unique to Single Frames ===")
    all_actions = set()
    for counts in frame_actions.values():
        all_actions.update(counts.keys())

    for action in sorted(all_actions):
        frames_with_action = [f for f, counts in frame_actions.items() if action in counts]
        if len(frames_with_action) == 1:
            frame = frames_with_action[0]
            count = frame_actions[frame][action]
            print(f"  0x{action:02X}: only in frame {frame} ({count} times)")

    print()

    # Look for specific death-related patterns
    # The death event might be a new event type that only appears when death happens
    print("=== Comparing Frame 2 (potentially alive) vs Frame 3 (potentially dead/respawning) ===")

    # Find events unique to frame 3 (death might have happened here)
    if 2 in frames and 3 in frames:
        actions_f2 = set(frame_actions.get(2, {}).keys())
        actions_f3 = set(frame_actions.get(3, {}).keys())

        new_in_f3 = actions_f3 - actions_f2
        print(f"Actions only in frame 3: {[hex(a) for a in new_in_f3]}")

        # Look at the 0x42 event in frame 3 (it's unique to frame 3)
        if 0x42 in actions_f3:
            print("\n=== Analyzing 0x42 event (unique to frame 3) ===")
            data = frames[3]
            pattern = entity_bytes + b'\x00\x00'
            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break
                if idx + 5 <= len(data):
                    action = data[idx + 4]
                    if action == 0x42:
                        payload = data[idx + 5:idx + 25]
                        print(f"  Offset {idx}: action=0x42")
                        print(f"    Payload: {payload.hex()}")
                        print(f"    Payload bytes: {list(payload)}")
                idx += 1

    print()

    # Search for any patterns that might indicate death
    # In MOBA games, death events often contain respawn timer or position data
    print("=== Looking for 0x07 events (appears in frames 2,3 only) ===")
    for frame_num in [2, 3]:
        if frame_num not in frames:
            continue
        data = frames[frame_num]
        pattern = entity_bytes + b'\x00\x00'
        idx = 0
        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break
            if idx + 5 <= len(data):
                action = data[idx + 4]
                if action == 0x07:
                    payload = data[idx + 5:idx + 25]
                    print(f"  Frame {frame_num}, Offset {idx}: action=0x07")
                    print(f"    Payload: {payload.hex()}")
            idx += 1

    print()

    # Search for death-related markers in raw bytes
    # Common death markers: respawn position (spawn coordinates), death timer
    print("=== Searching for potential death markers ===")

    # Compare byte sequences across frames to find changes
    if 1 in frames and 2 in frames:
        # Find sequences that exist in frame 2 but not in frame 1
        # (indicating something new happened)
        print("Frame 1 -> 2 size diff:", len(frames[2]) - len(frames[1]))

    if 2 in frames and 3 in frames:
        print("Frame 2 -> 3 size diff:", len(frames[3]) - len(frames[2]))

    if 3 in frames and 4 in frames:
        print("Frame 3 -> 4 size diff:", len(frames[4]) - len(frames[3]))


if __name__ == "__main__":
    analyze_ringo_death_test()
