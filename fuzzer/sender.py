import socket
import time

class Sender:
    def __init__(self, host="127.0.0.1", port=8080):
        self.host = host
        self.port = port
        self.timeout = 0.1 # seconds (Fast fuzzing)

    def send(self, payload):
        """
        Sends a payload to the target.
        Returns:
            (success, status_code)
            status_code: int (e.g., 200, 404, 500), or 0 if no response/error
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        try:
            s.connect((self.host, self.port))
            s.sendall(payload)
            
            status_code = 0
            try:
                # Read response head
                resp = s.recv(4096)
                if resp:
                    # Simple HTTP Status Parsing
                    # ex: HTTP/1.1 200 OK
                    first_line = resp.split(b"\r\n")[0]
                    parts = first_line.split(b" ")
                    if len(parts) >= 2 and parts[1].isdigit():
                        status_code = int(parts[1])
            except socket.timeout:
                pass # Timeout is fine
                
            s.close()
            return True, status_code
            
        except ConnectionRefusedError:
            return False, 0
        except Exception as e:
            return False, 0
