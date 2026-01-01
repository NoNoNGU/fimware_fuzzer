import random
import re
import os

class Mutator:
    def __init__(self, dict_path=None):
        self.magic_numbers = [
            b"\x00", b"\xff", b"\x7f", b"\x80", # Integers
            b"A" * 100, b"A" * 1000, # Possible Overflows
            b"%s", b"%x", b"%n", # Format Strings
            b"/bin/sh", b";", b"|", # Injection
            b"\r\n", b"\n",
            b"../../", b"..%2f..%2f" # Path Traversal
        ]
        self.dictionary = []
        if dict_path and os.path.exists(dict_path):
            self.load_dictionary(dict_path)
        
        # Hardcoded fallback dictionary if file missing
        if not self.dictionary:
            self.dictionary = [b"GET", b"POST", b"HTTP/1.1", b"Content-Length", b"Host", b"Cookie", b"User-Agent"]

    def load_dictionary(self, path):
        try:
            with open(path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"): continue
                    # Remove quotes if present "WORD" -> WORD
                    if line.startswith('"') and line.endswith('"'):
                        line = line[1:-1]
                    self.dictionary.append(line.encode())
            print(f"[Mutator] Loaded {len(self.dictionary)} words from dictionary.")
        except Exception as e:
            print(f"[Mutator] Failed to load dictionary: {e}")

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

    def mutate_structure(self, data):
        """Attempts to mutate HTTP structure directly."""
        try:
            # Try to split lines
            parts = data.split(b"\r\n")
            if len(parts) < 1: return None
            
            # Simple heuristic: Request Line is parts[0]
            req_line = parts[0].split(b" ")
            if len(req_line) >= 2:
                target = random.choice(["method", "path", "proto"])
                if target == "method":
                    # Swap Method
                    verbs = [w for w in self.dictionary if w.isupper() and len(w) < 10]
                    if verbs: req_line[0] = random.choice(verbs)
                elif target == "path":
                    # Append garbage to path
                    req_line[1] += random.choice(self.magic_numbers)
                
                parts[0] = b" ".join(req_line)
                return b"\r\n".join(parts)
        except:
            pass
        return None

    def mutate(self, data):
        """Smart Mutation Logic."""
        r = random.random()
        
        # 10% Chance: Structure Mutation (High Level)
        if r < 0.1:
            res = self.mutate_structure(data)
            if res: return res

        # 40% Chance: Dictionary/Magic Insert (Logic/Parser Fuzzing)
        if r < 0.5:
            if random.random() < 0.5:
                return self.dictionary_insert(data)
            else:
                return self.magic_insert(data)
        
        # 50% Chance: Bit/Byte Flip (Raw Fuzzing)
        else:
            if random.random() < 0.5:
                return self.bit_flip(data)
            else:
                return self.byte_flip(data)

    def generate_initial_seeds(self):
        return [
            b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"POST /cgi-bin/luci HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 5\r\n\r\nadmin",
            b"GET /webpages/index.html HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"HEAD / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n",
            b"GET /nonexistent HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
        ]
