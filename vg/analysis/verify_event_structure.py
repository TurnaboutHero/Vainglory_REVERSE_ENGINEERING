#!/usr/bin/env python3
"""
Verify Event Structure - Check if [EntityID 2B LE][00 00][ActionCode][Payload 32B] is correct

This script will:
1. Find all occurrences of known entity IDs
2. Check what follows each entity ID
3. Determine the actual event structure
"""

import struct
from pathlib import Path
from collections import Counter


class EventStructureVerifier:
    """Verify the actual event structure in VGR replays"""

    # Team composition for 21.11.04
    TEAM_1_IDS = [56325, 56581, 56837]  # Phinn, Yates, Caine
    TEAM_2_IDS = [57093, 57349, 57605]  # Petal, Karas, Baron
    ALL_ENTITY_IDS = TEAM_1_IDS + TEAM_2_IDS

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)

    def load_frames(self, max_frames: int = 10) -> bytes:
        """Load first N frames"""
        vgr_files = sorted(self.cache_dir.glob("*.vgr"), key=lambda p: self._frame_index(p))

        data_chunks = []
        for frame_file in vgr_files[:max_frames]:
            with open(frame_file, 'rb') as f:
                data_chunks.append(f.read())

        combined = b''.join(data_chunks)
        print(f"[DATA] Loaded {len(data_chunks)} frames, total {len(combined):,} bytes")
        return combined

    @staticmethod
    def _frame_index(path: Path) -> int:
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    def analyze_entity_id_context(self, data: bytes, entity_id: int, sample_size: int = 50) -> None:
        """Analyze what follows after entity ID occurrences"""
        print(f"\n[FINDING] Analyzing context around entity ID {entity_id}")

        entity_bytes = entity_id.to_bytes(2, 'little')

        # Find all occurrences
        offsets = []
        idx = 0
        while len(offsets) < sample_size:
            idx = data.find(entity_bytes, idx)
            if idx == -1:
                break
            offsets.append(idx)
            idx += 1

        print(f"  Found {len(offsets)} occurrences (showing first {sample_size})")

        # Analyze patterns after entity ID
        next_2_bytes = Counter()
        next_4_bytes = Counter()
        action_at_plus_4 = Counter()

        for offset in offsets[:sample_size]:
            if offset + 10 < len(data):
                # Next 2 bytes
                next_2 = data[offset+2:offset+4]
                next_2_bytes[next_2.hex()] += 1

                # Next 4 bytes
                next_4 = data[offset+2:offset+6]
                next_4_bytes[next_4.hex()] += 1

                # Byte at +4 (assumed action code position)
                action_at_plus_4[data[offset+4]] += 1

        print(f"\n  Next 2 bytes after entity ID (top 10):")
        for pattern, count in next_2_bytes.most_common(10):
            print(f"    {pattern}: {count}/{len(offsets[:sample_size])} ({count/len(offsets[:sample_size])*100:.1f}%)")

        print(f"\n  Byte at offset +4 (assumed action code position):")
        for action, count in sorted(action_at_plus_4.items(), key=lambda x: -x[1])[:15]:
            print(f"    0x{action:02X}: {count}/{len(offsets[:sample_size])} ({count/len(offsets[:sample_size])*100:.1f}%)")

    def find_37_byte_events(self, data: bytes) -> None:
        """Search for 37-byte event patterns starting with entity IDs"""
        print(f"\n[FINDING] Searching for 37-byte event structures")

        for entity_id in self.ALL_ENTITY_IDS:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern_prefix = entity_bytes + b'\x00\x00'

            matches = 0
            idx = 0
            action_codes = Counter()

            while True:
                idx = data.find(pattern_prefix, idx)
                if idx == -1:
                    break

                if idx + 37 <= len(data):
                    action_code = data[idx + 4]
                    action_codes[action_code] += 1
                    matches += 1

                idx += 1

            if matches > 0:
                print(f"\n  Entity {entity_id}: {matches} events with [ID][00 00][action] pattern")
                print(f"    Top action codes:")
                for action, count in sorted(action_codes.items(), key=lambda x: -x[1])[:10]:
                    print(f"      0x{action:02X}: {count}")

    def scan_cross_entity_references(self, data: bytes) -> None:
        """Look for places where multiple entity IDs appear close together"""
        print(f"\n[FINDING] Scanning for cross-entity references (kill event candidates)")

        # Build list of all entity ID positions
        entity_positions = []

        for entity_id in self.ALL_ENTITY_IDS:
            entity_bytes = entity_id.to_bytes(2, 'little')
            idx = 0
            while True:
                idx = data.find(entity_bytes, idx)
                if idx == -1:
                    break
                entity_positions.append((idx, entity_id))
                idx += 1

        # Sort by position
        entity_positions.sort()

        print(f"  Total entity ID occurrences: {len(entity_positions)}")

        # Find close pairs (within 40 bytes)
        close_pairs = []
        for i in range(len(entity_positions) - 1):
            pos1, eid1 = entity_positions[i]
            pos2, eid2 = entity_positions[i + 1]

            distance = pos2 - pos1

            if distance <= 40 and eid1 != eid2:
                # Check if from different teams
                team1 = 1 if eid1 in self.TEAM_1_IDS else 2
                team2 = 1 if eid2 in self.TEAM_2_IDS else 2

                if team1 != team2:
                    close_pairs.append({
                        'pos1': pos1,
                        'entity1': eid1,
                        'pos2': pos2,
                        'entity2': eid2,
                        'distance': distance,
                    })

        print(f"  Cross-team entity pairs within 40 bytes: {len(close_pairs)}")

        if close_pairs:
            print(f"\n  Examples (first 10):")
            for pair in close_pairs[:10]:
                print(f"    @{pair['pos1']}: {pair['entity1']} -> @{pair['pos2']}: {pair['entity2']} (distance: {pair['distance']})")

                # Show the bytes between them
                start = pair['pos1']
                end = pair['pos2'] + 2
                context = data[start:min(end, start+45)]
                print(f"      Context: {context.hex()}")

    def run_verification(self) -> None:
        """Run complete event structure verification"""
        print("[OBJECTIVE] Verify VGR event structure format")

        data = self.load_frames(max_frames=10)

        # Analyze context around one entity ID
        print("\n" + "="*60)
        print("STEP 1: Analyze byte patterns after entity IDs")
        print("="*60)
        self.analyze_entity_id_context(data, self.ALL_ENTITY_IDS[0], sample_size=100)

        # Find 37-byte events
        print("\n" + "="*60)
        print("STEP 2: Count events with [EntityID][00 00][Action] pattern")
        print("="*60)
        self.find_37_byte_events(data)

        # Scan for cross-entity references
        print("\n" + "="*60)
        print("STEP 3: Find cross-team entity ID proximity (kill candidates)")
        print("="*60)
        self.scan_cross_entity_references(data)

        print("\n[FINDING] Verification complete")


def main():
    cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"

    verifier = EventStructureVerifier(cache_dir)
    verifier.run_verification()

    print("\n[LIMITATION] Analysis limited to first 10 frames to reduce processing time")


if __name__ == '__main__':
    main()
