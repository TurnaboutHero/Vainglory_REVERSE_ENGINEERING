# Vainglory 아이템 한/영 매핑 (Korean/English Item Mapping)

Source: 나무위키 베인글로리/아이템

## CRITICAL DISCOVERY: Two item acquisition mechanisms

The `[10 04 3D]` acquire event uses a `qty` byte at offset +9:
- **qty=1 + IDs 200-255**: Standard shop purchase (T1/T2/T3 components)
- **qty=2 + IDs 0-27**: T3/special item completion (crafted from components)

Evidence that qty=2 = items (NOT ability upgrades):
- Only 2-5 qty=2 events per player (max level=12, ability upgrades would need 12)
- Hero role distribution matches expected item buyers perfectly
- ID 14 is universal system event (excluded)

Previous hypothesis that "low IDs are ability upgrades" was WRONG.
The original low ID → item mappings were actually CORRECT.

## 2. 타격 아이템 (Weapon Items)

### T1
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 단검 | Weapon Blade | 202 | tentative |
| 찬가의 고서 | Book of Eulogies | 243 | confirmed |
| 자동 권총 | Swift Shooter | 204 | confirmed |
| 여우 발 | Minion's Foot | ? | unmapped |

### T2
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 강철 대검 | Heavy Steel | 249 | tentative |
| 죄악의 표창 | Six Sins | 205 | tentative |
| 가시 바늘 | Barbed Needle | 237 | tentative |
| 미늘창 | Piercing Spear | 250 | tentative |
| 기관단총 | Blazing Salvo | 207 | tentative |
| 행운의 과녁 | Lucky Strike | 235 | confirmed |

### T3
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 비탄의 도끼 | Sorrowblade | 208 | confirmed |
| 바다뱀의 가면 | Serpent Mask | 223 | confirmed |
| 주문검 | Spellsword | 12 | inferred (qty=2, Caine 7x dominant) |
| 맹독 단검 | Poisoned Shiv | 252 | tentative (WP 100%, co-occurs w/ Blazing Salvo+Barbed Needle) |
| 천공기 | Breaking Point | 251 | confirmed |
| 탄성궁 | Tension Bow | 224 | confirmed |
| 뼈톱 | Bonesaw | 226 | confirmed |
| 폭풍인도자 | Tornado Trigger | 210 | confirmed |
| 폭군의 단안경 | Tyrant's Monocle | 5 | inferred (qty=2, Baron 6x, Ringo 5x) |

## 3. 수정 아이템 (Crystal Items)

### T1
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 수정 조각 | Crystal Bit | 203 | tentative |
| 에너지 배터리 | Energy Battery | 206 | tentative |
| 모래시계 | Hourglass | 216 | tentative |

### T2
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 대형 프리즘 | Heavy Prism | 0 | inferred (qty=2, 63 CP buyers) |
| 일식 프리즘 | Eclipse Prism | ? | unmapped |
| 공허의 배터리 | Void Battery | ? | unmapped |
| 관통 샤드 | Piercing Shard | 254 | confirmed |
| 초시계 | Chronograph | 218 | tentative |

### T3
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 강화유리 | Shatterglass | 209 | confirmed |
| 주문불꽃 | Spellfire | 10 | inferred (qty=2, 38 CP mages) |
| 얼음불꽃 | Frostburn | 230 | confirmed |
| 용의 눈 | Dragon's Eye | 11 | inferred (qty=2, 19 CP carries) |
| 시계장치 | Clockwork | 220 | confirmed |
| 신화의 종말 | Broken Myth | 240 | confirmed |
| 영혼수확기 | Eve of Harvest | 255 | confirmed |
| 연쇄충격기 | Aftershock | 236 | confirmed |
| 교류 전류 | Alternating Current | 253 | confirmed |

## 4. 방어 아이템 (Defense Items)

### T1
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 떡갈나무 심장 | Oakheart | 212 | tentative |
| 작은 방패 | Light Shield | 211 | tentative |
| 가죽 갑옷 | Light Armor | 213 | tentative |

### T2
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 용심장 | Dragonheart | 214 | tentative |
| 생명의 샘 | Lifespring | 248 | tentative |
| 반사의 완갑 | Reflex Block | 229 | tentative |
| 수호자의 계약서 | Protector Contract | ? | unmapped |
| 반응형 장갑 | Kinetic Shield | 246 | tentative |
| 전쟁갑옷 | Warmail | 26 | inferred (qty=2, 45 captain/tank buyers) |
| 판금 흉갑 | Coat of Plates | 228 | tentative (4 tank buyers, co-occurs w/ Light Armor 100%) |

### T3
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 척력장 | Pulseweave | 21 | inferred (qty=2, 40 bruiser/tank buyers) |
| 도가니 | Crucible | 232 | confirmed |
| 축전판 | Capacitor Plate | 22 | inferred (qty=2, 25 captain buyers) |
| 수호령 | Rook's Decree | 23 | inferred (qty=2, 16 captain buyers) |
| 재생의 분수 | Fountain of Renewal | 231 | confirmed |
| 이지스 | Aegis | 247 | confirmed |
| 거대괴수 갑주 | Slumbering Husk | 13 | inferred (qty=2, 19 mixed carry+tank) |
| 용린갑 | Metal Jacket | 27 | inferred (qty=2, 31 bruiser+carry buyers) |
| 거인의 견갑 | Atlas Pauldron | 242 | confirmed |

## 5. 보조 아이템 (Utility Items)

### T1
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 가죽 신발 | Sprint Boots | 221 | tentative |

### T2
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 신속의 신발 | Travel Boots | 222 | tentative |
| 조명탄총 | Flare Gun | ? | unmapped |
| 경비대의 깃발 | Stormguard Banner | 219 | tentative |

### T3
| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 순간이동 신발 | Teleport Boots | ? | unmapped |
| 질주의 신발 | Journey Boots | 1 | inferred (qty=2, 57 melee/bruiser buyers) |
| 전쟁 걸음 | War Treads | 241 | confirmed |
| 할시온 박차 | Halcyon Chargers | 234 | confirmed |
| 만능 허리띠 | Contraption | 16 | inferred (qty=2, 15 captain buyers) |
| 폭풍우 왕관 | Stormcrown | 7 | inferred (qty=2, 39 jungler/bruiser buyers) |
| 만년한철 | Shiversteel | 17 | inferred (qty=2, 13 captain buyers) |

## 6. 기타 (Consumables / Others)

| 한국어 | English | Binary ID | Status |
|--------|---------|-----------|--------|
| 조명탄총 | Flare Gun | ? | unmapped |
| 회복연고 | Healing Flask | ? | unmapped |
| 조명탄 | Flare | 238 | confirmed |
| 정찰 지뢰 | Scout Trap | 225 | tentative (captains, qty up to 24x) |
| 미니언 사탕 | Minion Candy | ? | unmapped |
| 정찰 부표 | Scout Cam | ? | unmapped |
| 다용도 부표 | ScoutPak | ? | unmapped |
| 고성능 부표 | ScoutTuff | ? | unmapped |
| 강화 부표 | SuperScout 2000 | 15 | inferred (qty=2, 12 captain buyers) |
| 경비대의 계약서 | Ironguard Contract | ? | unmapped |
| 수호자의 계약서 | Protector Contract | ? | unmapped |
| 용의 피 계약서 | Dragonblood Contract | ? | unmapped |
| 타격 강화제 | Weapon Infusion | 244 | confirmed |
| 수정 강화제 | Crystal Infusion | 233? | unknown (4 buyers, very late game) |
| 레벨 주스 | Level Juice | ? | unmapped |

## 8. 삭제된 아이템 (Deleted Items)

| 한국어 | English | Notes |
|--------|---------|-------|
| 전쟁의 뿔피리 | Warhorn | deleted |
| 경비대의 계약서 | Ironguard | deleted (old version) |
| 할시온 물약 | Halcyon Potion | deleted |
| 골드 항아리 | Pot of Gold | deleted |
| 메아리 | Echo | deleted |

## Binary ID Summary

### Two ID ranges (56 replays, 502 players, 58 unique items)

| Range | qty | Count | Description |
|-------|-----|-------|-------------|
| 200-255 | 1 | 40 mapped | Standard shop purchases (T1/T2/T3) |
| 0-27 | 2 | 16 mapped | T3/special item completions (crafted) |
| 14 | 2 | system | Universal system event (excluded) |
| 201 | 1 | system | Starting item (every player, avg 13s) |

### qty=2 items (IDs 0-27) - T3/special item completions

| ID | Item | Category | Buyers | Top Heroes |
|----|------|----------|--------|------------|
| 0 | Heavy Prism | Crystal T2 | 63 | All CP heroes |
| 1 | Journey Boots | Utility T3 | 57 | Melee/bruiser |
| 5 | Tyrant's Monocle | Weapon T3 | 15 | Baron 6x, Ringo 5x |
| 7 | Stormcrown | Utility T3 | 39 | Junglers/bruisers |
| 10 | Spellfire | Crystal T3 | 38 | CP mages |
| 11 | Dragon's Eye | Crystal T3 | 19 | CP carries |
| 12 | Spellsword | Weapon T3 | 12 | Caine 7x |
| 13 | Slumbering Husk | Defense T3 | 19 | Mixed carry+tank |
| 15 | SuperScout 2000 | Utility T3 | 12 | All captains |
| 16 | Contraption | Utility T3 | 15 | All captains |
| 17 | Shiversteel | Defense T3 | 13 | All captains |
| 21 | Pulseweave | Defense T3 | 40 | Bruisers/tanks |
| 22 | Capacitor Plate | Defense T3 | 25 | All captains |
| 23 | Rook's Decree | Defense T3 | 16 | All captains |
| 26 | Warmail | Defense T2 | 45 | Captains/tanks |
| 27 | Metal Jacket | Defense T3 | 31 | Bruisers+carries |

### Consumables (excluded from final build)

| ID | qty | Item | Note |
|----|-----|------|------|
| 8 | 2 | Weapon Infusion | WP carries, late-game |
| 18 | 2 | Crystal Infusion | Mixed, late-game |
| 20 | 2 | Flare Gun | Captains |
| 225 | 1 | Scout Trap | Captains, qty up to 24x |
| 238 | 1 | Flare | Vision consumable |
| 244 | 1 | Weapon Infusion | WP buff consumable |

### Encoding note
IDs > 255 (e.g., 65505=0xFFE1, 65519=0xFFEF) are encoding artifacts.
The low byte is the real ID (225, 239). The decoder normalizes these with `item_id & 0xFF`.
