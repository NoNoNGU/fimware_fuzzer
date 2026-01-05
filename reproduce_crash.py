import socket
import sys
import time
import os

HOST = "127.0.0.1"
PORT = 8080

def send_payload(payload):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, PORT))
        print(f"[*] Connected. Sending {len(payload)} bytes...")
        s.sendall(payload)
        
        try:
            data = s.recv(1024)
            print(f"[*] Response: {data[:50]}...")
        except socket.timeout:
            print("[*] No response (Timeout)")
            
        s.close()
        return True
    except ConnectionRefusedError:
        print("[!] Connection Refused (Target Dead?)")
        return False
    except Exception as e:
        print(f"[!] Error: {e}")
        return False

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <crash_file>")
    sys.exit(1)

crash_file = sys.argv[1]
with open(crash_file, "rb") as f:
    payload = f.read()

print(f"[*] Reproducing {crash_file}...")
if send_payload(payload):
    print("[*] Payload sent. Checking if target is alive...")
    time.sleep(1)
    # Check by connecting again
    if send_payload(b"GET / HTTP/1.1\r\n\r\n"):
        print("[*] Target is ALIVE.")
    else:
        print("[!] Target seems DEAD.")
else:
    print("[!] Failed to send payload.")
