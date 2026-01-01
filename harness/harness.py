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
WORK_ROOTFS_NAME = "tplink_fuzzer_rootfs"

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
    Patches a binary to use /tmp/ubus.sock instead of /var/run/ubus.sock.
    """
    if not os.path.exists(file_path):
        print(f"[!] Binary not found: {file_path}")
        return

    # Original: /var/run/ubus.sock (18 bytes)
    # New:      /tmp/ubus.sock\x00\x00\x00\x00 (18 bytes)
    original_str = b"/var/run/ubus.sock"
    new_str      = b"/tmp/ubus.sock\x00\x00\x00\x00"
    
    print(f"[*] Patching {file_path}...")
    try:
        with open(file_path, "rb") as f:
            data = f.read()
            
        if original_str not in data:
            if b"/tmp/ubus.sock" in data:
                print("    Already patched/Not found.")
                return 
            print(f"[!] Warning: Could not find socket string in {os.path.basename(file_path)}")
            # Don't return, maybe it uses a different mechanism, but warn.
            return

        newdata = data.replace(original_str, new_str)
        
        with open(file_path, "wb") as f:
            f.write(newdata)
        print("    Patch applied successfully.")
        
    except Exception as e:
        print(f"[!] Patch failed: {e}")

def prepare_environ():
    if os.path.exists(DEST_ROOTFS_PATH):
        subprocess.run(["chmod", "-R", "755", DEST_ROOTFS_PATH], check=False)
    else:
        print(f"[*] Copying rootfs to {DEST_ROOTFS_PATH}...")
        subprocess.run(["cp", "-r", "--no-preserve=mode,ownership", SRC_ROOTFS_PATH, DEST_ROOTFS_PATH], check=True)
        subprocess.run(["chmod", "-R", "755", DEST_ROOTFS_PATH], check=True)

    var_path = os.path.join(DEST_ROOTFS_PATH, "var")
    if os.path.islink(var_path): os.unlink(var_path)
    if not os.path.exists(var_path): os.makedirs(var_path)
    os.makedirs(os.path.join(var_path, "run"), exist_ok=True)
    subprocess.run(["chmod", "-R", "777", var_path], check=False)

    # PATCH BOTH LIBUBUS AND UHTTPD
    patch_binary(os.path.join(DEST_ROOTFS_PATH, "lib", "libubus.so"))
    patch_binary(os.path.join(DEST_ROOTFS_PATH, "usr", "sbin", "uhttpd"))

    return DEST_ROOTFS_PATH

def run_fuzzer():
    prepare_environ()

    env = os.environ.copy()
    env["QEMU_LD_PREFIX"] = DEST_ROOTFS_PATH
    
    host_socket_path = "/tmp/ubus.sock"
    if os.path.exists(host_socket_path): os.remove(host_socket_path)

    # Start ubusd
    ubusd_cmd = [
        QEMU_BINARY,
        "-L", DEST_ROOTFS_PATH,
        UBUSD_FULL_PATH,
        "-s", host_socket_path
    ]
    
    print(f"[*] Starting ubusd (Socket: {host_socket_path})...")
    ubusd_log = open("ubusd.log", "w")
    ubusd_proc = subprocess.Popen(ubusd_cmd, env=env, stdout=ubusd_log, stderr=ubusd_log)
    
    started = False
    for i in range(20):
        if ubusd_proc.poll() is not None:
             print("[!] ubusd died unexpectedly!")
             break
        if os.path.exists(host_socket_path):
            print(f"[*] Socket created successfully!")
            started = True
            break
        time.sleep(0.1)

    if not started:
        print("[!] ubusd failure. Log dump:")
        ubusd_log.close()
        with open("ubusd.log", "r") as f:
            print(f.read())
        return

    # Start uhttpd
    target_cmd = [
        QEMU_BINARY,
        "-L", DEST_ROOTFS_PATH,
        TARGET_FULL_PATH, 
        "-f",           
        "-p", "8080",   
        "-h", "/www",
        # Pass -U flag just in case patching missed something or it's needed
        "-U", host_socket_path 
    ]
    
    print(f"[*] Starting uhttpd...")
    print("-" * 50)
    
    uhttpd_proc = None
    try:
        uhttpd_proc = subprocess.Popen(target_cmd, env=env)
        uhttpd_proc.wait()
    except KeyboardInterrupt:
        print("\n[!] Stopping fuzzer...")
    finally:
        if uhttpd_proc and uhttpd_proc.poll() is None:
            uhttpd_proc.terminate()
        if ubusd_proc:
            ubusd_proc.terminate()
            ubusd_proc.wait()

if __name__ == "__main__":
    run_fuzzer()
