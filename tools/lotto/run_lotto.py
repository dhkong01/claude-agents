"""
로또 예측 전체 파이프라인:
collect → normalize → ml_analyze → predict → kakao 전송

매주 토요일 자동 실행용.
"""
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
PY   = sys.executable

STEPS = [
    ("데이터 수집",       BASE / "collect.py"),
    ("통계 정규화",       BASE / "normalize.py"),
    ("ML 정합성 분석",    BASE / "ml_analyze.py"),
    ("5게임 예측",        BASE / "predict.py"),
    ("카카오톡 전송",     BASE / "kakao_lotto_sender.py"),
]

def run():
    print("=" * 50)
    print(" 로또 예측 파이프라인 시작")
    print("=" * 50)
    for label, script in STEPS:
        print(f"\n[{label}] {script.name}")
        result = subprocess.run([PY, str(script)], capture_output=False)
        if result.returncode != 0:
            print(f"  ❌ 실패 (exit {result.returncode}) — 파이프라인 중단")
            sys.exit(result.returncode)
        print(f"  ✅ 완료")
    print("\n" + "=" * 50)
    print(" 모든 단계 완료")
    print("=" * 50)

if __name__ == "__main__":
    run()
