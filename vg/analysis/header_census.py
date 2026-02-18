#!/usr/bin/env python3
"""
Header Census - Comprehensive survey of all event headers across replay files.

Scans for all 3-byte headers of the form [XX 04 YY] in replay frame data
and produces a frequency table with payload analysis.

Usage:
    python -m vg.analysis.header_census [replay_dir] [-n 5]
"""

import argparse
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

# Known decoded headers
KNOWN_HEADERS = {
    (0x08, 0x04, 0x31): "Death event",
    (0x18, 0x04, 0x1C): "Kill event",
    (0x10, 0x04, 0x1D): "Credit/gold record",
    (0x10, 0x04, 0x3D): "Item acquire",
    (0x10, 0x04, 0x4B): "Item equip",
    (0x18, 0x04, 0x3E): "Player heartbeat (~32B)",
    (0x28, 0x04, 0x3F): "Player action (~48B)",
    (0x18, 0x04, 0x1E): "Entity state",
    (0x18, 0x04, 0x8A): "Ability unlock",
    (0x68, 0x04, 0x5C): "Entity snapshot (4448B)",
    (0x10, 0x04, 0x8C): "Structure event",
}

PLAYER_EID_RANGE = range(1500, 1510)


def find_replays(directory: Path) -> list:
    replays = []
    for f in sorted(directory.rglob('*.0.vgr')):
        if f.name.startswith('._'):
            continue
        replays.append(f)
    return replays


def load_frames(replay_path: Path) -> list:
    """Load all frames (skip frame 0 = metadata)."""
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]
    frame_files = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def idx(p):
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0

    frame_files.sort(key=idx)
    frames = []
    for f in frame_files:
        fi = idx(f)
        if fi == 0:
            continue
        frames.append((fi, f.read_bytes()))
    return frames


def scan_headers(data: bytes) -> Counter:
    """Scan for all [XX 04 YY] headers. Returns Counter of (b0, 0x04, b2) tuples."""
    counts = Counter()
    for i in range(len(data) - 2):
        if data[i + 1] == 0x04:
            header = (data[i], 0x04, data[i + 2])
            counts[header] += 1
    return counts


def analyze_header(data: bytes, header: tuple) -> dict:
    """Analyze a specific header: payload estimation, entity ID check, timestamp check."""
    h_bytes = bytes(header)
    positions = []
    pos = 0
    while len(positions) < 200:
        idx = data.find(h_bytes, pos)
        if idx == -1:
            break
        positions.append(idx)
        pos = idx + 1

    if len(positions) < 2:
        return {
            'avg_spacing': 0,
            'player_eid_pct': 0,
            'has_timestamps': False,
            'example_hex': '',
        }

    # Average spacing between consecutive occurrences
    spacings = [positions[i+1] - positions[i] for i in range(len(positions) - 1)]
    avg_spacing = sum(spacings) / len(spacings) if spacings else 0

    # Check entity ID field (bytes +5,+6 as uint16 BE)
    player_eid_count = 0
    ts_count = 0
    for p in positions[:100]:
        if p + 13 <= len(data):
            eid = struct.unpack_from(">H", data, p + 5)[0]
            if eid in PLAYER_EID_RANGE:
                player_eid_count += 1
            # Check for float32 timestamps at common offsets (+7, +9)
            for off in [7, 9]:
                if p + off + 4 <= len(data):
                    val = struct.unpack_from(">f", data, p + off)[0]
                    if 10 < val < 3000:
                        ts_count += 1
                        break

    n = min(len(positions), 100)
    example_pos = positions[0]
    end = min(example_pos + 19, len(data))
    example_hex = data[example_pos:end].hex(' ')

    return {
        'avg_spacing': round(avg_spacing, 1),
        'player_eid_pct': round(player_eid_count / n * 100, 1) if n else 0,
        'has_timestamps': ts_count > n * 0.3,
        'example_hex': example_hex,
    }


def run_census(replay_dir: str, max_replays: int = 5):
    dir_path = Path(replay_dir)
    replays = find_replays(dir_path)

    if not replays:
        print(f"No replays found in {replay_dir}")
        return

    replays = replays[:max_replays]
    print(f"Scanning {len(replays)} replays for event headers...\n")

    global_counts = Counter()
    per_replay = defaultdict(set)  # header -> set of replay indices
    all_data_sample = b""  # Use first replay data for analysis

    for ri, replay in enumerate(replays):
        print(f"  [{ri+1}/{len(replays)}] {replay.parent.name}/{replay.stem}")
        frames = load_frames(replay)
        data = b"".join(d for _, d in frames)
        if ri == 0:
            all_data_sample = data

        counts = scan_headers(data)
        for header, cnt in counts.items():
            global_counts[header] += cnt
            per_replay[header].add(ri)

    # Analyze each header
    print(f"\nAnalyzing {len(global_counts)} unique headers...")
    results = []
    for header, total_count in global_counts.most_common():
        known = KNOWN_HEADERS.get(header)
        status = "DECODED" if known else "UNKNOWN"
        purpose = known or ""

        analysis = {}
        if all_data_sample:
            analysis = analyze_header(all_data_sample, header)

        results.append({
            'header': header,
            'header_hex': f"{header[0]:02X} {header[1]:02X} {header[2]:02X}",
            'total_count': total_count,
            'avg_per_replay': round(total_count / len(replays), 1),
            'replays_present': len(per_replay[header]),
            'status': status,
            'purpose': purpose,
            'avg_spacing': analysis.get('avg_spacing', 0),
            'player_eid_pct': analysis.get('player_eid_pct', 0),
            'has_timestamps': analysis.get('has_timestamps', False),
            'example_hex': analysis.get('example_hex', ''),
        })

    # Print table
    print(f"\n{'='*110}")
    print(f"  EVENT HEADER CENSUS ({len(replays)} replays, {len(results)} unique headers)")
    print(f"{'='*110}")
    print(f"  {'Header':>12s} {'Count':>8s} {'Avg/Rep':>8s} {'#Rep':>5s} {'AvgSpc':>7s} {'PlrEID%':>8s} {'TS?':>4s}  {'Status':>8s}  Purpose")
    print(f"  {'─'*105}")

    decoded_count = 0
    unknown_count = 0
    for r in results:
        ts_mark = 'Y' if r['has_timestamps'] else ''
        tag = r['status']
        if tag == "DECODED":
            decoded_count += 1
        else:
            unknown_count += 1
        print(f"  {r['header_hex']:>12s} {r['total_count']:>8d} {r['avg_per_replay']:>8.1f} {r['replays_present']:>5d}"
              f" {r['avg_spacing']:>7.1f} {r['player_eid_pct']:>7.1f}% {ts_mark:>4s}  {tag:>8s}  {r['purpose']}")

    print(f"\n  Summary: {decoded_count} decoded, {unknown_count} unknown, {len(results)} total")

    # Highlight interesting unknowns
    interesting = [r for r in results
                   if r['status'] == 'UNKNOWN'
                   and r['total_count'] > 100
                   and r['replays_present'] == len(replays)]
    if interesting:
        print(f"\n  Interesting UNKNOWN headers (>100 count, present in all replays):")
        print(f"  {'─'*90}")
        for r in interesting[:10]:
            print(f"    {r['header_hex']}  count={r['total_count']:>7d}  spacing={r['avg_spacing']:.0f}B"
                  f"  playerEID={r['player_eid_pct']:.0f}%  ts={'Y' if r['has_timestamps'] else 'N'}")
            print(f"      example: {r['example_hex']}")


def main():
    parser = argparse.ArgumentParser(description='Event header census across VGR replays')
    parser.add_argument(
        'replay_dir', nargs='?',
        default=r'D:\Desktop\My Folder\Game\VG\vg replay',
        help='Directory containing replay files'
    )
    parser.add_argument(
        '-n', '--num-replays', type=int, default=5,
        help='Number of replays to scan (default: 5)'
    )
    args = parser.parse_args()

    run_census(args.replay_dir, args.num_replays)


if __name__ == '__main__':
    main()
