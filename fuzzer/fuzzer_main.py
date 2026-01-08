import os
import time
import signal
import sys
import shutil
import hashlib
import multiprocessing
import subprocess
from executor import Executor
from sender import Sender
from mutator import Mutator
from coverage import CoverageManager
from dashboard import FuzzerDashboard
from rich.live import Live

# Settings
NUM_WORKERS = 4  # 병렬 워커 수 (CPU 코어 수에 맞게 조정)
HARNESS_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "harness", "harness.py")
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRASH_DIR_VERIFIED = os.path.join(BASE_DIR, "crashes", "verified")
CRASH_DIR_IGNORED = os.path.join(BASE_DIR, "crashes", "ignored")
HTTP_ERROR_DIR = os.path.join(BASE_DIR, "crashes", "http_errors") # 500 에러 저장소

for d in [CRASH_DIR_VERIFIED, CRASH_DIR_IGNORED, HTTP_ERROR_DIR]:
    if not os.path.exists(d):
        os.makedirs(d)

# 딕셔너리 경로 (없으면 기본 딕셔너리 사용)
DICT_PATH = os.path.join(BASE_DIR, "dictionaries", "http.dict")
if not os.path.exists(DICT_PATH):
    DICT_PATH = None

# 커버리지 가이드 설정
ENABLE_COVERAGE = True  # 커버리지 추적 활성화
CORPUS_DIR = os.path.join(BASE_DIR, "corpus")
if not os.path.exists(CORPUS_DIR):
    os.makedirs(CORPUS_DIR)

# 전역 크래시 시그니처 집합 (중복 제거용) - Manager로 공유
manager = multiprocessing.Manager()
seen_signatures = manager.dict()
seen_http_errors = manager.dict() # HTTP 에러 중복 제거용


def force_cleanup(instance_id):
    """강제 클린업 - 포트, 소켓, 프로세스 모두 정리"""
    port = 8080 + instance_id
    socket_path = f"/tmp/ub{instance_id}.sock"
    
    # 포트 점유 프로세스 강제 종료
    subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], 
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    
    # 소켓 점유 프로세스 종료
    if os.path.exists(socket_path):
        subprocess.run(["fuser", "-k", socket_path], 
                       stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        try:
            os.remove(socket_path)
        except:
            pass
    
    # rootfs 정리는 하지 않음 (시간이 오래 걸림)
    time.sleep(0.3)


def generate_crash_signature(exit_code, payload):
    """
    크래시 시그니처 생성
    """
    sig_name = "UNKNOWN"
    if exit_code is not None and exit_code < 0:
        try:
            sig_name = signal.Signals(-exit_code).name
        except:
            sig_name = f"SIG{-exit_code}"
    
    # 페이로드의 처음 100바이트만 해시 (구조적 유사성)
    payload_hash = hashlib.md5(payload[:100]).hexdigest()[:8]
    
    signature = f"{sig_name}_{payload_hash}"
    return signature, sig_name


def save_http_error(payload, status, instance_id, seen_errors, log_queue):
    """HTTP 500 등 서버 에러 저장"""
    def log(msg):
        if log_queue: log_queue.put(msg)
        else: print(msg)

    payload_hash = hashlib.md5(payload).hexdigest()[:8]
    sig = f"{status}_{payload_hash}"
    
    if sig in seen_errors:
        return
    
    seen_errors[sig] = True
    
    timestamp = int(time.time())
    filename = f"error_{status}_{payload_hash}_{timestamp}.bin"
    save_path = os.path.join(HTTP_ERROR_DIR, filename)
    
    try:
        with open(save_path, "wb") as f:
            f.write(payload)
        log(f"[{instance_id}] 💾 Saved HTTP {status} Error: {filename}")
    except Exception as e:
        log(f"[{instance_id}] Failed to save error: {e}")


def validate_crash(executor, sender, payload, instance_id, seen_sigs, log_queue=None, max_retries=3):
    """
    크래시가 의심될 때, 깨끗한 상태에서 다시 한 번 실행하여 검증합니다.
    """
    def log(msg):
        if log_queue:
            log_queue.put(msg)
        else:
            print(msg)

    log(f"[{instance_id}] 🔍 Validating potential crash...")
    
    for attempt in range(max_retries):
        # 강제 클린업
        force_cleanup(instance_id)
        
        # 타겟 재시작
        if not executor.restart_target():
            log(f"[{instance_id}] ⏳ Restart attempt {attempt+1}/{max_retries} failed, retrying...")
            time.sleep(1)
            continue
        
        # 안정화 대기
        time.sleep(0.5)
        
        # 페이로드 재전송
        sender.send(payload) # 여기서는 status code 무시
        
        # 상태 확인 (약간의 지연 후)
        time.sleep(0.3)
        is_alive, exit_code = executor.check_alive()
        
        if not is_alive:
            log(f"[{instance_id}] ✅ Crash Confirmed! Exit Code: {exit_code}")
            return True, exit_code
        else:
            log(f"[{instance_id}] ⚠️ False Positive (Target stayed alive)")
            return False, None
    
    log(f"[{instance_id}] ❌ All restart attempts failed")
    return False, None


def save_crash_if_unique(payload, exit_code, instance_id, seen_sigs, log_queue):
    """
    시그니처 기반 중복 확인 후 저장
    """
    def log(msg):
        if log_queue: log_queue.put(msg)
        else: print(msg)

    signature, sig_name = generate_crash_signature(exit_code, payload)
    
    # 중복 확인
    if signature in seen_sigs:
        log(f"[{instance_id}] 🔄 Duplicate crash (sig={signature}), skipping")
        return False
    
    # 새로운 크래시 - 저장
    seen_sigs[signature] = True
    
    timestamp = int(time.time())
    filename = f"crash_{sig_name}_{signature}_{timestamp}.bin"
    
    # 시그널별 서브디렉토리
    sig_dir = os.path.join(CRASH_DIR_VERIFIED, sig_name)
    if not os.path.exists(sig_dir):
        os.makedirs(sig_dir)
    
    save_path = os.path.join(sig_dir, filename)
    
    try:
        with open(save_path, "wb") as f:
            f.write(payload)
        log(f"[{instance_id}] 💾 NEW unique crash saved: {sig_name}/{filename}")
        return True
    except Exception as e:
        log(f"[{instance_id}] Failed to save crash: {e}")
        return False


def fuzz_worker(instance_id, total_execs, total_crashes, total_unique, total_edges, seen_sigs, seen_http_errors, log_queue):
    """퍼징 워커 프로세스"""
    os.environ["INSTANCE_ID"] = str(instance_id)
    
    def log(msg):
        if log_queue: log_queue.put(msg)
        else: print(msg)

    # 커버리지 트레이스 활성화
    if ENABLE_COVERAGE:
        os.environ["ENABLE_COVERAGE_TRACE"] = "1"
    
    target_port = 8080 + instance_id
    trace_log_path = f"/tmp/qemu_trace_{instance_id}.log"

    # Initialize components
    executor = Executor(HARNESS_SCRIPT)
    sender = Sender("127.0.0.1", target_port)
    mutator = Mutator(dict_path=DICT_PATH)
    cov_manager = CoverageManager(corpus_dir=CORPUS_DIR) if ENABLE_COVERAGE else None
    
    # 시드 설정: 코퍼스 파일 로드 포함
    seeds = mutator.generate_initial_seeds()
    if os.path.exists(CORPUS_DIR):
        for fname in os.listdir(CORPUS_DIR):
            fpath = os.path.join(CORPUS_DIR, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, 'rb') as f:
                        seeds.append(f.read())
                except:
                    pass
    
    # Cleanup previous run
    force_cleanup(instance_id)

    # Start Target
    if not executor.start_target():
        log(f"[{instance_id}] Failed to start harness. Exiting worker.")
        return

    local_execs = 0
    http_errors = 0 # 연속 에러 카운트
    
    try:
        while True:
            seed = seeds[local_execs % len(seeds)]
            payload = mutator.mutate(seed)
            
            # Send Payload & Get Status
            sent, status = sender.send(payload)
            
            # HTTP Status Logging & Saving
            if status >= 500:
                log(f"[{instance_id}] 🔥 HTTP {status} Error detected!")
                save_http_error(payload, status, instance_id, seen_http_errors, log_queue)
            
            # 커버리지 체크 (타겟이 살아있을 때만)
            if ENABLE_COVERAGE and cov_manager:
                is_new, new_count, new_pcs = cov_manager.check_new_coverage(trace_log_path)
                if is_new:
                    # 새로운 커버리지 발견! 시드로 저장
                    saved_path = cov_manager.save_interesting_input(payload, new_pcs)
                    if saved_path:
                        seeds.append(payload)  # 다음 변이에 사용
                        log(f"[{instance_id}] 🌟 NEW coverage! +{new_count} edges (Last HTTP: {status})")
                        with total_edges.get_lock():
                            total_edges.value = cov_manager.total_edges
                # 로그 초기화
                cov_manager.clear_log(trace_log_path)
            
            # Check Health
            is_alive, exit_code = executor.check_alive()
            
            if not is_alive:
                # 크래시 의심 - 검증 시도
                confirmed, valid_exit_code = validate_crash(
                    executor, sender, payload, instance_id, seen_sigs, log_queue
                )
                
                if confirmed:
                    # 500 에러와 크래시는 별개 취급하되, 크래시가 우선
                    with total_crashes.get_lock():
                        total_crashes.value += 1
                    
                    if save_crash_if_unique(payload, valid_exit_code, instance_id, seen_sigs, log_queue):
                        with total_unique.get_lock():
                            total_unique.value += 1
                
                # 복구: 타겟 재시작
                force_cleanup(instance_id)
                executor.restart_target()
                time.sleep(0.5)
            
            with total_execs.get_lock():
                total_execs.value += 1
            local_execs += 1
            
            # 속도 조절
            time.sleep(0.01)

    except KeyboardInterrupt:
        pass
    finally:
        executor.cleanup()


def start_fuzzing():
    # Global Cleanup
    print("[*] Cleaning up previous processes...")
    subprocess.run(["pkill", "-9", "-f", "qemu-mipsel"], stderr=subprocess.DEVNULL)
    time.sleep(1)

    for d in [CRASH_DIR_VERIFIED, CRASH_DIR_IGNORED, HTTP_ERROR_DIR]:
        if not os.path.exists(d):
            os.makedirs(d)
    
    # Global Stats
    total_execs = multiprocessing.Value('i', 0)
    total_crashes = multiprocessing.Value('i', 0)
    total_unique = multiprocessing.Value('i', 0)
    total_edges = multiprocessing.Value('i', 0)
    
    # Dashboard shared stats
    stats_dict = {'execs': 0, 'crashes': 0, 'unique': 0, 'edges': 0, 'start_time': time.time()}
    log_queue = multiprocessing.Queue()
    
    print(f"[*] Starting {NUM_WORKERS} Parallel Fuzzers...")
    print(f"[*] Dictionary: {DICT_PATH}")
    print(f"[*] Corpus: {CORPUS_DIR}")
    print(f"[*] Coverage: {'Enabled' if ENABLE_COVERAGE else 'Disabled'}")
    
    processes = []
    for i in range(NUM_WORKERS):
        p = multiprocessing.Process(
            target=fuzz_worker, 
            args=(i, total_execs, total_crashes, total_unique, total_edges, seen_signatures, seen_http_errors, log_queue)
        )
        p.start()
        processes.append(p)
        time.sleep(2)  # 워커 간 시작 딜레이
    
    # Dashboard 시작
    dashboard = FuzzerDashboard(NUM_WORKERS, stats_dict, log_queue)
    
    with Live(dashboard.make_layout(), refresh_per_second=4, screen=False) as live:
        try:
            while True:
                time.sleep(0.5)
                
                # Update Stats
                stats_dict['execs'] = total_execs.value
                stats_dict['crashes'] = total_crashes.value
                stats_dict['unique'] = total_unique.value
                stats_dict['edges'] = total_edges.value
                
                dashboard.stats = stats_dict # 갱신
                
                # Update UI
                live.update(dashboard.update())
                
                # Check dead workers
                if not any(p.is_alive() for p in processes):
                    log_queue.put("[!] All workers died. Exiting.")
                    break

        except KeyboardInterrupt:
            log_queue.put("[*] Stopping Cluster...")
            
        finally:
            for p in processes:
                p.terminate()
            for p in processes:
                p.join()
            
            # 최종 통계
            print(f"\n[*] Final Stats: {total_execs.value} execs, "
                  f"{total_crashes.value} crashes, {total_unique.value} unique")


if __name__ == "__main__":
    start_fuzzing()
