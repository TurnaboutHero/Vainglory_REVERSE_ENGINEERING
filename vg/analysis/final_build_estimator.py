#!/usr/bin/env python3
"""
Final Build Estimator - Estimate each player's final 6-slot item build.

Uses upgrade tree to remove consumed components (T1/T2 that were upgraded to T3).
Removes starter/consumable items. Caps at 6 slots (game maximum).
"""
import json
import struct
import sys
import os
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

ITEM_ACQUIRE = bytes([0x10, 0x04, 0x3D])
PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']

# Upgrade tree using BINARY REPLAY IDs (from ITEM_ID_MAP in vgr_mapping.py)
# component_id -> set of result_ids it could have been upgraded into
# T1 entries include transitive T3 targets to handle skipped T2 purchases
UPGRADE_TREE = {
    # ====== Weapon T1 → T2 + T3 (transitive) ======
    # Weapon Blade (202)
    202: {249, 205, 250, 24, 244, 237,           # WP T2
          208, 223, 12, 251, 235, 5, 226, 253},  # WP T3
    # Book of Eulogies (243)
    243: {237, 223},                              # → Barbed Needle → Serpent Mask
    # Swift Shooter (204)
    204: {24, 244,                                # → Blazing Salvo, Lucky Strike
          226, 251, 253, 5},                      # → Bonesaw, Breaking Point, Alt Current, Tyrants Monocle

    # ====== Weapon T2 → T3 ======
    249: {208, 223, 12, 251},    # Heavy Steel → Sorrowblade, Serpent Mask, Spellsword, Breaking Point
    205: {208, 235, 5},          # Six Sins → Sorrowblade, Tension Bow, Tyrants Monocle
    237: {223},                  # Barbed Needle → Serpent Mask
    250: {235, 226},             # Piercing Spear → Tension Bow, Bonesaw
    24:  {226, 251, 253},        # Blazing Salvo → Bonesaw, Breaking Point, Alt Current
    244: {5},                    # Lucky Strike → Tyrants Monocle
    207: {208, 223, 12, 251},   # Weapon T2 (unknown) → same as Heavy Steel
    252: {226, 235, 251},        # Weapon T2-T3 (unknown)

    # ====== Crystal T1 → T2 + T3 (transitive) ======
    # Crystal Bit (203) → used in most crystal T2/T3 paths
    203: {0, 238, 254,                             # Crystal T2 (0=Heavy Prism)
          209, 10, 230, 11, 236, 253, 240, 255},  # Crystal T3
    # Energy Battery (206) → Void Battery (not in map) → T3s
    206: {220, 255, 234},        # → Clockwork, Eve of Harvest, Halcyon Chargers
    # Hourglass (216) → Chronograph → T3s
    216: {218,                      # → Chronograph
          220, 236, 12, 7, 27, 16}, # → Clockwork, Aftershock, Spellsword, Stormcrown, Rooks Decree, Contraption

    # ====== Crystal T2 → T3 ======
    # Heavy Prism (ID 0, ~1200g) → most crystal T3 items
    0:   {209, 10, 230, 11, 240, 255, 253},  # → Shatterglass, Spellfire, Frostburn, Dragons Eye, Broken Myth, Eve, Alt Current
    238: {209, 10, 230, 11, 236},  # Eclipse Prism → Shatterglass, Spellfire, Frostburn, Dragons Eye, Aftershock
    254: {253, 240},               # Piercing Shard → Alt Current, Broken Myth
    218: {220, 236, 12, 7, 27, 16}, # Chronograph → Clockwork, Aftershock, Spellsword, Stormcrown, Rooks Decree, Contraption

    # ====== Defense T1 → T2 + T3 (transitive) ======
    # Oakheart (212)
    212: {214, 248, 229, 219,                    # Defense T2
          21, 232, 27, 241, 231, 247, 7, 16, 17}, # Defense/Utility T3 (incl. Contraption, Shiversteel)
    # Light Shield (211)
    211: {246, 26,                            # → Kinetic Shield, Warmail
          231, 247, 13, 242},                 # → Fountain, Aegis, Slumbering Husk, Atlas Pauldron
    # Light Armor (213)
    213: {26, 242},              # → Warmail → Atlas Pauldron
    # Defense T1 (245, unknown)
    245: {246,                   # → Kinetic Shield
          231, 247, 13},         # → Fountain, Aegis, Slumbering Husk
    # Defense T1 (215, unknown)
    215: {246,                   # → Kinetic Shield
          231, 247, 13},         # → Fountain, Aegis, Slumbering Husk

    # ====== Defense T2 → T3 ======
    214: {21, 232, 27, 241, 17},  # Dragonheart → Pulseweave, Crucible, Rooks Decree, War Treads, Shiversteel
    248: {21, 231},              # Lifespring → Pulseweave, Fountain of Renewal
    229: {232, 247},             # Reflex Block → Crucible, Aegis
    246: {231, 247, 13},         # Kinetic Shield → Fountain, Aegis, Slumbering Husk
    26:  {242},                  # Warmail → Atlas Pauldron

    # ====== Boots ======
    221: {222, 241, 234},        # Sprint Boots → Travel Boots, War Treads, Halcyon Chargers
    222: {241, 234},             # Travel Boots → War Treads, Halcyon Chargers

    # ====== Utility T2 → T3 ======
    219: {7, 16},                # Stormguard Banner → Stormcrown, Contraption
}

# Starter/consumable IDs - never in final build
# ID 1 = captain starter, ID 14 & 201 = starting items
# ID 8 = Weapon Infusion, ID 18 = Crystal Infusion (late-game consumables)
# ID 20 = Flare, ID 217 = Unknown 217 (likely contract)
STARTER_IDS = {1, 8, 14, 18, 20, 201, 217}

# KO mapping
EN_TO_KO = {
    "Weapon Blade": "단검", "Book of Eulogies": "찬가의 고서",
    "Swift Shooter": "자동권총", "Minions Foot": "여우발",
    "Heavy Steel": "강철대검", "Six Sins": "죄악의 표창",
    "Barbed Needle": "가시바늘", "Piercing Spear": "미늘창",
    "Blazing Salvo": "기관단총", "Lucky Strike": "행운의 과녁",
    "Sorrowblade": "비탄의 도끼", "Serpent Mask": "바다뱀의 가면",
    "Spellsword": "주문검", "Poisoned Shiv": "맹독 단검",
    "Breaking Point": "천공기", "Tension Bow": "탄성궁",
    "Bonesaw": "뼈톱", "Tornado Trigger": "폭풍인도자",
    "Tyrants Monocle": "폭군의 단안경",
    "Crystal Bit": "수정 조각", "Energy Battery": "에너지 배터리",
    "Hourglass": "모래시계",
    "Heavy Prism": "대형 프리즘", "Eclipse Prism": "일식 프리즘",
    "Void Battery": "공허의 배터리", "Piercing Shard": "관통 샤드",
    "Chronograph": "초시계",
    "Shatterglass": "강화유리", "Spellfire": "주문불꽃",
    "Frostburn": "얼음불꽃", "Dragons Eye": "용의 눈",
    "Clockwork": "시계장치", "Broken Myth": "신화의 종말",
    "Eve of Harvest": "영혼수확기", "Aftershock": "연쇄충격기",
    "Alternating Current": "교류전류",
    "Oakheart": "떡갈나무 심장", "Light Shield": "작은 방패",
    "Light Armor": "가죽 갑옷",
    "Dragonheart": "용심장", "Lifespring": "생명의 샘",
    "Reflex Block": "반사의 완갑", "Protector Contract": "수호자의 계약서",
    "Kinetic Shield": "반응형 장갑", "Warmail": "전쟁 갑옷",
    "Coat of Plates": "판금 흉갑",
    "Pulseweave": "척력장", "Crucible": "도가니",
    "Capacitor Plate": "축전판", "Rooks Decree": "수호령",
    "Fountain of Renewal": "재생의 분수", "Aegis": "이지스",
    "Slumbering Husk": "거대괴수 갑주", "Metal Jacket": "용린갑",
    "Atlas Pauldron": "거인의 견갑",
    "Sprint Boots": "가죽 신발", "Travel Boots": "신속의 신발",
    "Teleport Boots": "순간이동 신발", "Journey Boots": "질주의 신발",
    "War Treads": "전쟁 걸음", "Halcyon Chargers": "할시온 박차",
    "Contraption": "만능 허리띠", "Stormcrown": "폭풍우 왕관",
    "Shiversteel": "만년한철", "Stormguard Banner": "경비대의 깃발",
    "SuperScout 2000": "강화부표",
    "Crystal Infusion": "수정강화제", "Weapon Infusion": "타격 강화제",
    "Dragonblood Contract": "용의피 계약서", "Ironguard Contract": "경비대의 계약서",
    "Defense T1": "방어T1(미확인)", "Weapon T2": "무기T2(미확인)",
    "Weapon T2-T3": "무기T2-T3(미확인)", "Flare": "조명탄",
    "Unknown 201": "시작템(201)", "Unknown 217": "계약서(217)",
}


def le_to_be(v):
    return struct.unpack('>H', struct.pack('<H', v))[0]


def extract_players(data):
    players = []
    seen = set()
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            if pos + 0xD6 > len(data):
                pos += 1
                continue
            ns = pos + len(marker)
            ne = ns
            while ne < len(data) and ne < ns + 30:
                if data[ne] < 32 or data[ne] > 126:
                    break
                ne += 1
            name = data[ns:ne].decode('ascii', errors='replace')
            if len(name) >= 3 and not name.startswith('GameMode'):
                eid_le = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                eid_be = le_to_be(eid_le)
                team_byte = data[pos + 0xD5]
                team = "left" if team_byte == 1 else "right" if team_byte == 2 else "?"
                hero_id = struct.unpack('<H', data[pos + 0xA9:pos + 0xA9 + 2])[0]
                he = BINARY_HERO_ID_MAP.get(hero_id)
                hero_name = he if isinstance(he, str) else (he.get('name', '?') if isinstance(he, dict) else f'?({hero_id})')
                if eid_le not in seen:
                    players.append({'name': name, 'eid_be': eid_be, 'team': team, 'hero': hero_name})
                    seen.add(eid_le)
            pos += 1
    return players


def extract_item_sequences(all_data, player_eids):
    seqs = defaultdict(list)
    pos = 0
    while True:
        pos = all_data.find(ITEM_ACQUIRE, pos)
        if pos == -1:
            break
        if pos + 20 > len(all_data):
            pos += 1
            continue
        if all_data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid not in player_eids:
            pos += 1
            continue
        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        ts = struct.unpack_from(">f", all_data, pos + 16)[0]
        seqs[eid].append((ts, item_id))
        pos += 3
    return seqs


def estimate_final_build(item_ids_set):
    """Remove consumed components, starters. Return up to 6 items."""
    remaining = set(item_ids_set) - STARTER_IDS

    # Iteratively remove components that have been upgraded
    changed = True
    while changed:
        changed = False
        to_remove = set()
        for comp_id, result_ids in UPGRADE_TREE.items():
            if comp_id in remaining and (remaining & result_ids):
                to_remove.add(comp_id)
        if to_remove:
            remaining -= to_remove
            changed = True

    # Convert to named items, sorted by tier desc
    items = []
    for iid in remaining:
        info = ITEM_ID_MAP.get(iid)
        if info:
            items.append((info.get('tier', 0), info['name'], iid))
        else:
            items.append((-1, f"Unknown_{iid}", iid))

    items.sort(key=lambda x: (-x[0], x[1]))
    return items[:6]


def main():
    with open('vg/output/tournament_truth.json', 'r') as f:
        truth = json.load(f)

    MATCH_NAMES = {
        0: "SFC vs Team Stooopid (Semi) - Game 1",
        1: "SFC vs Team Stooopid (Semi) - Game 2",
        2: "SFC vs Maitun Gaming - Game 1",
        3: "SFC vs Maitun Gaming - Game 2",
        4: "SFC vs Law Enforcers (Finals) - Game 1",
        5: "SFC vs Law Enforcers (Finals) - Game 2",
        6: "SFC vs Law Enforcers (Finals) - Game 3",
        7: "SFC vs Law Enforcers (Finals) - Game 4",
        8: "SFC vs Law Enforcers (Finals) - Game 5 (Incomplete)",
        9: "Buffalo vs RRONE - Game 1",
        10: "Buffalo vs RRONE - Game 2",
    }

    result = {
        "description": "Estimated final build per player. Upgrade components removed. Max 6 slots.",
        "matches": [],
    }

    for mi, match in enumerate(truth['matches']):
        rf = match['replay_file']
        base = rf.rsplit('.0.vgr', 1)[0]
        frames = []
        idx = 0
        while True:
            fp = f"{base}.{idx}.vgr"
            if os.path.exists(fp):
                with open(fp, 'rb') as ff:
                    frames.append(ff.read())
                idx += 1
            else:
                break
        if not frames:
            continue

        players = extract_players(frames[0])
        all_data = b''.join(frames)
        player_eids = {p['eid_be'] for p in players}
        seqs = extract_item_sequences(all_data, player_eids)

        match_data = {
            "match": mi + 1,
            "match_name": MATCH_NAMES.get(mi, f"Match {mi+1}"),
            "players": {},
        }

        for p in players:
            seq = seqs.get(p['eid_be'], [])
            all_ids = {iid for _, iid in seq}
            final = estimate_final_build(all_ids)

            items_en = [name for _, name, _ in final]
            items_ko = [EN_TO_KO.get(name, f"?{name}") for name in items_en]

            match_data["players"][p['name']] = {
                "hero": p['hero'],
                "team": p['team'],
                "final_build": items_en,
                "final_build_ko": items_ko,
                "slot_count": len(final),
            }

        result["matches"].append(match_data)

    out_path = "D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays/extracted_items_all_matches.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Done! {len(result['matches'])} matches")
    for m in result['matches']:
        print(f"\n=== M{m['match']}: {m['match_name']} ===")
        for pname, pdata in m['players'].items():
            slots = pdata['slot_count']
            build = ' | '.join(pdata['final_build_ko'])
            print(f"  {pname:<20} {pdata['hero']:<15} [{slots}] {build}")


if __name__ == '__main__':
    main()
