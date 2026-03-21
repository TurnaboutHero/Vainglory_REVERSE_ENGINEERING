# Decoder Validation 2026-03-21

실제 tournament `.vgr` 파일과 truth fixture를 기준으로 현재 Python 디코더 계층을 재검증한 결과다.
목적은 다음 두 가지다.

1. 현재 디코더가 어떤 구조로 동작하는지 정리한다.
2. 기존 문서와 코드 주장이 실제 replay 기준으로 맞는지 판정한다.

---

## 1. 검증 범위

검증 대상:
- `vg/core/vgr_parser.py`
- `vg/core/unified_decoder.py`
- `vg/core/kda_detector.py`
- `vg/core/hero_matcher.py`
- `vg/core/vgr_mapping.py`
- `vg/analysis/decode_tournament.py`

참조 문서:
- `README.md`
- `vg/docs/PROJECT_OVERVIEW.md`
- `vg/docs/HERO_DETECTION_RESULTS.md`
- `vg/docs/EVENT_HEADER_SURVEY_README.md`

데이터셋:
- `vg/output/tournament_truth.json`
- truth에 연결된 실제 tournament replay 11경기

중요 제한:
- 이번 검증은 실제로 존재하는 11경기 tournament truth fixture에 기반한다.
- item build, objective classification, raw event header catalog 전체는 이번 라운드에서 독립 재증명하지 않았다.
- 이번 라운드에서 `decode_tournament.py`도 수정했다. 이제 `decode()` 기반으로 검증하고, OCR 이름 오탈자를 흡수하는 이름 매칭을 사용한다.

---

## 2. 현재 디코더 구조

### A. `VGRParser`

역할:
- frame 0 기준 정적 정보 추출
- player block 파싱
- 팀/영웅/엔티티/모드 추출
- truth overlay 적용

핵심 구조:
- player block marker 탐색: `DA 03 EE`, `E0 03 EE`
- player block offset
  - `+0xA5`: player entity id
  - `+0xA9`: hero id
  - `+0xD5`: team byte
- 결과 shape:
  - `match_info`
  - `teams.left[]`
  - `teams.right[]`

### B. `KDADetector`

역할:
- 전체 frame를 순회하면서 kill / death / assist / minion kill 추출

핵심 구조:
- kill header: `18 04 1C`
- death header: `08 04 31`
- credit header: `10 04 1D`
- `get_results(game_duration=..., team_map=...)`에서 post-game filtering과 assist counting 적용

### C. `UnifiedDecoder`

역할:
- `VGRParser` + `KDADetector` + `WinLossDetector` + item/gold/objective/crystal 루틴을 묶은 최종 디코더

처리 순서:
1. `VGRParser.parse()`로 frame 0 정적 정보 추출
2. 전체 frame 로드
3. `KDADetector`로 kill/death/assist/minion scan
4. `WinLossDetector`로 winner 후보 추정
5. item/gold scan
6. crystal death 기반 duration 추정
7. duration 기반 KDA 후처리
8. objective event 추정

### D. `ReplayExtractor`

역할:
- parser 결과를 보다 단순한 추출 결과로 감싼 API

현재 상태:
- 이번 작업으로 현재 존재하는 `HeroMatcher.detect_heroes()` API 기준으로 복구함
- 다만 검증과 기능 면에서는 `UnifiedDecoder`가 실질적인 메인 디코더다

---

## 3. 실제 replay 기반 검증 결과

### A. Player Block Offset 검증

검증 방법:
- truth 11경기의 실제 `.0.vgr`를 직접 읽음
- raw bytes에서 marker를 찾고
- `+0xA5`, `+0xA9`, `+0xD5`를 직접 읽음
- truth와 비교

결과:
- 11경기 모두에서 player block 10개 추출
- hero id offset `+0xA9`: **109/109 = 100.0%**
  - truth OCR 오탈자와 이름 흔들림을 흡수하는 normalized / fuzzy name match 기준 비교
- entity id offset `+0xA5`: 모든 player block에서 non-zero
- team byte `+0xD5`: 전체 110개 player block에서 값 분포 `{1: 55, 2: 55}`

판정:
- `+0xA5`, `+0xA9`, `+0xD5` 오프셋 주장은 현재 fixture 기준 **확정**

### B. Tournament Truth 기준 디코더 정확도

검증 방법:
- `python -m vg.analysis.decode_tournament --truth vg/output/tournament_truth.json`
- 결과 파일: `vg/output/decode_tournament_validation_v2.json`

전체 11경기 기준:
- Hero: `109/109`, `100.0%`
- Team: `109/109`, `100.0%`
- Winner: `10/11`, `90.9%`
- Kills: `104/109`, `95.4%`
- Deaths: `102/109`, `93.6%`
- Assists: `102/109`, `93.6%`
- Minion kills: `69/89`, `77.5%`

중요 outlier:
- Match 6: K/D/A는 `8/9`, minion kill은 `1/9`
- Match 9: winner false, K/D/A와 minion이 크게 붕괴

### C. Incomplete Replay 분리 후 정확도

truth 9번째 경기는 replay directory 이름 자체가 `5 (Incomplete)`다.
실제 frame 수도 85개뿐이라 complete replay와 같은 기준으로 보면 안 된다.

이 incomplete match를 제외하면:
- Winner: `10/10`, `100.0%`
- Kills: `98/99`, `99.0%`
- Deaths: `97/99`, `98.0%`
- Assists: `97/99`, `98.0%`
- Minion kills: `69/79`, `87.3%`

판정:
- complete replay 기준으로 winner / K / D / A는 상당히 강함
- minion kill은 여전히 약함
- incomplete replay handling은 별도 처리 필요

### D. Duration 독립 검증

주의:
- `decode_tournament.py`는 `decode_with_truth()`를 사용하므로 duration은 truth로 덮어씌워진다.
- 그래서 duration은 별도 검증함

검증 방법:
- 각 match에 대해 `UnifiedDecoder(...).decode()`를 직접 호출
- truth duration과 비교

결과:
- exact match: `0/11`
- absolute error:
  - 전체 MAE: `128.18s`
  - complete replay만 기준 MAE: `17.4s`
  - complete replay 기준 median: `10.0s`
  - complete replay 기준 max error: `65s`
- incomplete replay는 `473s` vs truth `1709s`로 크게 붕괴

판정:
- duration은 **대체로 근사치**
- exact duration으로 취급하면 안 됨
- incomplete replay에서는 신뢰 불가

---

## 4. 문서 주장 판정

### A. `vg/docs/HERO_DETECTION_RESULTS.md`

주장:
- hero detection solved at 100%
- hero id at player block `+0xA9`

판정:
- **확정**

근거:
- raw player block 직접 검증 `109/109`
- current parser/unified decoder와 truth validation 모두 일치

### B. `README.md`

주요 주장과 판정:

- player names / UUID 100%
  - **대체로 수용**
  - 이번 라운드에서 UUID 전수 재검증은 안 했지만 parser 구조상 타당

- team assignment 100%
  - **조건부 수용**
  - team byte grouping은 맞음
  - 하지만 API convention 기준 left/right label은 screenshot-side swap 보정이 필요함

- hero selection / entity id 100%
  - **확정**

- win/loss 99% (1 replay validated)
  - **문서가 outdated**
  - complete tournament fixture 기준 현재는 `10/10 = 100%`
  - incomplete match 포함 시 `10/11 = 90.9%`

- K/D/A research stage
  - **문서가 outdated**
  - 현재 디코더는 complete fixture 기준
    - kills `99.0%`
    - deaths `98.0%`
    - assists `98.0%`

### C. `vg/docs/PROJECT_OVERVIEW.md`

주요 주장과 판정:

- 플레이어/영웅/엔티티/게임 모드/hero hash/hero id
  - **대체로 확정**

- 승패 결과 연구중
  - **문서가 outdated**
  - complete fixture 기준으로는 충분히 usable

- K/D/A 추출 불가능
  - **문서가 outdated**
  - 현재는 완전하지 않지만 complete fixture 기준 높은 정확도로 추출 가능

- 골드/경험치 추출 불가능
  - **보류**
  - 코드상 gold detection은 존재하지만 이번 라운드에서 truth 기준 독립 검증은 하지 않음

- 프레임 수(경기 길이) 100%
  - **표현 수정 필요**
  - frame count는 맞지만, decoder의 `duration_seconds`는 exact하지 않음
  - “frame count”와 “wall-clock duration”을 분리해서 써야 함

### D. `vg/docs/EVENT_HEADER_SURVEY_README.md`

주장:
- comprehensive header survey 및 header catalog 구조

판정:
- **이번 라운드에서는 독립 재증명 안 함**

비고:
- survey 방법론은 엔지니어링적으로 타당해 보임
- 하지만 현재 검증은 디코더 정확도 중심이었고, header catalog 전체 재생성은 수행하지 않음

---

## 5. 엔지니어링 결론

### 지금 믿어도 되는 것

- player block 기반 player / entity / hero parsing
- hero id offset `+0xA9`
- complete replay 기준 hero/team/winner
- complete replay 기준 K/D/A

### 아직 조심해야 하는 것

- duration exactness
- incomplete replay 처리
- minion kill
- objective classification
- gold / item build의 정확도 수치

### 현재 디코더에 대한 실무적 판단

- `VGRParser`는 production-grade에 가까운 정적 메타데이터 파서다.
- `UnifiedDecoder`는 “complete replay 기준 상당히 usable한 통합 디코더”다.
- 다만 duration과 minion kill은 아직 품질 보증 수치가 약하고,
  incomplete replay guard가 없어서 결과를 오염시킬 수 있다.

---

## 6. 다음 실험 우선순위

1. **Incomplete replay 감지 규칙 추가**
   - frame count 급감
   - crystal death 부재
   - K/D/A 분포 붕괴
   - truth fixture의 incomplete 경기와 현재 오차 패턴 비교

2. **Duration estimator 재검정**
   - current `crystal death` vs `last death timestamp` 휴리스틱 비교
   - complete fixture 10경기 기준 MAE를 낮추는 방향으로 재실험

3. **Match 6 집중 분석**
   - complete replay인데 minion kill이 `1/9`
   - K/D/A도 `8/9`
   - outlier라서 detector weakness를 가장 잘 드러냄

4. **Gold / item accuracy 독립 검증**
   - screenshot truth 또는 수동 annotation 기준 비교 필요

5. **문서 정리**
   - README / PROJECT_OVERVIEW에서 outdated claim 제거
   - “확정”, “고정밀”, “근사”, “연구중” 상태를 분리해서 다시 쓰기

---

## 7. 요약

이번 검증으로 확인된 핵심은 다음과 같다.

- hero / entity / player block 구조는 실제 replay 기준으로 매우 강하게 확인됐다.
- complete replay 기준 `UnifiedDecoder`는 hero/team/winner/K/D/A에서 꽤 높은 품질을 보인다.
- 다만 duration은 exact하지 않고, minion kill은 아직 취약하다.
- 기존 문서 중 일부는 이미 현재 코드 상태를 따라가지 못해 outdated 상태다.

즉, 현재 상태는
"파싱은 강하게 신뢰 가능"
"디코딩은 complete replay 기준으로 상당히 쓸 만함"
"duration / minion / incomplete handling은 추가 연구 필요"
로 정리하는 것이 가장 정확하다.
