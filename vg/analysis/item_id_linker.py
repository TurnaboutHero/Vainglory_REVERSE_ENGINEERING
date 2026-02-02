#!/usr/bin/env python3
"""
Item ID Linker - 0xBC 이벤트와 아이템 ID 연결 분석
Vainglory 리플레이 바이너리에서 아이템 구매 이벤트(0xBC)와 아이템 ID의 관계를 탐색한다.

알려진 사실:
- 0xBC (Entity 0) = 아이템 구매 이벤트 (통제 테스트 5/5 일치)
- 아이템 ID (101-423)는 바이너리에 존재하나, 0xBC 페이로드에 직접 포함되지 않음
- 0xBC 페이로드 첫 4바이트는 IEEE 754 float 값 (증가 패턴)
- 0x3D (Entity 0)도 테스트에서 정확히 5회 발생 - 관련 가능성 있음
"""

import argparse
import json
import struct
import sys
from pathlib import Path
from collections import defaultdict, OrderedDict
from typing import Dict, List, Any, Optional, Tuple

# === 코어 모듈 임포트 ===
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_mapping import ITEM_ID_MAP, VGRMapping


# ─────────────────────────────────────────────────────────
# 상수 정의
# ─────────────────────────────────────────────────────────

# Entity 0 패턴: 00 00 00 00 (2B entity ID LE + 00 00 padding)
ENTITY_0_PREFIX = b'\x00\x00\x00\x00'

# 아이템 구매 테스트에서 알려진 구매 내역
KNOWN_PURCHASES = {
    0: [101, 102],   # Frame 0: Weapon Blade + Book of Eulogies
    5: [111, 103],   # Frame 5: Heavy Steel + Swift Shooter
    6: [121],        # Frame 6: Sorrowblade
}
PURCHASE_FRAMES = set(KNOWN_PURCHASES.keys())
TEST_ITEM_IDS = {101, 102, 103, 111, 121}

# 기본 리플레이 경로
DEFAULT_REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test")

# 출력 경로
OUTPUT_DIR = Path(__file__).parent.parent / 'output'
OUTPUT_JSON = OUTPUT_DIR / 'item_id_link_analysis.json'

# 페이로드 덤프 길이
PAYLOAD_DUMP_LEN = 48


# ─────────────────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────────────────

def get_replay_info(replay_dir: Path) -> Tuple[str, List[Path]]:
    """리플레이 디렉토리에서 이름과 프레임 파일 목록을 가져온다."""
    vgr_files = sorted(
        replay_dir.glob("*.vgr"),
        key=lambda p: int(p.stem.split('.')[-1])
    )
    if not vgr_files:
        raise FileNotFoundError(f"No .vgr files found in {replay_dir}")

    replay_name = '.'.join(vgr_files[0].stem.split('.')[:-1])
    return replay_name, vgr_files


def find_pattern_offsets(data: bytes, pattern: bytes) -> List[int]:
    """바이너리 데이터에서 패턴의 모든 출현 위치를 반환한다."""
    offsets = []
    idx = 0
    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break
        offsets.append(idx)
        idx += 1
    return offsets


def hex_dump(data: bytes, max_bytes: int = 48) -> str:
    """바이트 데이터를 보기 좋은 hex 문자열로 변환한다."""
    return ' '.join(f'{b:02X}' for b in data[:max_bytes])


def interpret_payload(payload: bytes) -> Dict[str, Any]:
    """페이로드 첫 부분을 다양한 형식으로 해석한다."""
    result = {}

    # Float32 (IEEE 754) - 첫 4바이트
    if len(payload) >= 4:
        result['float32'] = struct.unpack('<f', payload[:4])[0]

    # uint16 LE 쌍 - 첫 4바이트
    if len(payload) >= 4:
        result['uint16_pair'] = (
            struct.unpack('<H', payload[:2])[0],
            struct.unpack('<H', payload[2:4])[0]
        )

    # uint32 LE - 첫 4바이트
    if len(payload) >= 4:
        result['uint32'] = struct.unpack('<I', payload[:4])[0]

    # 추가 바이트 해석 (오프셋 4-7)
    if len(payload) >= 8:
        result['float32_offset4'] = struct.unpack('<f', payload[4:8])[0]
        result['uint32_offset4'] = struct.unpack('<I', payload[4:8])[0]
        result['uint16_pair_offset4'] = (
            struct.unpack('<H', payload[4:6])[0],
            struct.unpack('<H', payload[6:8])[0]
        )

    return result


def find_entity0_events(data: bytes, action_filter: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    바이너리 데이터에서 Entity 0 이벤트를 찾는다.
    이벤트 형식: [EntityID(2B LE)][00 00][ActionType(1B)][Payload...]
    Entity 0 = 00 00 00 00 + ActionType
    """
    events = []
    offsets = find_pattern_offsets(data, ENTITY_0_PREFIX)

    for offset in offsets:
        if offset + 5 > len(data):
            continue

        action = data[offset + 4]

        if action_filter is not None and action != action_filter:
            continue

        payload_start = offset + 5
        payload_end = min(payload_start + PAYLOAD_DUMP_LEN, len(data))
        payload = data[payload_start:payload_end]

        events.append({
            'offset': offset,
            'action': action,
            'action_hex': f'0x{action:02X}',
            'payload': payload,
            'payload_hex': hex_dump(payload),
            'interpretations': interpret_payload(payload),
        })

    return events


# ─────────────────────────────────────────────────────────
# 분석 함수 1: 0xBC 이벤트 덤프
# ─────────────────────────────────────────────────────────

def dump_0xBC_events(replay_dir: Path) -> Dict[str, Any]:
    """
    0xBC 이벤트 전체 덤프 (Entity 0)
    패턴: 00 00 00 00 BC [payload...]
    각 이벤트의 프레임, 오프셋, 전체 페이로드 hex, float/uint 해석을 출력한다.
    """
    print("=" * 70)
    print("Analysis 1: 0xBC Events (Entity 0) - 아이템 구매 이벤트 덤프")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'replay_name': replay_name,
        'total_frames': len(frame_files),
        'events': []
    }

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        events = find_entity0_events(data, action_filter=0xBC)

        for evt in events:
            entry = {
                'frame': frame_num,
                'file_offset': evt['offset'],
                'payload_hex': evt['payload_hex'],
                'float32': evt['interpretations'].get('float32'),
                'uint16_pair': evt['interpretations'].get('uint16_pair'),
                'uint32': evt['interpretations'].get('uint32'),
            }
            # 추가 해석 값
            if 'float32_offset4' in evt['interpretations']:
                entry['float32_offset4'] = evt['interpretations']['float32_offset4']
                entry['uint32_offset4'] = evt['interpretations']['uint32_offset4']
                entry['uint16_pair_offset4'] = evt['interpretations']['uint16_pair_offset4']

            results['events'].append(entry)

            # 콘솔 출력
            known = ""
            if frame_num in KNOWN_PURCHASES:
                items = [ITEM_ID_MAP[iid]['name'] for iid in KNOWN_PURCHASES[frame_num]]
                known = f"  <-- Known: {', '.join(items)}"

            print(f"\n  Frame {frame_num} | Offset 0x{evt['offset']:06X}{known}")
            print(f"    Hex: {evt['payload_hex']}")
            print(f"    float32     = {entry['float32']:.6f}")
            print(f"    uint16 pair = {entry['uint16_pair']}")
            print(f"    uint32      = {entry['uint32']}")
            if 'float32_offset4' in entry:
                print(f"    float32[4:8] = {entry['float32_offset4']:.6f}")
                print(f"    uint32[4:8]  = {entry['uint32_offset4']}")

    print(f"\n  Total 0xBC events: {len(results['events'])}")
    return results


# ─────────────────────────────────────────────────────────
# 분석 함수 2: 0x3D 이벤트 덤프
# ─────────────────────────────────────────────────────────

def dump_0x3D_events(replay_dir: Path) -> Dict[str, Any]:
    """
    0x3D 이벤트 전체 덤프 (Entity 0)
    패턴: 00 00 00 00 3D [payload...]
    0xBC와 비교하기 위한 구조 분석.
    """
    print("\n" + "=" * 70)
    print("Analysis 2: 0x3D Events (Entity 0) - 관련 이벤트 덤프")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'replay_name': replay_name,
        'events': []
    }

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        events = find_entity0_events(data, action_filter=0x3D)

        for evt in events:
            entry = {
                'frame': frame_num,
                'file_offset': evt['offset'],
                'payload_hex': evt['payload_hex'],
                'float32': evt['interpretations'].get('float32'),
                'uint16_pair': evt['interpretations'].get('uint16_pair'),
                'uint32': evt['interpretations'].get('uint32'),
            }
            if 'float32_offset4' in evt['interpretations']:
                entry['float32_offset4'] = evt['interpretations']['float32_offset4']
                entry['uint32_offset4'] = evt['interpretations']['uint32_offset4']
                entry['uint16_pair_offset4'] = evt['interpretations']['uint16_pair_offset4']

            results['events'].append(entry)

            print(f"\n  Frame {frame_num} | Offset 0x{evt['offset']:06X}")
            print(f"    Hex: {evt['payload_hex']}")
            print(f"    float32     = {entry['float32']:.6f}")
            print(f"    uint16 pair = {entry['uint16_pair']}")
            print(f"    uint32      = {entry['uint32']}")
            if 'float32_offset4' in entry:
                print(f"    float32[4:8] = {entry['float32_offset4']:.6f}")
                print(f"    uint32[4:8]  = {entry['uint32_offset4']}")

    print(f"\n  Total 0x3D events: {len(results['events'])}")

    # 0xBC와 구조 비교
    print("\n  --- 0xBC vs 0x3D 구조 비교 ---")
    if results['events']:
        print(f"  0x3D count: {len(results['events'])}")
        frames_3d = sorted(set(e['frame'] for e in results['events']))
        print(f"  0x3D frames: {frames_3d}")
    else:
        print("  0x3D events not found in this replay.")

    return results


# ─────────────────────────────────────────────────────────
# 분석 함수 3: 0xBC 주변 아이템 ID 탐색
# ─────────────────────────────────────────────────────────

def search_near_0xBC(replay_dir: Path, search_radius: int = 200) -> Dict[str, Any]:
    """
    각 0xBC 이벤트 위치 +-search_radius 바이트 범위에서 알려진 아이템 ID를 탐색한다.
    1바이트, 2바이트 LE, 4바이트 LE로 검색한다.
    """
    print("\n" + "=" * 70)
    print(f"Analysis 3: 0xBC 주변 +-{search_radius}B 아이템 ID 탐색")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'search_radius': search_radius,
        'hits': []
    }

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        # 이 프레임에서 기대되는 아이템 ID
        expected_items = set(KNOWN_PURCHASES.get(frame_num, []))

        events_0xbc = find_entity0_events(data, action_filter=0xBC)

        for evt in events_0xbc:
            bc_offset = evt['offset']
            region_start = max(0, bc_offset - search_radius)
            region_end = min(len(data), bc_offset + 5 + search_radius)
            region = data[region_start:region_end]

            hits_for_event = []

            for item_id in TEST_ITEM_IDS:
                # 1바이트 검색 (item_id < 256인 경우)
                if item_id < 256:
                    for i, b in enumerate(region):
                        if b == item_id:
                            abs_offset = region_start + i
                            rel_offset = abs_offset - bc_offset
                            hits_for_event.append({
                                'item_id': item_id,
                                'item_name': ITEM_ID_MAP[item_id]['name'],
                                'encoding': '1byte',
                                'abs_offset': abs_offset,
                                'rel_to_0xBC': rel_offset,
                                'expected': item_id in expected_items,
                            })

                # 2바이트 LE 검색
                id_2b = struct.pack('<H', item_id)
                pos = 0
                while True:
                    pos = region.find(id_2b, pos)
                    if pos == -1:
                        break
                    abs_offset = region_start + pos
                    rel_offset = abs_offset - bc_offset
                    hits_for_event.append({
                        'item_id': item_id,
                        'item_name': ITEM_ID_MAP[item_id]['name'],
                        'encoding': '2byte_LE',
                        'abs_offset': abs_offset,
                        'rel_to_0xBC': rel_offset,
                        'expected': item_id in expected_items,
                    })
                    pos += 1

                # 4바이트 LE 검색
                id_4b = struct.pack('<I', item_id)
                pos = 0
                while True:
                    pos = region.find(id_4b, pos)
                    if pos == -1:
                        break
                    abs_offset = region_start + pos
                    rel_offset = abs_offset - bc_offset
                    hits_for_event.append({
                        'item_id': item_id,
                        'item_name': ITEM_ID_MAP[item_id]['name'],
                        'encoding': '4byte_LE',
                        'abs_offset': abs_offset,
                        'rel_to_0xBC': rel_offset,
                        'expected': item_id in expected_items,
                    })
                    pos += 1

            if hits_for_event:
                result_entry = {
                    'frame': frame_num,
                    'bc_offset': bc_offset,
                    'hits': hits_for_event,
                }
                results['hits'].append(result_entry)

                print(f"\n  Frame {frame_num} | 0xBC @ 0x{bc_offset:06X}")
                # 기대 아이템과 일치하는 히트만 강조
                for h in hits_for_event:
                    marker = " <<<" if h['expected'] else ""
                    print(f"    {h['item_name']:20s} (ID {h['item_id']:3d}) "
                          f"@ rel {h['rel_to_0xBC']:+5d}  [{h['encoding']:8s}]{marker}")

    # 요약: 상대 오프셋 패턴 분석
    print(f"\n  --- 상대 오프셋 패턴 요약 ---")
    rel_offset_counts = defaultdict(lambda: defaultdict(int))
    for entry in results['hits']:
        for h in entry['hits']:
            if h['expected']:
                rel_offset_counts[h['encoding']][h['rel_to_0xBC']] += 1

    for encoding, offsets in sorted(rel_offset_counts.items()):
        print(f"\n  Encoding: {encoding}")
        for rel_off, count in sorted(offsets.items(), key=lambda x: -x[1]):
            print(f"    rel_offset {rel_off:+5d}: {count} expected hits")

    print(f"\n  Total proximity hits: {sum(len(e['hits']) for e in results['hits'])}")
    return results


# ─────────────────────────────────────────────────────────
# 분석 함수 4: 구매 프레임 내 모든 Entity 0 이벤트 덤프
# ─────────────────────────────────────────────────────────

def dump_all_entity0_events_in_purchase_frames(replay_dir: Path) -> Dict[str, Any]:
    """
    아이템 구매가 발생하는 프레임(0, 5, 6)에서 모든 Entity 0 이벤트를 덤프한다.
    액션 타입별로 그룹화하고, 아이템 ID가 포함된 이벤트를 강조한다.
    """
    print("\n" + "=" * 70)
    print("Analysis 4: 구매 프레임 내 모든 Entity 0 이벤트")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'frames': {}
    }

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        if frame_num not in PURCHASE_FRAMES:
            continue

        data = frame_path.read_bytes()
        events = find_entity0_events(data)

        # 액션 타입별 그룹화
        by_action = defaultdict(list)
        for evt in events:
            by_action[evt['action_hex']].append(evt)

        frame_result = {
            'expected_items': [
                {'id': iid, 'name': ITEM_ID_MAP[iid]['name']}
                for iid in KNOWN_PURCHASES.get(frame_num, [])
            ],
            'total_entity0_events': len(events),
            'action_types': {},
        }

        expected_ids = set(KNOWN_PURCHASES.get(frame_num, []))

        print(f"\n  Frame {frame_num} | Expected: "
              f"{[ITEM_ID_MAP[i]['name'] for i in KNOWN_PURCHASES.get(frame_num, [])]}")
        print(f"  Total Entity 0 events: {len(events)}")

        for action_hex, action_events in sorted(by_action.items()):
            action_entries = []
            print(f"\n    Action {action_hex}: {len(action_events)} events")

            for evt in action_events:
                payload = evt['payload']

                # 페이로드에서 아이템 ID 검색
                contains_items = []
                for item_id in expected_ids:
                    # 2바이트 LE
                    id_bytes = struct.pack('<H', item_id)
                    if id_bytes in payload:
                        pos = payload.find(id_bytes)
                        contains_items.append({
                            'item_id': item_id,
                            'item_name': ITEM_ID_MAP[item_id]['name'],
                            'offset_in_payload': pos,
                            'encoding': '2byte_LE',
                        })
                    # 1바이트 (for IDs < 256)
                    if item_id < 256:
                        for i, b in enumerate(payload):
                            if b == item_id:
                                contains_items.append({
                                    'item_id': item_id,
                                    'item_name': ITEM_ID_MAP[item_id]['name'],
                                    'offset_in_payload': i,
                                    'encoding': '1byte',
                                })

                entry = {
                    'offset': evt['offset'],
                    'payload_hex': hex_dump(payload, 24),
                    'contains_item_ids': contains_items,
                }
                action_entries.append(entry)

                marker = ""
                if contains_items:
                    names = [f"{c['item_name']}@{c['offset_in_payload']}" for c in contains_items]
                    marker = f" <<< ITEM HIT: {', '.join(names)}"

                print(f"      0x{evt['offset']:06X}: {hex_dump(payload, 20)}{marker}")

            frame_result['action_types'][action_hex] = {
                'count': len(action_entries),
                'events': action_entries,
            }

        results['frames'][str(frame_num)] = frame_result

    return results


# ─────────────────────────────────────────────────────────
# 분석 함수 5: 글로벌 아이템 ID 검색
# ─────────────────────────────────────────────────────────

def find_item_ids_globally(replay_dir: Path) -> Dict[str, Any]:
    """
    각 프레임의 전체 바이너리에서 아이템 ID를 2바이트 LE 및 4바이트 LE로 검색한다.
    구매 프레임과 비구매 프레임의 출현 패턴을 비교한다.
    """
    print("\n" + "=" * 70)
    print("Analysis 5: 글로벌 아이템 ID 검색 (전체 바이너리)")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'by_item': {},
        'by_frame': {},
    }

    for item_id in sorted(TEST_ITEM_IDS):
        results['by_item'][str(item_id)] = {
            'name': ITEM_ID_MAP[item_id]['name'],
            'frames': {}
        }

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()
        is_purchase = frame_num in PURCHASE_FRAMES

        frame_result = {
            'is_purchase_frame': is_purchase,
            'expected_items': KNOWN_PURCHASES.get(frame_num, []),
            'file_size': len(data),
            'item_hits': {},
        }

        print(f"\n  Frame {frame_num} ({'PURCHASE' if is_purchase else 'no purchase'}) "
              f"| size={len(data)} bytes")

        for item_id in sorted(TEST_ITEM_IDS):
            item_name = ITEM_ID_MAP[item_id]['name']

            # 2바이트 LE 검색
            id_2b = struct.pack('<H', item_id)
            offsets_2b = find_pattern_offsets(data, id_2b)

            # 4바이트 LE 검색
            id_4b = struct.pack('<I', item_id)
            offsets_4b = find_pattern_offsets(data, id_4b)

            expected_here = item_id in KNOWN_PURCHASES.get(frame_num, [])

            hit_info = {
                '2byte_LE': {
                    'count': len(offsets_2b),
                    'offsets': offsets_2b[:20],  # 최대 20개까지 기록
                },
                '4byte_LE': {
                    'count': len(offsets_4b),
                    'offsets': offsets_4b[:20],
                },
                'expected': expected_here,
            }

            frame_result['item_hits'][str(item_id)] = hit_info
            results['by_item'][str(item_id)]['frames'][str(frame_num)] = hit_info

            marker = " <<<" if expected_here else ""
            if offsets_2b or offsets_4b:
                print(f"    ID {item_id:3d} ({item_name:15s}): "
                      f"2B={len(offsets_2b):3d}  4B={len(offsets_4b):3d}{marker}")

        results['by_frame'][str(frame_num)] = frame_result

    # 비교 분석: 구매 프레임에만 나타나는 출현 여부
    print("\n  --- 구매 프레임 vs 비구매 프레임 비교 ---")
    for item_id in sorted(TEST_ITEM_IDS):
        item_data = results['by_item'][str(item_id)]
        item_name = item_data['name']
        purchase_counts = []
        non_purchase_counts = []

        for fn_str, hit in item_data['frames'].items():
            fn = int(fn_str)
            c2 = hit['2byte_LE']['count']
            if fn in PURCHASE_FRAMES and item_id in KNOWN_PURCHASES.get(fn, []):
                purchase_counts.append(c2)
            else:
                non_purchase_counts.append(c2)

        avg_purchase = sum(purchase_counts) / len(purchase_counts) if purchase_counts else 0
        avg_non = sum(non_purchase_counts) / len(non_purchase_counts) if non_purchase_counts else 0
        print(f"  {item_name:15s} (ID {item_id:3d}): "
              f"avg 2B in purchase frames = {avg_purchase:.1f}, "
              f"avg 2B in other frames = {avg_non:.1f}")

    return results


# ─────────────────────────────────────────────────────────
# 분석 함수 6: 0xBC 주변 이벤트 상관 분석
# ─────────────────────────────────────────────────────────

def correlate_0xBC_with_nearby_events(replay_dir: Path, radius: int = 50) -> Dict[str, Any]:
    """
    각 0xBC 이벤트 주변 +-radius 바이트 범위에서 다른 이벤트를 찾고,
    해당 이벤트의 페이로드에 아이템 ID가 포함되어 있는지 확인한다.
    가설: 0xBC가 아이템 ID를 포함하는 다른 이벤트와 쌍을 이룸
    """
    print("\n" + "=" * 70)
    print(f"Analysis 6: 0xBC 주변 +-{radius}B 이벤트 상관 분석")
    print("=" * 70)

    replay_name, frame_files = get_replay_info(replay_dir)
    results = {
        'radius': radius,
        'correlations': [],
    }

    # 이벤트 패턴: [XX XX 00 00 YY] 형태 (2바이트 entity + 00 00 + action)
    # Entity 0이 아닌 이벤트도 포함하여 검색

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        events_0xbc = find_entity0_events(data, action_filter=0xBC)
        expected_items = set(KNOWN_PURCHASES.get(frame_num, []))

        for bc_evt in events_0xbc:
            bc_offset = bc_evt['offset']
            nearby = []

            # 주변 범위에서 [XX XX 00 00 YY] 패턴 검색
            search_start = max(0, bc_offset - radius)
            search_end = min(len(data), bc_offset + 5 + radius)

            pos = search_start
            while pos < search_end - 4:
                # [entity_lo][entity_hi][00][00][action] 패턴 확인
                if data[pos + 2] == 0x00 and data[pos + 3] == 0x00:
                    entity_id = data[pos] | (data[pos + 1] << 8)
                    action = data[pos + 4]

                    # 0xBC 자체는 건너뛴다
                    if pos == bc_offset:
                        pos += 1
                        continue

                    # 페이로드 추출
                    payload_start = pos + 5
                    payload_end = min(payload_start + 32, len(data))
                    payload = data[payload_start:payload_end]

                    # 페이로드에서 아이템 ID 검색
                    item_hits = []
                    for item_id in TEST_ITEM_IDS:
                        # 1바이트
                        if item_id < 256:
                            for i, b in enumerate(payload):
                                if b == item_id:
                                    item_hits.append({
                                        'item_id': item_id,
                                        'item_name': ITEM_ID_MAP[item_id]['name'],
                                        'payload_offset': i,
                                        'encoding': '1byte',
                                        'expected': item_id in expected_items,
                                    })
                        # 2바이트 LE
                        id_2b = struct.pack('<H', item_id)
                        idx_in_payload = 0
                        while True:
                            idx_in_payload = payload.find(id_2b, idx_in_payload)
                            if idx_in_payload == -1:
                                break
                            item_hits.append({
                                'item_id': item_id,
                                'item_name': ITEM_ID_MAP[item_id]['name'],
                                'payload_offset': idx_in_payload,
                                'encoding': '2byte_LE',
                                'expected': item_id in expected_items,
                            })
                            idx_in_payload += 1

                    nearby_entry = {
                        'offset': pos,
                        'rel_to_0xBC': pos - bc_offset,
                        'entity_id': entity_id,
                        'action': action,
                        'action_hex': f'0x{action:02X}',
                        'payload_hex': hex_dump(payload, 16),
                        'item_hits': item_hits,
                    }
                    nearby.append(nearby_entry)

                pos += 1

            correlation_entry = {
                'frame': frame_num,
                'bc_offset': bc_offset,
                'expected_items': [
                    {'id': i, 'name': ITEM_ID_MAP[i]['name']} for i in expected_items
                ],
                'nearby_events': nearby,
                'nearby_with_item_hits': [n for n in nearby if n['item_hits']],
            }
            results['correlations'].append(correlation_entry)

            print(f"\n  Frame {frame_num} | 0xBC @ 0x{bc_offset:06X}")
            print(f"    Nearby events within +-{radius} bytes: {len(nearby)}")

            for n in nearby:
                marker = ""
                if n['item_hits']:
                    hit_names = [
                        f"{h['item_name']}({'EXP' if h['expected'] else 'unk'})"
                        for h in n['item_hits']
                    ]
                    marker = f"  <<< ITEMS: {', '.join(hit_names)}"

                print(f"      rel {n['rel_to_0xBC']:+5d} | Entity {n['entity_id']:5d} | "
                      f"{n['action_hex']} | {n['payload_hex'][:40]}{marker}")

    # 요약: 아이템 ID를 포함한 주변 이벤트 통계
    print("\n  --- 아이템 ID 포함 주변 이벤트 요약 ---")
    action_item_counts = defaultdict(int)
    for corr in results['correlations']:
        for n in corr['nearby_with_item_hits']:
            for h in n['item_hits']:
                if h['expected']:
                    action_item_counts[n['action_hex']] += 1

    for action_hex, count in sorted(action_item_counts.items(), key=lambda x: -x[1]):
        print(f"    Action {action_hex}: {count} expected item ID hits in nearby payloads")

    return results


# ─────────────────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────────────────

def print_summary(all_results: Dict[str, Any]) -> None:
    """분석 결과 요약 출력."""
    print("\n" + "=" * 70)
    print("SUMMARY - 분석 결과 종합")
    print("=" * 70)

    # 0xBC 이벤트 수
    bc_events = all_results.get('0xBC_events', {}).get('events', [])
    print(f"\n  1. 0xBC events found: {len(bc_events)}")
    if bc_events:
        frames_with_bc = sorted(set(e['frame'] for e in bc_events))
        print(f"     In frames: {frames_with_bc}")
        print(f"     Float32 values: {[e['float32'] for e in bc_events]}")

    # 0x3D 이벤트 수
    events_3d = all_results.get('0x3D_events', {}).get('events', [])
    print(f"\n  2. 0x3D events found: {len(events_3d)}")
    if events_3d:
        frames_with_3d = sorted(set(e['frame'] for e in events_3d))
        print(f"     In frames: {frames_with_3d}")

    # 0xBC 주변 아이템 ID 히트
    proximity = all_results.get('proximity_search', {})
    total_proximity_hits = sum(
        len(entry['hits']) for entry in proximity.get('hits', [])
    )
    expected_proximity = sum(
        1 for entry in proximity.get('hits', [])
        for h in entry['hits']
        if h.get('expected')
    )
    print(f"\n  3. Proximity search: {total_proximity_hits} total hits, "
          f"{expected_proximity} expected item matches")

    # 가장 유망한 발견 강조
    print(f"\n  4. Most promising findings:")

    # 상관 분석 결과에서 유망한 패턴 추출
    correlations = all_results.get('nearby_correlations', {}).get('correlations', [])
    promising = defaultdict(list)
    for corr in correlations:
        for n in corr.get('nearby_with_item_hits', []):
            for h in n.get('item_hits', []):
                if h.get('expected'):
                    promising[n['action_hex']].append({
                        'frame': corr['frame'],
                        'item': h['item_name'],
                        'rel_offset': n['rel_to_0xBC'],
                        'entity_id': n['entity_id'],
                    })

    if promising:
        for action_hex, hits in sorted(promising.items(), key=lambda x: -len(x[1])):
            print(f"\n     Action {action_hex}: {len(hits)} expected item hits near 0xBC")
            for h in hits[:5]:
                print(f"       Frame {h['frame']}: {h['item']} "
                      f"(entity={h['entity_id']}, rel={h['rel_offset']:+d})")
    else:
        print("     No strong action-item correlations found near 0xBC events.")

    # 글로벌 검색 결과 요약
    global_search = all_results.get('global_item_search', {})
    print(f"\n  5. Global item ID presence:")
    for item_str, item_data in global_search.get('by_item', {}).items():
        total_2b = sum(
            f_data['2byte_LE']['count']
            for f_data in item_data.get('frames', {}).values()
        )
        print(f"     {item_data['name']:15s} (ID {item_str}): "
              f"{total_2b} total 2-byte LE occurrences")


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Item ID Linker - 0xBC 이벤트와 아이템 ID 연결 분석'
    )
    parser.add_argument(
        '--replay-dir',
        type=str,
        default=str(DEFAULT_REPLAY_DIR),
        help='리플레이 디렉토리 경로 (default: item buy test)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default=str(OUTPUT_JSON),
        help='결과 JSON 출력 경로'
    )
    parser.add_argument(
        '--search-radius',
        type=int,
        default=200,
        help='0xBC 주변 아이템 ID 검색 범위 (bytes, default: 200)'
    )
    parser.add_argument(
        '--correlation-radius',
        type=int,
        default=50,
        help='0xBC 주변 이벤트 상관 분석 범위 (bytes, default: 50)'
    )
    parser.add_argument(
        '--skip',
        nargs='*',
        choices=['bc', '3d', 'proximity', 'entity0', 'global', 'correlate'],
        default=[],
        help='건너뛸 분석 단계'
    )
    args = parser.parse_args()

    replay_dir = Path(args.replay_dir)
    if not replay_dir.is_dir():
        print(f"Error: Directory not found: {replay_dir}")
        return 1

    print("=" * 70)
    print("Item ID Linker Analysis")
    print(f"Replay: {replay_dir}")
    print("=" * 70)

    # 리플레이 정보 확인
    replay_name, frame_files = get_replay_info(replay_dir)
    print(f"Replay name: {replay_name}")
    print(f"Total frames: {len(frame_files)}")
    print(f"Known purchases: {KNOWN_PURCHASES}")
    print(f"Test item IDs: {sorted(TEST_ITEM_IDS)}")

    all_results = {
        'replay_dir': str(replay_dir),
        'replay_name': replay_name,
        'total_frames': len(frame_files),
        'known_purchases': {
            str(k): [
                {'id': iid, 'name': ITEM_ID_MAP[iid]['name']}
                for iid in v
            ]
            for k, v in KNOWN_PURCHASES.items()
        },
        'test_item_ids': sorted(TEST_ITEM_IDS),
    }

    skip = set(args.skip)

    # === 분석 1: 0xBC 이벤트 덤프 ===
    if 'bc' not in skip:
        all_results['0xBC_events'] = dump_0xBC_events(replay_dir)

    # === 분석 2: 0x3D 이벤트 덤프 ===
    if '3d' not in skip:
        all_results['0x3D_events'] = dump_0x3D_events(replay_dir)

    # === 분석 3: 0xBC 주변 아이템 ID 탐색 ===
    if 'proximity' not in skip:
        all_results['proximity_search'] = search_near_0xBC(
            replay_dir, search_radius=args.search_radius
        )

    # === 분석 4: 구매 프레임 Entity 0 이벤트 ===
    if 'entity0' not in skip:
        all_results['purchase_frame_entity0'] = dump_all_entity0_events_in_purchase_frames(
            replay_dir
        )

    # === 분석 5: 글로벌 아이템 ID 검색 ===
    if 'global' not in skip:
        all_results['global_item_search'] = find_item_ids_globally(replay_dir)

    # === 분석 6: 0xBC 주변 이벤트 상관 분석 ===
    if 'correlate' not in skip:
        all_results['nearby_correlations'] = correlate_0xBC_with_nearby_events(
            replay_dir, radius=args.correlation_radius
        )

    # === 결과 요약 ===
    print_summary(all_results)

    # === JSON 저장 ===
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON 직렬화를 위해 bytes/tuple 객체 정리
    def sanitize_for_json(obj):
        if isinstance(obj, bytes):
            return obj.hex()
        if isinstance(obj, tuple):
            return list(obj)
        if isinstance(obj, set):
            return sorted(obj)
        if isinstance(obj, dict):
            return {str(k): sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [sanitize_for_json(item) for item in obj]
        if isinstance(obj, float):
            if obj != obj:  # NaN check
                return None
            if obj == float('inf') or obj == float('-inf'):
                return str(obj)
        return obj

    sanitized = sanitize_for_json(all_results)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sanitized, f, indent=2, ensure_ascii=False)

    print(f"\n  Results saved to: {output_path}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
