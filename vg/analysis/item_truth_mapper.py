#!/usr/bin/env python3
"""
Item Truth Mapper - Match binary item IDs to actual item names using truth data.
================================================================================

Uses the user-provided item truth (Korean names from screenshots) for matches 1-4
to identify which binary item IDs correspond to which Vainglory items.

Strategy: Frequency matching (same method that solved K/D detection)
- For each truth item name, count which players have it in their final build
- For each binary item ID, count which players acquired it
- Match IDs to names where the PLAYER SETS overlap

Usage:
    python -m vg.analysis.item_truth_mapper
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import BINARY_HERO_ID_MAP

# Korean → English item name mapping
KO_TO_EN = {
    # Weapon T1
    "단검": "Weapon Blade",
    "찬가의 고서": "Book of Eulogies",
    "자동권총": "Swift Shooter",
    "자동 권총": "Swift Shooter",
    "여우발": "Minions Foot",
    "여우 발": "Minions Foot",
    # Weapon T2
    "강철 대검": "Heavy Steel",
    "강철대검": "Heavy Steel",
    "죄악의 표창": "Six Sins",
    "가시 바늘": "Barbed Needle",
    "가시바늘": "Barbed Needle",
    "미늘창": "Piercing Spear",
    "기관단총": "Blazing Salvo",
    "행운의 과녁": "Lucky Strike",
    # Weapon T3
    "비탄의 도끼": "Sorrowblade",
    "바다뱀의 가면": "Serpent Mask",
    "주문검": "Spellsword",
    "맹독 단검": "Poisoned Shiv",
    "천공기": "Breaking Point",
    "탄성궁": "Tension Bow",
    "뼈톱": "Bonesaw",
    "폭풍인도자": "Tornado Trigger",
    "폭군의 단안경": "Tyrants Monocle",
    # Crystal T1
    "수정 조각": "Crystal Bit",
    "수정조각": "Crystal Bit",
    "에너지 배터리": "Energy Battery",
    "에너지배터리": "Energy Battery",
    "모래시계": "Hourglass",
    # Crystal T2
    "대형 프리즘": "Heavy Prism",
    "대형프리즘": "Heavy Prism",
    "일식 프리즘": "Eclipse Prism",
    "일식프리즘": "Eclipse Prism",
    "공허의 배터리": "Void Battery",
    "관통 샤드": "Piercing Shard",
    "관통샤드": "Piercing Shard",
    "초시계": "Chronograph",
    # Crystal T3
    "강화유리": "Shatterglass",
    "주문불꽃": "Spellfire",
    "주문불곷": "Spellfire",  # typo in data
    "얼음불꽃": "Frostburn",
    "용의 눈": "Dragons Eye",
    "시계장치": "Clockwork",
    "신화의 종말": "Broken Myth",
    "영혼수확기": "Eve of Harvest",
    "연쇄충격기": "Aftershock",
    "교류전류": "Alternating Current",
    "교류 전류": "Alternating Current",
    # Defense T1
    "떡갈나무 심장": "Oakheart",
    "떡갈나무심장": "Oakheart",
    "작은 방패": "Light Shield",
    "작은방패": "Light Shield",
    "가죽 갑옷": "Light Armor",
    # Defense T2
    "용심장": "Dragonheart",
    "생명의 샘": "Lifespring",
    "재생의 샘": "Lifespring",
    "반사의 완갑": "Reflex Block",
    "수호자의 계약서": "Protector Contract",
    "반응형 장갑": "Kinetic Shield",
    "전쟁 갑옷": "Warmail",
    "전쟁갑옷": "Warmail",
    "판금 흉갑": "Coat of Plates",
    # Defense T3
    "척력장": "Pulseweave",
    "도가니": "Crucible",
    "축전판": "Capacitor Plate",
    "수호령": "Rooks Decree",
    "천상의 장막": "Rooks Decree",  # alternate name
    "재생의 분수": "Fountain of Renewal",
    "이지스": "Aegis",
    "거대괴수 갑주": "Slumbering Husk",
    "거대괴수": "Slumbering Husk",
    "용린갑": "Metal Jacket",
    "거인의 견갑": "Atlas Pauldron",
    # Boots
    "가죽 신발": "Sprint Boots",
    "신속의 신발": "Travel Boots",
    "2티어신발": "Travel Boots",
    "순간이동 신발": "Teleport Boots",
    "질주의 신발": "Journey Boots",
    "전쟁 걸음": "War Treads",
    "전쟁걸음": "War Treads",
    "할시온 박차": "Halcyon Chargers",
    "할시온박차": "Halcyon Chargers",
    # Utility
    "만능 허리띠": "Contraption",
    "폭풍우 왕관": "Stormcrown",
    "만년한철": "Shiversteel",
    "경비대의 깃발": "Stormguard Banner",
    "경비대의 길밧": "Stormguard Banner",  # typo
    # Vision & consumables
    "조명탄총": "Flare Gun",
    "조명탄": "Flare",
    "정찰 지뢰": "Scout Trap",
    "강화부표": "SuperScout 2000",
    "강화 부표": "SuperScout 2000",
    # Other
    "수정강화제": "Crystal Infusion",
    "수정 강화제": "Crystal Infusion",
    "타격 강화제": "Weapon Infusion",
    "용의피 계약서": "Dragonblood Contract",
    "용의 피 계약서": "Dragonblood Contract",
    "경비대의 계약서": "Ironguard Contract",
}

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET = 0xA9
ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])


def load_truth():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def load_frames(replay_file):
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def fi(p):
        try: return int(p.stem.split('.')[-1])
        except: return 0
    frames.sort(key=fi)
    return [(fi(fp), fp.read_bytes()) for fp in frames]


def extract_players(data):
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    while True:
        pos = -1
        marker = None
        for c in markers:
            idx = data.find(c, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = c
        if pos == -1 or marker is None:
            break
        ns = pos + len(marker)
        ne = ns
        while ne < len(data) and ne < ns + 30:
            b = data[ne]
            if b < 32 or b > 126: break
            ne += 1
        name = ""
        if ne > ns:
            try: name = data[ns:ne].decode('ascii')
            except: pass
        if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
            seen.add(name)
            eid_be = struct.unpack_from(">H", data, pos + ENTITY_ID_OFFSET)[0] if pos + ENTITY_ID_OFFSET + 2 <= len(data) else None
            players.append({'name': name, 'entity_id_be': eid_be})
        search_start = pos + 1
    return players


def scan_acquires(data, eid_set):
    """Get all item acquire events for given entity IDs."""
    results = []
    pos = 0
    while True:
        pos = data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1: break
        if pos + 20 > len(data):
            pos += 1; continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1; continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_set:
            pos += 1; continue
        qty = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        results.append({'eid': eid, 'item_id': item_id, 'qty': qty})
        pos += 3
    return results


def parse_item_truth():
    """Parse the user-provided item truth template."""
    template_path = Path("D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays/item_truth_template.json")
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the JSON part (starts with {)
    json_start = content.find('{\n  "instructions"')
    if json_start == -1:
        json_start = content.find('"instructions"')
        if json_start > 0:
            json_start = content.rfind('{', 0, json_start)

    json_text = content[json_start:]

    # The items arrays contain Korean without quotes - need to fix
    import re

    # Fix unquoted Korean arrays: [word1, word2] → ["word1", "word2"]
    def fix_items_array(match):
        inner = match.group(1)
        if not inner.strip():
            return '"items": []'
        # Split by comma, strip, quote each
        items = [item.strip() for item in inner.split(',')]
        quoted = [f'"{item}"' for item in items if item]
        return '"items": [' + ', '.join(quoted) + ']'

    json_text = re.sub(r'"items":\s*\[([^\]]*)\]', fix_items_array, json_text)

    data = json.loads(json_text)
    return data


def main():
    print("=" * 90)
    print("ITEM TRUTH MAPPER - Binary ID ↔ Item Name Matching")
    print("=" * 90)

    truth = load_truth()
    item_truth = parse_item_truth()

    # Build player → truth items mapping for matches 1-4
    # truth item: Korean → English
    player_truth_items = {}  # (match_idx, player_name) → [english_item_names]
    unmapped_ko = set()

    for match_entry in item_truth['matches']:
        midx = match_entry['match'] - 1  # 0-indexed
        if midx >= 4:  # only matches 1-4 have data
            continue
        for pname, pdata in match_entry['players'].items():
            ko_items = pdata.get('items', [])
            if not ko_items:
                continue
            en_items = []
            for ko in ko_items:
                ko_clean = ko.strip()
                en = KO_TO_EN.get(ko_clean)
                if en:
                    en_items.append(en)
                else:
                    unmapped_ko.add(ko_clean)
                    en_items.append(f"?{ko_clean}")
            player_truth_items[(midx, pname)] = en_items

    if unmapped_ko:
        print(f"\nWARNING: Unmapped Korean item names: {unmapped_ko}")

    print(f"\nLoaded truth items for {len(player_truth_items)} players across 4 matches")

    # For each match, get binary acquire events per player
    player_binary_ids = {}  # (match_idx, player_name) → set of item_ids

    for midx in range(4):
        match = truth['matches'][midx]
        frames = load_frames(match['replay_file'])
        if not frames:
            continue

        players = extract_players(frames[0][1])
        eid_map = {p['entity_id_be']: p['name'] for p in players}
        eid_set = set(eid_map.keys())

        all_data = b"".join(d for _, d in frames)
        acquires = scan_acquires(all_data, eid_set)

        for acq in acquires:
            pname = eid_map.get(acq['eid'])
            if pname:
                key = (midx, pname)
                if key not in player_binary_ids:
                    player_binary_ids[key] = set()
                player_binary_ids[key].add(acq['item_id'])

    # FREQUENCY MATCHING: for each item name, find which item IDs appear
    # in EXACTLY the same set of players
    print(f"\n{'=' * 90}")
    print("ITEM NAME → BINARY ID MATCHING")
    print(f"{'=' * 90}")

    # Build: item_name → set of (match_idx, player_name) who have it
    name_to_players = defaultdict(set)
    for key, items in player_truth_items.items():
        for item_name in items:
            name_to_players[item_name].add(key)

    # Build: item_id → set of (match_idx, player_name) who acquired it
    id_to_players = defaultdict(set)
    for key, ids in player_binary_ids.items():
        for iid in ids:
            id_to_players[iid].add(key)

    # For each item name, find the best matching item ID
    # Score = |intersection| / |union| (Jaccard similarity)
    matches_found = {}
    match_details = []

    for item_name in sorted(name_to_players.keys()):
        truth_players = name_to_players[item_name]
        if len(truth_players) < 1:
            continue

        best_id = None
        best_score = 0
        best_intersection = 0
        candidates = []

        for iid in sorted(id_to_players.keys()):
            id_players = id_to_players[iid]
            intersection = len(truth_players & id_players)
            union = len(truth_players | id_players)
            if union == 0:
                continue
            jaccard = intersection / union
            # Also compute recall (what fraction of truth players have this ID)
            recall = intersection / len(truth_players)

            if intersection >= 1 and recall >= 0.5:
                candidates.append((iid, jaccard, recall, intersection, len(id_players)))

            if jaccard > best_score or (jaccard == best_score and intersection > best_intersection):
                best_score = jaccard
                best_id = iid
                best_intersection = intersection

        candidates.sort(key=lambda x: (-x[1], -x[2]))

        match_details.append({
            'name': item_name,
            'truth_count': len(truth_players),
            'best_id': best_id,
            'best_score': best_score,
            'candidates': candidates[:5],
        })

    # Print results grouped by confidence
    high_conf = []  # Jaccard >= 0.3 and recall >= 0.7
    med_conf = []   # Jaccard >= 0.1 and recall >= 0.5
    low_conf = []

    for md in match_details:
        if md['candidates']:
            top = md['candidates'][0]
            iid, jaccard, recall = top[0], top[1], top[2]
            if recall >= 0.7 and jaccard >= 0.2:
                high_conf.append(md)
            elif recall >= 0.5:
                med_conf.append(md)
            else:
                low_conf.append(md)
        else:
            low_conf.append(md)

    print(f"\n--- HIGH CONFIDENCE (recall >= 70%, Jaccard >= 20%) ---")
    for md in sorted(high_conf, key=lambda x: -x['candidates'][0][1]):
        top = md['candidates'][0]
        iid = top[0]
        print(f"  {md['name']:<25s} → ID {iid:>3d}  "
              f"(J={top[1]:.2f}, recall={top[2]:.0%}, "
              f"truth={md['truth_count']}, matched={top[3]}/{top[4]} acquired)")
        if iid in matches_found and matches_found[iid] != md['name']:
            print(f"    [!] CONFLICT: ID {iid} already matched to {matches_found[iid]}")
        matches_found[iid] = md['name']

    print(f"\n--- MEDIUM CONFIDENCE (recall >= 50%) ---")
    for md in sorted(med_conf, key=lambda x: -x['candidates'][0][1]):
        top = md['candidates'][0]
        iid = top[0]
        conflict = ""
        if iid in matches_found and matches_found[iid] != md['name']:
            conflict = f" [!] CONFLICT with {matches_found[iid]}"
        print(f"  {md['name']:<25s} → ID {iid:>3d}  "
              f"(J={top[1]:.2f}, recall={top[2]:.0%}){conflict}")
        if not conflict:
            matches_found[iid] = md['name']

    print(f"\n--- LOW CONFIDENCE / NO MATCH ---")
    for md in low_conf:
        if md['candidates']:
            top = md['candidates'][0]
            print(f"  {md['name']:<25s} → ID {top[0]:>3d}?  "
                  f"(J={top[1]:.2f}, recall={top[2]:.0%}, truth={md['truth_count']})")
        else:
            print(f"  {md['name']:<25s} → NO CANDIDATES (truth={md['truth_count']})")

    # Print candidate alternatives for ambiguous matches
    print(f"\n{'=' * 90}")
    print("TOP CANDIDATES FOR EACH ITEM (showing alternatives)")
    print(f"{'=' * 90}")

    for md in sorted(match_details, key=lambda x: x['name']):
        if len(md['candidates']) > 1:
            print(f"\n  {md['name']} (truth_count={md['truth_count']}):")
            for iid, jaccard, recall, inter, total in md['candidates'][:5]:
                marker = " ←" if iid == md.get('best_id') else ""
                already = f" [={matches_found.get(iid, '')}]" if iid in matches_found else ""
                print(f"    ID {iid:>3d}: J={jaccard:.2f} recall={recall:.0%} "
                      f"({inter}/{md['truth_count']} matched, {total} total){already}{marker}")

    # Final mapping summary
    print(f"\n{'=' * 90}")
    print("FINAL MAPPING SUMMARY")
    print(f"{'=' * 90}")

    for iid in sorted(matches_found.keys()):
        print(f"  ID {iid:>3d} → {matches_found[iid]}")

    print(f"\n  Total mapped: {len(matches_found)} item IDs")
    print(f"  Unmapped IDs in replay data: ", end="")
    all_replay_ids = set()
    for ids in id_to_players.values():
        pass
    for iid in sorted(id_to_players.keys()):
        if iid not in matches_found and iid >= 200:
            all_replay_ids.add(iid)
    print(sorted(all_replay_ids))


if __name__ == '__main__':
    main()
