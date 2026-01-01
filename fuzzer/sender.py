import socket
import time

class Sender:
    def __init__(self, host="127.0.0.1", port=8080):
        self.host = host
        self.port = port
        self.timeout = 1.0 # seconds

    def send(self, payload):
        """
        Sends a payload to the target.
        Returns:
            True: If sent successfully.
            False: If connection refused or error (Target likely down).
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, self.port))
            s.sendall(payload)
            
            # Optionally read response to ensure server processed it
            # But for fuzzing, sometimes we just want to fire and forget
            # Or read a bit to see if it responds validly
            try:
                s.recv(1024)
            except socket.timeout:
                pass # Timeout is fine, server might process slowly
                
            s.close()
            return True
        except ConnectionRefusedError:
            # print("[Sender] Connection Refused - Target maybe down?")
            return False
        except Exception as e:
            # print(f"[Sender] Error: {e}")
            return False
