
from pathlib import Path
import re
from collections import Counter

def analyze():
    # Load first frame
    replay_dir = Path(r'D:\Desktop\My Folder\Game\VG\vg replay\replay-test')
    frames = sorted(replay_dir.glob('*.vgr'), key=lambda x: int(x.stem.split('.')[-1]))
    
    if not frames:
        print("No replay files found!")
        return

    with open(frames[0], 'rb') as f:
        data = f.read()

    print(f"Analyzing {frames[0].name} ({len(data)} bytes)")

    # 1. Find Player Block (Marker: DA 03 EE)
    marker = bytes([0xDA, 0x03, 0xEE])
    
    player_positions = []
    pos = 0
    while True:
        pos = data.find(marker, pos)
        if pos == -1:
            break
        
        # Name is at pos+3
        try:
            name_chunk = data[pos+3:pos+33].split(b'\x00')[0]
            name = name_chunk.decode('ascii', errors='ignore')
            print(f"\nFound Player: {name} at 0x{pos:06X}")
            player_positions.append((name, pos))
            
            # Dump context
            context = data[pos:pos+100]
            print(f"  Context: {context.hex()}")
            
        except:
            pass
        pos += 3

    # 2. Find Active IDs in this replay
    print("\nScanning for Top Active Entity IDs...")
    
    # Read all frames combined
    all_data = b''
    for frame in frames:
        with open(frame, 'rb') as f:
            all_data += f.read()
            
    id_counts = Counter()
    for i in range(1, 256):
        pattern = bytes([i, 0, 0, 0])
        count = all_data.count(pattern)
        if count > 50:
            id_counts[i] = count
            
    print("\nTop Active IDs:")
    for i, count in id_counts.most_common(10):
        print(f"  ID {i}: {count} events")
        
    # 3. Correlation: Do active IDs appear in player blocks?
    print("\nCorrelation Check:")
    for name, pos in player_positions:
        # Check specific offsets relative to player block
        # Based on previous research + new hypothesis
        context = data[pos:pos+200]
        
        for i, count in id_counts.most_common(10):
            # Search for ID as byte or int
            cbytes = bytes([i])
            cint = bytes([i, 0, 0, 0])
            
            offset_byte = context.find(cbytes)
            offset_int = context.find(cint)
            
            if offset_byte != -1:
                print(f"  [{name}] contains ID {i} (Activity: {count}) at offset +{offset_byte} (Byte)")
            if offset_int != -1:
                print(f"  [{name}] contains ID {i} (Activity: {count}) at offset +{offset_int} (Int)")

if __name__ == "__main__":
    analyze()
