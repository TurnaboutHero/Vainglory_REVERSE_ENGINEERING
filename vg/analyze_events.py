from pathlib import Path

replay_path = Path(r'D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test')
files = sorted(replay_path.glob('*.vgr'))

# Load frame by frame to track timing
frame_data = []
for f in files:
    with open(f, 'rb') as fp:
        frame_data.append(fp.read())

all_data = b''.join(frame_data)

# Calculate where each frame starts in the combined data
frame_offsets = []
offset = 0
for d in frame_data:
    frame_offsets.append(offset)
    offset += len(d)

def get_frame(pos):
    for i, off in enumerate(frame_offsets):
        if i + 1 < len(frame_offsets):
            if off <= pos < frame_offsets[i+1]:
                return i
        else:
            if pos >= off:
                return i
    return -1

# Find events occurring exactly 5 times (Item Purchase count)
print('=== Events Occurring EXACTLY 5 Times ===')
print('Items: 단검, 고서, 강철대검, 표창, 비탄의 도끼\n')

from collections import Counter
event_counter = Counter()
event_positions = {}

for i in range(len(all_data) - 5):
    if all_data[i+1] == 0 and all_data[i+2] == 0 and all_data[i+3] == 0:
        entity = all_data[i]
        code = all_data[i+4]
        key = (entity, code)
        event_counter[key] += 1
        if key not in event_positions:
            event_positions[key] = []
        event_positions[key].append(i)

# Show all events with exactly 5 occurrences, along with their frames
print('Entity | Code | Frames')
print('-------|------|-------')
for (entity, code), count in sorted(event_counter.items()):
    if count == 5:
        positions = event_positions[(entity, code)]
        frames = [get_frame(p) for p in positions]
        print(f'{entity:6} | 0x{code:02X} | {frames}')

# Focus on Entity 0 events (likely global/player events)
print('\n=== Entity 0 Events with 5 occurrences ===')
for (entity, code), count in sorted(event_counter.items()):
    if count == 5 and entity == 0:
        positions = event_positions[(entity, code)]
        frames = [get_frame(p) for p in positions]
        payloads = []
        for p in positions:
            payload = all_data[p+5:p+13]
            payloads.append(' '.join(f'{b:02X}' for b in payload[:4]))
        print(f'Code 0x{code:02X}: Frames={frames}')
        for i, pay in enumerate(payloads):
            print(f'  Event {i+1}: {pay}')
