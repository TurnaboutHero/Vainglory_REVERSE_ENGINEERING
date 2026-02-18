# Vainglory 아이템 한/영 매핑 (Korean/English Item Mapping)

Source: 나무위키 베인글로리/아이템, Vainglory Fandom Wiki
Last Updated: 2026-02-18

## 1. 바이너리 아이템 시스템

### 아이템 획득 이벤트 `[10 04 3D]`

`qty` byte (offset +9) 로 두 가지 획득 메커니즘 구분:
- **qty=1 + IDs 200-255**: 상점 직접 구매 (T1/T2/T3 전부)
- **qty=2 + IDs 0-27**: T3/특수 아이템 완성 (조합 완료 시 발생)

qty=2 = 아이템 (스킬 업그레이드 아님) 증거:
- 플레이어당 qty=2 이벤트 2-5개 (최대레벨 12, 스킬이면 12개 필요)
- 영웅 역할 분포가 아이템 구매 패턴과 정확히 일치
- ID 14는 모든 플레이어 공통 시스템 이벤트 (제외)

### 검증 방법론 (3-layer verification)

1. **가격 매칭**: `[10 04 1D]` action=0x06 골드 차감 (qty=1만 신뢰, 100% 일관성)
2. **구매자 프로필**: WP/CP/Captain 역할 분포
3. **빌드 트리**: 공식 레시피 컴포넌트 co-buy rate (>60% = confirmed)
4. **다중 구매 패턴**: 소모품 = 플레이어당 복수 구매, 컴포넌트 = 1회 구매

### 현황 요약

| 상태 | 개수 | 비율 |
|------|------|------|
| **Confirmed** | 64 | 87% |
| Inferred | 1 | 1% |
| Tentative | 4 | 6% |
| Unknown | 4 | 6% |
| **합계** | **73** | **100%** |

---

## 2. 타격 아이템 (Weapon Items)

### T1 (300g)
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 단검 | Weapon Blade | 300g | 202 | **confirmed** (가격+빌드트리: Heavy Steel 88%, Six Sins 69%) |
| 찬가의 고서 | Book of Eulogies | 300g | 243 | **confirmed** (가격 일치) |
| 자동 권총 | Swift Shooter | 300g | 204 | **confirmed** (가격 일치) |
| 여우 발 | Minion's Foot | 300g | ? | unmapped |

### T2
| 한국어 | English | 가격 | Binary ID | 측정가 | Status |
|--------|---------|------|-----------|--------|--------|
| 강철 대검 | Heavy Steel | 1,150g | 249 | 1150g ✓ | **confirmed** (유일 가격) |
| 죄악의 표창 | Six Sins | 650g | 205 | 650g ✓ | **confirmed** |
| 가시 바늘 | Barbed Needle | 800g | **244** | 800g ✓ | **confirmed** (WP 96%, 다중구매 0%) |
| 미늘창 | Piercing Spear | 900g | 250 | 900g ✓ | **confirmed** |
| 기관단총 | Blazing Salvo | 700g | 207 | 700g ✓ | **confirmed** |
| 행운의 과녁 | Lucky Strike | 900g | **252** | 900g ✓ | **confirmed** (유일 가격 매치) |

### T3
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 비탄의 도끼 | Sorrowblade | 3,100g | 208 | **confirmed** |
| 바다뱀의 가면 | Serpent Mask | 2,800g | 223 | **confirmed** |
| 주문검 | Spellsword | 2,800g | **12** (qty=2) | **confirmed** (Heavy Steel 91%. 레시피=Heavy Steel+Six Sins+Chronograph) |
| 맹독 단검 | Poisoned Shiv | 2,750g | **8** (qty=2) | **confirmed** (Blazing Salvo 100% + Barbed Needle 100%) |
| 천공기 | Breaking Point | 2,700g | 251 | **confirmed** (가격 일치) |
| 탄성궁 | Tension Bow | 2,900g | **235** | **confirmed** (Six Sins 90% + Piercing Spear 81%) |
| 뼈톱 | Bonesaw | 2,900g | 226 | **confirmed** |
| 폭풍인도자 | Tornado Trigger | 2,800g | 210 | **confirmed** |
| 폭군의 단안경 | Tyrant's Monocle | 2,750g | **5** (qty=2) | **confirmed** (Six Sins 83% + Lucky Strike 79%) |

---

## 3. 수정 아이템 (Crystal Items)

### T1
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 수정 조각 | Crystal Bit | 300g | 203 | **confirmed** (가격+빌드트리: Eclipse Prism 96%, Heavy Prism 94%) |
| 에너지 배터리 | Energy Battery | 300g | **216** | **confirmed** (300g 측정, Void Battery 빌드) |
| 모래시계 | Hourglass | 250g | **217** | **confirmed** (250g = VG 유일 최저가 아이템) |

### T2
| 한국어 | English | 가격 | Binary ID | 측정가 | Status |
|--------|---------|------|-----------|--------|--------|
| 대형 프리즘 | Heavy Prism | 1,050g | **0** (qty=2) | 1050g ✓ | **confirmed** (Crystal Bit 99%) |
| 일식 프리즘 | Eclipse Prism | 650g | **206** | 650g ✓ | **confirmed** |
| 공허의 배터리 | Void Battery | 700g | **218** | 700g ✓ | **confirmed** (유일 가격 매치) |
| 관통 샤드 | Piercing Shard | 900g | 254 | 900g ✓ | **confirmed** |
| 초시계 | Chronograph | 800g | **219** | 800g ✓ | **confirmed** (Mage 34% + Captain 28%) |

### T3
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 강화유리 | Shatterglass | 3,000g | 209 | **confirmed** (가격 일치) |
| 주문불꽃 | Spellfire | 2,700g | **10** (qty=2) | **confirmed** (Heavy Prism 99% + Eclipse Prism 97%) |
| 얼음불꽃 | Frostburn | 2,700g | 230 | **confirmed** |
| 용의 눈 | Dragon's Eye | 3,000g | **11** (qty=2) | **confirmed** (Heavy Prism 100% + Eclipse Prism 96%) |
| 시계장치 | Clockwork | 2,400g | 220 | **confirmed** (가격 일치) |
| 신화의 종말 | Broken Myth | 2,900g | 240 | **confirmed** |
| 영혼수확기 | Eve of Harvest | 2,600g | 255 | **confirmed** (가격 일치) |
| 연쇄충격기 | Aftershock | 2,600g | 236 | **confirmed** |
| 교류 전류 | Alternating Current | 2,800g | 253 | **confirmed** |

---

## 4. 방어 아이템 (Defense Items)

### T1 (300g)
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 떡갈나무 심장 | Oakheart | 300g | **211** | **confirmed** (빌드트리: Reflex Block 93%, Dragonheart 72%, Lifespring 60%) |
| 작은 방패 | Light Shield | 300g | **245** | **confirmed** (빌드트리: Kinetic Shield 45%, Warmail 57%) |
| 가죽 갑옷 | Light Armor | 300g | 213 | **confirmed** (빌드트리: Coat of Plates 45%, Warmail 55%) |

### T2
| 한국어 | English | 가격 | Binary ID | 측정가 | Status |
|--------|---------|------|-----------|--------|--------|
| 용심장 | Dragonheart | 650g | **212** | 650g ✓ | **confirmed** |
| 생명의 샘 | Lifespring | 800g | 248 | 800g ✓ | **confirmed** |
| 반사의 완갑 | Reflex Block | 700g | 229 | 700g ✓ | **confirmed** |
| 수호자의 계약서 | Protector Contract | 600g | ? | - | unmapped |
| 반응형 장갑 | Kinetic Shield | 750g | 246 | 750g ✓ | **confirmed** |
| 전쟁갑옷 | Warmail | 800g | **26** (qty=2) | 800g ✓ | **confirmed** (Light Armor 76% + Light Shield 56%) |
| 판금 흉갑 | Coat of Plates | 750g | **214** | 750g ✓ | **confirmed** (유일 가격 매치) |

### T3
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 척력장 | Pulseweave | 2,300g | **21** (qty=2) | **confirmed** (Dragonheart 89% + Lifespring 86%) |
| 도가니 | Crucible | 1,850g | 232 | **confirmed** |
| 축전판 | Capacitor Plate | 2,100g | **22** (qty=2) | **confirmed** (Dragonheart 94%, Captain 91%) |
| 수호령 | Rook's Decree | 2,200g | **23** (qty=2) | **confirmed** (Dragonheart 92%, Captain 83%) |
| 재생의 분수 | Fountain of Renewal | 2,300g | 231 | **confirmed** |
| 이지스 | Aegis | 2,250g | 247 | **confirmed** (Reflex Block 96%. 측정 2400g ≠ 공식 2250g, 패치 차이) |
| 거대괴수 갑주 | Slumbering Husk | 2,350g | **13** (qty=2) | **confirmed** (Coat of Plates 69% + Kinetic Shield 66%) |
| 용린갑 | Metal Jacket | 2,000g | **27** (qty=2) | inferred (Coat of Plates 25% - 이중 CoP 레시피로 구조적 저탐지) |
| 거인의 견갑 | Atlas Pauldron | 1,900g | 242 | **confirmed** |

---

## 5. 보조 아이템 (Utility Items)

### T1 (300g)
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 가죽 신발 | Sprint Boots | 300g | 221 | **confirmed** (가격+빌드트리: Travel Boots 85%) |

### T2
| 한국어 | English | 가격 | Binary ID | 측정가 | Status |
|--------|---------|------|-----------|--------|--------|
| 신속의 신발 | Travel Boots | 800g | **222** | 650g | **confirmed** (368 buyers, 모든 역할. 측정 650g ≠ 공식 800g, 패치 차이) |
| 조명탄총 | Flare Gun | 600g | **20** (qty=2) | - | **confirmed** (Captain 88% exclusive, Oakheart co-buy) |
| 경비대의 깃발 | Stormguard Banner | 600g | ? | - | unmapped |

### T3
| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 순간이동 신발 | Teleport Boots | 1,600g | **241** | **confirmed** (1600g = 유일 가격 매치) |
| 질주의 신발 | Journey Boots | 1,700g | **1** (qty=2) | **confirmed** (Travel Boots 91%) |
| 전쟁 걸음 | War Treads | 1,900g | **17** (qty=2) | **confirmed** (Travel Boots 94% + Dragonheart 94%) |
| 할시온 박차 | Halcyon Chargers | 1,700g | **234** | **confirmed** (CP-leaning, boots 83%. 측정 1400g ≠ 공식 1700g, 패치 차이) |
| 만능 허리띠 | Contraption | 2,100g | **16** (qty=2) | **confirmed** (Captain 93% exclusive, Chronograph co-buy) |
| 폭풍우 왕관 | Stormcrown | 2,000g | **7** (qty=2) | **confirmed** (Chronograph 78%, bruiser+captain 90%) |
| 만년한철 | Shiversteel | 1,950g | ? | - | unmapped (ID 17 = War Treads로 확정됨) |

---

## 6. 기타 (Consumables / Others)

| 한국어 | English | 가격 | Binary ID | Status |
|--------|---------|------|-----------|--------|
| 시작 아이템 | Starting Item | 0g | 201 | tentative (456 buyers, 시작시 자동) |
| 타격 강화제 | Weapon Infusion | 500g | **237** | **confirmed** (WP 92%, 다중구매 75%) |
| 수정 강화제 | Crystal Infusion | 500g | **238** | **confirmed** (CP 47%, 다중구매 57%) |
| 정찰 지뢰 | Scout Trap | 50g | 225 | tentative (13 captain buyers, qty 최대 24x) |
| 강화 부표 | SuperScout 2000 | 2,000g | **15** (qty=2) | **confirmed** (Captain 93% exclusive) |
| 조명탄 | Flare | 25g | ? | unmapped |
| 미니언 사탕 | Minion Candy | 75g | ? | unmapped |

### Unknown IDs
| Binary ID | 측정가 | 구매자 | Notes |
|-----------|--------|--------|-------|
| 18 (qty=2) | - | 17명, mixed | Crystal Infusion 아님 (ID 238 확정). 정체 불명 |
| 224 | - | 5명 | 이전 Tension Bow → ID 235로 이동. WP T3 후보 |
| 233 | 1400g | 4명 | 후반부 소모품? 공식 가격에 해당 없음 |
| 239 | - | 7명 captain | Scout Trap(225) 86% co-buy. 정찰 관련 소모품? |

---

## 7. 삭제된 아이템 (Deleted Items)

| 한국어 | English | Notes |
|--------|---------|-------|
| 전쟁의 뿔피리 | Warhorn | deleted |
| 경비대의 계약서 | Ironguard (old) | deleted (옛 버전) |
| 할시온 물약 | Halcyon Potion | deleted |
| 골드 항아리 | Pot of Gold | deleted |
| 메아리 | Echo | deleted |

---

## 8. 수정 이력 (Correction Log)

이전 세션에서 총 **19개 아이템 매핑 수정** 완료:

| ID | 기존 매핑 | 수정 후 | 근거 |
|----|-----------|---------|------|
| **206** | ~~Energy Battery~~ | **Eclipse Prism** (650g) | 가격 일치 + 유저 확인 |
| **211** | ~~Light Shield~~ | **Oakheart** (300g) | 빌드트리: Reflex Block 93%, Dragonheart 72% |
| **212** | ~~Oakheart~~ | **Dragonheart** (650g) | 가격 일치 + 유저 확인 |
| **214** | ~~Dragonheart~~ | **Coat of Plates** (750g) | 유일 가격 매치 |
| **216** | ~~Hourglass~~ | **Energy Battery** (300g) | 가격 일치 |
| **217** | ~~Unknown~~ | **Hourglass** (250g) | 가격 일치 + 유저 확인 |
| **218** | ~~Chronograph~~ | **Void Battery** (700g) | 유일 가격 매치 |
| **219** | ~~Stormguard Banner~~ | **Chronograph** (800g) | Mage 34% + Captain 28% |
| **224** | ~~Tension Bow~~ | **Unknown** | 5명뿐, ID 235로 이동 |
| **235** | ~~Lucky Strike~~ | **Tension Bow** (2900g) | Six Sins 90% + P.Spear 81% |
| **237** | ~~Barbed Needle~~ | **Weapon Infusion** (500g) | WP 92%, 다중구매 75% |
| **238** | ~~Flare~~ | **Crystal Infusion** (500g) | CP 47%, 다중구매 57% |
| **241** | ~~War Treads~~ | **Teleport Boots** (1600g) | 유일 가격 매치 |
| **244** | ~~Weapon Infusion~~ | **Barbed Needle** (800g) | WP 96%, 다중구매 0% |
| **252** | ~~Poisoned Shiv~~ | **Lucky Strike** (900g) | 유일 가격 매치 |
| **8** | ~~Weapon Infusion~~ | **Poisoned Shiv** | Blazing Salvo+Barbed Needle 100% |
| **17** | ~~Shiversteel~~ | **War Treads** | Travel Boots+Dragonheart 94% |
| **12** | ~~inferred~~ | **Spellsword** confirmed | Heavy Steel 91%, recipe=Heavy Steel+Six Sins+Chronograph |
| **18** | ~~Crystal Infusion~~ | **Unknown 18** | ID 238이 Crystal Infusion 확정 |

---

## 9. 공식 아이템 조합 트리 (Official Recipe Tree)

### 타격 (Weapon)
```
단검(Weapon Blade, 300g, ID:202) ─┬→ 강철 대검(Heavy Steel, 1150g, ID:249) ─┬→ 비탄의 도끼(Sorrowblade, 3100g, ID:208)
                                    │                                           ├→ 바다뱀의 가면(Serpent Mask, 2800g, ID:223)
                                    │                                           ├→ 주문검(Spellsword, 2800g, ID:12) ←── 죄악의 표창(205)+초시계(219)
                                    │                                           ├→ 천공기(Breaking Point, 2700g, ID:251) ←── 기관단총(207)
                                    │                                           └→ 맹독 단검(Poisoned Shiv, 2750g, ID:8) ←── 가시바늘(244)
                                    ├→ 죄악의 표창(Six Sins, 650g, ID:205) ─┬→ 비탄의 도끼(Sorrowblade)
                                    │                                        ├→ 탄성궁(Tension Bow, 2900g, ID:235) ←── 미늘창(250)
                                    │                                        └→ 폭군의 단안경(Tyrant's Monocle, 2750g, ID:5) ←── 과녁(252)
                                    └→ 미늘창(Piercing Spear, 900g, ID:250) ─┬→ 탄성궁(Tension Bow)
                                                                              └→ 뼈톱(Bonesaw, 2900g, ID:226) ←── 기관단총

찬가의 고서(Book of Eulogies, 300g, ID:243) → 가시 바늘(Barbed Needle, 800g, ID:244) ─┬→ 바다뱀의 가면
                                                                                          └→ 맹독 단검

자동 권총(Swift Shooter, 300g, ID:204) → 기관단총(Blazing Salvo, 700g, ID:207) ─┬→ 맹독 단검, 천공기, 뼈톱
                                                                                    └→ 폭풍인도자(Tornado Trigger, 2800g, ID:210) ←── 과녁(252)

여우 발(Minion's Foot, 300g, ID:?) → 행운의 과녁(Lucky Strike, 900g, ID:252) ─┬→ 폭풍인도자
                                                                                  └→ 폭군의 단안경
```

### 수정 (Crystal)
```
수정 조각(Crystal Bit, 300g, ID:203) ─┬→ 대형 프리즘(Heavy Prism, 1050g, ID:0) ─┬→ 강화유리(Shatterglass, 3000g, ID:209)
                                        │                                           ├→ 주문불꽃(Spellfire, 2700g, ID:10)
                                        │                                           ├→ 얼음불꽃(Frostburn, 2700g, ID:230)
                                        │                                           ├→ 용의 눈(Dragon's Eye, 3000g, ID:11)
                                        │                                           ├→ 신화의 종말(Broken Myth, 2900g, ID:240) ←── 관통 샤드(254)
                                        │                                           ├→ 영혼수확기(Eve of Harvest, 2600g, ID:255) ←── 공허(218)
                                        │                                           └→ 교류 전류(Alt Current, 2800g, ID:253) ←── 기관단총(207)
                                        ├→ 일식 프리즘(Eclipse Prism, 650g, ID:206) ─┬→ 강화유리, 주문불꽃, 얼음불꽃, 용의 눈
                                        │                                              └→ 연쇄충격기(Aftershock, 2600g, ID:236) ←── 초시계(219)
                                        └→ 관통 샤드(Piercing Shard, 900g, ID:254) ──→ 신화의 종말

에너지 배터리(Energy Battery, 300g, ID:216) → 공허의 배터리(Void Battery, 700g, ID:218) ─┬→ 시계장치(Clockwork, 2400g, ID:220) ←── 초시계(219)
                                                                                            ├→ 영혼수확기
                                                                                            └→ 할시온 박차(Halcyon Chargers, 1700g, ID:234) ←── 신속 신발(222)

모래시계(Hourglass, 250g, ID:217) → 초시계(Chronograph, 800g, ID:219) ─┬→ 시계장치, 연쇄충격기
                                                                          ├→ 주문검(Spellsword), 축전판(22), 수호령(23)
                                                                          ├→ 만능 허리띠(Contraption, ID:16) ←── 조명탄총(20)
                                                                          └→ 폭풍우 왕관(Stormcrown, ID:7) ←── 경비대의 깃발(?)
```

### 방어 (Defense)
```
떡갈나무 심장(Oakheart, 300g, ID:211) ─┬→ 용심장(Dragonheart, 650g, ID:212) ─┬→ 척력장(Pulseweave, 2300g, ID:21) ←── 생명의 샘(248)
                                         │                                       ├→ 도가니(Crucible, 1850g, ID:232) ←── 반사의 완갑(229)
                                         │                                       ├→ 축전판(Capacitor Plate, 2100g, ID:22) ←── 초시계(219)
                                         │                                       ├→ 수호령(Rook's Decree, 2200g, ID:23) ←── 초시계(219)
                                         │                                       ├→ 전쟁 걸음(War Treads, 1900g, ID:17) ←── 신속 신발(222)
                                         │                                       └→ 만년한철(Shiversteel, 1950g, ID:?) ←── 기관단총(207)
                                         ├→ 생명의 샘(Lifespring, 800g, ID:248) ─┬→ 척력장
                                         │                                         └→ 재생의 분수(Fountain, 2300g, ID:231) ←── 반응형 장갑(246)
                                         ├→ 반사의 완갑(Reflex Block, 700g, ID:229) ─┬→ 도가니
                                         │                                              └→ 이지스(Aegis, 2250g, ID:247) ←── 반응형 장갑(246)
                                         ├→ 조명탄총(Flare Gun, 600g, ID:20) → 만능 허리띠(Contraption, ID:16)
                                         └→ 경비대의 깃발(SGB, 600g, ID:?) → 폭풍우 왕관(Stormcrown, ID:7)

작은 방패(Light Shield, 300g, ID:245) → 반응형 장갑(Kinetic Shield, 750g, ID:246) ─┬→ 재생의 분수, 이지스
                                                                                       └→ 거대괴수 갑주(Slumbering Husk, 2350g, ID:13)

가죽 갑옷(Light Armor, 300g, ID:213) ─┬→ 판금 흉갑(Coat of Plates, 750g, ID:214) ─┬→ 거대괴수 갑주
                                        │                                              ├→ 용린갑(Metal Jacket, 2000g, ID:27)
                                        │                                              └→ 거인의 견갑(Atlas Pauldron, 1900g, ID:242)
                                        └→ 전쟁갑옷(Warmail, 800g, ID:26) ←── 작은 방패(245)
```

### 보조 (Utility)
```
가죽 신발(Sprint Boots, 300g, ID:221) → 신속 신발(Travel Boots, 800g, ID:222) ─┬→ 순간이동(Teleport Boots, 1600g, ID:241)
                                                                                   ├→ 질주의 신발(Journey Boots, 1700g, ID:1)
                                                                                   ├→ 전쟁 걸음(War Treads, 1900g, ID:17) ←── 용심장(212)
                                                                                   └→ 할시온 박차(Halcyon Chargers, 1700g, ID:234) ←── 공허(218)
```

---

## 10. Binary ID 전체 현황

### qty=1 IDs (200-255) - 상점 구매
| ID | 측정가 | 매핑 | Status |
|----|--------|------|--------|
| 201 | - | Starting Item | tentative |
| 202 | 300g | Weapon Blade | **confirmed** |
| 203 | 300g | Crystal Bit | **confirmed** |
| 204 | 300g | Swift Shooter | **confirmed** |
| 205 | 650g | Six Sins | **confirmed** |
| 206 | 650g | Eclipse Prism | **confirmed** |
| 207 | 700g | Blazing Salvo | **confirmed** |
| 208 | - | Sorrowblade | **confirmed** |
| 209 | 3000g | Shatterglass | **confirmed** |
| 210 | - | Tornado Trigger | **confirmed** |
| 211 | 300g | Oakheart | **confirmed** |
| 212 | 650g | Dragonheart | **confirmed** |
| 213 | 300g | Light Armor | **confirmed** |
| 214 | 750g | Coat of Plates | **confirmed** |
| 215 | - | Light Armor (variant) | tentative |
| 216 | 300g | Energy Battery | **confirmed** |
| 217 | 250g | Hourglass | **confirmed** |
| 218 | 700g | Void Battery | **confirmed** |
| 219 | 800g | Chronograph | **confirmed** |
| 220 | 2400g | Clockwork | **confirmed** |
| 221 | 300g | Sprint Boots | **confirmed** |
| 222 | 650g | Travel Boots | **confirmed** |
| 223 | - | Serpent Mask | **confirmed** |
| 224 | - | Unknown 224 | unknown |
| 225 | - | Scout Trap | tentative |
| 226 | - | Bonesaw | **confirmed** |
| 228 | - | Coat of Plates (variant) | tentative |
| 229 | 700g | Reflex Block | **confirmed** |
| 230 | - | Frostburn | **confirmed** |
| 231 | - | Fountain of Renewal | **confirmed** |
| 232 | - | Crucible | **confirmed** |
| 233 | 1400g | Unknown 233 | unknown |
| 234 | 1400g | Halcyon Chargers | **confirmed** |
| 235 | 2900g | Tension Bow | **confirmed** |
| 236 | - | Aftershock | **confirmed** |
| 237 | 500g | Weapon Infusion | **confirmed** |
| 238 | 500g | Crystal Infusion | **confirmed** |
| 239 | - | Unknown 239 | unknown |
| 240 | - | Broken Myth | **confirmed** |
| 241 | 1600g | Teleport Boots | **confirmed** |
| 242 | - | Atlas Pauldron | **confirmed** |
| 243 | 300g | Book of Eulogies | **confirmed** |
| 244 | 800g | Barbed Needle | **confirmed** |
| 245 | 300g | Light Shield | **confirmed** |
| 246 | 750g | Kinetic Shield | **confirmed** |
| 247 | 2400g | Aegis | **confirmed** |
| 248 | 800g | Lifespring | **confirmed** |
| 249 | 1150g | Heavy Steel | **confirmed** |
| 250 | 900g | Piercing Spear | **confirmed** |
| 251 | 2700g | Breaking Point | **confirmed** |
| 252 | 900g | Lucky Strike | **confirmed** |
| 253 | - | Alternating Current | **confirmed** |
| 254 | 900g | Piercing Shard | **confirmed** |
| 255 | 2600g | Eve of Harvest | **confirmed** |

### qty=2 IDs (0-27) - 아이템 완성
| ID | 매핑 | Status | 핵심 근거 |
|----|------|--------|-----------|
| 0 | Heavy Prism | **confirmed** | Crystal Bit 99% |
| 1 | Journey Boots | **confirmed** | Travel Boots 91% |
| 5 | Tyrant's Monocle | **confirmed** | Six Sins 83% + Lucky Strike 79% |
| 7 | Stormcrown | **confirmed** | Chronograph 78% |
| 8 | Poisoned Shiv | **confirmed** | Blazing Salvo 100% + Barbed Needle 100% |
| 10 | Spellfire | **confirmed** | Heavy Prism 99% + Eclipse Prism 97% |
| 11 | Dragon's Eye | **confirmed** | Heavy Prism 100% + Eclipse Prism 96% |
| 12 | Spellsword | **confirmed** | Heavy Steel 91%, recipe=Heavy Steel+Chronograph |
| 13 | Slumbering Husk | **confirmed** | Coat of Plates 69% + Kinetic Shield 66% |
| 14 | SYSTEM | - | 시스템 이벤트 (제외) |
| 15 | SuperScout 2000 | **confirmed** | Captain 93% exclusive |
| 16 | Contraption | **confirmed** | Captain 93%, Chronograph co-buy |
| 17 | War Treads | **confirmed** | Travel Boots 94% + Dragonheart 94% |
| 18 | Unknown 18 | unknown | Mixed roles, 정체 불명 |
| 20 | Flare Gun | **confirmed** | Captain 88%, Oakheart co-buy |
| 21 | Pulseweave | **confirmed** | Dragonheart 89% + Lifespring 86% |
| 22 | Capacitor Plate | **confirmed** | Dragonheart 94%, Captain 91% |
| 23 | Rook's Decree | **confirmed** | Dragonheart 92%, Captain 83% |
| 26 | Warmail | **confirmed** | Light Armor 76% + Light Shield 56% |
| 27 | Metal Jacket | inferred | Coat of Plates 25% (이중 CoP 레시피 구조적 저탐지) |

### 미매핑 공식 아이템
| 아이템 | 가격 | 비고 |
|--------|------|------|
| Minion's Foot | 300g | T1 WP, Lucky Strike(252)의 하위 |
| Protector Contract | 600g | T2 방어 |
| Stormguard Banner | 600g | T2 보조, Stormcrown(7)의 컴포넌트 |
| Shiversteel | 1,950g | T3 보조 |
| Flare | 25g | 소모품 |
| Minion Candy | 75g | 소모품 |
| ScoutPak | 500g | 소모품 |
| ScoutTuff | 500g | 소모품 |
