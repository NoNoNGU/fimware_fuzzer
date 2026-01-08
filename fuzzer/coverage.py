"""
Coverage Manager - QEMU 실행 로그에서 커버리지 정보 추출
"""
import os
import re
from typing import Set, Tuple

class CoverageManager:
    """커버리지 맵 관리 및 새로운 경로 탐지"""
    
    def __init__(self, corpus_dir: str = None):
        self.global_coverage: Set[int] = set()  # 전역 커버리지 (PC 주소들)
        self.corpus_dir = corpus_dir
        self.total_edges = 0
        
        if corpus_dir and not os.path.exists(corpus_dir):
            os.makedirs(corpus_dir)
    
    def parse_qemu_log(self, log_path: str) -> Set[int]:
        """
        QEMU exec 로그에서 실행된 PC 주소들을 추출
        
        로그 형식 예시:
        Trace 0x00400abc [0000000000400abc/00000002/00000005/03000001]
        """
        pcs = set()
        
        if not os.path.exists(log_path):
            return pcs
        
        try:
            with open(log_path, 'r', errors='ignore') as f:
                for line in f:
                    # "Trace 0: 0x..." 또는 "Trace 0x..." 패턴 매칭
                    # 예: Trace 0: 0x7f... [00000000/...]
                    match = re.search(r'Trace.*0x([0-9a-fA-F]+)', line)
                    if match:
                        pc = int(match.group(1), 16)
                        pcs.add(pc)
        except Exception as e:
            pass
        
        return pcs
    
    def check_new_coverage(self, log_path: str) -> Tuple[bool, int, Set[int]]:
        """
        새로운 커버리지가 발견되었는지 확인
        
        Returns:
            (is_interesting, new_count, new_pcs)
        """
        current_pcs = self.parse_qemu_log(log_path)
        
        if not current_pcs:
            return False, 0, set()
        
        # 새로 발견된 PC들
        new_pcs = current_pcs - self.global_coverage
        
        if new_pcs:
            # 전역 커버리지 업데이트
            self.global_coverage.update(new_pcs)
            self.total_edges = len(self.global_coverage)
            return True, len(new_pcs), new_pcs
        
        return False, 0, set()
    
    def save_interesting_input(self, payload: bytes, new_pcs: Set[int]) -> str:
        """
        새로운 커버리지를 발견한 입력을 코퍼스에 저장
        
        Returns: 저장된 파일 경로
        """
        if not self.corpus_dir:
            return None
        
        import hashlib
        import time
        
        # 파일명: hash_timestamp.bin
        payload_hash = hashlib.md5(payload).hexdigest()[:8]
        timestamp = int(time.time())
        filename = f"id_{payload_hash}_{timestamp}.bin"
        filepath = os.path.join(self.corpus_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(payload)
        
        return filepath
    
    def get_stats(self) -> dict:
        """현재 커버리지 통계"""
        return {
            "total_edges": self.total_edges,
            "corpus_size": len(os.listdir(self.corpus_dir)) if self.corpus_dir and os.path.exists(self.corpus_dir) else 0
        }
    
    def clear_log(self, log_path: str):
        """로그 파일 초기화 (다음 실행을 위해)"""
        try:
            if os.path.exists(log_path):
                # 파일 비우기
                open(log_path, 'w').close()
        except:
            pass


# 테스트용
if __name__ == "__main__":
    cm = CoverageManager(corpus_dir="/tmp/test_corpus")
    
    # 가상 테스트
    test_log = "/tmp/test_qemu.log"
    with open(test_log, 'w') as f:
        f.write("Trace 0x00400100 [0000000000400100/00000002/00000005/03000001]\n")
        f.write("Trace 0x00400200 [0000000000400200/00000002/00000005/03000001]\n")
    
    is_new, count, pcs = cm.check_new_coverage(test_log)
    print(f"New coverage: {is_new}, count: {count}, pcs: {pcs}")
    print(f"Stats: {cm.get_stats()}")
