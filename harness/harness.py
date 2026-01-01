import os
import sys
import shutil
import subprocess
import signal

# [Harness Configuration for WSL]
WINDOWS_BASE = r"c:\Users\ypete\Downloads\firmware_extract_tplink"
WSL_BASE = "/mnt/c/Users/ypete/Downloads/firmware_extract_tplink"

PROJECT_DIR = "tplink_fuzzer"
ROOTFS_DIR = "rootfs"
TOOLS_DIR = "tools"

def get_base_path():
    if os.path.exists("/mnt/c"):
        return WSL_BASE
    return os.getcwd()

BASE_PATH = get_base_path()
PROJECT_PATH = os.path.join(BASE_PATH, PROJECT_DIR)
ROOTFS_PATH = os.path.join(PROJECT_PATH, ROOTFS_DIR)
TOOLS_PATH = os.path.join(PROJECT_PATH, TOOLS_DIR)

QEMU_BINARY = os.path.join(TOOLS_PATH, "qemu-mipsel-static")
NVRAM_LIB_SRC = os.path.join(TOOLS_PATH, "libnvram.so")
NVRAM_LIB_DEST_DIR = os.path.join(ROOTFS_PATH, "lib")
NVRAM_LIB_DEST = os.path.join(NVRAM_LIB_DEST_DIR, "libmocknvram.so")

TARGET_BINARY_REL_PATH = "usr/sbin/uhttpd" 
TARGET_FULL_PATH = os.path.join(ROOTFS_PATH, TARGET_BINARY_REL_PATH)

def run_fuzzer():
    if not os.path.exists(NVRAM_LIB_DEST_DIR):
        os.makedirs(NVRAM_LIB_DEST_DIR)
    
    # print(f"[*] Copying mock lib to jail: {NVRAM_LIB_DEST}")
    shutil.copy(NVRAM_LIB_SRC, NVRAM_LIB_DEST)

    env = os.environ.copy()
    env["QEMU_LD_PREFIX"] = ROOTFS_PATH
    
    # Set LD_PRELOAD
    env["LD_PRELOAD"] = "/lib/libmocknvram.so"
    
    cmd = [
        QEMU_BINARY,
        "-L", ROOTFS_PATH,
        # Pass LD_DEBUG to the guest loader to see what's happening
        "-E", "LD_DEBUG=libs", 
        "-E", "LD_PRELOAD=/lib/libmocknvram.so", 
        TARGET_FULL_PATH, 
        "-f",           
        "-p", "8080",   
        "-h", "/www"
    ]
    
    print(f"[*] LD_DEBUG=libs enabled. Checking why library fails to load...")
    print("-" * 50)
    
    try:
        proc = subprocess.Popen(cmd, env=env)
        proc.wait()
    except KeyboardInterrupt:
        print("\n[!] Stopping fuzzer...")
        proc.send_signal(signal.SIGINT)
        proc.wait()
    except OSError as e:
        print(f"\n[!] Execution failed: {e}")

if __name__ == "__main__":
    run_fuzzer()
