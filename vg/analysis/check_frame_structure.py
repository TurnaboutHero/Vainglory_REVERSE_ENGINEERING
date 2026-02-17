"""Check where credit records actually appear - in frames or only in .0.vgr?"""

import struct
from pathlib import Path
from collections import Counter

def check_credit_records_in_frames(replay_dir: str):
    """Check which frame files contain credit records"""

    replay_path = Path(replay_dir)
    frame_files = sorted(replay_path.glob('*.vgr'))

    print(f"Replay: {replay_path.name}")
    print(f"Total frame files: {len(frame_files)}\n")

    credit_header = bytes([0x10, 0x04, 0x1D])

    for i, frame_file in enumerate(frame_files[:10]):  # Check first 10 frames
        data = frame_file.read_bytes()
        count = data.count(credit_header)

        print(f"Frame {i} ({frame_file.name}): {len(data):,} bytes, {count} credit records")

        if count > 0:
            # Parse first few
            pos = 0
            for _ in range(min(5, count)):
                pos = data.find(credit_header, pos)
                if pos == -1:
                    break

                if pos + 12 <= len(data):
                    eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                    value = struct.unpack('>f', data[pos+7:pos+11])[0]
                    action = data[pos+11]

                    entity_type = "player" if 50000 <= eid_be <= 60000 else "structure" if 1000 <= eid_be <= 20000 else "other"
                    print(f"  eid={eid_be:5d} ({entity_type}), value={value:8.2f}, action=0x{action:02X}")

                pos += 1

def main():
    # Check first tournament match
    match1_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays/SFC vs Team Stooopid (Semi)/1")

    if match1_dir.exists():
        check_credit_records_in_frames(str(match1_dir))
    else:
        print(f"Directory not found: {match1_dir}")

if __name__ == '__main__':
    main()
