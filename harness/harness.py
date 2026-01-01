import os
import sys
import time
import shutil
import subprocess
import signal

# [Harness Configuration]
WINDOWS_BASE = r"c:\Users\ypete\Downloads\firmware_extract_tplink"
WSL_BASE = "/mnt/c/Users/ypete/Downloads/firmware_extract_tplink"
PROJECT_DIR_NAME = "tplink_fuzzer"
WORK_BASE = "/tmp"

# Instance Configuration
INSTANCE_ID = int(os.environ.get("INSTANCE_ID", 0))
WORK_ROOTFS_NAME = f"tplink_fuzzer_rootfs_{INSTANCE_ID}"
HTTP_PORT = str(8080 + INSTANCE_ID)
SOCKET_NAME = f"ubus_{INSTANCE_ID}.sock"

def get_base_path():
    if os.path.exists("/mnt/c"):
        return WSL_BASE
    return os.getcwd()

SRC_PROJECT_PATH = os.path.join(get_base_path(), PROJECT_DIR_NAME)
SRC_ROOTFS_PATH = os.path.join(SRC_PROJECT_PATH, "rootfs")
SRC_TOOLS_PATH = os.path.join(SRC_PROJECT_PATH, "tools")
DEST_ROOTFS_PATH = os.path.join(WORK_BASE, WORK_ROOTFS_NAME)
QEMU_BINARY = os.path.join(SRC_TOOLS_PATH, "qemu-mipsel-static")
UBUSD_REL_PATH = "sbin/ubusd"
UBUSD_FULL_PATH = os.path.join(DEST_ROOTFS_PATH, UBUSD_REL_PATH)
TARGET_BINARY_REL_PATH = "usr/sbin/uhttpd" 
TARGET_FULL_PATH = os.path.join(DEST_ROOTFS_PATH, TARGET_BINARY_REL_PATH)

def patch_binary(file_path):
    """
    Patches a binary to use /tmp/ubus_{ID}.sock instead of /var/run/ubus.sock.
    """
    if not os.path.exists(file_path):
        print(f"[{INSTANCE_ID}] Binary not found: {file_path}")
        return

    # Original: /var/run/ubus.sock (18 bytes)
    # Target:   /tmp/ubus_N.sock   (Max 18 bytes)
    original_str = b"/var/run/ubus.sock"
    target_path_bytes = f"/tmp/{SOCKET_NAME}".encode()
    
    # Pad with null bytes to match length
    if len(target_path_bytes) > len(original_str):
        print(f"[{INSTANCE_ID}] Error: Socket path too long for patching!")
        return
    
    new_str = target_path_bytes + b"\x00" * (len(original_str) - len(target_path_bytes))
    
    # print(f"[{INSTANCE_ID}] Patching {os.path.basename(file_path)} -> {target_path_bytes}")
    try:
        with open(file_path, "rb") as f:
            data = f.read()
            
        if original_str not in data:
            if target_path_bytes in data:
                return # Already patched
            # print(f"[{INSTANCE_ID}] Warning: Original string not found.")
            return

        newdata = data.replace(original_str, new_str)
        
        with open(file_path, "wb") as f:
            f.write(newdata)
        
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
    if os.path.exists(host_socket_path): os.remove(host_socket_path)

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
    for i in range(30):
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
        "-h", "/www",
        "-U", host_socket_path 
    ]
    
    # print(f"[{INSTANCE_ID}] Starting uhttpd on port {HTTP_PORT}...")
    
    uhttpd_proc = None
    try:
        uhttpd_proc = subprocess.Popen(target_cmd, env=env)
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
