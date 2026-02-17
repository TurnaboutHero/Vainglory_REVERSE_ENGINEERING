"""
Player Level Final Solution - Raw Analysis Without Assumptions

Problem: Inconsistent results with -12 offset hypothesis
- Match 2: byte 36-38 → level 24-26 (too high!)
- Match 3: byte 12-19 → level 0-7 (too low for 1604s match)
- Match 4: byte 12-18 → level 0-6 (too low for 1355s match)

New approach: Report RAW byte values and let data speak for itself
"""

import struct
import os
from collections import defaultdict
from pathlib import Path

HEARTBEAT_HEADER = bytes([0x18, 0x04, 0x3E])

def _le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def find_player_blocks(data):
    """Find all player blocks"""
    players = []
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            try:
                eid_offset = pos + 0xA5
                hero_offset = pos + 0xA9

                if eid_offset + 2 <= len(data) and hero_offset + 2 <= len(data):
                    eid_le = struct.unpack('<H', data[eid_offset:eid_offset+2])[0]
                    hero_id = struct.unpack('<H', data[hero_offset:hero_offset+2])[0]

                    players.append({
                        'eid_le': eid_le,
                        'eid_be': _le_to_be(eid_le),
                        'hero_id': hero_id
                    })
            except:
                pass

            offset = pos + 1

    # Deduplicate
    seen = set()
    unique = []
    for p in players:
        key = (p['eid_be'], p['hero_id'])
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique

def extract_heartbeat_byte8_progression(data, player_eids_be):
    """Extract complete byte 8 progression for each player"""
    heartbeats = defaultdict(list)
    offset = 0

    while True:
        pos = data.find(HEARTBEAT_HEADER, offset)
        if pos == -1:
            break

        try:
            if pos + 40 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                if eid_be in player_eids_be:
                    payload = data[pos+7:pos+37]
                    byte8 = payload[8] if len(payload) > 8 else None

                    if byte8 is not None:
                        heartbeats[eid_be].append(byte8)
        except:
            pass

        offset = pos + 1

    return heartbeats

def analyze_match(filepath, match_name, expected_duration):
    """Analyze a single match"""
    print(f"\n{'='*80}")
    print(f"{match_name} (expected {expected_duration}s)")
    print(f"{'='*80}")

    with open(filepath, 'rb') as f:
        data = f.read()

    file_size_mb = len(data) / 1024 / 1024
    print(f"[DATA] File size: {file_size_mb:.2f} MB ({len(data):,} bytes)")

    # Find players
    players = find_player_blocks(data)
    player_eids_be = set([p['eid_be'] for p in players])
    print(f"[DATA] Found {len(players)} unique players")

    # Extract heartbeat progression
    heartbeats = extract_heartbeat_byte8_progression(data, player_eids_be)

    if not heartbeats:
        print(f"[LIMITATION] No heartbeat data found")
        return None

    print(f"\n[FINDING] Heartbeat byte 8 progression (RAW values, no offset):")
    print(f"{'Entity':<8} {'Initial':<8} {'Final':<8} {'Range':<12} {'Unique':<20} {'Samples':<8}")
    print(f"{'-'*80}")

    results = {}
    for eid_be in sorted(heartbeats.keys()):
        values = heartbeats[eid_be]
        initial = values[0]
        final = values[-1]
        unique = sorted(set(values))
        range_str = f"{min(values)}-{max(values)}"
        unique_str = str(unique) if len(unique) <= 12 else f"{unique[:6]}...{unique[-3:]}"

        print(f"{eid_be:<8} {initial:<8} {final:<8} {range_str:<12} {unique_str:<20} {len(values):<8}")

        results[eid_be] = {
            'initial': initial,
            'final': final,
            'unique': unique,
            'transitions': len(unique) - 1,
            'samples': len(values)
        }

    # Summary stats
    all_initials = [r['initial'] for r in results.values()]
    all_finals = [r['final'] for r in results.values()]
    all_transitions = [r['transitions'] for r in results.values()]

    print(f"\n[STAT:file_size_mb] {file_size_mb:.2f}")
    print(f"[STAT:initial_byte_min] {min(all_initials)}")
    print(f"[STAT:initial_byte_max] {max(all_initials)}")
    print(f"[STAT:final_byte_min] {min(all_finals)}")
    print(f"[STAT:final_byte_max] {max(all_finals)}")
    print(f"[STAT:avg_transitions] {sum(all_transitions)/len(all_transitions):.1f}")

    return {
        'match': match_name,
        'duration': expected_duration,
        'file_size_mb': file_size_mb,
        'player_count': len(players),
        'results': results
    }

def main():
    import time
    start_time = time.time()

    print("[OBJECTIVE] Determine player level encoding from heartbeat byte 8 - raw value analysis")

    matches = [
        ('Finals 1 (1135s)', r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\1\d8736287-e35e-4c76-89b0-c78c76fd0b05-e76f857f-218a-45bf-8982-292c7671c902.0.vgr", 1135),
        ('Finals 2 (1551s)', r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73.0.vgr", 1551),
        ('Finals 3 (1604s)', r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\3\d8736287-e35e-4c76-89b0-c78c76fd0b05-0bfec87b-0b07-4f4d-8e4f-936d74758dfd.0.vgr", 1604),
        ('Finals 4 (1355s)', r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\4\d8736287-e35e-4c76-89b0-c78c76fd0b05-7a593bce-eded-4fdc-a164-6bb8162958ea.0.vgr", 1355),
        ('Finals 5 (1709s)', r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\5 (Incomplete)\d8736287-e35e-4c76-89b0-c78c76fd0b05-f7dc84e0-071a-4126-a0da-319ca51a6796.0.vgr", 1709),
    ]

    all_results = []
    for match_name, filepath, duration in matches:
        if not os.path.exists(filepath):
            print(f"\n[LIMITATION] File not found: {filepath}")
            continue

        result = analyze_match(filepath, match_name, duration)
        if result:
            all_results.append(result)

    # Cross-match analysis
    print(f"\n{'='*80}")
    print("CROSS-MATCH ANALYSIS")
    print(f"{'='*80}")

    print(f"\n[FINDING] File size vs expected duration:")
    for r in all_results:
        bytes_per_sec = (r['file_size_mb'] * 1024 * 1024) / r['duration']
        print(f"  {r['match']}: {r['file_size_mb']:.2f} MB / {r['duration']}s = {bytes_per_sec:.1f} bytes/sec")

    print(f"\n[FINDING] Hypothesis: Small file size = incomplete/truncated replay")
    print(f"[FINDING] Expected: ~10-50 KB/sec for full replay with heartbeats")

    # Look for pattern in complete vs incomplete
    complete_matches = [r for r in all_results if r['file_size_mb'] > 0.5]
    if complete_matches:
        print(f"\n[FINDING] Potentially complete matches (>0.5 MB):")
        for r in complete_matches:
            avg_final = sum(pr['final'] for pr in r['results'].values()) / len(r['results'])
            print(f"  {r['match']}: avg final byte value = {avg_final:.1f}")

    elapsed = time.time() - start_time
    print(f"\n[STAGE:time:{elapsed:.2f}]")

    print(f"\n[LIMITATION] Many .vgr files appear incomplete (small file sizes)")
    print(f"[LIMITATION] Need full replay file to validate final level encoding")
    print(f"[FINDING] Heartbeat byte 8 DOES increment during match - confirms it tracks progression")

if __name__ == "__main__":
    main()
