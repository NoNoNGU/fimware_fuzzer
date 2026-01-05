import os
import sys
import time
import shutil
import subprocess
import signal

# [Harness Configuration]
# 동적 경로 계산 - 현재 스크립트 위치 기준
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)  # harness의 상위 = 프로젝트 루트
WORK_BASE = "/tmp"

# Instance Configuration
INSTANCE_ID = int(os.environ.get("INSTANCE_ID", 0))
WORK_ROOTFS_NAME = f"tplink_fuzzer_rootfs_{INSTANCE_ID}"
HTTP_PORT = str(8080 + INSTANCE_ID)
SOCKET_NAME = f"ub{INSTANCE_ID}.sock"  # 짧은 이름: /tmp/ub0.sock (12 bytes)

def get_wsl_path(win_path):
    """Windows 경로를 WSL 경로로 변환"""
    if os.path.exists("/mnt/c"):
        # WSL 환경
        return win_path.replace("\\", "/").replace("C:", "/mnt/c").replace("c:", "/mnt/c")
    return win_path

def get_base_path():
    """프로젝트 루트 경로 반환 (WSL 호환)"""
    if os.path.exists("/mnt/c"):
        # WSL 환경에서 Windows 경로를 변환
        return get_wsl_path(PROJECT_DIR)
    return PROJECT_DIR

SRC_PROJECT_PATH = get_base_path()
SRC_ROOTFS_PATH = os.path.join(SRC_PROJECT_PATH, "squashfs-root")  # 펌웨어 루트 파일시스템
SRC_TOOLS_PATH = os.path.join(SRC_PROJECT_PATH, "tools")
DEST_ROOTFS_PATH = os.path.join(WORK_BASE, WORK_ROOTFS_NAME)
QEMU_BINARY = os.path.join(SRC_TOOLS_PATH, "qemu-mipsel-static")
UBUSD_REL_PATH = "sbin/ubusd"
UBUSD_FULL_PATH = os.path.join(DEST_ROOTFS_PATH, UBUSD_REL_PATH)
TARGET_BINARY_REL_PATH = "usr/sbin/uhttpd" 
TARGET_FULL_PATH = os.path.join(DEST_ROOTFS_PATH, TARGET_BINARY_REL_PATH)

def patch_binary(file_path):
    """
    Patches a binary to use /tmp/ubus_{ID}.sock instead of default ubus socket paths.
    Supports both /var/run/ubus.sock and /tmp/ubus.sock patterns.
    """
    if not os.path.exists(file_path):
        print(f"[{INSTANCE_ID}] Binary not found: {file_path}")
        return

    target_path_bytes = f"/tmp/{SOCKET_NAME}".encode()
    
    # Possible original patterns to replace
    original_patterns = [
        b"/var/run/ubus.sock",  # 18 bytes
        b"/tmp/ubus.sock",       # 14 bytes
    ]
    
    try:
        with open(file_path, "rb") as f:
            data = f.read()
        
        # Check if already patched
        if target_path_bytes in data:
            return  # Already patched
        
        modified = False
        for original_str in original_patterns:
            if original_str in data:
                # Pad with null bytes to match length
                if len(target_path_bytes) > len(original_str):
                    print(f"[{INSTANCE_ID}] Warning: Target path too long for {original_str}, skipping")
                    continue
                
                new_str = target_path_bytes + b"\x00" * (len(original_str) - len(target_path_bytes))
                data = data.replace(original_str, new_str)
                modified = True
                print(f"[{INSTANCE_ID}] Patched {os.path.basename(file_path)}: {original_str} -> {target_path_bytes}")
        
        if modified:
            with open(file_path, "wb") as f:
                f.write(data)
        
    except Exception as e:
        print(f"[{INSTANCE_ID}] Patch failed: {e}")

def prepare_environ():
    if not os.path.exists(DEST_ROOTFS_PATH):
        # Only copy if not exists (for speed on restart)
        # But for parallelism, we might want fresh copies.
        # Let's assume the manager cleans up if needed.
        # print(f"[{INSTANCE_ID}] Copying rootfs...")
        subprocess.run(["cp", "-r", "--no-preserve=mode,ownership", SRC_ROOTFS_PATH, DEST_ROOTFS_PATH], check=True)
        subprocess.run(["chmod", "-R", "755", DEST_ROOTFS_PATH], check=True)

    var_path = os.path.join(DEST_ROOTFS_PATH, "var")
    if os.path.islink(var_path): os.unlink(var_path)
    if not os.path.exists(var_path): os.makedirs(var_path)
    os.makedirs(os.path.join(var_path, "run"), exist_ok=True)
    subprocess.run(["chmod", "-R", "777", var_path], check=False)

    # Patch binaries with unique socket path
    patch_binary(os.path.join(DEST_ROOTFS_PATH, "lib", "libubus.so"))
    patch_binary(os.path.join(DEST_ROOTFS_PATH, "usr", "sbin", "uhttpd"))

    return DEST_ROOTFS_PATH

def run_fuzzer():
    prepare_environ()

    env = os.environ.copy()
    env["QEMU_LD_PREFIX"] = DEST_ROOTFS_PATH
    
    host_socket_path = f"/tmp/{SOCKET_NAME}"
    
    # 기존 소켓 점유 프로세스 정리
    if os.path.exists(host_socket_path):
        subprocess.run(["fuser", "-k", host_socket_path], stderr=subprocess.DEVNULL)
        try:
            os.remove(host_socket_path)
        except: pass
    
    # 잠시 대기
    time.sleep(0.5)

    # Start ubusd
    ubusd_cmd = [
        QEMU_BINARY,
        "-L", DEST_ROOTFS_PATH,
        UBUSD_FULL_PATH,
        "-s", host_socket_path
    ]
    
    # print(f"[{INSTANCE_ID}] Starting ubusd on {host_socket_path}...")
    ubusd_log = open(f"ubusd_{INSTANCE_ID}.log", "w")
    ubusd_proc = subprocess.Popen(ubusd_cmd, env=env, stdout=ubusd_log, stderr=ubusd_log)
    
    started = False
    for i in range(50):
        if ubusd_proc.poll() is not None:
             break
        if os.path.exists(host_socket_path):
            started = True
            break
        time.sleep(0.1)

    if not started:
        print(f"[{INSTANCE_ID}] ubusd failed to start.")
        ubusd_log.close()
        return

    # Start uhttpd
    target_cmd = [
        QEMU_BINARY,
        "-L", DEST_ROOTFS_PATH,
        TARGET_FULL_PATH, 
        "-f",           
        "-p", HTTP_PORT,   
        "-h", os.path.join(DEST_ROOTFS_PATH, "www"),  # 호스트 절대 경로 사용
        "-U", host_socket_path 
    ]
    
    # print(f"[{INSTANCE_ID}] Starting uhttpd on port {HTTP_PORT}...")
    
    uhttpd_proc = None
    try:
        # cwd를 rootfs로 설정하여 상대 경로 접근 지원
        uhttpd_proc = subprocess.Popen(target_cmd, env=env, cwd=DEST_ROOTFS_PATH)
        uhttpd_proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if uhttpd_proc and uhttpd_proc.poll() is None:
            uhttpd_proc.terminate()
        if ubusd_proc:
            ubusd_proc.terminate()
            ubusd_proc.wait()
        ubusd_log.close()

if __name__ == "__main__":
    run_fuzzer()
