#!/usr/bin/env python3
"""
Item Deep Probe - 0xBC 이벤트 심층 바이너리 분석
Vainglory 리플레이에서 아이템 구매 이벤트의 바이너리 구조를 정밀 탐색한다.

이전 분석(item_id_linker.py) 결과:
- 0xBC (Entity 0) = 아이템 구매 이벤트 (5개 이벤트 = 5개 구매)
- 페이로드에 아이템 ID (101-423)가 직접 포함되지 않음
- Frame 0의 0xBC 2개 이벤트는 동일한 페이로드 -> 0xBC만으로는 아이템 구분 불가
- 아이템 ID는 바이너리에 2바이트 LE로 존재하나 노이즈가 많음
- 0x3D (Entity 0)도 정확히 5회 발생 (frames [3,5,5,5,6])
"""

import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple

# === Core module import ===
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_mapping import ITEM_ID_MAP

# ─────────────────────────────────────────────────────────
# Constants / 상수 정의
# ─────────────────────────────────────────────────────────

ENTITY_0_PREFIX = b'\x00\x00\x00\x00'

KNOWN_PURCHASES = {
    0: [101, 102],   # Frame 0: Weapon Blade + Book of Eulogies
    5: [111, 103],   # Frame 5: Heavy Steel + Swift Shooter
    6: [121],        # Frame 6: Sorrowblade
}
PURCHASE_FRAMES = {0, 5, 6}
TEST_ITEM_IDS = {101, 102, 103, 111, 121}

# Item costs (gold)
ITEM_COSTS = {
    101: 300,   # Weapon Blade
    102: 300,   # Book of Eulogies
    103: 300,   # Swift Shooter
    111: 1150,  # Heavy Steel
    121: 3100,  # Sorrowblade
}
CUMULATIVE_GOLD = [300, 600, 1750, 2050, 5150]

DEFAULT_REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test")
OUTPUT_DIR = Path(__file__).parent.parent / 'output'
OUTPUT_TXT = OUTPUT_DIR / 'item_deep_probe_output.txt'

# ─────────────────────────────────────────────────────────
# Utilities / 유틸리티
# ─────────────────────────────────────────────────────────

def get_replay_info(replay_dir: Path) -> Tuple[str, List[Path]]:
    """Get replay name and sorted frame file list."""
    vgr_files = sorted(
        replay_dir.glob("*.vgr"),
        key=lambda p: int(p.stem.split('.')[-1])
    )
    if not vgr_files:
        raise FileNotFoundError(f"No .vgr files found in {replay_dir}")
    replay_name = '.'.join(vgr_files[0].stem.split('.')[:-1])
    return replay_name, vgr_files


def find_pattern_offsets(data: bytes, pattern: bytes) -> List[int]:
    """Find all occurrences of a byte pattern."""
    offsets = []
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        offsets.append(idx)
        idx += 1
    return offsets


def hex_dump_block(data: bytes, start_offset: int, length: int,
                   highlight_offsets: Optional[Dict[int, str]] = None,
                   base_addr: int = 0) -> str:
    """
    Produce a hex-editor style dump.
    highlight_offsets: {absolute_offset: label} for highlighting.
    base_addr: the absolute file offset of data[0].
    """
    lines = []
    highlight_offsets = highlight_offsets or {}
    end = min(length, len(data) - start_offset)
    chunk = data[start_offset:start_offset + end]

    for row_start in range(0, len(chunk), 16):
        row_bytes = chunk[row_start:row_start + 16]
        addr = base_addr + start_offset + row_start

        hex_parts = []
        ascii_parts = []
        annotations = []

        for i, b in enumerate(row_bytes):
            abs_off = base_addr + start_offset + row_start + i
            if abs_off in highlight_offsets:
                hex_parts.append(f"[{b:02X}]")
                annotations.append(f"  ^^^ {highlight_offsets[abs_off]} at 0x{abs_off:06X}")
            else:
                hex_parts.append(f" {b:02X}")

            if 32 <= b < 127:
                ascii_parts.append(chr(b))
            else:
                ascii_parts.append('.')

        hex_str = ''.join(hex_parts)
        ascii_str = ''.join(ascii_parts)
        lines.append(f"  {addr:08X}: {hex_str:<52s}  |{ascii_str}|")
        for ann in annotations:
            lines.append(ann)

    return '\n'.join(lines)


def float32_at(data: bytes, offset: int) -> Optional[float]:
    """Read a float32 (LE) at offset, or None if out of bounds."""
    if offset + 4 <= len(data):
        return struct.unpack('<f', data[offset:offset + 4])[0]
    return None


def uint16_at(data: bytes, offset: int) -> Optional[int]:
    if offset + 2 <= len(data):
        return struct.unpack('<H', data[offset:offset + 2])[0]
    return None


def uint32_at(data: bytes, offset: int) -> Optional[int]:
    if offset + 4 <= len(data):
        return struct.unpack('<I', data[offset:offset + 4])[0]
    return None


# ─────────────────────────────────────────────────────────
# Part 1: Deep hex dump around 0xBC events
# 0xBC 이벤트 주변 심층 hex 덤프
# ─────────────────────────────────────────────────────────

def part1_deep_hex_dump(replay_dir: Path) -> None:
    print("=" * 80)
    print("PART 1: Deep Hex Dump Around 0xBC Events")
    print("파트 1: 0xBC 이벤트 주변 심층 hex 덤프")
    print("=" * 80)
    print()
    print("For each 0xBC event (pattern 00 00 00 00 BC),")
    print("dump 500 bytes BEFORE and 200 bytes AFTER.")
    print("Highlight bytes matching known item IDs (101, 102, 103, 111, 121).")
    print()

    bc_pattern = b'\x00\x00\x00\x00\xBC'

    _, frame_files = get_replay_info(replay_dir)
    event_num = 0

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        offsets = find_pattern_offsets(data, bc_pattern)
        if not offsets:
            continue

        known_items = KNOWN_PURCHASES.get(frame_num, [])
        known_str = ', '.join(ITEM_ID_MAP[i]['name'] for i in known_items) if known_items else 'none'

        for bc_off in offsets:
            event_num += 1
            print(f"--- 0xBC Event #{event_num} | Frame {frame_num} | Offset 0x{bc_off:06X} ---")
            print(f"    Known purchases in this frame: {known_str}")
            print()

            # Build highlight map for item IDs as single bytes
            highlights = {}
            # Mark the 0xBC pattern itself
            for k in range(5):
                highlights[bc_off + k] = "0xBC_PATTERN"

            # Mark item IDs as 2-byte LE in the dump range
            dump_start = max(0, bc_off - 500)
            dump_end = min(len(data), bc_off + 5 + 200)
            region = data[dump_start:dump_end]

            for item_id in TEST_ITEM_IDS:
                id_2b = struct.pack('<H', item_id)
                pos = 0
                while True:
                    pos = region.find(id_2b, pos)
                    if pos == -1:
                        break
                    abs_pos = dump_start + pos
                    item_name = ITEM_ID_MAP[item_id]['name']
                    highlights[abs_pos] = f"ITEM {item_id} ({item_name}) [lo]"
                    highlights[abs_pos + 1] = f"ITEM {item_id} ({item_name}) [hi]"
                    pos += 1

            # Print hex dump
            print(f"  [500 bytes BEFORE 0xBC]")
            before_start = max(0, bc_off - 500)
            before_len = bc_off - before_start
            if before_len > 0:
                print(hex_dump_block(data, before_start, before_len,
                                     highlight_offsets=highlights, base_addr=0))

            print(f"\n  [0xBC event + 200 bytes AFTER]")
            after_len = min(205, len(data) - bc_off)
            print(hex_dump_block(data, bc_off, after_len,
                                 highlight_offsets=highlights, base_addr=0))
            print()


# ─────────────────────────────────────────────────────────
# Part 2: All Entity 0 events in purchase frames ONLY
# 구매 프레임 내 모든 Entity 0 이벤트
# ─────────────────────────────────────────────────────────

def part2_entity0_in_purchase_frames(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 2: All Entity 0 Events in Purchase Frames")
    print("파트 2: 구매 프레임 (0, 5, 6) 내 모든 Entity 0 이벤트")
    print("=" * 80)
    print()

    _, frame_files = get_replay_info(replay_dir)

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        if frame_num not in PURCHASE_FRAMES:
            continue

        data = frame_path.read_bytes()
        known_items = KNOWN_PURCHASES.get(frame_num, [])
        known_str = ', '.join(ITEM_ID_MAP[i]['name'] for i in known_items)

        print(f"\n--- Frame {frame_num} | Expected: {known_str} ---")
        print(f"    File size: {len(data)} bytes")
        print()

        # Find all Entity 0 events: pattern [00 00 00 00][ActionType]
        action_counts: Counter = Counter()
        action_events: Dict[int, List[Dict]] = defaultdict(list)

        offsets = find_pattern_offsets(data, ENTITY_0_PREFIX)
        for off in offsets:
            if off + 5 > len(data):
                continue
            action = data[off + 4]
            payload_start = off + 5
            payload_end = min(payload_start + 48, len(data))
            payload = data[payload_start:payload_end]

            action_counts[action] += 1
            action_events[action].append({
                'offset': off,
                'payload': payload,
            })

        # Print action type summary
        print(f"  Action Type Summary (total unique: {len(action_counts)}):")
        print(f"  {'Action':<10s} {'Count':>6s}  Note")
        print(f"  {'-'*10} {'-'*6}  {'-'*30}")
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1]):
            note = ""
            if action == 0xBC:
                note = "<-- ITEM PURCHASE EVENT"
            elif action == 0x3D:
                note = "<-- RELATED? (5 total in replay)"
            print(f"  0x{action:02X}       {count:6d}  {note}")

        # Dump rare events (count < 20)
        print(f"\n  Rare events (count < 20) with full payloads:")
        for action, count in sorted(action_counts.items()):
            if count >= 20:
                continue
            evts = action_events[action]
            print(f"\n    Action 0x{action:02X} ({count} events):")
            for i, evt in enumerate(evts):
                payload_hex = ' '.join(f'{b:02X}' for b in evt['payload'][:48])
                print(f"      [{i}] @ 0x{evt['offset']:06X}: {payload_hex}")

        print()


# ─────────────────────────────────────────────────────────
# Part 3: Binary structure diff between 0xBC payloads
# 0xBC 페이로드 바이트별 비교 분석
# ─────────────────────────────────────────────────────────

def part3_payload_diff(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 3: Binary Structure Diff Between 0xBC Payloads")
    print("파트 3: 0xBC 페이로드 바이트별 비교 (변동 vs 고정)")
    print("=" * 80)
    print()

    bc_pattern = b'\x00\x00\x00\x00\xBC'
    _, frame_files = get_replay_info(replay_dir)

    # Collect all 5 payloads
    payloads: List[Tuple[int, bytes]] = []  # (frame, payload)
    purchase_labels = {
        0: ["Weapon Blade (300g)", "Book of Eulogies (300g)"],
        5: ["Heavy Steel (1150g)", "Swift Shooter (300g)"],
        6: ["Sorrowblade (3100g)"],
    }

    label_idx = 0
    all_labels = []
    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        offsets = find_pattern_offsets(data, bc_pattern)
        frame_labels = purchase_labels.get(frame_num, [])
        for i, off in enumerate(offsets):
            payload_start = off + 5
            payload_end = min(payload_start + 48, len(data))
            payload = data[payload_start:payload_end]
            label = frame_labels[i] if i < len(frame_labels) else f"Unknown #{label_idx}"
            payloads.append((frame_num, payload))
            all_labels.append(f"Evt{label_idx} F{frame_num}: {label}")
            label_idx += 1

    if len(payloads) < 2:
        print("  Not enough 0xBC payloads to compare.")
        return

    # Print all payloads aligned
    max_len = max(len(p[1]) for p in payloads)
    print("  All 0xBC payloads (hex):")
    for i, (frame, payload) in enumerate(payloads):
        hex_str = ' '.join(f'{b:02X}' for b in payload)
        print(f"    {all_labels[i]}")
        print(f"      {hex_str}")
    print()

    # Byte-by-byte diff
    print("  Byte-by-byte comparison:")
    print(f"  {'Offset':<8s}", end='')
    for i in range(len(payloads)):
        print(f"  {'Evt'+str(i):>6s}", end='')
    print("   Status     float32_interpretation")
    print(f"  {'------':<8s}", end='')
    for _ in range(len(payloads)):
        print(f"  {'------':>6s}", end='')
    print("   ------     ----------------------")

    changing_bytes = []
    constant_bytes = []

    for byte_off in range(max_len):
        values = []
        for _, payload in payloads:
            if byte_off < len(payload):
                values.append(payload[byte_off])
            else:
                values.append(None)

        unique = set(v for v in values if v is not None)
        is_changing = len(unique) > 1
        status = "CHANGE" if is_changing else "const"

        if is_changing:
            changing_bytes.append(byte_off)
        else:
            constant_bytes.append(byte_off)

        # Float interpretation at 4-byte aligned offsets
        float_str = ""
        if byte_off % 4 == 0:
            float_vals = []
            for _, payload in payloads:
                fv = float32_at(payload, byte_off)
                if fv is not None:
                    float_vals.append(f"{fv:.4f}")
                else:
                    float_vals.append("N/A")
            float_str = " | ".join(float_vals)

        print(f"  [{byte_off:3d}]   ", end='')
        for v in values:
            if v is not None:
                print(f"    {v:02X}", end='')
            else:
                print(f"    --", end='')
        print(f"   {status:<10s} {float_str}")

    print(f"\n  Summary:")
    print(f"    Changing byte offsets: {changing_bytes}")
    print(f"    Constant byte offsets: {constant_bytes[:30]}{'...' if len(constant_bytes) > 30 else ''}")
    print(f"    Total: {len(changing_bytes)} changing, {len(constant_bytes)} constant out of {max_len}")

    # Float32 at each 4-byte offset
    print(f"\n  Float32 at each 4-byte aligned offset:")
    print(f"  {'Offset':<8s}", end='')
    for i in range(len(payloads)):
        print(f"  {'Evt'+str(i):>14s}", end='')
    print()

    for byte_off in range(0, max_len - 3, 4):
        print(f"  [{byte_off:3d}]   ", end='')
        for _, payload in payloads:
            fv = float32_at(payload, byte_off)
            if fv is not None:
                print(f"  {fv:14.6f}", end='')
            else:
                print(f"  {'N/A':>14s}", end='')
        print()


# ─────────────────────────────────────────────────────────
# Part 4: Search for gold costs
# 골드 비용 검색
# ─────────────────────────────────────────────────────────

def part4_gold_search(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 4: Search for Gold Costs in Binary")
    print("파트 4: 골드 비용 값 검색 (2B LE, 4B LE, float32)")
    print("=" * 80)
    print()

    _, frame_files = get_replay_info(replay_dir)

    individual_costs = sorted(set(ITEM_COSTS.values()))
    cumulative_costs = CUMULATIVE_GOLD

    print(f"  Individual item costs: {individual_costs}")
    print(f"  Cumulative gold totals: {cumulative_costs}")
    print()

    all_costs = sorted(set(individual_costs + cumulative_costs))

    # Search in each frame
    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        print(f"  --- Frame {frame_num} ({len(data)} bytes) ---")

        for gold_val in all_costs:
            results = []

            # 2-byte LE
            if gold_val <= 0xFFFF:
                pattern_2b = struct.pack('<H', gold_val)
                hits_2b = find_pattern_offsets(data, pattern_2b)
                if hits_2b:
                    results.append(f"2B_LE: {len(hits_2b)} hits @ {[f'0x{o:06X}' for o in hits_2b[:8]]}")

            # 4-byte LE
            pattern_4b = struct.pack('<I', gold_val)
            hits_4b = find_pattern_offsets(data, pattern_4b)
            if hits_4b:
                results.append(f"4B_LE: {len(hits_4b)} hits @ {[f'0x{o:06X}' for o in hits_4b[:8]]}")

            # float32
            pattern_f = struct.pack('<f', float(gold_val))
            hits_f = find_pattern_offsets(data, pattern_f)
            if hits_f:
                results.append(f"float32: {len(hits_f)} hits @ {[f'0x{o:06X}' for o in hits_f[:8]]}")

            if results:
                print(f"    Gold {gold_val:5d}: {' | '.join(results)}")

    # Also search INSIDE 0xBC payloads specifically
    print(f"\n  --- Gold search within 0xBC payloads ---")
    bc_pattern = b'\x00\x00\x00\x00\xBC'
    evt_idx = 0
    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        offsets = find_pattern_offsets(data, bc_pattern)

        for off in offsets:
            payload = data[off + 5:off + 5 + 48]
            print(f"\n    0xBC Event #{evt_idx} (Frame {frame_num}):")

            for gold_val in all_costs:
                found_in = []
                # 2-byte LE
                if gold_val <= 0xFFFF:
                    p2 = struct.pack('<H', gold_val)
                    pos = payload.find(p2)
                    if pos != -1:
                        found_in.append(f"2B_LE @ payload[{pos}]")
                # 4-byte LE
                p4 = struct.pack('<I', gold_val)
                pos = payload.find(p4)
                if pos != -1:
                    found_in.append(f"4B_LE @ payload[{pos}]")
                # float32
                pf = struct.pack('<f', float(gold_val))
                pos = payload.find(pf)
                if pos != -1:
                    found_in.append(f"float32 @ payload[{pos}]")

                if found_in:
                    print(f"      Gold {gold_val:5d}: {', '.join(found_in)}")

            evt_idx += 1


# ─────────────────────────────────────────────────────────
# Part 5: Search for sequential item indices
# 순차적 아이템 인덱스 탐색
# ─────────────────────────────────────────────────────────

def part5_sequential_indices(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 5: Search for Sequential Item Indices")
    print("파트 5: 순차적 아이템 인덱스 탐색 (0-based)")
    print("=" * 80)
    print()
    print("  Hypothesis: items use 0-based or 1-based indices instead of 101-423.")
    print("  Look for small integers 0-9 at specific payload offsets.")
    print("  Check for counting pattern (purchase #1 = 0, #2 = 1, etc.)")
    print()

    bc_pattern = b'\x00\x00\x00\x00\xBC'
    _, frame_files = get_replay_info(replay_dir)

    payloads: List[Tuple[int, int, bytes]] = []  # (event_idx, frame, payload)
    evt_idx = 0
    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        offsets = find_pattern_offsets(data, bc_pattern)
        for off in offsets:
            payload = data[off + 5:off + 5 + 48]
            payloads.append((evt_idx, frame_num, payload))
            evt_idx += 1

    if not payloads:
        print("  No 0xBC events found.")
        return

    # Check each byte position for small integer patterns
    max_len = max(len(p[2]) for p in payloads)

    print("  Values at each payload offset across all 5 events:")
    print(f"  {'Off':<5s}", end='')
    for i in range(len(payloads)):
        print(f"  Evt{i}", end='')
    print("   Sequential?  uint16_LE")

    for byte_off in range(min(max_len, 48)):
        values = []
        for _, _, payload in payloads:
            if byte_off < len(payload):
                values.append(payload[byte_off])
            else:
                values.append(None)

        # Check if sequential (0,1,2,3,4 or 1,2,3,4,5)
        valid_vals = [v for v in values if v is not None]
        is_sequential = False
        seq_note = ""
        if len(valid_vals) == len(payloads):
            for start in range(10):
                expected = list(range(start, start + len(payloads)))
                if valid_vals == expected:
                    is_sequential = True
                    seq_note = f"YES ({start}-based)"
                    break
            # Also check monotonic increasing (not necessarily +1)
            if not is_sequential and all(valid_vals[i] <= valid_vals[i+1] for i in range(len(valid_vals)-1)):
                if valid_vals[0] != valid_vals[-1]:
                    seq_note = f"monotonic {valid_vals}"

        # uint16 LE at this offset
        u16_vals = []
        for _, _, payload in payloads:
            u16 = uint16_at(payload, byte_off)
            u16_vals.append(str(u16) if u16 is not None else "N/A")

        # Only print if interesting (small values or sequential)
        has_small = any(v is not None and v < 20 for v in values)
        if has_small or is_sequential or seq_note:
            print(f"  [{byte_off:3d}]", end='')
            for v in values:
                if v is not None:
                    print(f"  {v:4d}", end='')
                else:
                    print(f"    --", end='')
            u16_str = ','.join(u16_vals[:3]) + "..."
            print(f"   {seq_note:<15s} u16={u16_str}")

    # Check the first 4 bytes as float - maybe they encode a purchase index?
    print(f"\n  Float32 at offset 0 (purchase order hypothesis):")
    for evt_idx, frame_num, payload in payloads:
        fv = float32_at(payload, 0)
        uv = uint32_at(payload, 0)
        print(f"    Event {evt_idx} (Frame {frame_num}): float={fv:.6f}  uint32={uv}  hex={' '.join(f'{b:02X}' for b in payload[:4])}")


# ─────────────────────────────────────────────────────────
# Part 6: Frame-to-frame diff
# 프레임 간 바이너리 비교
# ─────────────────────────────────────────────────────────

def part6_frame_diff(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 6: Frame-to-Frame Binary Diff")
    print("파트 6: 프레임 간 바이너리 비교 (Frame 0 vs Frame 5)")
    print("=" * 80)
    print()

    _, frame_files = get_replay_info(replay_dir)

    frame_data: Dict[int, bytes] = {}
    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        frame_data[frame_num] = frame_path.read_bytes()

    if 0 not in frame_data or 5 not in frame_data:
        print("  Frame 0 or Frame 5 not found.")
        return

    d0 = frame_data[0]
    d5 = frame_data[5]

    print(f"  Frame 0 size: {len(d0)} bytes")
    print(f"  Frame 5 size: {len(d5)} bytes")
    print()

    # Find 4-byte sequences in Frame 5 but NOT in Frame 0
    # Focus on patterns related to item IDs 111 and 103
    target_items = {111: "Heavy Steel", 103: "Swift Shooter"}

    for item_id, item_name in target_items.items():
        print(f"\n  --- Searching for item {item_id} ({item_name}) patterns ---")

        # 2-byte LE
        id_2b = struct.pack('<H', item_id)
        offsets_f0 = set(find_pattern_offsets(d0, id_2b))
        offsets_f5 = set(find_pattern_offsets(d5, id_2b))
        new_in_f5 = offsets_f5 - offsets_f0

        print(f"    2B LE (0x{item_id:04X}): Frame0={len(offsets_f0)}, Frame5={len(offsets_f5)}, NEW in F5={len(new_in_f5)}")

        if new_in_f5:
            for off in sorted(new_in_f5)[:10]:
                context_start = max(0, off - 8)
                context_end = min(len(d5), off + 10)
                ctx = d5[context_start:context_end]
                ctx_hex = ' '.join(f'{b:02X}' for b in ctx)
                rel = off - context_start
                print(f"      NEW @ 0x{off:06X}: {ctx_hex}  (item bytes at position {rel}-{rel+1})")

    # General new byte patterns: find 8-byte windows unique to Frame 5
    print(f"\n  --- Unique 8-byte sequences in Frame 5 near Entity 0 events ---")
    # Collect Entity 0 event offsets in Frame 5
    e0_offsets_f5 = find_pattern_offsets(d5, ENTITY_0_PREFIX)

    for e0_off in e0_offsets_f5:
        if e0_off + 5 > len(d5):
            continue
        action = d5[e0_off + 4]
        # Check if this exact 5-byte pattern (entity+action) exists in Frame 0
        pattern5 = d5[e0_off:e0_off + 5]
        count_in_f0 = d0.count(pattern5)
        count_in_f5 = d5.count(pattern5)

        if count_in_f5 > count_in_f0:
            diff_count = count_in_f5 - count_in_f0
            # Only report interesting differences
            if diff_count <= 5:
                payload = d5[e0_off + 5:e0_off + 5 + 20]
                payload_hex = ' '.join(f'{b:02X}' for b in payload)
                print(f"    Entity 0, Action 0x{action:02X}: F0={count_in_f0}, F5={count_in_f5} (+{diff_count})")
                print(f"      Sample payload: {payload_hex}")

    # Compare Frame 5 vs Frame 6 as well
    if 6 in frame_data:
        d6 = frame_data[6]
        print(f"\n  --- Frame 5 vs Frame 6 (Sorrowblade purchase in F6) ---")
        print(f"  Frame 6 size: {len(d6)} bytes")

        item_id = 121
        item_name = "Sorrowblade"
        id_2b = struct.pack('<H', item_id)
        offsets_f5_121 = set(find_pattern_offsets(d5, id_2b))
        offsets_f6_121 = set(find_pattern_offsets(d6, id_2b))
        new_in_f6 = offsets_f6_121 - offsets_f5_121

        print(f"    {item_name} (ID {item_id}) 2B LE: Frame5={len(offsets_f5_121)}, Frame6={len(offsets_f6_121)}, NEW in F6={len(new_in_f6)}")
        if new_in_f6:
            for off in sorted(new_in_f6)[:10]:
                context_start = max(0, off - 8)
                context_end = min(len(d6), off + 10)
                ctx = d6[context_start:context_end]
                ctx_hex = ' '.join(f'{b:02X}' for b in ctx)
                rel = off - context_start
                print(f"      NEW @ 0x{off:06X}: {ctx_hex}  (item bytes at position {rel}-{rel+1})")


# ─────────────────────────────────────────────────────────
# Part 7: Search for item IDs with context patterns
# 컨텍스트 패턴으로 아이템 ID 검색
# ─────────────────────────────────────────────────────────

def part7_item_id_context_search(replay_dir: Path) -> None:
    print()
    print("=" * 80)
    print("PART 7: Search for Item IDs with Context Patterns")
    print("파트 7: 컨텍스트 패턴을 사용한 아이템 ID 검색")
    print("=" * 80)
    print()
    print("  Search for item IDs preceded/followed by specific marker bytes.")
    print("  Check patterns after player block marker (DA 03 EE).")
    print()

    _, frame_files = get_replay_info(replay_dir)
    player_marker = bytes([0xDA, 0x03, 0xEE])

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        print(f"  --- Frame {frame_num} ({len(data)} bytes) ---")

        # Strategy A: Check for item IDs with specific preceding bytes
        # Common marker candidates: 00, 01, 02, FF, type tags
        print(f"\n    Strategy A: [marker_byte][item_id_2B_LE] patterns")
        for item_id in sorted(TEST_ITEM_IDS):
            id_2b = struct.pack('<H', item_id)
            item_name = ITEM_ID_MAP[item_id]['name']
            expected_in_frame = item_id in KNOWN_PURCHASES.get(frame_num, [])

            # Try each possible preceding byte
            preceding_hits: Dict[int, List[int]] = defaultdict(list)
            for off in find_pattern_offsets(data, id_2b):
                if off > 0:
                    prec = data[off - 1]
                    preceding_hits[prec].append(off)

            # Report preceding bytes that are consistent with expected items
            if expected_in_frame and preceding_hits:
                # Filter to preceding bytes with few occurrences (more specific)
                for prec_byte, offsets in sorted(preceding_hits.items()):
                    if len(offsets) <= 5:
                        off_str = ', '.join(f'0x{o:06X}' for o in offsets[:5])
                        print(f"      {item_name:15s} (ID {item_id}): "
                              f"prec=0x{prec_byte:02X} count={len(offsets)} @ {off_str}"
                              f"  {'<<< EXPECTED' if expected_in_frame else ''}")

        # Strategy B: Item IDs after player block marker (DA 03 EE)
        print(f"\n    Strategy B: Item IDs after player block marker (DA 03 EE)")
        marker_offsets = find_pattern_offsets(data, player_marker)
        print(f"    Player markers found: {len(marker_offsets)}")

        for m_off in marker_offsets:
            # Search the 500 bytes after the marker for item IDs
            search_region = data[m_off:m_off + 500]
            for item_id in sorted(TEST_ITEM_IDS):
                id_2b = struct.pack('<H', item_id)
                pos = 0
                while True:
                    pos = search_region.find(id_2b, pos)
                    if pos == -1:
                        break
                    abs_off = m_off + pos
                    item_name = ITEM_ID_MAP[item_id]['name']
                    expected = item_id in KNOWN_PURCHASES.get(frame_num, [])
                    context_start = max(0, pos - 4)
                    context_end = min(len(search_region), pos + 6)
                    ctx = search_region[context_start:context_end]
                    ctx_hex = ' '.join(f'{b:02X}' for b in ctx)
                    marker_text = " <<< EXPECTED" if expected else ""
                    print(f"      Marker@0x{m_off:06X} +{pos:4d}: {item_name:15s} (ID {item_id}) ctx={ctx_hex}{marker_text}")
                    pos += 1

        # Strategy C: Look for item IDs in pairs matching known purchases
        print(f"\n    Strategy C: Item ID pairs matching known purchases")
        known_items_this_frame = KNOWN_PURCHASES.get(frame_num, [])
        if len(known_items_this_frame) == 2:
            id1, id2 = known_items_this_frame
            id1_2b = struct.pack('<H', id1)
            id2_2b = struct.pack('<H', id2)
            name1 = ITEM_ID_MAP[id1]['name']
            name2 = ITEM_ID_MAP[id2]['name']

            # Find locations where both IDs appear within 50 bytes of each other
            offsets1 = find_pattern_offsets(data, id1_2b)
            offsets2 = find_pattern_offsets(data, id2_2b)

            pairs_found = 0
            for o1 in offsets1:
                for o2 in offsets2:
                    dist = abs(o2 - o1)
                    if 2 <= dist <= 50:
                        start = min(o1, o2)
                        end = max(o1, o2) + 2
                        region = data[max(0, start - 4):min(len(data), end + 4)]
                        region_hex = ' '.join(f'{b:02X}' for b in region)
                        print(f"      PAIR: {name1}@0x{o1:06X} + {name2}@0x{o2:06X} (dist={dist})")
                        print(f"        Context: {region_hex}")
                        pairs_found += 1
                        if pairs_found >= 10:
                            break
                if pairs_found >= 10:
                    break

            if pairs_found == 0:
                print(f"      No close pairs found for {name1} + {name2}")

        # Strategy D: Look for item IDs as 4-byte LE with specific following pattern
        print(f"\n    Strategy D: [item_id_4B_LE] with context analysis")
        for item_id in sorted(TEST_ITEM_IDS):
            id_4b = struct.pack('<I', item_id)
            item_name = ITEM_ID_MAP[item_id]['name']
            expected = item_id in KNOWN_PURCHASES.get(frame_num, [])

            offsets = find_pattern_offsets(data, id_4b)
            if offsets and expected:
                for off in offsets[:5]:
                    ctx_start = max(0, off - 4)
                    ctx_end = min(len(data), off + 12)
                    ctx = data[ctx_start:ctx_end]
                    ctx_hex = ' '.join(f'{b:02X}' for b in ctx)
                    print(f"      {item_name:15s} (ID {item_id}) 4B_LE @ 0x{off:06X}: {ctx_hex} <<< EXPECTED")

        print()


# ─────────────────────────────────────────────────────────
# Main / 메인 실행
# ─────────────────────────────────────────────────────────

def main() -> int:
    import io

    replay_dir = DEFAULT_REPLAY_DIR
    if not replay_dir.is_dir():
        print(f"Error: Directory not found: {replay_dir}")
        return 1

    # Tee output to both stdout and file
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    class TeeWriter:
        """Write to both stdout and a file."""
        def __init__(self, file_path: Path):
            self.file = open(file_path, 'w', encoding='utf-8')
            self.stdout = sys.stdout

        def write(self, text):
            self.stdout.write(text)
            self.file.write(text)

        def flush(self):
            self.stdout.flush()
            self.file.flush()

        def close(self):
            self.file.close()

    tee = TeeWriter(OUTPUT_TXT)
    sys.stdout = tee

    try:
        replay_name, frame_files = get_replay_info(replay_dir)

        print("=" * 80)
        print("Item Deep Probe - 아이템 구매 이벤트 심층 분석")
        print("=" * 80)
        print(f"  Replay: {replay_name}")
        print(f"  Directory: {replay_dir}")
        print(f"  Frames: {len(frame_files)}")
        print(f"  Known purchases: {KNOWN_PURCHASES}")
        print(f"  Item costs: {ITEM_COSTS}")
        print()

        # Run all parts
        part1_deep_hex_dump(replay_dir)
        part2_entity0_in_purchase_frames(replay_dir)
        part3_payload_diff(replay_dir)
        part4_gold_search(replay_dir)
        part5_sequential_indices(replay_dir)
        part6_frame_diff(replay_dir)
        part7_item_id_context_search(replay_dir)

        print()
        print("=" * 80)
        print("ANALYSIS COMPLETE / 분석 완료")
        print(f"Output saved to: {OUTPUT_TXT}")
        print("=" * 80)

    finally:
        sys.stdout = tee.stdout
        tee.close()

    print(f"\nOutput saved to: {OUTPUT_TXT}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
