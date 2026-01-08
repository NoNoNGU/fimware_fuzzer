import random
import re
import os
import json

class Mutator:
    def __init__(self, dict_path=None):
        self.magic_numbers = [
            b"\x00", b"\xff", b"\x7f", b"\x80", # Integers
            b"A" * 100, b"A" * 3000, # Possible Overflows
            b"%s", b"%x", b"%n", b"%p" * 10, # Format Strings
            b"/bin/sh", b";", b"|", b"`", # Injection
            b"\r\n", b"\n",
            b"../../", b"..%2f..%2f", b"%2e%2e/" # Path Traversal
        ]
        
        # 위험한 경로 리스트 (Target Specific)
        self.dangerous_paths = [
            b"/cgi-bin/", b"/cgi-bin/luci", b"/admin", b"/login", 
            b"/etc/passwd", b"/proc/self/maps", b"/dev/null",
            b"/sys/class", b"/tmp"
        ]
        
        self.dictionary = []
        if dict_path and os.path.exists(dict_path):
            self.load_dictionary(dict_path)
        
        # Hardcoded fallback dictionary
        if not self.dictionary:
            self.dictionary = [b"GET", b"POST", b"HTTP/1.1", b"Content-Length", 
                               b"Host", b"Cookie", b"User-Agent", b"Authorization"]

    def load_dictionary(self, path):
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    if line.startswith('"') and line.endswith('"'):
                        line = line[1:-1]
                    self.dictionary.append(line.encode())
            print(f"[Mutator] Loaded {len(self.dictionary)} words from dictionary.")
        except Exception as e:
            print(f"[Mutator] Failed to load dictionary: {e}")

    # --- Raw Bytes Mutation ---

    def bit_flip(self, data):
        if not data: return data
        data = bytearray(data)
        idx = random.randint(0, len(data) - 1)
        bit = random.randint(0, 7)
        data[idx] ^= (1 << bit)
        return bytes(data)

    def byte_flip(self, data):
        if not data: return data
        data = bytearray(data)
        idx = random.randint(0, len(data) - 1)
        data[idx] ^= 0xFF
        return bytes(data)

    def magic_insert(self, data):
        if not data: return data
        data = bytearray(data)
        magic = random.choice(self.magic_numbers)
        idx = random.randint(0, len(data))
        return bytes(data[:idx]) + magic + bytes(data[idx:])
    
    def dictionary_insert(self, data):
        if not data or not self.dictionary: return data
        data = bytearray(data)
        word = random.choice(self.dictionary)
        idx = random.randint(0, len(data))
        return bytes(data[:idx]) + word + bytes(data[idx:])

    # --- JSON Structure Mutation ---
    
    def mutate_json_value(self, val):
        """Recursively mutate JSON values while keeping structure"""
        if isinstance(val, dict):
            if not val: return val
            k = random.choice(list(val.keys()))
            val[k] = self.mutate_json_value(val[k])
        
        elif isinstance(val, list):
            if not val: return val
            idx = random.randint(0, len(val)-1)
            val[idx] = self.mutate_json_value(val[idx])
            
        elif isinstance(val, str):
            # String Mutation
            r = random.random()
            if r < 0.3:
                # Injection
                val += random.choice(["../../", "A"*1000, "%n%n%n", "' OR '1'='1"])
            elif r < 0.6:
                # Bit flip simulation
                try:
                    b = val.encode('latin-1')
                    b = self.byte_flip(b)
                    val = b.decode('latin-1')
                except:
                    val += "A"
            else:
                # Format string
                val = "%s"*10
                
        elif isinstance(val, int):
            # Integer Overflow
            val = random.choice([-1, 0, 2147483648, -2147483648, val*100, val+1])
            
        elif isinstance(val, bool):
            val = not val
            
        return val

    # --- Structure-Aware (HTTP) Mutation ---
    
    def parse_http(self, data):
        """
        Returns: { 'method': b'GET', 'uri': b'/', 'version': b'HTTP/1.1', 'headers': [...], 'body': b'...' } or None
        """
        try:
            if b"\r\n\r\n" in data:
                head, body = data.split(b"\r\n\r\n", 1)
            else:
                head = data
                body = b""
            
            lines = head.split(b"\r\n")
            if not lines: return None
            
            req_line = lines[0].split(b" ")
            if len(req_line) < 2: return None
            
            method = req_line[0]
            uri = req_line[1]
            version = req_line[2] if len(req_line) > 2 else b"HTTP/1.1"
            
            headers = []
            for line in lines[1:]:
                if b":" in line:
                    k, v = line.split(b":", 1)
                    headers.append((k.strip(), v.strip()))
            
            return {
                'method': method,
                'uri': uri,
                'version': version,
                'headers': headers,
                'body': body
            }
        except:
            return None

    def build_http(self, req):
        """파싱된 객체를 다시 바이트로 조립"""
        try:
            # Request Line
            res = req['method'] + b" " + req['uri'] + b" " + req['version'] + b"\r\n"
            
            # Headers
            for k, v in req['headers']:
                res += k + b": " + v + b"\r\n"
            
            res += b"\r\n"
            res += req['body']
            return res
        except:
            return b""

    def mutate_http_method(self, req):
        if random.random() < 0.5:
            req['method'] = random.choice([b"POST", b"PUT", b"DELETE", b"HEAD", b"OPTIONS", b"TRACE", b"CONNECT"])
        else:
            req['method'] = random.choice([
                b"A" * 100,  # Stack Overflow?
                b"INVALID",
                b"\x00GET"
            ])

    def mutate_http_uri(self, req):
        base_uri = req['uri']
        strategy = random.choice(['append', 'replace', 'injection'])
        
        if strategy == 'append':
            req['uri'] += random.choice(self.magic_numbers)
        elif strategy == 'replace':
            req['uri'] = random.choice(self.dangerous_paths)
        elif strategy == 'injection':
            injection = random.choice([b";reboot", b"|ls", b"$(id)", b"' OR '1'='1"])
            req['uri'] += injection

    def mutate_http_header(self, req):
        if not req['headers']:
            req['headers'].append((b"User-Agent", b"Fuzzer"))
            
        idx = random.randint(0, len(req['headers']) - 1)
        k, v = req['headers'][idx]
        
        strategy = random.choice(['val_overflow', 'key_overflow', 'integer', 'format'])
        
        if strategy == 'val_overflow':
            v = b"A" * 2000
        elif strategy == 'key_overflow':
            k = b"A" * 2000
        elif strategy == 'integer':
            v = random.choice([b"-1", b"0", b"2147483648", b"4294967295"])
        elif strategy == 'format':
            v = b"%s%s%s%s%n"
            
        req['headers'][idx] = (k, v)
        
        if random.random() < 0.3:
            req['headers'].append((b"Content-Length", b"-100"))

    def mutate_http_body(self, req):
        """Body 변조 - JSON Aware or Raw"""
        if not req['body']:
            req['body'] = b"A" * 100
            return

        # Try JSON Mutation first
        is_json = False
        # Content-Type check (simple)
        for k, v in req['headers']:
            if k.lower() == b"content-type" and b"json" in v.lower():
                is_json = True
                break
        
        if not is_json and req['body'].strip().startswith(b"{"):
            is_json = True

        if is_json:
            try:
                # Decode -> Load -> Mutate -> Dump -> Encode
                json_str = req['body'].decode('utf-8', errors='ignore')
                json_obj = json.loads(json_str) 
                
                # Mutate JSON Structure
                self.mutate_json_value(json_obj)
                
                new_body = json.dumps(json_obj).encode('utf-8')
                req['body'] = new_body
                
                # Update Content-Length if exists
                # (Optional, but good for validity)
                new_headers = []
                for k, v in req['headers']:
                    if k.lower() == b"content-length":
                        v = str(len(new_body)).encode()
                    new_headers.append((k, v))
                req['headers'] = new_headers
                
                return # JSON mutation success
            except:
                pass # JSON parsing failed, fall back to raw

        # Fallback to Raw Mutation
        strategy = random.choice(['flip', 'magic', 'overflow'])
        
        if strategy == 'flip':
            req['body'] = self.byte_flip(req['body'])
        elif strategy == 'magic':
            req['body'] = self.magic_insert(req['body'])
        elif strategy == 'overflow':
            req['body'] += b"A" * 1024

    def mutate_structure_aware(self, data):
        req = self.parse_http(data)
        if not req: return None
        
        target = random.choice(['method', 'uri', 'header', 'header', 'body', 'body']) # Body 가중치 증가
        
        if target == 'method':
            self.mutate_http_method(req)
        elif target == 'uri':
            self.mutate_http_uri(req)
        elif target == 'header':
            self.mutate_http_header(req)
        elif target == 'body':
            self.mutate_http_body(req)
            
        return self.build_http(req)

    def mutate(self, data):
        """Smart Mutation Entry Point"""
        r = random.random()
        
        # 70% Chance: Structure Aware (Smart)
        if r < 0.7:
            res = self.mutate_structure_aware(data)
            if res: return res
        
        # 20% Chance: Magic/Dict Insert
        if r < 0.9:
            if random.random() < 0.5:
                return self.dictionary_insert(data)
            else:
                return self.magic_insert(data)
        
        # 10% Chance: Raw Bit/Byte Flip
        else:
            if random.random() < 0.5:
                return self.bit_flip(data)
            else:
                return self.byte_flip(data)

    def generate_initial_seeds(self):
        return [
            b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"POST /cgi-bin/luci HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\nContent-Length: 35\r\n\r\n{\"method\":\"login\",\"params\":[\"admin\"]}",
            b"GET /webpages/index.html HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"HEAD / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"GET /nonexistent HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        ]
