# Decoder V2 Foundation

`decoder_v2`는 기존 `UnifiedDecoder`를 조금씩 덧대는 방식이 아니라,
"바이트 레벨 사실"과 "상위 추론"을 분리하는 새 구조를 목표로 한다.

## 설계 목표

- 전적검색 시스템 기준으로 필드별 신뢰 수준을 명시한다.
- 직접 저장된 값과 추론된 값을 같은 층에서 다루지 않는다.
- fixture 기반 근거 없이 production-ready라고 선언하지 않는다.
- incomplete replay를 억지로 해석하지 않는다.

## 현재 추가된 기반 모듈

- `vg/decoder_v2/registry.py`
  - offset claim
  - event header claim
  - decoder field status

- `vg/decoder_v2/player_blocks.py`
  - raw player block marker 파서
  - low-level record 추출

- `vg/decoder_v2/validation.py`
  - tournament truth fixture 기반 foundation report 생성
  - 현재 decoder와 direct-offset claim을 같은 리포트 안에서 비교

## 핵심 원칙

1. direct offset claim은 fixture로 검증한다.
2. heuristic field는 accuracy와 failure mode를 함께 기록한다.
3. incomplete replay는 별도 분류한다.
4. 새 디코더는 registry를 소비하는 구조로 만든다.

## 다음 단계

1. canonical event catalog를 `decoder_v2` 내부로 이동
2. field별 decoder를 개별 모듈로 분리
3. complete / incomplete eligibility gate 추가
4. minion kill / duration 전용 실험 루틴을 v2 validator에 통합
