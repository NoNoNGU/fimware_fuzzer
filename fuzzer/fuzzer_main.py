import os
import time
import signal
import sys
import multiprocessing
from executor import Executor
from sender import Sender
from mutator import Mutator

# Settings
HARNESS_SCRIPT = os.path.join(os.path.dirname(__file__), "..", "harness", "harness.py")
CRASH_DIR = "crashes"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_PATH = r"c:\Users\ypete\Downloads\firmware_extract_tplink\AFLplusplus\dictionaries\http.dict"

CRASH_DIR = os.path.join(BASE_DIR, "crashes")

def fuzz_worker(instance_id, total_execs, total_crashes):
    # Set Environment for this worker
    os.environ["INSTANCE_ID"] = str(instance_id)
    target_port = 8080 + instance_id

    # Initialize components
    executor = Executor(HARNESS_SCRIPT)
    sender = Sender("127.0.0.1", target_port)
    mutator = Mutator(dict_path=DICT_PATH)
    
    seeds = mutator.generate_initial_seeds()
    
    # Cleanup previous run (best effort)
    try:
        shutil.rmtree(f"/tmp/tplink_fuzzer_rootfs_{instance_id}")
    except: pass

    # Start Target
    if not executor.start_target():
        print(f"[{instance_id}] Failed to start harness. Exiting worker.")
        return

    # print(f"[{instance_id}] Worker Started on Port {target_port}")
    
    local_execs = 0
    
    try:
        while True:
            seed = seeds[local_execs % len(seeds)]
            payload = mutator.mutate(seed)
            
            sender.send(payload)
            
            # Check Health
            if not executor.check_alive():
                with total_crashes.get_lock():
                    total_crashes.value += 1
                
                print(f"\n[{instance_id}] CRASH! Saving payload...")
                crash_filename = os.path.join(CRASH_DIR, f"crash_{instance_id}_{int(time.time())}.bin")
                try:
                    with open(crash_filename, "wb") as f:
                        f.write(payload)
                except: pass
                
                executor.restart_target()
                time.sleep(2) # Wait for restart
            
            with total_execs.get_lock():
                total_execs.value += 1
            local_execs += 1
            
            # Reduce sleep to maximize throughput, rely on OS scheduling
            # time.sleep(0.001)

    except KeyboardInterrupt:
        pass
    finally:
        executor.cleanup()

def start_fuzzing():
    if not os.path.exists(CRASH_DIR):
        os.makedirs(CRASH_DIR)
    
    # Global Stats
    total_execs = multiprocessing.Value('i', 0)
    total_crashes = multiprocessing.Value('i', 0)
    
    print(f"[*] Starting {NUM_WORKERS} Parallel Fuzzers...")
    print(f"[*] Dictionary: {DICT_PATH}")
    
    processes = []
    for i in range(NUM_WORKERS):
        p = multiprocessing.Process(target=fuzz_worker, args=(i, total_execs, total_crashes))
        p.start()
        processes.append(p)
    
    print("[*] Fuzzing Cluster Running! Press Ctrl+C to stop.")
    start_time = time.time()

    try:
        while True:
            time.sleep(1)
            elapsed = time.time() - start_time
            execs = total_execs.value
            crashes = total_crashes.value
            speed = execs / elapsed if elapsed > 0 else 0
            
            sys.stdout.write(f"\r[*] Total Execs: {execs} | Crashes: {crashes} | Cluster Speed: {speed:.2f} exec/s")
            sys.stdout.flush()
            
            # Check if all workers died
            if not any(p.is_alive() for p in processes):
                print("\n[!] All workers died. Exiting.")
                break

    except KeyboardInterrupt:
        print("\n[*] Stopping Cluster...")
        for p in processes:
            p.terminate()
        for p in processes:
            p.join()

if __name__ == "__main__":
    start_fuzzing()
