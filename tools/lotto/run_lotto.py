"""
로또 예측 전체 파이프라인:
collect → normalize → ml_analyze → predict → 알림 전송(Telegram 우선 / Kakao 폴백)

매주 자동 실행용. 로컬 실행 시 tools/lotto/notify_config.json에서 자격증명 로드.
"""
import os
import subprocess
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서도 UTF-8 출력 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).parent
PY   = sys.executable
ENV_UTF8 = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}

STEPS = [
    ("데이터 수집",       BASE / "collect.py"),
    ("통계 정규화",       BASE / "normalize.py"),
    ("ML 정합성 분석",    BASE / "ml_analyze.py"),
    ("5게임 예측",        BASE / "predict.py"),
    ("알림 전송",         BASE / "github_actions" / "send_notify.py"),
]

def run():
    print("=" * 50)
    print(" 로또 예측 파이프라인 시작")
    print("=" * 50)
    for label, script in STEPS:
        print(f"\n[{label}] {script.name}")
        result = subprocess.run([PY, str(script)], capture_output=False,
                                env={**os.environ, **ENV_UTF8})
        if result.returncode != 0:
            print(f"  [실패] exit {result.returncode} — 파이프라인 중단")
            sys.exit(result.returncode)
        print(f"  [완료]")
    print("\n" + "=" * 50)
    print(" 모든 단계 완료")
    print("=" * 50)

if __name__ == "__main__":
    run()
