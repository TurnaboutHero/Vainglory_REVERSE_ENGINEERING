# VGR Reverse Engineering - Failed Attempts Record

**Purpose:** 이전에 시도해서 실패한 접근법을 기록하여, 같은 실수를 반복하지 않기 위한 문서.

---

## 1. KDA (Kill/Death/Assist) Detection - 모든 접근 실패

### 1.1 Action Code 0x29 = Kill Signature (실패)

**가설:** 플레이어 Entity의 0x29 action code가 Kill 이벤트를 나타낸다.

**시도:**
- `vg/analysis/player_kill_detector.py` - 0x29 이벤트를 kill로 해석
- `vg/analysis/baron_anomaly_investigation.py` - Baron의 0x29 이상치 조사
- `vg/analysis/baron_0x29_deep_analysis.py` - 다중 리플레이 검증

**결과:** 17.1% 정확도 (6/35 kills, Baron만 일치)

**실패 원인:**
- 0x29는 **영웅별 고유 능력 코드**이지, kill 이벤트가 아님
- Baron은 0x29 이벤트가 1,087개 (6개가 아님!)
- "6 kills = 6개 0x29 이벤트"는 **우연의 일치**였음
- 21.12.06 리플레이에서는 모든 플레이어의 0x29가 0개
- 히어로마다 0x29 빈도가 완전히 다름 (Baron 1087, Caine 37, 일부 0)

**교훈:** 단일 리플레이에서 수치가 일치한다고 해서 인과관계가 아님. 반드시 **다중 리플레이 교차 검증** 필수.

---

### 1.2 Action Code 0x18 = Death Marker (실패)

**가설:** 0x18 action code가 영웅 사망을 나타낸다.

**시도:**
- `vg/analysis/validate_death_code.py` - 0x18 검증
- `vg/analysis/death_kill_validation.py` - 4개 리플레이 교차 검증
- `vg/analysis/verify_0x10_death_marker.py` - 0x10 변형도 시도

**결과:** 91배 과다 감지 (truth 28 deaths vs 감지 2,567개)

**실패 원인:**
- 0x18은 **전투 상태 브로드캐스트** (Combat state broadcast)
- 사망과 무관하게 전투 중 지속적으로 발생
- 빈도가 너무 높아 death 이벤트가 될 수 없음

**교훈:** 빈도가 truth와 크게 차이나는 이벤트는 즉시 폐기. 과다 감지(10배 이상)는 완전히 다른 의미의 이벤트.

---

### 1.3 Action Code 0x13 = Death Marker (실패)

**가설:** 0x13이 사망 이벤트일 수 있다.

**시도:** `vg/analysis/verify_0x13_death.py`

**결과:** 일치하지 않음

**실패 원인:** 0x13도 일반적인 게임플레이 이벤트로, death와 무관

---

### 1.4 Entity Disappearance = Death (실패)

**가설:** 플레이어가 사망하면 해당 프레임에서 이벤트가 사라진다.

**시도:**
- `vg/analysis/entity_lifecycle_tracker.py` - Entity 생명주기 추적
- `vg/analysis/death_frame_forensics.py` - 프레임별 사망 포렌식
- `vg/analysis/kda_lifecycle_detector.py` - 생명주기 기반 KDA

**결과:** 0/15 deaths 감지

**실패 원인:**
- **플레이어는 사망해도 이벤트에서 사라지지 않음!**
- 모든 플레이어가 거의 모든 프레임에 존재
- VGR 리플레이는 "입력" 기록이지 "상태" 기록이 아닐 수 있음

**교훈:** 사망 = 엔티티 부재라는 가정 자체가 틀림. VGR은 서버의 이벤트 로그로, 사망 상태와 무관하게 엔티티 이벤트가 계속 기록됨.

---

### 1.5 Respawn Timer Pattern (실패)

**가설:** 사망 후 부활까지 이벤트 빈도가 급감하므로 타이밍으로 감지 가능.

**시도:** `vg/analysis/respawn_timer_analyzer.py` - 3가지 전략 (Progressive timer, Fixed window, Clustering)

**결과:** Clustering MAE=1.5, 6명 중 1명만 정확

**실패 원인:**
- 영웅별 이벤트 빈도가 크게 다름 (Phinn: 0 deaths인데 18/103 프레임에만 존재)
- 자연적 이벤트 갭과 사망 갭을 구분할 수 없음
- 영웅 이벤트 빈도 의존도가 너무 높음

**교훈:** 이벤트 빈도 기반 접근은 영웅마다 기본 패턴이 다르므로 신뢰 불가.

---

### 1.6 0x00/0x05 Event Count Correlation (실패)

**가설:** 0x00 또는 0x05 action code의 빈도가 K/D/A와 상관관계가 있다.

**시도:** `vg/analysis/universal_kda_decoder.py`

**결과:** 0% 일치

**실패 원인:**
- 0x00 payload에 15,973개의 플레이어 참조 (K+D+A 합계보다 수백 배 많음)
- 0x05도 마찬가지로 범용 이벤트
- 고빈도 이벤트는 특정 게임 이벤트(kill/death)와 매핑 불가

**교훈:** 모든 플레이어에게 공통적으로 높은 빈도를 보이는 이벤트는 K/D/A 후보가 아님.

---

### 1.7 0x80 Payload Deep Analysis (실패)

**가설:** 0x80 action code의 payload 내에 kill/death 정보가 인코딩되어 있다.

**시도:** `vg/analysis/kda_payload_analyzer.py`

**결과:** 상관관계 없음

**실패 원인:** 0x80(=Entity 128)은 시스템 엔티티로, 대량의 브로드캐스트 이벤트 생성

---

### 1.8 Per-Player Payload Kill/Victim Decode (실패)

**가설:** 각 플레이어의 이벤트 payload에 다른 플레이어의 Entity ID가 포함되면 kill/death 관계.

**시도:** `vg/analysis/kda_per_player_decoder.py`

**결과:** 상관관계 미발견

**실패 원인:** Payload 내 Entity ID 참조는 전투, 스킬 타겟팅 등 다양한 이유로 발생

---

### 1.9 Frame Anomaly Detection (부분 실패)

**가설:** 프레임 수준의 이벤트 급증/급감이 팀파이트/다중 킬과 연관.

**시도:** `vg/analysis/frame_anomaly_detector.py`

**결과:** Frame 85 (z=9.22)가 최고 anomaly score이나, 개별 kill/death 매핑 불가

**실패 원인:**
- 전체 프레임 수준 anomaly는 팀파이트 감지에는 유용하나 개별 KDA 추출 불가
- Expected deaths = 0으로 truth data 미매핑 (해당 리플레이에 truth 없음)

**교훈:** 프레임 anomaly는 "무언가 큰 일이 발생"한 시점을 찾는 데 유용하지만, KDA의 직접 증거는 아님.

---

### 1.10 Position Vector Search (부분 성공 - KDA와는 무관)

**가설:** IEEE 754 float32 좌표 벡터 [x, z, y]가 리플레이 바이너리에 있다.

**시도:** `vg/analysis/position_vector_finder.py`

**1차 결과:** 대부분 (0.0, 0.0, 0.0) - Player block 내 null padding에서 false positive

**2차 결과 (확장 분석):** 625개의 non-zero 위치 벡터 발견!
- **Payload offset +8**: 주요 위치 필드 (119회 출현)
- **Action code 0x05**: 이동/위치 업데이트 (667개 이벤트 중 314개에 위치 포함)
- **좌표 범위**: X [-12.06, 32.00], Y [-1.39, 32.00] → VG 맵 경계 일치
- 프레임 10→90으로 갈수록 위치 이벤트 감소 (413→43) → MOBA 게임 패턴과 일치

**KDA 관련성:** 위치 데이터 자체는 유용하나, KDA 감지와는 직접 관련 없음.
향후 kill 위치 매핑이나 death 위치 추적에 활용 가능.

**교훈:** Null padding 제거 후 유의미한 float32 좌표가 존재함. 0x05가 주요 위치 이벤트.

---

## 2. Hero Detection - 이전 실패 (최종 해결됨)

### 2.1 Event Pattern Matching (실패 → 포기)

**가설:** 각 영웅은 고유한 action code 빈도 패턴을 가진다.

**시도:**
- `vg/analysis/validate_event_pattern_detection.py`
- `vg/analysis/validate_event_pattern_loocv.py`
- `vg/analysis/validate_signature_loocv.py`
- `vg/core/event_pattern_detector.py`
- `vg/core/signature_detector.py`

**결과:** 0% 정확도

**실패 원인:**
- 게임 상황에 따라 이벤트 패턴이 크게 변함
- 같은 영웅이라도 경기마다 다른 action code 분포
- Machine learning 접근도 실패 (특징이 불안정)

**최종 해결:** Player block 내 **+0xA9 offset의 uint16 LE hero ID** 발견으로 100% 해결

**교훈:** 통계적/ML 접근보다 **구조적 바이너리 분석**이 정답. 이벤트 패턴은 영웅보다 게임 상황에 더 의존.

---

## 3. Entity Parsing Bugs

### 3.1 Entity 0 Parsing 누락 (수정됨)

**문제:** Entity 0의 이벤트가 0개로 파싱됨

**원인:** Entity 0 바이트는 `00 00 00 00 [ActionCode]` — Entity ID `00 00`과 `00 00` 마커가 동일하여 표준 파서가 건너뜀

**실제:** Entity 0 = 2,889 이벤트, Entity 128 = 10,511 이벤트

**수정:** `vg/analysis/system_entity_analyzer.py`에서 특수 패턴 매칭으로 파싱

**교훈:** 바이너리 파서에서 특수값(0, 128 등)은 항상 edge case 테스트 필요.

---

### 3.2 Entity ID 범위 혼동

**문제:** Entity ID 범위별 역할이 명확하지 않았음

**정리:**
- Entity 0: 시스템 브로드캐스트 (2,889 이벤트/리플레이)
- Entity 1-10: 저수준 인프라 (Entity 1 = 83,268 이벤트!)
- Entity 128: 시스템 엔티티 (10,511 이벤트)
- 1000-20000: 터렛/구조물
- 20000-50000: 미니언/정글몹
- 50000-60000: 플레이어

---

## 4. Item Detection - 이전 실패 (부분 해결됨)

### 4.1 단순 Action Code 매칭 (부분 성공)

**시도:** 0xBC action code = item purchase

**결과:** 일부 아이템만 매칭, 모든 아이템 감지 불가

**해결:** `vg/analysis/item_extractor.py` - 4가지 패턴 전략 (FF/05/00 마커 + direct 2-byte LE) 통합

---

## 5. KDA 연구 현재 상태 및 향후 방향

### 5.1 왜 KDA가 어려운가

1. **VGR은 서버 이벤트 로그**: E.V.I.L. 엔진은 server-authoritative. KDA는 서버가 계산하는 값이며, 리플레이에는 **raw input/state** 만 기록될 수 있음.

2. **명시적 Kill/Death 이벤트가 없을 수 있음**: API 텔레메트리에는 KillActor 이벤트가 있었지만, 바이너리 VGR 포맷에는 다른 방식으로 인코딩되었을 수 있음.

3. **시도하지 않은 것들:**
   - HP 변화 추적 (HP가 0이 되는 시점 = death)
   - 특정 payload 바이트 위치의 의미 분석 (37바이트 payload 중 미해독 바이트 다수)
   - 멀티 이벤트 시퀀스 분석 (연속된 2-3개 이벤트의 조합)
   - API 텔레메트리 KillActor 필드와 바이너리 패턴 매핑
   - Gold 획득 이벤트 역추적 (킬 골드 = kill 증거)
   - VGReborn MITM 프로토콜 분석에서 실마리 찾기

### 5.2 절대 다시 시도하지 말 것

| 접근법 | 이유 |
|--------|------|
| 특정 action code 하나 = kill/death | Action code는 영웅별/상황별 의미가 다름 |
| 이벤트 빈도 통계 ↔ KDA 상관 | 빈도는 게임 상황 의존, KDA와 무관 |
| Entity 소멸 = 사망 | 사망해도 Entity는 이벤트에서 사라지지 않음 |
| 단일 리플레이 우연 일치 = 법칙 | 반드시 4+ 리플레이 교차 검증 |
| 고빈도 이벤트 (>100/프레임) = 특정 이벤트 | 고빈도 = 범용/시스템 이벤트 |

---

## 6. 성공한 접근법 (참고)

| 기능 | 접근법 | 정확도 | 핵심 스크립트 |
|------|--------|--------|---------------|
| Hero Detection | Player block +0xA9 uint16 LE | 100% (107/107) | `vg/core/hero_matcher.py` |
| Win/Loss | Turret ID clustering + Crystal destruction | 100% (19/19) | `vg/analysis/win_loss_detector.py` |
| Team Detection | Player block +0xD5 byte | 100% | `vg/core/vgr_parser.py` |
| Item Detection | 4-strategy unified extractor | 부분 성공 | `vg/analysis/item_extractor.py` |

---

*Last Updated: 2026-02-15*
*이 문서는 새로운 실패 시도가 발생할 때마다 업데이트할 것.*
