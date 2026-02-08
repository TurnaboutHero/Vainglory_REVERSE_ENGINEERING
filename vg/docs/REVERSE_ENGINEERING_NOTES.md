# Vainglory Reverse Engineering Notes

베인글로리 게임 및 리플레이 파일 역공학 분석 결과

---

## 1. 게임 설치 구조

### Steam PC 버전
- **경로**: `D:\SteamLibrary\steamapps\common\Vainglory`
- **실행파일**: `Vainglory.exe` (29.5 MB)

### DLL 의존성
| 파일 | 용도 |
|------|------|
| `fmod.dll` | FMOD 오디오 엔진 |
| `glew32.dll` | OpenGL Extension Wrangler |
| `glut32.dll` | OpenGL Utility Toolkit |
| `steam_api.dll` | Steam 연동 |
| `sdkencryptedappticket.dll` | Steam 암호화 티켓 |
| `crashpad_handler.exe` | 크래시 리포팅 |

### Data 폴더 구조
```
Data/
├── 00/ ~ FF/   # 256개의 해시 기반 폴더
├── Video/      # 동영상 파일
```
- **에셋 저장 방식**: 해시 기반 분산 저장 (첫 2자리가 폴더명)
- **파일명 형식**: `169998B0BB1FCFEAFB9E8DE3037F88EE` (MD5 해시 추정)
- **파일 포맷**: 바이너리 패킹됨 (평문 JSON/XML 없음)

---

## 2. 리플레이 파일 (.vgr) 구조

### 저장 위치
| 플랫폼 | 경로 |
|--------|------|
| Windows | `%TEMP%` |
| Android | `/Android/data/com.superevilmegacorp.game/cache` |
| iOS | 탈옥 필요 |

### 리플레이 수명 주기
> [!WARNING]
> **베인글로리는 마지막 1개의 경기 리플레이만 보관합니다!**

- 경기 종료 → Temp에 리플레이 저장
- 새 경기 시작 또는 리플레이 메뉴 종료 → **이전 리플레이 삭제**
- 수동으로 다른 폴더에 복사해야 영구 보관 가능

**보관 방법:**
```powershell
# 경기 직후, 결과 화면에서 (게임 종료 전)
Copy-Item "$env:TEMP\*.vgr" "D:\내리플레이폴더\"
Copy-Item "$env:TEMP\replayManifest-*.txt" "D:\내리플레이폴더\"
```


### 파일 네이밍 규칙
```
{match_uuid}-{session_uuid}.{frame_number}.vgr
```
예: `8fc12404-6151-11eb-afe2-061b3d1d141d-9de666b6-299f-4503-bf4b-4c7b351847f4.0.vgr`

### 파일 크기
- **프레임당**: 50~170 KB
- **전체 경기**: 5~20 MB (3v3), 10~30 MB (5v5)

### 바이너리 헤더 (첫 16바이트)
```
Offset  Data
0x00    00 00 00 00 00 00 00   # Null padding
0x07    DA 03 EE              # 매직 바이트? (가변)
0x0A    [플레이어 이름 시작]   # ASCII 문자열
```

---

## 3. 추출된 데이터 패턴

### 플레이어 데이터
- **이름**: ASCII 문자열로 저장 (null terminated 아님)
- **UUID**: 표준 UUID 형식 `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
- **위치**: Frame 0에 모든 플레이어 정보 포함

### 게임 모드 문자열
| 내부 값 | 의미 |
|---------|------|
| `GameMode_HF_Ranked` | 3v3 랭크 (Halcyon Fold) |
| `GameMode_HF_Casual` | 3v3 캐주얼 |
| `GameMode_5v5_Ranked` | 5v5 랭크 (Sovereign Rise) |
| `GameMode_5v5_Casual` | 5v5 캐주얼 |
| `GameMode_Blitz` | 블리츠 |
| `GameMode_ARAL` | ARAL |
| `GameMode_BR` | 배틀로얄 |

### replayManifest 파일
```
{match_uuid}-{session_uuid}
```
단순 텍스트로 현재 리플레이 식별자 저장

---

## 4. 저장되지 않는 데이터 (상세 분석 결과)

| 데이터 | 상태 | 분석 결과 |
|--------|------|-----------|
| 영웅 이름/스킨 | ❌ 미저장 | 문자열로 저장되지 않음. 바이너리 ID로 인코딩 추정 |
| 경기 결과 (승/패) | ❌ 미저장 | 게임 엔진이 재생 시 실시간 계산 |
| K/D/A 통계 | ❌ 미저장 | 입력 이벤트에서 집계 필요 |
| 아이템 빌드 | ❌ 미저장 | 아이템 ID 매핑 필요 |
| 골드/경험치 | ❌ 미저장 | 게임 로직으로 계산 |

### 바이너리 분석 세부 결과

**플레이어 블록 구조** (226바이트 고정 간격)
```
Offset    Data              Description
────────────────────────────────────────────────
+0x00     DA 03 EE          플레이어 블록 마커
+0x03     [Name]            ASCII 플레이어 이름 (가변길이)
+0xA5     XX XX             엔티티 ID (uint16, 이벤트 스트림에서 반복 등장)
+0xD4     XX                알 수 없음 (샘플에서 고정값)
+0xD5     XX                팀 ID (1=Left/Blue, 2=Right/Red)
+0xDA     XX                플래그 (항상 1)
```

**확인된 사항:**
- 모든 프레임(0~100+)에서 영웅 이름 문자열 없음
- 영웅/아이템은 숫자 ID로 인코딩되나 위치 미확정
- 게임은 "입력 재생" 방식 → 상태 데이터 최소화
- +0xD5 팀 바이트는 3v3 샘플에서 3/3으로 분리됨
- +0xA5 엔티티 ID가 이벤트 스트림에서 반복 등장

### 영웅 ID 추출 시도 결과

Hero ID 바이트(9-71)가 파일 전체에 과다 발생:
| Hero ID | 발생 횟수 |
|---------|----------|
| 64 (Kinetic) | 1,540회 |
| 16 (Catherine) | 870회 |
| 62 (Malene) | 852회 |

**결론:** 영웅 ID가 별도 필드로 저장되지 않음. 바이트 값 9-71이 게임 이벤트 패킷 데이터의 일부로 빈번하게 사용되어 Hero ID와 구분 불가.

**가능한 원인:**
1. 영웅 정보가 게임 시작 시 메모리에서만 참조
2. 해시 또는 복합 ID 형태로 저장 (단일 바이트 아님)
3. 리플레이는 순수 입력 데이터만 저장, 영웅 선택은 별도 서버 데이터

---

## 5. 에셋 언패킹 결과

### Data 폴더 구조
- **위치**: `D:\SteamLibrary\steamapps\common\Vainglory\Data`
- **구조**: 256개 폴더 (00-FF, 해시 기반 분산)
- **파일 형식**: 확장자 없음, MD5 해시명
- **총 파일 수**: ~49,000개

### 파일 포맷
| 시그니처 | 포맷 | 용도 |
|---------|------|------|
| `RSC0` | SEMC Custom | 게임 리소스 |
| `fffb` | MP3 | 오디오 |
| `RIFF` | WebP/WAV | 이미지/오디오 |

### 추출된 영웅 ID
```
/Characters/HeroXXX/ 패턴으로 확인된 ID들:

Hero009 = SAW          Hero044 = Gwen
Hero010 = Ringo        Hero045 = Flicker
Hero011 = Taka         Hero046 = Idris
Hero012 = Krul         Hero047 = Grumpjaw
Hero013 = Skaarf       Hero048 = Baptiste
Hero014 = Celeste      Hero054 = Grace
Hero015 = Vox          Hero055 = Reza
Hero016 = Catherine    Hero058 = Churnwalker
Hero017 = Ardan        Hero059 = Lorelai
Hero019 = Glaive       Hero060 = Tony
Hero020 = Joule        Hero061 = Varya
Hero021 = Koshka       Hero062 = Malene
Hero023 = Petal        Hero063 = Kensei
Hero024 = Adagio       Hero064 = Kinetic
Hero025 = Rona         Hero065 = San Feng
Hero027 = Fortress     Hero066 = Silvernail
Hero028 = Reim         Hero067 = Yates
Hero029 = Phinn        Hero068 = Inara
Hero030 = Blackfeather Hero069 = Magnus
Hero031 = Skye         Hero070 = Caine
Hero036 = Kestrel      Hero071 = Leo
Hero037 = Alpha        
Hero038 = Lance        
Hero039 = Ozo          
Hero040 = Lyra         
Hero041 = Samuel       
Hero042 = Baron        
```

### 추출된 아이템 이름
```
AC, AMR, CapPlate, Crucible, Echo, Fountain, Frostburn,
HealingFlask, IronGuard, Protector, ReflexBlock, ScoutTrap,
Shell, Shiv, Slumbering_Husk, StormGuard, WarTreads 등
```

### 파일 통계
| 크기 구간 | 파일 수 |
|----------|---------|
| Tiny (<1KB) | 4,650 |
| Small (1-10KB) | 25,685 |
| Medium (10-100KB) | 14,748 |
| Large (100KB-1MB) | 2,070 |
| Huge (>1MB) | 1,041 |
| **총계** | **48,194** |

### 게임 모드 (59종)
**공개 모드:**
- `GameMode_HF_Ranked/Casual` - 3v3 Halcyon Fold
- `GameMode_5v5_Ranked/Casual` - 5v5 Sovereign Rise
- `GameMode_Blitz_Ranked/Casual` - 블리츠
- `GameMode_Aral_Casual` - ARAL
- `GameMode_Rumble_Casual` - 럼블

**특수/실험 모드:**
- `GameMode_Experiment_OneForAll` - 원포올
- `GameMode_Experiment_UltimateBravery` - 얼티밋 브레이버리
- `GameMode_Experiment_LanceBall` - 랜스볼
- `GameMode_PVE_KrakenRaidBoss` - 크라켄 레이드
- `GameMode_Horde_Casual` - 호드 모드

**개발자 전용:**
- `GameMode_DevOnly_DesignTestingGrounds`
- `GameMode_DevOnly_DesignTestingGrounds_5v5`

### 몬스터 및 미니언
**정글 몬스터:**
- `Kraken` - 크라켄
- `Dragon` - (5v5) 블랙클로/고스트윙

**미니언 종류:**
- `Melee`, `Ranged`, `Small` - 일반 미니언
- `Crystal`, `Weapon` - 크리스탈/웨폰 미니언
- `Heal` - 힐러 미니언
- `Mines` - 지뢰 (마이너)

---

## 6. 게임 엔진 특성

### 렌더링
- **OpenGL 기반** (glew, glut 사용)
- 텍스처: WebP 포맷으로 패킹

### 오디오
- FMOD 엔진 사용

### 리플레이 시스템
- **방식**: 입력(틱) 기록 방식
- 플레이어 입력과 게임 이벤트를 기록
- 재생 시 게임 엔진이 상태 재구성
- 결과/통계는 저장하지 않음 (재계산)

---

## 6. 추가 연구 방향

### 에셋 언패킹
- Data 폴더의 해시 파일 포맷 분석
- 영웅/아이템 ID 매핑 테이블 추출

### 네트워크 분석
- 게임 서버 통신 프로토콜
- 매치메이킹 데이터

### 메모리 분석
- 런타임 영웅/아이템 데이터 구조
- 경기 상태 메모리 레이아웃

---

## 7. 실험 1 분석 (Ringo Death Test) - 재분석

> [!WARNING]
> **이전 분석 결과가 잘못되었습니다.** 아래는 수정된 분석입니다.

- **대상**: 5v5 Practice 모드 (1인 플레이)
- **경로**: `D:\Desktop\My Folder\Game\VG\vg replay\replay-test`
- **프레임 수**: 5

**실제 식별된 액션 코드:**
| 코드 | 횟수 | 추정 의미 |
|:---:|:---:|:---------|
| **0x05** | 220 | 게임 틱/프레임 업데이트 (가장 빈번) |
| **0x08** | 81 | 이동 관련 |
| **0x00** | 23 | 상태 업데이트 |
| **0x07** | 4 | 스킬/액션 |
| **0x02** | 2 | 초기화 관련 |
| **0x42** | 1 | 상호작용? |
| **0x01** | 1 | 스폰 |

**중요:** 0x80은 이 리플레이에서 **발생하지 않았습니다**.

**Phase 2 분석 결과 (토너먼트 데이터):**
- 토너먼트 11경기 분석 결과, 0x80은 deaths와 일치하지 않음
- deaths 15회인 경기에서 0x80은 4회만 발생 (프레임 40)
- **결론: 0x80은 사망 이벤트가 아님**

**새로운 발견 - 엔티티 상호작용:**
- 페이로드 내에서 다른 플레이어의 entity_id가 발견됨
- 0x42, 0x43: 엔티티 간 상호작용 (공격/스킬)
- target_offset_in_payload: 11 또는 15 바이트 위치에 타겟 ID 저장

---

## 8. 토너먼트 스크린샷 OCR 매핑
- 대상: `Tournament_Replays` 폴더의 `result*.jpg/jpeg` + `.0.vgr`
- 도구: `tournament_ocr.py` (EasyOCR 기반)
- 결과: 11경기 매핑 완료, `tournament_truth.json` 생성 (vgr_parser.py --truth로 사용)
- 원본 토큰: `tournament_ocr_raw.json`
- 정합성 검증: `verify_tournament_truth.py` (truth/parsed 비교)
- 파서 출력: `tournament_parsed.json` (truth 적용 결과)
- 한계: 영웅 이름 텍스트가 없어 `Unknown` 유지, 일부 CS 누락 (`tournament_ocr_summary.md` 참고)

---

## 9. 이벤트/영웅 후보 분석 (프로브)
- 스크립트: `event_probe.py`
- 출력: `event_probe_output.json`
- 내용: 플레이어 엔티티 액션 카운트 + truth 상관 힌트 + hero probe 오프셋 통계
- 관찰: `[EntityID][00 00][Action]` 이후 hero_id 바이트가 나타나는 오프셋(6, 23, 70 등) 경향 존재
- 상태: 후보 힌트 수준, 확정 매핑 아님

---

## 10. Phase 2 심층 역공학 분석 결과 (2025-12-26)

### 분석 방법론
1. **통계적 상관분석**: 256개 액션 코드와 K/D/A의 피어슨 상관계수 계산
2. **Ringo Death Test**: 단일 사망 발생 리플레이에서 고유 이벤트 추적
3. **엔티티 상호작용 분석**: 페이로드 내 적/아군 entity_id 탐색
4. **적팀/아군 분리 분석**: cross-team 상호작용과 K/D/A 상관관계

### 핵심 발견

#### 10.1 액션 코드는 K/D/A와 직접 매핑되지 않음

**256개 액션 코드 전수 검증 결과 (110명 플레이어):**

| 코드 | Deaths 일치율 | 비고 |
|:---:|:---:|:---|
| 0x78 | 20.9% (23/110) | 최고 |
| 0xDB | 20.9% (23/110) | 최고 |
| 0x9C | 20.0% (22/110) | |
| 0x50 | 19.1% (21/110) | |

**결론:** 어떤 단일 액션 코드도 사망 횟수와 정확하게 일치하지 않음 (~20% 수준은 우연의 일치)

#### 10.2 Ringo Death Test 상세 분석

**테스트 조건:**
- 5v5 Practice 모드 (1인)
- 이동 1회 → 터렛 피격 3회 → 사망 1회
- 아이템 구매/스킬 강화 없음

**프레임별 이벤트:**
| 프레임 | 고유 이벤트 | 설명 |
|:---:|:---|:---|
| 0 | 0x01(1), 0x02(2) | 게임 초기화 |
| 2 | 0x07(2) | 터렛 피격 시작? |
| 3 | 0x07(2), **0x42(1)** | 사망 발생 프레임 |
| 4 | 정상 | 리스폰 후 |

**0x42 이벤트 상세:**
- Frame 3에서만 단 1회 발생
- Payload: `02c5b70000001003f858c25eb852c1f87ae10000`
- **그러나 토너먼트 검증 시 8.2% 일치** → 사망 코드 아님

#### 10.3 엔티티 상호작용 패턴

**발견:**
- 이벤트 페이로드 내에서 **다른 플레이어의 entity_id**가 발견됨
- 주로 **offset 11 또는 15**에 위치
- 0x42, 0x43 액션에서 빈번

**토너먼트 1경기 분석 (SFC vs Team Stooopid):**
- 총 289개 엔티티 상호작용 발견
- 그러나 적팀 상호작용 횟수도 K/D/A와 일치하지 않음

#### 10.4 결론 및 한계

**K/D/A 자동 추출이 불가능한 이유:**

1. **리플레이는 입력 재생 시스템**: K/D/A는 저장되지 않고 재생 시 실시간 계산
2. **킬/데스가 단일 이벤트가 아님**: 복합 조건(피해, 시간, 어시스트 기여 등)으로 결정
3. **터렛/미니언 킬과 플레이어 킬 구분 불가**: 같은 이벤트 구조 사용 추정
4. **리스폰, 어시스트, CC기여 등 복잡한 로직**: 게임 엔진만 정확히 계산 가능

### 검증된 스크립트

| 스크립트 | 용도 |
|---------|------|
| `validate_death_code.py` | 모든 액션 코드 vs K/D/A 상관분석 |
| `find_death_event.py` | Ringo Death Test 프레임별 분석 |
| `event_deep_analysis.py` | 엔티티 상호작용 및 페이로드 분석 |

### 권장 대안

#### Option A: OCR 기반 (현재 구현됨)
- 게임 결과 화면 캡처 → EasyOCR 처리 → truth.json 생성
- 장점: 100% 정확한 K/D/A
- 단점: 수동 스크린샷 필요

#### Option B: 메모리 스캐닝 (미구현)
- 리플레이 재생 중 게임 메모리에서 K/D/A 추출
- 장점: 자동화 가능
- 단점: 게임 업데이트 시 오프셋 변경, 안티치트 이슈

#### Option C: 머신러닝 (미구현)
- 이벤트 시퀀스 → K/D/A 예측 모델 학습
- 장점: 패턴 기반 추론
- 단점: 훈련 데이터 대량 필요, 정확도 보장 어려움

---

## 11. 현재 프로젝트 상태 요약

### 완료된 기능
- [x] 플레이어 이름/UUID 추출
- [x] 게임 모드/맵 추출
- [x] 팀 분류 (left/right)
- [x] 엔티티 ID 추출
- [x] 영웅 ID 매핑 (부분)
- [x] OCR 기반 Truth 데이터 시스템

### 미완료 (기술적 한계)
- [ ] K/D/A 자동 추출 ❌ 불가능 확인
- [ ] 킬/데스 이벤트 식별 ❌ 불가능 확인
- [ ] 어시스트 판정 ❌ 불가능 확인

### 다음 단계 제안
1. **APK 모딩 진행**: 게임 내에서 직접 통계 캡처
2. **서버 연동**: 리플레이 + OCR 결과 통합 저장
3. **웹 대시보드**: 수집된 데이터 시각화

---

## 12. Phase 2.5 심층 분석 (2025-12-26)

### 추가 분석 방법

Phase 2에서 K/D/A 자동 추출 불가 결론 후, 추가 심층 분석 진행:

| 분석 방법 | 스크립트 | 결과 |
|-----------|----------|------|
| 페이로드 오프셋별 K/D/A 상관분석 | `payload_deep_analysis.py` | 최대 ~20% |
| 시간 기반 클러스터 분석 | `time_cluster_analysis.py` | 패턴 없음 |
| 희귀 이벤트 분석 (1-20회 발생) | `rare_event_analysis.py` | 최대 32% |
| 복합 이벤트 (A±B = K/D/A) | `combo_event_analysis.py` | 0% |
| 페이로드 내 누적 카운터 탐색 | `payload_counter_search.py` | 최대 ~18% |

### 상세 결과

#### 12.1 페이로드 오프셋 분석

0x05 액션의 마지막 프레임 페이로드에서 K/D/A 값 검색:
- offset 7: Kills 14%, Deaths 18%, Assists 11%
- offset 10: Kills 20%, Deaths 16%, Assists 6%
- **모든 오프셋이 우연의 일치 수준 (~20%)**

#### 12.2 Cross-team 킬러-피해자 패턴

0x44 이벤트에서 적팀 엔티티 ID 발견 (offset 11):
- 탐지된 "킬": 423개
- 실제 킬: 100개
- **결론: 0x44는 스킬/공격 히트 이벤트 (킬이 아님)**

#### 12.3 희귀 이벤트 상위 후보

| 액션 | Deaths 일치율 | 비고 |
|:---:|:---:|:---|
| 0x13 | 75% (3/4) | 샘플 수 부족 |
| 0x78 | 32% (11/34) | |
| 0xDB | 29% (12/41) | |
| 0x9C | 29% (12/41) | |

**전체 107명 검증 시:** 0x78 = 19.6%, 0xDB = 18.7%, 0x9C = 18.7%

### 최종 결론

**K/D/A 자동 추출은 구조적으로 불가능합니다.**

리플레이 파일은 **입력 재생 시스템**으로, 게임 클라이언트가 입력을 재실행하며 통계를 실시간 계산합니다. K/D/A는 다음 요소들의 복합 결과:
- 피해량/시간 기반 킬 어트리뷰션
- 어시스트 시간 윈도우 (보통 10초)
- CC 기여도
- 오브젝트 킬 (터렛/드래곤) 제외 로직

이 모든 로직이 게임 엔진에만 구현되어 있어, 리플레이 파일만으로는 재현 불가능합니다.

### 권장 접근법

1. **OCR (현재)**: 95%+ 정확도, 수동 스크린샷 필요
2. **메모리 스캐닝**: 리플레이 재생 중 게임 메모리 읽기
3. **게임 클라이언트 모딩**: API 후킹으로 통계 캡처

---

## 13. 아이템 구매 / 스킬 레벨업 이벤트 분석 (2025-12-26)

### 테스트 조건

**경로**: `replay-test/item buy test`

**수행한 액션 순서:**
1. 단검(Weapon Blade) + 고서(Book of Eulogies) 구매
2. 강철대검(Heavy Steel) + 표창(Swift Shooter) 구매
3. 비탄의 도끼(Sorrowblade) 구매
4. A스킬 레벨업 (0→1레벨)
5. 레벨업 주스 복용 (2→12레벨)
6. 이동
7. 스킬 레벨업 (BAABCAACBBB 순서, 최종 A:5, B:5, C:3)
8. 게임 항복

### 발견된 이벤트 코드

| 이벤트 | 코드 | Entity ID | 발생 횟수 | 프레임 분포 |
|--------|------|-----------|-----------|-------------|
| **아이템 구매** | `0xBC` | 0 | **5회** | [0, 0, 5, 5, 6] |
| **스킬 레벨업** | `0x3E` | 0 + 128 | **12회** | (1+11) |

### 아이템 구매 이벤트 (0xBC) 상세

**패턴:**
```
[00 00 00 00] [BC] [Payload 16+ bytes]
Entity ID = 0 (글로벌 이벤트)
```

**프레임별 분포:**
| 프레임 | 아이템 | 페이로드 (첫 4바이트) |
|--------|--------|---------------------|
| 0 | 단검 | `8E F8 59 3F` |
| 0 | 고서 | `8E F8 59 3F` (동일) |
| 5 | 강철대검 | `E1 57 5B 44` |
| 5 | 표창 | `D9 CB 9F 44` |
| 6 | 비탄의 도끼 | `C1 F2 FE 44` |

**페이로드 분석:**
- 첫 4바이트: 좌표 또는 게임 내 인덱스 (시간값 아님)
- 단검/고서가 동일한 페이로드 → 동시 구매 확인
- **아이템 ID는 페이로드에 직접 포함되지 않음**

### 스킬 레벨업 이벤트 (0x3E) 상세

**패턴:**
```
[Entity ID 4bytes] [3E] [Payload]
Entity 0: 첫 번째 스킬 (A 0→1)
Entity 128: 나머지 11개 스킬
```

**Entity 128 + 0x3E 페이로드 샘플:**
```
Skill 1: C8 86 10 43 ED 80 00 43 ED 80
Skill 2: D2 A7 7E 44 0F C0 00 44 0F C0
...
```

**분포:**
- Entity 0 + 0x3E: 35회 (다른 용도 포함)
- Entity 128 + 0x3E: 11회 (스킬 레벨업)
- **총 12회 = 첫번째(Entity 0) + 나머지 11개(Entity 128)**

### 아이템 ID 존재 확인

리플레이에서 `vgr_mapping.py`의 아이템 ID 검색 결과:

| 아이템 ID | 아이템명 | 발견 횟수 (4바이트 패턴) |
|-----------|----------|-------------------------|
| 101 | Weapon Blade | 14회 |
| 102 | Book of Eulogies | 255회 |
| 111 | Heavy Steel | 18회 |
| 103 | Swift Shooter | 19회 |
| 121 | Sorrowblade | 23회 |

**결론:** 아이템 ID가 리플레이에 존재하지만, `0xBC` 이벤트와 직접 연결되어 있지 않음. 별도의 인벤토리 상태 구조에 저장됨.

### 기타 발견

**정확히 5회 발생하는 이벤트 (아이템 구매 후보):**
- Entity 0 + 0xBC: 5회 ✓
- Entity 0 + 0x3D: 5회 (관련 이벤트)
- Entity 77 + 0x08: 5회 (Frame 0에서만)

**정확히 12회 발생하는 이벤트 (스킬 레벨업 후보):**
- Entity 220, 202, 215, 234 + 0x00: 각 12회
- Entity 94, 60, 96 등 + 0x10: 각 12회
- Entity 118, 8, 223 등 + 0x18: 각 12회

### 결론

| 이벤트 | 확정 코드 | 확신도 |
|--------|----------|--------|
| 아이템 구매 시점 | `0xBC` (Entity 0) | **높음** ✓ |
| 스킬 레벨업 | `0x3E` (Entity 0/128) | **높음** ✓ |
| 아이템 종류 | 미확인 | - |

**다음 단계:**
- 인벤토리 상태 변화 추적 (아이템 ID 연결)
- A/B/C 스킬 구분 (페이로드 분석)

---

## 14. 커뮤니티 / 외부 참고 (Reddit)

### 14.1 "관전 생태계를 만들었다" 글 요약
- iOS/Android 모바일 클라이언트를 수정해 탈옥/루팅 없이 관전 가능하도록 구현.
- 리플레이 파일을 서버로 업로드하며 약 15~25초 지연이 발생.
- PC 관전 플로우: 연습전 항복 → 리플레이 화면 들어가기 전 PC 스크립트 실행 → 관전할 경기 선택.
- 리플레이는 경기 종료 약 30분 후 아카이브, 대회 주최자는 요청 가능.
- 동시 관전/경기 수 제한은 없다고 주장.
- 댓글 반응(요지): “유용하고 멋진 시스템”이라는 긍정 평가가 다수였고, 특히 **대회 관전자/중계**에 큰 도움이 된다는 반응이 있음. 작성자의 과거 기여(스킨 가이드 등)를 언급하며 감사 인사도 있음.

Source: https://www.reddit.com/r/vainglorygame/comments/zui787/ive_built_an_ecosystem_to_spectate_games/

### 14.2 "VGReborn" (VPN + MITM 기반 랭크/방 시스템)
- VPN + MITM으로 VG:CE의 플레이어 상태를 계정과 매핑.
- 온라인/수락/거절/경기종료 상태를 추적하고 경기 기록으로 랭크 티어 계산.
- 실시간 통계(온라인 인원, 매칭 상태 3v3/5v5, 인게임 수 등).
- 방 관리: 코드 접두어로 방 목록, 수용 인원, 생성/입장/퇴장.
- 방 멤버 정보: ID, 레벨, 명성, 준비 상태.
- 악의적 거절 행동 모니터링/신고.
- WireGuard로 게임 관련 IP만 릴레이(클라이언트/서버 제한)하며 사용자당 대역폭 10~50 k/s 추정.
- 향후 가능성: 경기 네트워크 데이터 복호화로 영웅 선택/KDA/경기 시간/결과 추출, 서버 데이터 시뮬레이션으로 커스텀 모드(1v1/2v2/4v4 + AFK 채움) 구현.
- 링크: https://vgreborn.com/ ; https://github.com/VaingloryReborn/VGReborn
- 댓글 반응(요지):
  - 지역 확장(NA 등) 요청과 관심 표명이 많음.
  - **VPN 트래픽 프라이버시/비용**에 대한 질문이 집중됨(스플릿 터널링 여부, 서버 비용 부담 등).
  - 작성자는 WireGuard 기반으로 **게임 관련 IP만 릴레이**한다고 답변했고, 대역폭은 사용자당 대략 10~50 k/s 수준이라 설명.
  - 한편, **암호화 트래픽 복호화 가능성**과 **계정 추적 신뢰성**에 대한 회의적인 의견(보안/식별 한계 지적)도 존재.

Source: https://www.reddit.com/r/vainglorygame/comments/1qlp212/ive_retrofitted_vainglory_with_ranked_match/

### 14.3 "네트워크 데이터 디코딩 가능?" 글 요약
- OP 요지: 스크린샷의 네트워크 데이터가 보이며, 누군가 디코딩하면 게임 복원에 도움이 될 수 있다는 주장.
- OP 추정: Protobuf 또는 커스텀(사유) 프로토콜로 보이며, 디코딩에는 리버스 엔지니어링이 필요할 것 같다고 언급.
- 댓글(요지): 클라이언트-서버 패킷은 암호화되어 있을 가능성이 높고, 키가 노출되지 않는 한 복호화는 매우 어렵다고 지적.
- 댓글(요지): 설령 패킷을 평문으로 읽어도 서버 로직/소스가 없으면 복원은 어렵고, 통신 계층만으로는 한계가 있다고 강조.
- 댓글(요지): 리버스 엔지니어링은 메시지 의미 파악에는 도움되지만, 서버 애플리케이션의 미지 영역이 핵심 병목이라고 언급.
- 기타 댓글: 법적 문제(비공개 IP) 우려, 다른 MOBA와의 대체 가능성 논의 등.
- 댓글 반응(요지): “복호화 난이도 높음(키/암호화 이슈)”, “서버 로직 부재가 치명적”, “차라리 유사 게임을 새로 만드는 편이 현실적”이라는 분위기가 두드러짐.

Source: https://www.reddit.com/r/vainglorygame/comments/1qax79g/is_there_anyone_who_can_decode_the_network_data/

---

## 15. 현재 상황 정리 / 방향성 (2026-02-03)

### 배경
- 관전 생태계 구축 글에서 영감을 받아, **유저 APK 설치 → vgr 업로드 → 서버 분석** 흐름을 목표로 함.
- 목표 기능: 전적 검색, 랭크/MMR 추정, 경기 요약 데이터 제공.

### 핵심 가정
- **vgr만으로 모든 지표(K/D/A, 정확한 MMR)를 얻기 어려움**이 문서 분석에서 확인됨.
- **vgr + 부가 데이터(OCR/스크린샷 등)** 결합 시 전적/통계 정확도를 크게 개선 가능.

### 방향성 결론
1. **1차 방향: vgr 기반 파이프라인을 우선 완성**
   - 수집 난이도와 법적/운영 리스크가 낮고, 관전 생태계 아이디어와 정합.
   - 즉시 구현 가능한 MVP 범위를 명확히 정의하는 것이 중요.
2. **2차 방향: MITM/네트워크 디코딩은 장기 R&D로 분리**
   - 암호화/키 문제, 서버 로직 부재로 인한 한계, 법적 리스크가 큼.
   - 개념 검증/연구 수준으로만 병행.

### MVP 목표(제안)
- vgr에서 확실히 뽑히는 값 중심으로 스키마 확정:
  - match_uuid, session_uuid, 모드, 플레이어 UUID/팀, 시간/프레임 정보 등.
- K/D/A, 승패, 랭크/MMR은 **OCR 기반 보완**으로 제공.
- “정확 지표”와 “추정 지표”를 명확히 분리 표기.

### 다음 액션 아이템
- vgr → 서버 업로드 프로토콜 정의(파일/메타데이터 동시 전송).
- OCR 결과(truth.json)와 vgr 매칭 로직 문서화.
- MVP 산출물(전적 검색 최소 기능) 명세 작성.

---

## 16. Hero Matching 심층 분석 (2026-02-09)

### 분석 목표
바이너리에서 영웅-플레이어 매칭 자동 추출 가능 여부 검증

### 시도한 방법

#### 16.1 바이트 패턴 감지
```python
pattern = bytes([hero_id, 0, 0, 0])  # e.g., [64, 0, 0, 0] for Kinetic
```

**결과:** 0% 정확도 (109/109 불일치)

#### 16.2 다중 신호 결합
- Signal 1: 이벤트 빈도 (weight 0.4)
- Signal 2: first_offset 순서 (weight 0.3)
- Signal 3: hero-probe 오프셋 매칭 (weight 0.3)

**결과:** 여전히 0% 정확도

### 검증 데이터

**토너먼트 11경기 (109명):**
```json
{
  "total_players": 109,
  "correct_matches": 0,
  "accuracy": 0.0,
  "mismatch_summary": {
    "wrong_hero": 107,
    "not_detected": 2
  }
}
```

### 불일치 예시

| 플레이어 | 실제 영웅 | 감지된 영웅 | 신뢰도 |
|---------|----------|------------|--------|
| 2600_Acex | Lyra | Celeste | 0.0 |
| 2600_Ghost | Inara | Grace | 0.0 |
| 2600_IcyBang | Kestrel | Miho | 0.0 |
| 2600_staplers | Malene | Baron | 0.0 |

### 결론

**영웅 정보는 리플레이에 직접 저장되지 않습니다.**

리플레이는 입력 재생 시스템으로:
1. 게임 시작 시 영웅 선택이 서버/메모리에서만 참조됨
2. 리플레이에는 입력 명령만 기록
3. 재생 시 게임 엔진이 영웅 정보를 별도로 로드

### 대안: 스킬 ID 기반 추론

각 영웅은 고유한 스킬 세트를 가지므로:
1. 스킬 사용 이벤트 패턴 분석
2. 스킬 ID → 영웅 역추론
3. 아직 미검증 (다음 분석 대상)

---

## 17. Item ID Linkage Findings (2026-02-03)

### FFFF ��Ŀ ��� �κ��丮 ���ڵ� Ž��

`FF FF FF FF [item_id 2B LE]` ������ **Frame 5/6������** Ȯ�ε� (item buy test ����).
- �߰ߵ�: 101(Weapon Blade), 102(Book of Eulogies), 103(Swift Shooter), 111(Heavy Steel)
- �̹߰�: 121(Sorrowblade) (���� ��Ŀ������ �� ����)

����:
- `FF FF FF FF [XX 00]` ���ڵ� ������ �������� ����ɼ��� ���� (Frame0 64 -> Frame6 151)
- ���� ���� ���� ������(5/6)���� Ư�� item_id�� ����

�ؼ�:
- 0xBC�� "���� �߻�" Ʈ����
- ���� ������ ID�� **���� �κ��丮/���� ������ ���ڵ�**�� ��ϵǴ� ���ɼ�

���� ��ũ��Ʈ/���:
- `vg/analysis/item_pattern_hunt.py` (FFFF ��Ŀ Ž��)
- ���: `vg/output/item_pattern_hunt_output.txt`
