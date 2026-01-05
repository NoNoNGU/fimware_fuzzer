import socket
import sys
import time

HOST = "127.0.0.1"
PORT = 8080

payload = b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    s.connect((HOST, PORT))
    print(f"[*] Connected to {HOST}:{PORT}")
    s.sendall(payload)
    print("[*] Sent payload")
    
    data = s.recv(4096)
    print(f"[*] Received {len(data)} bytes")
    print("-" * 20)
    print(data.decode(errors='ignore'))
    print("-" * 20)
    s.close()
except Exception as e:
    print(f"[!] Error: {e}")
