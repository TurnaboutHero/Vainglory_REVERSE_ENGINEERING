# Vainglory 리플레이 분석 프로젝트

## 프로젝트 목표 (Updated)

**Vainglory Global Stats Server 구축**
1. **APK Modding**: 게임 클라이언트가 종료 시 리플레이를 자동으로 서버로 전송하도록 수정
2. **Replay Analysis Server**: 수신된 리플레이를 자동 분석하여 데이터베이스화
3. **Global Leaderboard**: 웹사이트 또는 인게임 Overlay를 통해 전 세계 유저의 전적/랭킹 제공

**핵심 가치:**
- **자동화**: 유저가 수동으로 업로드할 필요 없음
- **대규모 데이터**: 모든 경기를 수집하여 정확한 메타(Meta) 분석 가능 ("Ringo 승률 52%" 등)

---

## 총정리
- Tournament_Replays 11경기 truth 데이터 수동 검증 완료
- `vgr_parser.py` truth 정합성 보강 (플레이어 블록 마커 보강, 오타 이름 정규화, bounty/CS 처리)
- `tournament_parsed.json`이 `tournament_truth.json`과 일치함 (검증 스크립트 재확인)
- 이벤트/영웅 후보 분석 스크립트 추가 (`event_probe.py`)

---

## 현재 추출 가능한 데이터

| 데이터 | 상태 | 소스 |
|--------|------|------|
| 플레이어 이름 | ✅ 완료 | 플레이어 블록 마커 |
| 플레이어 UUID | ✅ 완료 | 정규식 패턴 |
| 게임 모드 | ✅ 완료 | GameMode 문자열 |
| 맵 (3v3/5v5) | ✅ 완료 | 모드 기반 추론 |
| 팀 구성 | ✅ 완료 | 플레이어 블록 팀 바이트(+0xD5) |
| 플레이어 엔티티 ID | ✅ 완료 | 플레이어 블록(+0xA5) |
| 프레임 수 (경기 길이) | ✅ 완료 | 파일 카운트 |
| 리플레이 날짜 | ✅ 완료 | 파일 메타데이터 |

---

## 현재 추출 불가능한 데이터 (리플레이 단독 기준)

| 데이터 | 상태 | 이유 |
|--------|------|------|
| 영웅 선택 | ⚠️ 실험적 | 휴리스틱 추정 가능하지만 정확도 낮음 |
| 아이템 빌드 | ❌ | 이벤트 스트림에서 추출 필요 |
| K/D/A 통계 | ❌ | 이벤트 집계 필요 |
| 승패 결과 | ❌ | 게임 엔진 재계산 필요 |
| 골드/경험치 | ❌ | 실시간 계산 데이터 |

참고: MATCH_DATA_*.md/JSON 보정을 사용하면 승패/스코어/KDA/골드/CS/현상금/영웅 정보를 출력에 반영 가능.

## 이벤트 분석 결과 (58개 리플레이 분석)

### 이벤트 구조
```
[EntityID(LE, 2B)] [00 00] [ActionType] [Parameters...]
```

### 발견된 액션 타입
| 코드 | 빈도 | 추정 의미 |
|------|------|---------|
| 0x00 | 많음 | 초기화/스폰 |
| 0x0B | 중간 | 이동? |
| 0x0C | 많음 | 공격? |
| 0x0D-0x0E | 많음 | 스킬 사용? |
| 0x10-0x18 | 중간 | 특수 행동 |
| **0x80** | 적음 | **사망** (확인 필요) |

### 사망 이벤트 예시 (테스트 경기)
| 영웅 | 0x80 횟수 | 추정 데스 |
|------|---------|----------|
| Kensei | 1 | 1 데스 |
| Malene | 5 | 5 데스 |
| Magnus | 5 | 5 데스 |
| Kinetic | 6 | 6 데스 |

---

## 프로젝트 구조

```
vg/
├── vgr_parser.py      # 리플레이 파싱 (플레이어, 모드, 팀)
├── vgr_truth.py       # MATCH_DATA_*.md/JSON 보정 로더
├── vgr_mapping.py     # 영웅/아이템 ID 매핑 테이블
├── vgr_database.py    # SQLite 데이터베이스 관리
├── vgr_watcher.py     # 리플레이 자동 백업
├── vgr_loader.py      # 리플레이 로드 유틸리티
├── tournament_ocr.py  # 결과 스크린샷 OCR 매핑
├── event_probe.py     # 이벤트/영웅 후보 분석 스크립트
├── verify_tournament_truth.py  # truth/parsed 정합성 검증 스크립트
├── vg_mapping.json    # 매핑 데이터 JSON
├── MATCH_DATA_01.md   # 스크린샷 기반 보정 데이터 예시
└── REVERSE_ENGINEERING_NOTES.md  # 역공학 상세 노트
```

OCR 결과 파일:
- `tournament_truth.json` (vgr_parser.py --truth로 사용)
- `tournament_ocr_raw.json` (OCR 원본 토큰)
- `tournament_ocr_summary.md` (누락값 요약)

정합성 검증:
- `tournament_parsed.json` (truth 적용 파서 결과)
- `verify_tournament_truth.py` (truth/parsed 비교)

영웅 매핑 예시:
Hero070 = Caine        Hero062 = Malene  
Hero071 = Leo          Hero072 = Amael (NEW)
...49개 영웅 매핑 완료

### 누락된 영웅 후보 (이벤트 분석 기반)
| ID | 이벤트 수 | 유력 후보 |
|----|----------|----------|
| 32 | 9,407 | **Anka** (앙카) |
| 75 | 1,195 | **Ishtar** (이슈타르) |
| 82 | 1,159 | **Karas** (카라스) |
| 103 | 1,137 | **Shin** (신) |
| 56 | 1,063 | **Miho / Warhawk?** |

**확인 필요:** Viola, Ylva, Warhawk, Miho, Ishtar, Karas, Shin

---

## 기술적 발견

### VGR 파일 구조
- **형식**: 바이너리 게임 이벤트 스트림
- **프레임**: `리플레이명.N.vgr` (N = 0, 1, 2, ...)
- **크기**: 프레임당 40-130KB

### 플레이어 블록
```
오프셋   데이터
------   ------
+0x00    DA 03 EE (마커)
+0x03    플레이어 이름 (ASCII)
+0xA5    엔티티 ID (uint16)
+0xD4    알 수 없음 (샘플에서 고정값)
+0xD5    팀 ID (1=Left/Blue, 2=Right/Red)
```

### 영웅 ID 매핑 (에셋 기반)
```
Hero009 = SAW        Hero040 = Lyra
Hero010 = Ringo      Hero047 = Grumpjaw
Hero011 = Taka       Hero070 = Caine
...49개 영웅 매핑 완료
```

---

## 전적 검색 구현 로드맵

### Phase 1: 기본 데이터 (✅ 완료)
- [x] 플레이어 이름/UUID 추출
- [x] 게임 모드/맵 추출
- [x] 팀 구성 추출
- [x] 데이터베이스 스키마

### Phase 1.5: 토너먼트 정합성/검증 (✅ 완료)
- [x] Tournament_Replays truth 데이터 수동 검증
- [x] 파서 truth 정합성 보강 (이름 매칭/마커 보강/현상금 처리)
- [x] truth/parsed 정합성 검증 스크립트 통과

### Phase 2: 이벤트 파싱 (⚠️ 한계 발견)
- [x] 이벤트/영웅 후보 분석 스크립트 구축 (`event_probe.py`)
- [x] 통계적 상관분석 파이프라인 구축 (p-value, 신뢰구간 포함)
- [x] deaths=0 vs deaths>0 그룹 패턴 비교 분석
- [⚠️] **K/D/A 자동 추출 불가 확인** - 단순 액션 카운트로는 정확도 20% 미만

**Phase 2 분석 결과:**
- 최고 정확도: deaths 19.63% (0x78), kills 28.04% (0xD7)
- 0x80 코드: Ringo Death Test에서 사망당 2회 발생 (시작/종료 이벤트)
- 토너먼트 데이터에서는 일치하지 않음 (게임 버전 차이 가능성)
- deaths>0 그룹에서 더 많이 발생: 0x0F (+30.7), 0x44 (+23.4), 0x19 (+18.8)

**남은 작업 (추가 역공학 필요):**
- [ ] 이벤트 패킷 구조 역공학 (엔티티/타임스탬프/파라미터 분리)
- [ ] 킬/데스 이벤트 식별 (killer/victim 매핑)
- [ ] 영웅 스폰 이벤트 식별
- [ ] 아이템 구매 이벤트 식별
- [ ] 미니언/목표물 이벤트 정리 (CS/현상금 연동)

### Phase 3: 통계 시스템
- [ ] 플레이어별 전적 집계
- [ ] 영웅별 승률 계산
- [ ] 랭크 점수 시스템 (ELO/MMR)

### Phase 4: 웹 인터페이스
- [ ] 전적 검색 UI
- [ ] 플레이어 프로필
- [ ] 리더보드

---

## 현재 사용 가능한 기능

### 1. 리플레이 파싱
```bash
python vgr_parser.py "리플레이폴더" -o result.json
```
옵션:
- `--truth MATCH_DATA_01.md` : 스크린샷 기반 데이터로 결과 보정
- `--debug-events` : 플레이어별 이벤트 타입 카운트 출력
- `--detect-heroes` : 휴리스틱 영웅 감지(정확도 낮음)
- `--no-auto-truth` : 현재 폴더의 MATCH_DATA_*.md 자동 탐색 비활성화
출력 예시:
```json
{
  "match_info": {
    "mode": "GameMode_HF_Ranked",
    "mode_friendly": "Ranked (Halcyon Fold)",
    "map_name": "Halcyon Fold",
    "team_size": 3
  },
  "teams": {
    "left": [{"name": "Player1", "uuid": "abc-123"}],
    "right": [{"name": "Player2", "uuid": "def-456"}]
  }
}
```

### Truth 보정 데이터 포맷 (MATCH_DATA_*.md)
- 인식되는 항목: 리플레이 이름, 경기 시간(분/초), 승패, 팀별 K/D/A/골드/CS 테이블
- 필수 테이블 헤더: `플레이어 | 영웅 | K | D | A | 골드 | CS`
- JSON도 지원: `match_truth*.json`, `truth*.json`
- JSON에서 `bounty` 필드를 추가로 기록 가능 (미니언이 없는 경기에서 사용)

### 2. 영웅/아이템 조회
```bash
python vgr_mapping.py heroes          # 전체 영웅 목록
python vgr_mapping.py search -q 타카   # 한글 검색
python vgr_mapping.py items           # 전체 아이템 목록
```

### 3. 리플레이 자동 백업
```bash
python vgr_watcher.py --output "백업폴더"
```

### 4. 결과 스크린샷 OCR 매핑
```bash
python tournament_ocr.py "D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays"
```
출력:
- `tournament_truth.json` (vgr_parser.py --truth로 사용)
- `tournament_ocr_raw.json` (OCR 원본 토큰)
- `tournament_ocr_summary.md` (누락값 요약)

메모:
- Tournament_Replays 기준 11경기 매핑 완료
- 일부 CS는 OCR 실패로 누락될 수 있음 (summary 참고)
- 영웅 이름은 텍스트가 없어 `Unknown`으로 유지
- 마지막 2경기는 미니언 대신 현상금(bounty)만 기록됨
- `tournament_truth.json`은 수동 검증 완료 데이터로 간주
- 의존성: `easyocr` (처음 실행 시 모델 다운로드)

---

### 5. 이벤트/영웅 후보 분석
```bash
python event_probe.py "D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays" --batch --truth tournament_truth.json --hero-probe --output event_probe_output.json
```
출력:
- `event_probe_output.json` (액션 타입 상관/히어로 후보 오프셋 요약)

메모:
- 상관값은 후보 힌트로만 사용 (확정 매핑 아님)
- hero_probe 결과는 오프셋/액션 타입 경향 확인용

---

### 6. 토너먼트 정합성 검증
```bash
python verify_tournament_truth.py --truth tournament_truth.json --parsed tournament_parsed.json
```
출력:
- truth/parsed 매치 수와 불일치 건수
- 불일치 상세(있을 경우)

---

## 다음 단계 권장사항

### 옵션 A: Truth 기반 통계 시스템 (권장)
- OCR 추출 데이터(tournament_truth.json)를 활용
- 플레이어별 전적, 영웅별 승률 등 통계 API 구축
- 웹 인터페이스로 데이터 조회 제공
- 장점: 즉시 구현 가능, 11경기 데이터 활용
- 단점: 새 경기마다 OCR 필요

### 옵션 B: 이벤트 패킷 심층 역공학 (고난도)
- 게임 실행 중 Cheat Engine으로 메모리 분석
- 특정 이벤트(사망/킬) 발생 시 메모리 변화 추적
- 이벤트 패킷 페이로드 구조 분석
- 장점: 완전 자동화 가능
- 단점: 높은 기술적 난이도

### 옵션 C: APK Modding + 서버 연동
- 게임 클라이언트가 결과 화면 스크린샷을 서버로 전송
- 서버에서 OCR 자동 처리
- 장점: 대규모 데이터 수집 가능
- 단점: APK 수정 필요, 보안 이슈

### 옵션 D: 커뮤니티 수동 입력
- 웹 UI에서 사용자가 경기 결과 입력
- 자동 추출 데이터(플레이어/모드) + 수동 보완(K/D/A/영웅)
- 장점: 데이터 정확도 높음
- 단점: 사용자 참여 필요

---

## 참고 자료

- [역공학 상세 노트](./REVERSE_ENGINEERING_NOTES.md)
- [영웅 매핑 코드](./vgr_mapping.py)
- [데이터베이스 스키마](./vgr_database.py)

---

## Update (2026-02-03): Item ID Linkage

- `FF FF FF FF [item_id 2B LE]` 패턴이 아이템 프레임(5/6)에서 발견 확인
- 해당 패턴은 인벤토리/상점 데이터의 레코드일 가능성 있음
- 0xBC가 구매 트리거, 실제 아이템 ID는 별도 레코드에 기록되는 패턴 확인
- 상세 분석: `vg/output/item_pattern_hunt_output.txt`

---

## Update (2026-02-09): Item Mapping Analysis

### 아이템 추출 분석 결과

**FF FF FF FF 패턴 적용 범위:**
| 카테고리 | 추출 성공 | 비고 |
|----------|----------|------|
| Weapon (101-129) | ✅ 100% | 모든 Tier 1-3 발견 |
| Crystal (201-229) | ❌ 0% | 다른 저장 패턴 사용 |
| Defense (301-328) | ❌ 0% | 다른 저장 패턴 사용 |
| Utility (401-423) | ❌ 0% | 다른 저장 패턴 사용 |

**핵심 발견:**
- 0xBC = 아이템 구매 이벤트 (검증 완료)
- 0x3D = 인벤토리 상태 업데이트 이벤트 (추정)
- Weapon 아이템만 FF FF FF FF 패턴으로 저장됨
- Crystal/Defense/Utility는 다른 바이트 패턴 사용 (추가 역공학 필요)

**새로 발견된 아이템 ID:**
- 105-110: Unknown Weapon 아이템 (Tier 1 범위)
- 188: System Item (모든 프레임에서 발견)
- 255: Marker (특수 용도)

**생성된 스크립트:**
- `vg/analysis/extract_all_item_ids.py` - 아이템 ID 자동 추출
- `vg/analysis/verify_tournament_items.py` - 토너먼트 검증

**분석 결과 파일:**
- `vg/output/item_extraction_report.json` - Item Buy Test 분석
- `vg/output/tournament_item_verification.json` - 토너먼트 11경기 분석
- `vg/output/0x3D_event_analysis.txt` - 0x3D 이벤트 분석
- `vg/output/image_vs_extraction_comparison.md` - 이미지 vs 추출 비교

### 다음 단계
Crystal/Defense/Utility 아이템의 저장 패턴을 찾기 위해:
1. 해당 카테고리 아이템만 구매하는 테스트 리플레이 생성
2. 결과 이미지와 리플레이 hex dump 비교 분석
3. 새로운 바이트 패턴 식별
