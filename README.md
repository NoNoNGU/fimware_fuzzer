# TP-Link 펌웨어 퍼저 (Custom Implementation)

이 프로젝트는 MIPS 아키텍처 기반의 TP-Link 펌웨어, 특히 `uhttpd` 웹 서버를 대상으로 취약점을 탐지하기 위해 개발된 고성능 커스텀 그레이박스(Grey-box) 퍼저입니다.

## 🚀 주요 기능 (Key Features)

*   **병렬 퍼징 클러스터 (Parallel Fuzzing Cluster)**: Python `multiprocessing`을 활용하여 여러 개의 독립된 퍼징 워커(Worker)를 동시에 실행합니다. 각 워커는 격리된 QEMU 환경에서 동작하며, 코어 수에 따라 성능이 선형적으로 증가합니다 (현재 4코어 기준 약 50 execs/s).
*   **스마트 변이 엔진 (Smart Mutation Engine)**:
    *   **AFL++ Dictionary 연동**: `http.dict`와 같은 표준 HTTP 사전을 로드하여 유효한 키워드(`POST`, `Content-Length` 등)를 입력값에 주입합니다.
    *   **구조 인식(Structure-Awareness)**: 매직 넘버, 포맷 스트링, 버퍼 오버플로우 패턴 등을 무작위가 아닌 전략적으로 삽입하여 파서의 취약점을 겨냥합니다.
*   **강력한 에뮬레이션 하네스 (Robust Emulation Harness)**:
    *   **바이너리 패치 (Binary Patching)**: 메모리 상에서 `libubus.so`와 `uhttpd` 바이너리를 직접 수정하여, 하드코딩된 소켓 경로(`var/run/ubus.sock`)를 `/tmp/ubus_N.sock`으로 변경합니다. 이를 통해 충돌 없는 멀티 인스턴스 실행이 가능합니다.
    *   **파일시스템 격리**: 각 워커마다 임시 루트 파일시스템(`/tmp/tplink_fuzzer_rootfs_N`)을 생성하여 파일 충돌을 방지합니다.
    *   **서비스 오케스트레이션**: 실제 `ubusd` 데몬을 `uhttpd`와 함께 실행하여 실제와 유사한 런타임 환경을 모사합니다.

## 🏗 아키텍처 (Architecture)

퍼저는 다음과 같은 모듈형 구조로 설계되었습니다:

1.  **Harness (`harness/harness.py`)**:
    *   가짜 루트 파일시스템을 준비합니다 (`cp -r`).
    *   소켓 경로 사용을 위해 바이너리를 패치합니다.
    *   `ubusd`를 실행하고 소켓 생성을 대기합니다.
    *   `qemu-mipsel-static`으로 `uhttpd`를 실행합니다.
2.  **Executor (`fuzzer/executor.py`)**:
    *   Harness의 수명 주기(시작, 중지, 재시작)를 관리합니다.
    *   프로세스 상태를 모니터링하여 크래시(Segfault 등)를 감지합니다.
3.  **Mutator (`fuzzer/mutator.py`)**:
    *   초기 시드(HTTP 요청)를 받아 변이시킵니다.
    *   비트 플립, 바이트 플립, 매직 넘버 삽입, 딕셔너리 삽입 등의 전략을 사용합니다.
4.  **Sender (`fuzzer/sender.py`)**:
    *   Raw TCP 소켓을 통해 변이된 페이로드를 `localhost:8080+N`으로 전송합니다.
5.  **Orchestrator (`fuzzer/fuzzer_main.py`)**:
    *   메인 진입점입니다. 병렬 워커를 생성하고 통계를 수집하여 보여줍니다.

## 📂 디렉토리 구조 (Directory Structure)

```
tplink_fuzzer/
├── fuzzer/
│   ├── fuzzer_main.py   # 메인 실행 파일 (이걸 실행하세요!)
│   ├── executor.py      # 프로세스 관리자
│   ├── mutator.py       # 변이(Mutation) 로직
│   └── sender.py        # 네트워크 전송 클라이언트
├── harness/
│   └── harness.py       # QEMU 환경 실행 래퍼
├── rootfs/              # 추출된 펌웨어 루트 파일시스템
├── tools/
│   ├── qemu-mipsel-static
│   └── mock_nvram.c     # (선택사항) Mock 라이브러리 소스
└── crashes/             # 발견된 크래시 덤프 (*.bin)
```

## ⚡ 실행 방법 (How to Run)

1.  **필수 조건**:
    *   Windows Subsystem for Linux (WSL).
    *   Python 3.
    *   `qemu-mipsel-static` 설치 또는 `tools/` 경로에 위치.

2.  **퍼징 시작**:
    ```bash
    wsl python3 tplink_fuzzer/fuzzer/fuzzer_main.py
    ```

3.  **모니터링**:
    *   터미널에 표시되는 `Cluster Speed`와 `Crashes` 숫자를 확인하세요.
    *   크래시가 발견되면 `crashes/` 폴더를 확인하세요.

## 🔍 크래시 분석 (Crash Analysis)
크래시가 감지되면:
1.  페이로드가 `crashes/crash_<ID>_<TIMESTAMP>.bin` 파일로 저장됩니다.
2.  내용 확인:
    ```bash
    hexdump -C crashes/crash_0_...bin
    ```
3.  `netcat`이나 Python 스크립트를 사용하여 수동으로 재현(Replay)할 수 있습니다.
