# Decoder V2 Architecture

## 목적

`decoder_v2`는 현재 monolithic `UnifiedDecoder`를 대체하기 위한 새 구조다.

핵심 원칙:
- raw byte fact와 derived stat를 분리
- claim과 implementation을 분리
- validator를 decoder와 같은 수준의 1급 구성요소로 취급

## 계층

### 1. Raw Extraction Layer

책임:
- `.vgr` frame 로드
- player block marker 탐색
- raw event header 탐색

성격:
- 바이트 위치와 값만 추출
- 추론 금지

현재 기반 모듈:
- `vg/decoder_v2/player_blocks.py`
- `vg/decoder_v2/completeness.py`의 signal extractor

### 2. Protocol Registry Layer

책임:
- 알려진 offset / header / field claim을 구조화
- 각 claim의 상태와 근거를 관리

현재 기반 모듈:
- `vg/decoder_v2/registry.py`

### 3. Canonical Event Layer

계획:
- kill / death / credit / item / objective candidate를 공통 포맷으로 변환
- provenance와 raw offset을 유지

현재 상태:
- 아직 scaffold 단계

### 4. Field Decoder Layer

계획:
- hero
- team
- winner
- duration
- K/D/A
- minion

현재 기반 모듈:
- `vg/decoder_v2/duration.py`
- `vg/decoder_v2/kda.py`
- `vg/decoder_v2/winner.py`
- `vg/decoder_v2/minions.py`

규칙:
- 각 field decoder는 registry-backed claim만 사용
- 불완전한 replay에서는 `reject` 가능해야 한다

### 5. Validation Layer

책임:
- fixture 기준 exact / grouped / partial validation
- incomplete fixture 분리
- outlier 추적

현재 기반 모듈:
- `vg/decoder_v2/validation.py`
- `vg/decoder_v2/truth_inventory.py`
- `vg/decoder_v2/labeling_backlog.py`

### 6. Export Layer

역할:
- 전적검색 시스템용 safe schema 출력
- field별 acceptance policy 반영

현재 기반 모듈:
- `vg/decoder_v2/decode_match.py`
- `vg/decoder_v2/batch_decode.py`

정책:
- direct field는 기본 허용
- `winner`, `kills`, `deaths`, `assists`는 completeness-confirmed replay에서만 허용
- `duration_seconds`, `minion_kills`는 아직 withheld-by-default
- `safe-json`은 전적검색 시스템 소비용
- `debug-json`은 completeness/duration/minion candidate 연구용
- field는 `claim_status`와 `accepted_for_index`를 분리해서 출력한다

## 현재 판단

v2는 새 디코더를 즉시 완성하는 게 아니라,
"무엇을 안다고 주장할 수 있는지"를 registry와 validator로 먼저 굳히는 방향이 맞다.
