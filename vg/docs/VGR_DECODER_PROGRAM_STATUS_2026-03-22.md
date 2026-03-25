# VGR Decoder Program Status 2026-03-22

이 문서는 현재 VGR 파싱/디코딩 작업의 목표, 시도한 접근, 완료 범위, 남은 리스크를 한 번에 정리한 상태 문서다.

## 1. 최종 목표

최종 목표는 다음과 같다.

- Vainglory replay `.vgr`에서 전적검색 시스템에 필요한 데이터를 안정적으로 추출한다.
- “대충 맞는 추정치”가 아니라, 필드별로 어떤 바이트/이벤트에서 값이 나오는지 설명 가능한 디코더를 만든다.
- unsupported replay, incomplete replay, 아직 증명되지 않은 field는 억지로 채우지 않고 명시적으로 거부한다.

즉 목표는 단순히 “현재 fixture에 잘 맞는 Python 스크립트”가 아니라:

- 프로토콜 수준으로 설명 가능한 파서
- 제품에 넣어도 되는 field와 아직 보류해야 하는 field를 구분하는 정책
- truth 부족과 truth 품질 문제까지 같이 관리하는 검증 체계

를 만드는 것이다.

## 2. 왜 기존 방식만으로는 부족했는가

기존 `UnifiedDecoder` 중심 구조는 연구 성과는 많았지만 다음 문제가 있었다.

- direct offset field와 heuristic field가 같은 층에서 섞여 있었다.
- incomplete replay를 별도 정책 없이 해석했다.
- truth 기반 검증 코드 일부가 실제 decoder 정확도를 가리는 구조였다.
- 실험 스크립트와 production 후보 로직의 경계가 약했다.

그래서 현재 방향은:

- low-level proven fact는 유지
- 통합 디코더와 검증 정책은 `decoder_v2`로 분리

라는 `strangler rewrite`에 가깝다.

## 3. 지금까지 시도한 것

### A. 기존 core/tooling 복구

실행 경로 자체가 깨진 부분부터 복구했다.

- `vg/core/vgr_database.py`
  - package import fallback 추가
  - duplicate replay import 시 `lastrowid` 오염 제거
  - parser의 실제 field명(`duration_seconds`, `winner`)에 맞춤
- `vg/core/vgr_parser.py`
  - `.vgr_truth` 상대 import fallback 추가
- `vg/core/replay_extractor.py`
  - 존재하지 않는 hero matcher API 호출 제거
- `vg/core/export_matches.py`
  - heterogeneous row CSV export 복구
  - `--csv-only` 실제 반영
- `vg/tools/replay_batch_parser.py`
  - `map_mode` drift 수정
- `vg/ocr/tournament_ocr.py`
  - pair 0개 실패 처리
  - `.png/.jpg/.jpeg` 지원

### B. analysis/validation 정리

연구 스크립트 중 현재 검증에 직접 필요한 것들을 import-safe하게 정리하고, truth 기반 검증 경로를 바로잡았다.

- `vg/analysis/decode_tournament.py`
  - `decode_with_truth()` 대신 `decode()` 기준으로 검증
  - fuzzy name matching 추가
- `vg/analysis/generate_report.py`
  - import side effect 제거
- `vg/analysis/minion_kill_validation.py`
  - 현재 parser/KDADetector API 기준으로 재작성
- `vg/analysis/cross_validate_death_codes.py`
  - 실제 parser output shape 기준으로 수정
- `vg/analysis/test_kda_detector.py`
  - import-safe 정리

### C. `decoder_v2` foundation 구축

새 디코더 기반을 별도 패키지로 만들었다.

- registry / claim ledger / field status
- raw player block parser
- replay completeness assessment
- conservative duration estimate
- raw credit event parser
- raw player event parser
- conservative winner/KDA decode
- safe single-match export
- safe batch export
- index-safe export

핵심 원칙:

- direct field는 evidence 기반으로만 `accepted`
- derived field는 completeness gate를 통과한 경우만 `accepted`
- 아직 partial인 field는 safe output에서 `withheld`

### D. truth/coverage 파이프라인

truth가 부족하다는 가설을 코드로 검증했다.

- `truth_inventory.py`
  - local replay 디렉터리 대비 truth coverage 측정
- `labeling_backlog.py`
  - immediately-labelable / manifest-only / raw-only 분리
- `truth_stubs.py`
  - truth 없는 replay에 대한 prefilled stub 생성
- `truth_audit.py`
  - current truth vs OCR truth vs safe decode 비교

### E. minion research

현재 가장 큰 미해결 항목인 minion kill을 여러 단계로 팠다.

1. baseline signal 비교
- `0x0E@1.0`
- `0x0F@1.0`
- `0x0D_total`
- additive 조합

2. action `0x04` research
- replay 단위 payload 분포 조사
- complete fixture 전체에서 value bucket count 비교

3. sparse residual research
- `truth - 0x0E baseline` residual만 따로 평가
- `MAE`뿐 아니라 precision/recall/F1/exact-match 추가

4. same-frame minion window research
- `0x0E/0x0F` 주변 header enrichment
- same-frame credit pattern enrichment

## 4. 현재까지 완료된 것

### A. 직접 저장된 field

현재 fixture 기준으로 사실상 확정된 영역:

- player entity id
- hero id
- team byte grouping
- hero/team/entity parsing

현재 기준 수치:

- hero: `109/109 = 100.0%`
- team: `109/109 = 100.0%`

### B. complete replay 기준 strong field

현재 tournament complete fixture 기준 strong한 영역:

- winner: `10/10 = 100.0%`
- kills: `98/99 = 99.0%`
- deaths: `97/99 = 98.0%`
- assists: `97/99 = 98.0%`

이 field들은 `decoder_v2` safe output에서 complete-confirmed replay에 한해 index-safe 후보로 취급한다.

### C. incomplete replay gate

현재 tournament fixture에서는 completeness gate가 다음처럼 동작한다.

- `complete_confirmed`: 10
- `incomplete_confirmed`: 1

즉 incomplete replay는 now-safe 정책으로 winner/K/D/A를 withholding할 수 있다.

### D. truth coverage 측정

현재 local replay 풀 대비 truth coverage:

- replay directories: `56`
- truth-covered: `11`
- missing: `45`
- coverage: `19.6%`
- immediately labelable: `0`
- manifest-only: `41`
- raw-only: `4`

즉 decoder 연구는 진전됐지만, 검증 커버리지는 여전히 좁다.
또한 현재 상태에선 OCR를 더 돌린다고 coverage가 바로 늘어나지 않는다.

## 5. 아직 미완료인 것

### A. duration exact decode

현재 duration은 exact field가 아니다.

- exact match: `0/11`
- complete fixture MAE: `17.4s`

즉 현재는 approximate field이며, production DB에 그대로 넣으면 안 된다.

### B. minion kill exact decode

현재 baseline 결론:

- `0x0E@1.0`와 `0x0F@1.0`는 가장 강한 single signal
- 하지만 complete fixture match 6에서 체계적 undercount가 남는다
- `0x0E + 0x0F` 같은 단순 additive 해법은 틀린다

추가 결론:

- action `0x04` bucket은 `MAE`만 보면 좋아 보이지만 sparse residual 기준으로는 overfit 가능성이 높다
- match 6 same-frame window에서는 `28 04 3F`, `08 04 2C`, `18 04 1C`, 일부 `0x02`/`0x08`/`0x00` family가 positive residual 쪽에 더 자주 붙는다
- complete fixture 전체로 확장해도 positive residual은 사실상 한 경기(match 6)에만 몰려 있다
- 즉 지금 단계에선 “새 전역 규칙을 넣는다”보다 “왜 match 6만 특별한가”를 먼저 설명해야 한다

즉 minion은 아직 `withheld`가 맞다.

### C. truth 자체의 품질

OCR truth audit 결과:

- score mismatch matches: `8/11`
- player-level minion mismatches: `47/110`
- K/D/A mismatch는 상대적으로 작음

즉 OCR는 score/minion ground truth로 바로 승격하면 안 된다.

## 6. 지금 제품에 넣어도 되는 것과 아닌 것

### 지금 safe하게 index에 넣을 수 있는 것

- replay identity
- player names
- hero
- entity id
- team grouping
- complete-confirmed replay의 winner
- complete-confirmed replay의 kills/deaths/assists

### 아직 넣으면 안 되는 것

- duration exact value
- minion kills
- incomplete replay의 derived stats
- OCR score/minion을 그대로 ground truth로 간주한 값

## 7. 다음 우선순위

우선순위는 지금 기준으로 다음 순서가 더 맞다.

1. truth source 확장
   - 특히 manifest-only 41개에 대해 result image / score source를 확보
   - immediate OCR backlog는 0개이므로 OCR scale-out은 우선순위가 낮다
2. broader replay pool에서 completeness rule 검증
   - 현재 56 replay 기준 `complete_confirmed 53`, `incomplete_confirmed 3`, `unknown 0`
   - winner/K/D/A accepted replay도 53개까지 늘었다
   - broader replay 풀은 이제 conservative policy 기준으로 complete/incomplete가 모두 분류된다
3. minion outlier root-cause 분석
   - positive residual이 한 complete match에 몰려 있으므로, 먼저 match 6 특이성을 설명해야 한다
   - 현재 evidence상 match 6 outlier의 중심은 `action 0x02 family`다
   - same-hero peer 대비:
     - Kestrel은 `0x02@20.0`가 peer mean `14.0` 대비 target `117`
     - Samuel은 `0x02@17.4`가 peer mean `340.25` 대비 target `667`
     - Grumpjaw는 `0x02@4.0`가 peer baseline `0`인데 target `222`
     - Kinetic은 `0x02@9.54`가 peer mean `205.0` 대비 target `444`
   - 즉 minion undercount는 hero 일반 현상보다 replay-family에서 `0x02` 계열이 비정상적으로 커지는 문제에 더 가깝다
   - provenance/cluster evidence도 같은 방향이다
     - 핵심 `0x02` value 대부분은 same-frame에서 `0x06@3.0`, `0x08@0.6`, `0x03@1.0`과 강하게 묶인다
     - `0x02@17.4`, `0x02@14.34`, `0x02@9.54`, `0x02@4.0`는 cluster size가 거의 항상 `1`이라 team-wide shared event보다는 solo reward subfamily에 가깝다
     - `0x02@20.0`와 `0x02@-50.0`만 일부 multi-player cluster가 보이지만, 그래도 shared-cluster rate는 낮다
   - self/teammate/opponent presence를 보면 이 solo 계열도 순수 self reward로 단정하긴 이르다
   - 따라서 더 안전한 표현은 `solo reward`보다 `solo-cluster subfamily`다
   - 기존 repo의 주류 해석은 `0x02 = XP / team-wide sharing` 쪽이지만, 현재 evidence는 `0x02`를 하나의 semantic으로 다루면 안 된다는 쪽으로 움직였다
   - 현재 가장 실용적인 taxonomy:
     - `solo_subfamily_candidate`
       - `0x02@17.4`
       - `0x02@14.34`
       - `0x02@9.54`
       - `0x02@4.0`
     - `mixed_or_shared_subfamily_candidate`
       - `0x02@20.0`
       - `0x02@-50.0`
   - hero affinity도 강하다
     - `0x02@17.4`는 fixture 기준 사실상 `Samuel` 전용
     - `0x02@14.34`는 `Celeste` 중심, 일부 `Magnus`
     - `0x02@9.54`는 `Kinetic` 중심, 일부 `Ishtar`
     - `0x02@4.0`는 `Caine` 중심이지만 `Grumpjaw`/`Kestrel`도 포함
     - `0x02@20.0`와 `0x02@-50.0`는 여러 hero에 넓게 분포
   - 즉 다음 단계는 `0x02`를 하나의 의미로 해석하는 게 아니라, subfamily별 semantic 후보를 따로 검증하는 것이다
   - series-level 비교도 중요하다
     - Finals 시리즈 전체는 다른 series보다 `solo_subfamily_total`과 `solo_excess_vs_peer_mean`이 훨씬 높다
     - 하지만 Finals 2는 같은 Finals 내부 peer와 비교해도 여전히 값이 더 높다
       - Kestrel `0x02@20.0`: same-series mean `30.0`, target `117`
       - Samuel `0x02@17.4`: same-series mean `416.0`, target `667`
       - Grumpjaw `0x02@4.0`: same-series mean `0`, target `222`
       - Kinetic `0x02@9.54`: same-series mean `350.5`, target `444`
   - 따라서 current best explanation은:
     - Finals series 자체가 `0x02` solo-subfamily를 키우는 replay-family
     - 그 안에서도 Finals 2가 추가적인 match-specific amplification을 가진다
   - risk report 기준으로는 `solo_subfamily` excess만으로 residual-positive player를 clean하게 분리하지 못한다
     - Finals 1/3/4 zero-residual rows도 높은 solo excess를 가진다
     - 따라서 `solo_subfamily_total`을 minion 보정식으로 바로 쓰는 건 위험하다
   - ratio 정규화도 아직 충분하지 않다
     - `0x02@20.0_ratio` best rule은 `precision 0.75 / recall 0.43`
     - `solo_ratio` best rule은 `precision 0.60 / recall 0.43`
     - 즉 raw count보다 조금 낫지만, 아직 product minion rule로 쓰기엔 약하다
   - 하지만 partial acceptance candidate는 하나 보인다
     - current truth 기준 `Finals 제외` gate는 baseline `0x0E` minion을 `precision 1.0`으로 받는다
     - coverage는 `0.5128`로 낮지만, 지금까지 나온 첫 보수적 partial policy 후보다
     - 또 하나의 hybrid candidate는 `nonfinals_or_mixed_ratio<=0.1351`이고
       - `precision ~= 0.9796`
       - `coverage ~= 0.6282`
       - finals rows 일부만 추가로 받아들인다
   - 다만 truth coverage가 낮아서, 이 gate도 default policy로 바로 승격하진 않는 편이 맞다
   - 따라서 이건 기본 정책이 아니라 optional export mode로만 다루는 편이 맞다
   - 현재 optional policy name으로는 다음 둘을 지원한다
     - `nonfinals-baseline-0e`
     - `nonfinals-or-low-mixed-ratio-experimental`
   - current policy validation:
     - `none` -> `accepted_rows 0`, `precision 0.0`, `coverage 0.0`
     - `nonfinals-baseline-0e` -> `accepted_rows 40`, `precision 1.0`, `coverage 0.5128`
     - `nonfinals-or-low-mixed-ratio-experimental` -> `accepted_rows 49`, `precision 0.9796`, `coverage 0.6282`
   - practical recommendation:
     - 기본 정책은 계속 `none`
     - 필요하면 optional mode로 `nonfinals-baseline-0e`만 먼저 노출
     - experimental policy는 아직 research/ops용으로만 유지
   - 이 taxonomy는 아직 연구용 분류이며, product export rule로 바로 승격하면 안 된다
   - 즉 현재 evidence는 `0x02`를 하나의 전역 의미로 다루기보다
     - `shared XP / mixed reward candidate`
     - `solo-cluster / replay-family outlier candidate`
     로 분리해야 한다는 쪽을 지지한다
4. duration exact match-end signal 분리

## 8. 현재 판단

현재 프로젝트는 “기존 decoder를 무조건 보수하는 단계”를 지나서,

- 실행 경로 복구
- 검증 경로 복구
- conservative product policy 도입
- `decoder_v2` foundation 구축
- truth coverage/quality 계량화
- minion research를 residual/window 단계까지 확장

까지는 완료된 상태다.

하지만 전적검색 시스템을 위한 “100% 신뢰 가능한 전체 stat decode”는 아직 아니다.

현재 가장 정확한 표현은 다음과 같다.

- parser/direct field는 강하다
- complete replay 기준 winner/K/D/A는 꽤 강하다
- minion/duration은 아직 연구 대상이다
- truth coverage와 truth quality를 동시에 확장해야 한다
