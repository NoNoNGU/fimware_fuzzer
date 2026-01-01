import subprocess
import time
import os
import sys

# Adjust path to find harness
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "harness"))

class Executor:
    def __init__(self, harness_script):
        self.harness_script = harness_script
        self.process = None
        self.pid = os.getpid()
        self.log_path = f"fuzzer_harness_{self.pid}.log"
        self.log_file = open(self.log_path, "w")

    def start_target(self):
        """Starts the harness (which starts ubusd and uhttpd)."""
        if self.process:
            self.stop_target()

        # print(f"[Executor] Starting Target Harness (Log: {self.log_path})...")
        cmd = ["python3", "-u", self.harness_script]
        
        try:
            self.process = subprocess.Popen(
                cmd, 
                stdout=self.log_file, 
                stderr=subprocess.STDOUT
            )
            time.sleep(2) 
            if self.process.poll() is not None:
                # print("[Executor] Error: Target failed to start! Check log.")
                return False
            return True
        except Exception as e:
            # print(f"[Executor] Failed to launch harness: {e}")
            return False

    def check_alive(self):
        if self.process is None:
            return False
        
        ret = self.process.poll()
        if ret is not None:
            # print(f"[Executor] Target exited with code {ret}!")
            return False
        return True

    def stop_target(self):
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def restart_target(self):
        self.stop_target()
        return self.start_target()

    def cleanup(self):
        self.stop_target()
        if self.log_file:
            self.log_file.close()
