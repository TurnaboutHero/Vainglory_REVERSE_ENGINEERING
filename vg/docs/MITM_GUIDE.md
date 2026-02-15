# Vainglory Community Edition - MITM 네트워크 분석 가이드

## 목차

1. [개요](#1-개요)
2. [필요 도구](#2-필요-도구)
3. [환경 설정](#3-환경-설정)
4. [VGR + MITM 통합 분석](#4-vgr--mitm-통합-분석)
5. [VGReborn 분석](#5-vgreborn-분석)
6. [PC (Steam) 버전 MITM](#6-pc-steam-버전-mitm)
7. [예상 프로토콜 구조](#7-예상-프로토콜-구조)
8. [법적/윤리적 고려사항](#8-법적윤리적-고려사항)
9. [다음 단계](#9-다음-단계)

---

## 1. 개요

### MITM이란 무엇인가

MITM(Man-in-the-Middle)은 두 통신 주체 사이에 위치하여 오가는 데이터를 관찰하거나 변조하는 기법이다. 네트워크 분석에서는 클라이언트(게임)와 서버 사이의 트래픽을 프록시를 통해 캡처하는 데 사용한다.

```
[VG:CE 클라이언트] <---> [MITM 프록시] <---> [게임 서버]
                          |
                     패킷 캡처/분석
```

이 가이드에서는 Vainglory Community Edition(VG:CE)의 네트워크 트래픽을 분석하여 게임 데이터를 추출하는 방법을 다룬다.

### VGR 리플레이 분석의 한계

현재 VGR 리플레이 바이너리 분석으로 추출 가능한 데이터에는 명확한 한계가 있다.

| 데이터 | VGR 추출 정확도 | 한계 원인 |
|--------|----------------|----------|
| 플레이어 이름/UUID | 100% | 플레이어 블록에 직접 저장 |
| 팀 구분 | 100% | +0xD5 오프셋에 저장 |
| 게임 모드 | 100% | GameMode 문자열로 저장 |
| **영웅 선택** | **0%** | 바이너리에 저장되지 않음 |
| **K/D/A** | **~20%** | 게임 엔진이 실시간 계산하는 데이터 |
| **승패** | **추출 불가** | 게임 엔진 재계산 필요 |
| **아이템 빌드** | **부분적** | Weapon만 FF FF FF FF 패턴으로 추출 가능 |

VGR 리플레이는 **입력 재생(Input Replay) 시스템**이다. 게임 상태(영웅, KDA, 승패)는 저장되지 않고, 게임 엔진이 입력을 재생하면서 실시간으로 계산한다. 따라서 바이너리 분석만으로는 이러한 데이터를 추출할 수 없다.

### MITM으로 보완할 수 있는 데이터

MITM 캡처를 통해 VGR에서 추출 불가능한 데이터를 서버 통신에서 직접 가져올 수 있다.

| 데이터 | MITM 추출 가능성 | 근거 |
|--------|----------------|------|
| 영웅 선택 | 높음 | 매치메이킹/로비에서 서버에 전송 |
| K/D/A | 높음 | 경기 결과를 서버에 보고 |
| 승패 결과 | 높음 | 매치 종료 시 서버에 보고 |
| 아이템 빌드 | 중간 | 경기 결과 보고에 포함 가능 |
| 골드/경험치 | 낮음 | 실시간 데이터, 최종 수치만 가능 |
| 스킬 사용 통계 | 낮음 | UDP 스트림에 포함 가능 |

### VGReborn 프로젝트 참고

VGReborn(https://vgreborn.com/)은 이미 MITM 기법을 활용하여 VG:CE의 네트워크 트래픽을 분석하고 있다. 이 프로젝트는 WireGuard 기반 VPN을 통해 게임 트래픽을 릴레이하며, 플레이어 상태 추적 및 랭크 시스템을 구현하고 있다. 이는 MITM 접근 방식이 실현 가능함을 입증한다.

---

## 2. 필요 도구

### 핵심 도구

| 도구 | 용도 | 설치 |
|------|------|------|
| **mitmproxy** | HTTP/HTTPS 프록시, 트래픽 캡처 | `pip install mitmproxy` |
| **Wireshark** | 네트워크 패킷 분석 (TCP/UDP) | https://www.wireshark.org/ |
| **Frida** | 동적 계측, SSL 핀닝 우회 | `pip install frida-tools` |
| **adb** | Android Debug Bridge | Android SDK Platform Tools |
| **Python 3.x** | 스크립트 실행 | https://python.org/ |

### mitmproxy

무료 오픈소스 HTTP/HTTPS 프록시 도구. 웹 트래픽을 인터셉트하고 분석할 수 있다.

```bash
# 설치
pip install mitmproxy

# 주요 명령어
mitmproxy          # 터미널 UI
mitmweb            # 웹 UI (http://localhost:8081)
mitmdump           # 스크립트 가능한 덤프 모드
```

주요 기능:
- HTTPS 트래픽 복호화 (CA 인증서 설치 필요)
- Python 스크립트로 트래픽 필터링/수정
- 요청/응답 저장 및 재생
- WebSocket 지원

### Wireshark

네트워크 패킷 분석의 표준 도구. TCP/UDP 레벨의 패킷을 캡처하고 분석할 수 있다.

주요 용도:
- 게임 서버 IP/포트 식별
- TCP vs UDP 트래픽 분리
- 바이너리 프로토콜 패킷 구조 분석
- 캡처 필터: `host <게임서버IP>` 또는 `port <게임포트>`

### Frida

동적 계측(Dynamic Instrumentation) 프레임워크. 실행 중인 앱의 함수를 후킹하여 동작을 변경할 수 있다.

```bash
# PC 측 설치
pip install frida-tools

# Android 기기 측 Frida 서버 설치
# 1. 기기 아키텍처 확인
adb shell getprop ro.product.cpu.abi
# 2. 해당 아키텍처의 frida-server 다운로드
# https://github.com/frida/frida/releases
# 3. 기기에 전송 및 실행
adb push frida-server /data/local/tmp/
adb shell chmod 755 /data/local/tmp/frida-server
adb shell /data/local/tmp/frida-server &
```

주요 용도:
- SSL/TLS 핀닝 우회 (HTTPS 트래픽 복호화)
- 함수 후킹 및 인자/반환값 수정
- 런타임 메모리 조사

### Android 기기/에뮬레이터

루팅된 Android 기기 또는 에뮬레이터가 필요하다. 루팅이 필요한 이유는 시스템 CA 인증서 설치와 Frida 서버 실행 때문이다.

| 옵션 | 장점 | 단점 |
|------|------|------|
| **BlueStacks** | 설치 쉬움, 성능 좋음 | 루팅 복잡 |
| **LDPlayer** | 루팅 기본 지원, 가벼움 | 일부 게임 호환 문제 |
| **NoxPlayer** | 루팅 쉬움 | 광고 많음 |
| **실제 기기** | 가장 정확한 테스트 | 루팅 리스크 |
| **Android Studio AVD** | 공식 에뮬레이터 | 성능 낮음, 게임 호환성 |

권장: **LDPlayer** (루팅 기본 지원, VG:CE 실행 확인된 에뮬레이터)

### adb (Android Debug Bridge)

Android 기기와 PC 간 통신을 위한 명령줄 도구.

```bash
# 기기 연결 확인
adb devices

# 에뮬레이터 연결 (LDPlayer 기본 포트)
adb connect localhost:5555

# 앱 설치
adb install vgce.apk

# 프록시 설정
adb shell settings put global http_proxy <PC_IP>:8080

# 프록시 해제
adb shell settings put global http_proxy :0
```

---

## 3. 환경 설정

### Phase 1: 기본 트래픽 캡처

HTTP/HTTPS 트래픽을 mitmproxy로 캡처하는 기본 설정이다.

#### Step 1: mitmproxy 설치

```bash
# Python 가상환경 권장
python -m venv mitm_env
source mitm_env/bin/activate  # Windows: mitm_env\Scripts\activate

# mitmproxy 설치
pip install mitmproxy

# 설치 확인
mitmproxy --version
```

#### Step 2: Android 기기/에뮬레이터 프록시 설정

mitmproxy를 시작하고 기기가 이를 통해 통신하도록 설정한다.

```bash
# PC에서 mitmproxy 시작 (기본 포트 8080)
mitmproxy --listen-host 0.0.0.0 --listen-port 8080

# 또는 웹 UI 사용
mitmweb --listen-host 0.0.0.0 --listen-port 8080
```

Android 기기/에뮬레이터 설정:
1. **Wi-Fi 설정** -> 연결된 네트워크 -> 프록시 -> 수동
2. **프록시 호스트**: PC의 IP 주소 (에뮬레이터는 보통 `10.0.2.2` 또는 `192.168.x.x`)
3. **프록시 포트**: `8080`

또는 adb로 설정:
```bash
# PC IP 확인
ipconfig  # Windows
ifconfig  # Linux/Mac

# 프록시 설정
adb shell settings put global http_proxy <PC_IP>:8080
```

#### Step 3: CA 인증서 설치

HTTPS 트래픽을 복호화하려면 mitmproxy의 CA 인증서를 기기에 설치해야 한다.

1. 기기의 브라우저에서 `http://mitm.it` 접속
2. Android용 인증서 다운로드
3. **설정 -> 보안 -> 인증서 설치 -> CA 인증서** 에서 설치

루팅된 기기에서 시스템 인증서로 설치 (일부 앱은 사용자 인증서를 무시함):
```bash
# mitmproxy CA 인증서 해시 생성
openssl x509 -inform PEM -subject_hash_old \
  -in ~/.mitmproxy/mitmproxy-ca-cert.pem | head -1
# 출력: c8750f0d (예시)

# 시스템 인증서 디렉토리에 복사
adb root
adb remount
adb push ~/.mitmproxy/mitmproxy-ca-cert.pem \
  /system/etc/security/cacerts/c8750f0d.0
adb shell chmod 644 /system/etc/security/cacerts/c8750f0d.0
adb reboot
```

#### Step 4: VG:CE 실행 및 트래픽 관찰

1. VG:CE를 실행한다.
2. mitmproxy/mitmweb에서 트래픽을 관찰한다.
3. 관찰할 포인트:
   - 로그인 시 접속하는 서버 주소
   - API 엔드포인트 패턴
   - 요청/응답 데이터 구조
   - 인증 토큰 형식

```bash
# mitmdump으로 VG:CE 관련 트래픽만 필터링
mitmdump --listen-port 8080 \
  -w vgce_capture.flow \
  --set flow_detail=3
```

**예상 결과:**
- 일부 HTTP/HTTPS 트래픽이 보일 수 있음 (로그인, API 호출)
- 게임 플레이 데이터는 HTTP가 아닌 커스텀 TCP/UDP 프로토콜을 사용할 가능성이 높음
- SSL 핀닝이 적용되어 있으면 HTTPS 트래픽도 보이지 않을 수 있음

---

### Phase 2: SSL 핀닝 우회 (Frida)

VG:CE가 SSL 핀닝(Certificate Pinning)을 사용하는 경우, mitmproxy의 CA 인증서를 거부하여 HTTPS 트래픽을 캡처할 수 없다. Frida를 사용하여 이를 우회한다.

#### Step 1: Frida 서버 설치 (기기)

```bash
# 기기 아키텍처 확인
adb shell getprop ro.product.cpu.abi
# 보통: arm64-v8a (실제 기기), x86_64 (에뮬레이터)

# Frida 서버 다운로드 (버전을 PC의 frida-tools와 맞춰야 함)
# https://github.com/frida/frida/releases
# 예: frida-server-16.x.x-android-arm64.xz

# 압축 해제 후 기기에 전송
adb push frida-server /data/local/tmp/
adb shell chmod 755 /data/local/tmp/frida-server

# Frida 서버 실행 (root 필요)
adb shell su -c "/data/local/tmp/frida-server &"
```

#### Step 2: frida-tools 설치 (PC)

```bash
pip install frida-tools

# 연결 확인
frida-ps -U  # USB 연결된 기기의 프로세스 목록
frida-ps -U | grep -i vain  # VG:CE 프로세스 확인
```

#### Step 3: VG:CE APK 분석

SSL 핀닝 구현 방식을 확인하여 적절한 우회 방법을 선택한다.

```bash
# APK 디컴파일 (jadx 사용)
jadx vgce.apk -d vgce_decompiled

# SSL 관련 코드 검색
grep -r "certificate" vgce_decompiled/ --include="*.java"
grep -r "pinning" vgce_decompiled/ --include="*.java"
grep -r "X509TrustManager" vgce_decompiled/ --include="*.java"
grep -r "SSLContext" vgce_decompiled/ --include="*.java"
grep -r "OkHttp" vgce_decompiled/ --include="*.java"  # OkHttp 핀닝
```

확인할 사항:
- **네이티브 핀닝**: C/C++ 레벨 SSL 구현 (`libssl.so`, `libcrypto.so`)
- **Java 핀닝**: TrustManager, OkHttp CertificatePinner
- **네트워크 라이브러리**: OkHttp, Volley, Retrofit 등

#### Step 4: Universal SSL Bypass 스크립트

범용 SSL 핀닝 우회 스크립트를 Frida로 로드한다.

```bash
# universal_ssl_bypass.js 파일을 사용하여 Frida 실행
# (스크립트는 vg/tools/mitm_capture.py에 내장되어 있음)

# VG:CE 프로세스에 주입
frida -U -f com.superevilmegacorp.game \
  -l universal_ssl_bypass.js \
  --no-pause

# 또는 이미 실행 중인 프로세스에 주입
frida -U com.superevilmegacorp.game \
  -l universal_ssl_bypass.js
```

universal_ssl_bypass.js 핵심 내용:
```javascript
// Java 레벨 SSL 핀닝 우회
Java.perform(function() {
    // TrustManager 우회
    var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
    TrustManagerImpl.verifyChain.implementation = function() {
        return Java.use('java.util.ArrayList').$new();
    };

    // OkHttp CertificatePinner 우회
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List')
            .implementation = function() { return; };
    } catch(e) {}
});
```

#### Step 5: 복호화된 트래픽 캡처

SSL 핀닝 우회 후 mitmproxy에서 복호화된 HTTPS 트래픽을 캡처한다.

```bash
# 1. mitmproxy 시작
mitmweb --listen-port 8080 --set flow_detail=3

# 2. 다른 터미널에서 Frida로 VG:CE 시작
frida -U -f com.superevilmegacorp.game \
  -l universal_ssl_bypass.js --no-pause

# 3. mitmweb UI (http://localhost:8081)에서 트래픽 확인
```

---

### Phase 3: 게임 프로토콜 분석

VG:CE의 실시간 게임 데이터는 HTTP가 아닌 커스텀 프로토콜을 사용할 가능성이 높다. Wireshark로 TCP/UDP 레벨의 분석이 필요하다.

#### TCP vs UDP 트래픽 분리

```
Wireshark 캡처 필터:
  host <게임서버IP>

디스플레이 필터:
  tcp.port == <게임포트>     # TCP 트래픽 (로그인, 매치메이킹)
  udp.port == <게임포트>     # UDP 트래픽 (실시간 게임 데이터)
```

일반적인 게임 네트워크 구조:
```
[로그인/로비]  ---TCP/HTTPS---> [Auth/API 서버]
[매치메이킹]   ---TCP/HTTPS---> [Matchmaking 서버]
[게임 플레이]  ---UDP--------> [Game 서버]
[채팅]        ---TCP/WS------> [Chat 서버]
```

#### 바이너리 프로토콜 구조 파악

Wireshark에서 캡처한 패킷의 페이로드를 분석한다.

1. **패킷 크기 분포 확인**: 작은 패킷(< 100B)은 제어 메시지, 큰 패킷(> 500B)은 상태 업데이트
2. **반복 패턴 검색**: 동일한 바이트 시퀀스가 모든 패킷에 나타나면 헤더
3. **엔디안 확인**: Little-Endian(x86/ARM) vs Big-Endian(네트워크 표준)

#### Protobuf 여부 확인

Google Protocol Buffers를 사용하는지 확인한다. 많은 모바일 게임이 Protobuf를 사용한다.

```bash
# APK에서 .proto 파일 또는 Protobuf 라이브러리 검색
unzip -l vgce.apk | grep -i proto
jadx vgce.apk -d decompiled
grep -r "protobuf\|proto3\|GeneratedMessageV3" decompiled/ --include="*.java"

# Protobuf로 인코딩된 바이너리 특징:
# - 필드 번호 + 와이어 타입으로 시작 (varint)
# - 가변 길이 인코딩 (varint)
# - 중첩 구조

# protoc로 디코딩 시도
cat packet_payload.bin | protoc --decode_raw
```

#### 패킷 패턴 분석

```python
# Wireshark에서 추출한 패킷 데이터를 Python으로 분석
# tshark을 사용한 자동 추출
tshark -r capture.pcap \
  -Y "udp.port == 7000" \
  -T fields -e data.data > packets.txt
```

---

## 4. VGR + MITM 통합 분석

### VGR에서 추출 가능한 데이터 (100% 정확도)

VGR 리플레이 바이너리에서 확실하게 추출할 수 있는 데이터:

| 데이터 | 추출 방법 | 정확도 |
|--------|----------|--------|
| 플레이어 이름 | 플레이어 블록 마커 `DA 03 EE` | 100% |
| 플레이어 UUID | 정규식 패턴 매칭 | 100% |
| 게임 모드 | `GameMode_` 문자열 검색 | 100% |
| 맵 (3v3/5v5) | 게임 모드 기반 추론 | 100% |
| 팀 구성 | 플레이어 블록 +0xD5 | 100% |
| 엔티티 ID | 플레이어 블록 +0xA5 | 100% |
| 경기 길이 | 프레임 파일 카운트 | 100% |
| Weapon 아이템 | FF FF FF FF 패턴 | 100% |

### MITM에서 추출 가능한 데이터 (예상)

네트워크 트래픽에서 추출할 것으로 예상되는 데이터:

| 데이터 | 추출 시점 | 예상 정확도 |
|--------|----------|-----------|
| 영웅 선택 | 매치 로비/로딩 | 높음 |
| K/D/A | 경기 종료 보고 | 높음 |
| 승패 결과 | 경기 종료 보고 | 높음 |
| 아이템 빌드 | 경기 종료 보고 | 중간 |
| 매치 ID | 매치메이킹 완료 시 | 높음 |
| 서버 정보 | 매치 연결 시 | 높음 |

### 두 소스 교차 검증 방법

VGR과 MITM 데이터를 매칭하는 방법:

```
[VGR 리플레이]                    [MITM 캡처]
  |                                 |
  |-- 플레이어 이름 ----매칭키----> 플레이어 이름
  |-- 게임 모드 --------검증-----> 게임 모드
  |-- 타임스탬프 -------근접-----> 캡처 타임스탬프
  |-- 프레임 수 --------검증-----> 경기 시간
  |                                 |
  +--- 통합 데이터 -----------------+
       |-- 플레이어 (VGR)
       |-- 영웅 (MITM)
       |-- KDA (MITM)
       |-- 승패 (MITM)
       |-- 아이템 (VGR Weapon + MITM 나머지)
```

매칭 알고리즘:
1. **플레이어 이름 매칭**: VGR의 플레이어 이름과 MITM 캡처의 플레이어 이름 비교
2. **시간 근접 매칭**: VGR 리플레이 타임스탬프와 MITM 캡처 시간 비교 (+-5분 이내)
3. **게임 모드 검증**: 양쪽 데이터의 게임 모드가 일치하는지 확인
4. **팀 구성 검증**: 같은 팀 구성원이 일치하는지 확인

### 자동화 파이프라인 구성

```
[VG:CE 실행]
    |
    +---> [MITM 프록시] ---> mitm_capture.py ---> capture_YYYYMMDD_HHMMSS.json
    |
    +---> [VGR 리플레이 생성] ---> vgr_parser.py ---> parsed_replay.json
    |
    +---> [통합 스크립트]
              |
              |-- capture_*.json + parsed_*.json
              |-- 플레이어 이름으로 매칭
              |-- 통합 데이터 생성
              |-- 데이터베이스 저장
              v
         [완전한 경기 데이터]
```

---

## 5. VGReborn 분석

### VGReborn 개요

VGReborn(https://vgreborn.com/)은 VG:CE 커뮤니티 서비스로, MITM 기법을 활용하여 게임 데이터를 수집하고 있다. 이 프로젝트의 아키텍처를 이해하면 우리 프로젝트에 적용할 수 있는 인사이트를 얻을 수 있다.

### WireGuard 기반 VPN + MITM 아키텍처

VGReborn은 WireGuard VPN을 사용하여 게임 트래픽을 릴레이한다.

```
[VG:CE 클라이언트]
    |
    | WireGuard VPN 터널
    v
[VGReborn 서버]
    |
    |-- 게임 관련 IP만 릴레이 (선택적 라우팅)
    |-- 나머지 트래픽은 직접 연결
    |
    v
[SEMC/VG:CE 게임 서버]
```

장점:
- VPN이므로 모든 트래픽을 캡처할 수 있음 (HTTP뿐만 아니라 TCP/UDP 포함)
- WireGuard는 가볍고 성능 영향이 적음
- 클라이언트 수정 없이 VPN 연결만으로 동작
- 게임 외 트래픽은 릴레이하지 않아 프라이버시 보호

### 게임 관련 IP만 릴레이

VGReborn은 VG:CE가 접속하는 서버 IP 대역만 VPN을 통해 릴레이한다.

```
게임 서버 IP 대역 (예상):
  - AWS 리전 IP들 (게임 서버 호스팅)
  - SEMC API 서버
  - 매치메이킹 서버

라우팅 규칙:
  - 게임 서버 IP -> VPN 터널 -> VGReborn 서버 -> 게임 서버
  - 기타 IP -> 직접 연결 (VPN 우회)
```

### 플레이어 상태 추적

VGReborn이 네트워크 트래픽에서 감지하는 플레이어 상태:

| 상태 | 감지 방법 (추정) | 용도 |
|------|----------------|------|
| **온라인** | VPN 연결 + 게임 서버 연결 감지 | 온라인 플레이어 목록 |
| **매치 수락** | 매치메이킹 패킷 감지 | 매치 상태 추적 |
| **매치 거절** | 매치메이킹 타임아웃/거절 패킷 | 닷지 추적 |
| **경기 진행중** | 게임 서버 UDP 트래픽 감지 | 실시간 상태 |
| **경기 종료** | 게임 서버 연결 종료 | 전적 기록 |

### 랭크 시스템 구현 방법

VGReborn은 수집된 경기 데이터를 기반으로 자체 랭크 시스템을 운영한다.

추정 구현:
1. **경기 결과 수집**: 네트워크 트래픽에서 승패 감지
2. **ELO/MMR 계산**: 승패 기반 점수 계산
3. **티어 배정**: 점수 범위별 티어 할당
4. **리더보드**: 웹사이트에서 랭킹 표시

### 향후 가능성: 영웅/KDA/경기결과 추출

현재 VGReborn은 주로 플레이어 상태 추적에 집중하고 있지만, 네트워크 트래픽을 더 깊이 분석하면 추가 데이터 추출이 가능할 수 있다.

가능성:
- **영웅 선택**: 매치 로비 패킷에서 영웅 ID 추출
- **KDA**: 경기 종료 보고 패킷에서 킬/데스/어시스트 추출
- **아이템 빌드**: 경기 결과에 포함된 아이템 목록 추출
- **경기 타임라인**: 실시간 UDP 패킷 분석으로 이벤트 타임라인 구성

도전과제:
- 바이너리 프로토콜 구조 해석 필요
- Protobuf 또는 커스텀 직렬화 사용 가능
- 게임 업데이트 시 프로토콜 변경 가능성
- UDP 패킷은 암호화되어 있을 수 있음

---

## 6. PC (Steam) 버전 MITM

### Steam 버전 특성

Vainglory PC (Steam) 버전은 Windows 네이티브 바이너리로, 모바일 버전과 다른 접근 방식이 필요하다.

주요 DLL 파일:
| DLL | 용도 |
|-----|------|
| `fmod.dll` | 오디오 엔진 (FMOD) |
| `glew32.dll` | OpenGL Extension Wrangler |
| `steam_api.dll` | Steam API 연동 (인증, 매치메이킹) |

Steam 버전의 특징:
- Windows x86/x64 바이너리
- Steam 인증을 통한 로그인
- 모바일 버전과 동일한 게임 서버 사용 (크로스 플레이)
- DirectX/OpenGL 렌더링

### Windows에서의 트래픽 캡처 방법

#### 방법 1: Wireshark 직접 캡처

```bash
# Wireshark에서 VG:CE 프로세스의 트래픽만 필터링
# 1. 게임 실행 후 연결되는 서버 IP 확인
# 2. 디스플레이 필터 적용:
#    ip.addr == <게임서버IP>
```

#### 방법 2: mitmproxy + 시스템 프록시

```bash
# Windows 시스템 프록시 설정
# 설정 -> 네트워크 및 인터넷 -> 프록시 -> 수동 프록시 설정
# 주소: 127.0.0.1, 포트: 8080

# mitmproxy 실행
mitmproxy --listen-port 8080
```

주의: 게임이 시스템 프록시 설정을 무시할 수 있다. 이 경우 Proxifier를 사용한다.

### Proxifier 설정

Proxifier는 프로세스별로 프록시를 강제 적용할 수 있는 도구이다.

```
Proxifier 설정 순서:
1. Proxifier 설치 (https://www.proxifier.com/)
2. 프록시 서버 추가: 127.0.0.1:8080 (HTTPS)
3. 프록시 규칙 추가:
   - 애플리케이션: vainglory.exe (또는 게임 실행 파일명)
   - 동작: 프록시 서버 사용
4. mitmproxy 실행 후 게임 시작
```

### DLL 인젝션을 통한 후킹 가능성

Steam 버전에서는 Frida 대신 DLL 인젝션을 통해 네트워크 함수를 후킹할 수 있다.

```
후킹 대상 함수:
  - Winsock2: send(), recv(), sendto(), recvfrom()
  - OpenSSL: SSL_read(), SSL_write()
  - WinHTTP: WinHttpSendRequest(), WinHttpReceiveResponse()
```

DLL 인젝션 방법:
1. **SetWindowsHookEx**: 윈도우 훅을 통한 DLL 로딩
2. **CreateRemoteThread**: 원격 스레드 생성으로 LoadLibrary 호출
3. **Frida (Windows 버전)**: PC에서도 Frida 사용 가능

```python
# Frida를 사용한 Windows 후킹
import frida

session = frida.attach("vainglory.exe")
script = session.create_script("""
    // Winsock send() 후킹
    var send = Module.findExportByName("ws2_32.dll", "send");
    Interceptor.attach(send, {
        onEnter: function(args) {
            var buf = args[1];
            var len = args[2].toInt32();
            console.log("send() 호출, 크기: " + len);
            console.log(hexdump(buf, { length: Math.min(len, 256) }));
        }
    });

    // Winsock recv() 후킹
    var recv = Module.findExportByName("ws2_32.dll", "recv");
    Interceptor.attach(recv, {
        onLeave: function(retval) {
            var len = retval.toInt32();
            if (len > 0) {
                console.log("recv() 반환, 크기: " + len);
            }
        }
    });
""")
script.load()
```

---

## 7. 예상 프로토콜 구조

### 게임 서버 IP/포트 범위

VG:CE는 AWS 인프라를 사용하는 것으로 추정된다. 게임 서버 IP는 리전에 따라 다르다.

```
예상 서버 구조:
  [Auth 서버]       TCP 443 (HTTPS)    - 로그인/인증
  [API 서버]        TCP 443 (HTTPS)    - 프로필, 상점, 친구
  [매치메이킹 서버]   TCP/TLS           - 매치 검색/수락
  [게임 서버]        UDP 7000-8000 (?)  - 실시간 게임 플레이
  [채팅 서버]        TCP (WebSocket?)   - 텍스트 채팅
```

서버 IP 대역 식별 방법:
```bash
# 1. 게임 실행 전후 연결 비교
netstat -an > before.txt
# 게임 실행
netstat -an > after.txt
diff before.txt after.txt

# 2. Wireshark에서 게임 프로세스 트래픽 관찰
# 3. DNS 쿼리 모니터링
tshark -i eth0 -f "port 53" -Y "dns.qr == 0"
```

### TCP: 로그인, 매치메이킹, 채팅

TCP 기반 통신은 신뢰성이 중요한 데이터에 사용된다.

```
[로그인 시퀀스 (예상)]

Client -> Server:  AUTH_REQUEST
  {
    device_id: "...",
    platform: "android|steam",
    version: "4.x.x",
    token: "..."
  }

Server -> Client:  AUTH_RESPONSE
  {
    session_id: "...",
    player_id: "...",
    player_name: "...",
    region: "..."
  }

[매치메이킹 시퀀스 (예상)]

Client -> Server:  QUEUE_REQUEST
  {
    mode: "ranked_3v3",
    region: "SEA"
  }

Server -> Client:  MATCH_FOUND
  {
    match_id: "...",
    players: [...],
    game_server_ip: "...",
    game_server_port: 7001
  }

Client -> Server:  MATCH_ACCEPT

Server -> Client:  HERO_SELECT_START
  {
    ban_phase: true,
    team: "left|right",
    pick_order: [...]
  }

Client -> Server:  HERO_SELECT
  {
    hero_id: 10,  // Ringo
    skin_id: 3
  }

Server -> Client:  MATCH_START
  {
    all_heroes: [
      { player_id: "...", hero_id: 10, skin_id: 3 },
      ...
    ],
    game_server: { ip: "...", port: 7001 }
  }
```

### UDP: 실시간 게임 데이터

UDP는 실시간 게임 플레이 데이터에 사용된다. 패킷 손실을 허용하되 지연(latency)을 최소화해야 하기 때문이다.

```
[실시간 게임 패킷 (예상)]

-- 위치 업데이트 (Client -> Server, 초당 10-30회) --
  entity_id: uint16
  x: float32
  y: float32
  timestamp: uint32

-- 스킬 사용 (Client -> Server) --
  entity_id: uint16
  skill_id: uint8
  target_x: float32
  target_y: float32
  target_entity: uint16 (선택)

-- 데미지 (Server -> Client) --
  source_entity: uint16
  target_entity: uint16
  damage_amount: float32
  damage_type: uint8 (물리/마법/순수)
  is_critical: bool

-- 사망 (Server -> Client) --
  victim_entity: uint16
  killer_entity: uint16
  assist_entities: [uint16, ...]
  respawn_time: float32

-- 아이템 구매 (Client -> Server) --
  entity_id: uint16
  item_id: uint16
  slot: uint8
```

### 예상 패킷 구조

```
게임 패킷 기본 구조 (예상):

+--------+--------+--------+------------------+
| Header | MsgType| Length | Payload          |
| 4 byte | 2 byte | 2 byte| variable         |
+--------+--------+--------+------------------+

Header:  패킷 식별자/매직 넘버 또는 시퀀스 번호
MsgType: 메시지 타입 (로그인=0x01, 이동=0x10, 스킬=0x20, ...)
Length:  Payload 길이 (바이트)
Payload: 메시지 데이터 (Protobuf 또는 커스텀 바이너리)
```

VGR 리플레이의 이벤트 구조와 비교:
```
VGR 이벤트:  [EntityID(LE, 2B)] [00 00] [ActionType] [Parameters...]
네트워크:    [Header] [MsgType] [Length] [Payload]

유사점: 엔티티 ID, 액션 타입 등의 개념이 동일
차이점: 네트워크 패킷은 헤더/길이 필드가 추가됨
```

### Protobuf 또는 커스텀 바이너리

VG:CE가 사용하는 직렬화 방식은 다음 중 하나일 가능성이 높다:

1. **Google Protocol Buffers (Protobuf)**
   - 장점: 효율적, 스키마 기반, 하위 호환성
   - 감지: APK 내 `.proto` 파일 또는 Protobuf 라이브러리 존재
   - 특징: varint 인코딩, 필드 번호 + 와이어 타입

2. **커스텀 바이너리 직렬화**
   - 장점: 최적화 가능, 외부 의존성 없음
   - 감지: Protobuf 특징 없음, 고정 크기 필드
   - 특징: 고정/가변 길이 혼합, 게임 특화 구조

3. **FlatBuffers**
   - 장점: 제로 카피 액세스, 게임에 적합
   - 감지: APK 내 FlatBuffers 라이브러리
   - 특징: 오프셋 테이블, vtable 기반

---

## 8. 법적/윤리적 고려사항

### 교육/연구 목적의 리버스 엔지니어링

본 프로젝트는 교육 및 연구 목적의 리버스 엔지니어링으로, 다음과 같은 법적 근거를 가진다:

- **호환성 확보**: 종료된 서비스의 데이터를 보존하기 위한 역공학
- **연구 목적**: 게임 프로토콜 및 데이터 구조에 대한 학술적 분석
- **비영리**: 상업적 이용이 아닌 커뮤니티 보존 활동

참고: 각 국가의 법률에 따라 리버스 엔지니어링의 합법 범위가 다르다. 한국의 경우 저작권법 제101조의4에서 호환성 확보를 위한 역공학을 허용하고 있다.

### 게임 종료 후 보존/아카이빙 목적

Vainglory는 Super Evil Megacorp가 공식적으로 서비스를 종료한 게임이다. Community Edition(VG:CE)은 커뮤니티에 의해 유지되고 있다.

보존 활동의 윤리적 근거:
- **문화 보존**: 게임은 디지털 문화 자산이며, 종료 후에도 보존 가치가 있다
- **커뮤니티 기여**: 아직 게임을 즐기는 플레이어들에게 전적/랭킹 서비스 제공
- **역사적 기록**: 게임의 메타, 밸런스, 전략의 역사적 기록 보존
- **기술적 교육**: 게임 네트워크 프로토콜의 교육 자료

### 하지 말아야 할 것

다음 행위는 윤리적으로 허용되지 않으며, 법적 문제를 일으킬 수 있다:

| 금지 행위 | 이유 |
|----------|------|
| **치트/핵 개발** | 다른 플레이어의 게임 경험 파괴 |
| **착취/어뷰징** | 게임 경제 파괴, 불공정 이득 |
| **타인 개인정보 수집** | 개인정보 보호법 위반 |
| **계정 탈취** | 컴퓨터 사기 및 불법 접근 |
| **상업적 이용** | 수집한 데이터의 무단 상업화 |
| **서버 공격** | 서비스 방해, 컴퓨터 범죄 |
| **데이터 유출** | 민감한 통신 내용 공개 |

### VG:CE 커뮤니티 존중

- VG:CE 커뮤니티의 규칙과 가이드라인을 준수한다
- 수집한 데이터는 공공 통계 목적으로만 사용한다
- 개별 플레이어의 프라이버시를 존중한다
- 커뮤니티에 기여하는 방향으로 프로젝트를 운영한다
- VGReborn 등 기존 커뮤니티 프로젝트와 협력한다

---

## 9. 다음 단계

### Phase 1: 기본 트래픽 캡처 (현재 단계)

목표: VG:CE의 네트워크 통신 구조를 파악한다.

```
작업 항목:
  [x] MITM 가이드 문서 작성
  [ ] mitmproxy 설치 및 기본 설정
  [ ] Android 에뮬레이터 (LDPlayer) 프록시 설정
  [ ] CA 인증서 설치
  [ ] VG:CE 실행 및 HTTP/HTTPS 트래픽 관찰
  [ ] Wireshark로 TCP/UDP 트래픽 캡처
  [ ] 게임 서버 IP/포트 식별
  [ ] 기본 패킷 구조 분석
```

예상 소요: 1-2일

### Phase 2: 프로토콜 디코딩

목표: 게임 프로토콜을 해석하여 의미 있는 데이터를 추출한다.

```
작업 항목:
  [ ] SSL 핀닝 우회 (Frida)
  [ ] HTTPS 트래픽 복호화 및 API 엔드포인트 분석
  [ ] 매치메이킹 프로토콜 분석
  [ ] 영웅 선택 패킷 식별
  [ ] 경기 결과 보고 패킷 식별
  [ ] Protobuf/바이너리 구조 디코딩
  [ ] 데이터 추출 스크립트 작성
```

예상 소요: 1-2주

### Phase 3: VGR + MITM 통합 서버 구축

목표: VGR 리플레이와 MITM 데이터를 통합하는 서버를 구축한다.

```
작업 항목:
  [ ] VGR 데이터 + MITM 데이터 매칭 알고리즘
  [ ] 통합 데이터베이스 스키마 설계
  [ ] 자동 캡처 + 파싱 파이프라인
  [ ] REST API 구현
  [ ] 데이터 정합성 검증 시스템
```

예상 소요: 2-4주

### Phase 4: 자동 전적 수집 시스템

목표: 완전 자동화된 전적 수집 및 조회 시스템을 구축한다.

```
작업 항목:
  [ ] WireGuard VPN 서버 구축 (VGReborn 참고)
  [ ] 자동 트래픽 캡처 데몬
  [ ] 실시간 경기 데이터 파싱
  [ ] 플레이어별 전적 집계
  [ ] 영웅별 승률/픽률 통계
  [ ] ELO/MMR 기반 랭크 시스템
  [ ] 웹 인터페이스 (전적 검색, 리더보드)
  [ ] 인게임 오버레이 (선택)
```

예상 소요: 1-2개월

### 최종 목표 아키텍처

```
[VG:CE 클라이언트들]
    |
    | WireGuard VPN
    v
[VG Stats 서버]
    |
    +-- [MITM 프록시] --> 네트워크 데이터 캡처
    |       |
    |       +-- 영웅 선택 추출
    |       +-- KDA 추출
    |       +-- 승패 추출
    |
    +-- [VGR 리플레이 수신] --> 리플레이 바이너리 분석
    |       |
    |       +-- 플레이어/팀 추출
    |       +-- 아이템 추출
    |       +-- 이벤트 분석
    |
    +-- [데이터 통합 엔진]
    |       |
    |       +-- VGR + MITM 교차 검증
    |       +-- 데이터베이스 저장
    |
    +-- [웹 API / UI]
            |
            +-- 전적 검색
            +-- 플레이어 프로필
            +-- 영웅 통계
            +-- 리더보드
            +-- 메타 분석
```

---

## 참고 자료

- [mitmproxy 공식 문서](https://docs.mitmproxy.org/)
- [Frida 공식 문서](https://frida.re/docs/)
- [Wireshark 사용자 가이드](https://www.wireshark.org/docs/)
- [VGReborn](https://vgreborn.com/)
- [WireGuard](https://www.wireguard.com/)
- [프로젝트 개요](./PROJECT_OVERVIEW.md)
- [역공학 노트](./REVERSE_ENGINEERING_NOTES.md)
