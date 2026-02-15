#!/usr/bin/env python3
"""
Item Pattern Discovery - Multi-Strategy Exploration
Reverse engineer Crystal/Defense/Utility item storage patterns
"""

import sys
import struct
from pathlib import Path
from collections import defaultdict
import json

# Add to path
sys.path.insert(0, str(Path.cwd()))
from vg.core.vgr_mapping import ITEM_ID_MAP

# Test replay directory
REPLAY_DIR = Path(r"D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache")

# Item ID ranges
WEAPON_IDS = list(range(101, 130))
CRYSTAL_IDS = list(range(201, 230))
DEFENSE_IDS = list(range(301, 329))
UTILITY_IDS = list(range(401, 424))

print("[OBJECTIVE] Discover Crystal/Defense/Utility item storage patterns")
print(f"[DATA] Test replay: {REPLAY_DIR}")
print(f"[DATA] Item ranges: Crystal(201-229), Defense(301-328), Utility(401-423)")

# Load frame files
frame_files = sorted(REPLAY_DIR.glob("*.vgr"),
                     key=lambda p: int(p.stem.split('.')[-1]))

if not frame_files:
    print("[LIMITATION] No .vgr files found")
    sys.exit(1)

print(f"[DATA] Total frames: {len(frame_files)}")

# Strategy 1: Direct ID search (2-byte LE)
print("\n[FINDING] Strategy 1: Direct 2-byte LE pattern search")
print("=" * 70)

pattern_hits = defaultdict(lambda: defaultdict(list))

for frame_path in frame_files[:20]:  # First 20 frames
    frame_num = int(frame_path.stem.split('.')[-1])
    data = frame_path.read_bytes()

    # Search for each item ID category
    for category, id_range in [("Crystal", CRYSTAL_IDS),
                                ("Defense", DEFENSE_IDS),
                                ("Utility", UTILITY_IDS)]:
        for item_id in id_range:
            # 2-byte LE search
            id_bytes = struct.pack('<H', item_id)
            offset = 0
            while True:
                offset = data.find(id_bytes, offset)
                if offset == -1:
                    break
                pattern_hits[category][item_id].append({
                    'frame': frame_num,
                    'offset': offset,
                    'context': data[max(0, offset-4):offset+10].hex()
                })
                offset += 1

# Report findings
for category in ["Crystal", "Defense", "Utility"]:
    total_hits = sum(len(v) for v in pattern_hits[category].values())
    unique_items = len([k for k, v in pattern_hits[category].items() if v])
    print(f"\n{category} Items:")
    print(f"  Unique IDs found: {unique_items}")
    print(f"  Total occurrences: {total_hits}")

    if unique_items > 0:
        # Show top 5 most frequent
        sorted_items = sorted(pattern_hits[category].items(),
                             key=lambda x: len(x[1]), reverse=True)[:5]
        for item_id, hits in sorted_items:
            item_name = ITEM_ID_MAP.get(item_id, {}).get('name', f'Unknown {item_id}')
            print(f"    {item_name} (ID {item_id}): {len(hits)} hits")
            # Show first context
            if hits:
                ctx = hits[0]['context']
                print(f"      Context: {ctx}")

print(f"\n[STAT:crystal_unique_ids] {len([k for k, v in pattern_hits['Crystal'].items() if v])}")
print(f"[STAT:defense_unique_ids] {len([k for k, v in pattern_hits['Defense'].items() if v])}")
print(f"[STAT:utility_unique_ids] {len([k for k, v in pattern_hits['Utility'].items() if v])}")

# Save detailed results
results = {
    'strategy': 'direct_2byte_le',
    'pattern_hits': {
        category: {
            str(item_id): [
                {'frame': h['frame'], 'offset': h['offset'], 'context': h['context']}
                for h in hits
            ]
            for item_id, hits in pattern_hits[category].items()
        }
        for category in ["Crystal", "Defense", "Utility"]
    }
}

output_path = Path('.omc/scientist/strategy1_results.json')
with open(output_path, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n[FINDING] Results saved to {output_path}")
