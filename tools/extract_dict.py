import re
import sys
import os

def extract_strings(filename, min_len=4):
    """바이너리 파일에서 문자열 추출"""
    with open(filename, "rb") as f:
        data = f.read()
    
    # ASCII 문자열 패턴 (출력 가능한 문자들)
    # 4글자 이상
    pattern = b"[ -~]{4,}"
    
    strings = []
    for match in re.finditer(pattern, data):
        s = match.group().decode("ascii", errors="ignore")
        strings.append(s)
        
    return strings

def sanitize_string(s):
    """딕셔너리에 넣기 적합한지 확인 및 정제"""
    # 너무 길면 패스
    if len(s) > 64:
        return None
    
    # 공백만 있거나 특수문자만 있는 경우 패스
    if not any(c.isalnum() for c in s):
        return None
        
    # AFL 딕셔너리 포맷으로 이스케이프
    # " -> \"
    # \ -> \\
    escaped = s.replace("\\", "\\\\").replace("\"", "\\\"")
    
    # Hex escaping for non-printable checks (though we filtered for printable)
    # Just wrap in quotes
    return f'"{escaped}"'

def main():
    if len(sys.argv) < 3:
        print("Usage: python3 extract_dict.py <target_binary> <output_dict>")
        sys.exit(1)
        
    target_path = sys.argv[1]
    output_path = sys.argv[2]
    
    print(f"[*] Extracting strings from {target_path}...")
    
    try:
        raw_strings = extract_strings(target_path)
    except FileNotFoundError:
        print(f"[!] File not found: {target_path}")
        sys.exit(1)
        
    unique_tokens = set()
    
    # 흥미로운 키워드 필터링 (선택적)
    interesting_keywords = [
        "admin", "password", "user", "html", "cgi", "bin", "lua", "http",
        "cookie", "set-cookie", "auth", "token", "session", "debug",
        "system", "exec", "eval"
    ]
    
    count = 0
    with open(output_path, "w") as f:
        f.write("# Auto-generated dictionary from binary\n")
        
        for s in raw_strings:
            token = sanitize_string(s)
            if token and token not in unique_tokens:
                # 너무 일반적인 텍스트는 제외할 수도 있음
                # 하지만 Fuzzing에서는 다 넣어보는 게 좋음
                f.write(f"{token}\n")
                unique_tokens.add(token)
                count += 1
                
    print(f"[*] Done. Extracted {count} unique tokens to {output_path}")

if __name__ == "__main__":
    main()
