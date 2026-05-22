#!/usr/bin/env python3
"""
ACF Bonding Resistance Predictor
Real-time terminal UI — Monte Carlo + FEM Surrogate + ML Correction
"""
import sys
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import warnings
import numpy as np
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich import box
except ImportError:
    print("ERROR: 'rich' 라이브러리가 없습니다. 설치: pip install rich")
    sys.exit(1)

try:
    from simulation import LiteratureParams, run_monte_carlo, run_fem_surrogate, compute_resistance
    from ml_correction import ACFMLCorrector
except ImportError as e:
    print(f"ERROR: 모듈 임포트 실패 — {e}")
    print("현재 디렉토리가 tools/acf_predictor/ 인지 확인하세요.")
    sys.exit(1)

console = Console(legacy_windows=False)


def parse_args():
    p = argparse.ArgumentParser(
        description="ACF 본딩 저항 예측기",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  python main.py
  python main.py --T 190 --P 2.5 --t 8 --bump-dia 25
  python main.py --T 180 --P 2.0 --calibration calibration.json
        """,
    )
    p.add_argument("--T",           type=float, default=180.0, metavar="°C",  help="본딩 온도 (기본값: 180)")
    p.add_argument("--P",           type=float, default=2.0,   metavar="MPa", help="본딩 압력 (기본값: 2.0)")
    p.add_argument("--t",           type=float, default=10.0,  metavar="s",   help="본딩 시간 (기본값: 10)")
    p.add_argument("--bump-dia",    type=float, default=30.0,  dest="bump_dia",    help="범프 직경 μm (기본값: 30)")
    p.add_argument("--bump-pitch",  type=float, default=50.0,  dest="bump_pitch",  help="범프 피치 μm (기본값: 50)")
    p.add_argument("--bump-height", type=float, default=15.0,  dest="bump_height", help="범프 높이 μm (기본값: 15)")
    p.add_argument("--substrate",   type=str,   default="glass (COG)")
    p.add_argument("--n-runs",      type=int,   default=3000,  dest="n_runs",      help="Monte Carlo 반복 수 (기본값: 3000)")
    p.add_argument("--calibration", type=str,   default=None,                      help="보정 데이터 JSON 파일 경로")
    return p.parse_args()


def _confidence(result, correction, mc, fem):
    gates = mc.converged and fem.r2 > 0.95
    r_mOhm = result.R_total_mean * 1000
    err = abs(r_mOhm - 45.0) / 45.0 * 100  # vs. typical benchmark
    if gates and err <= 10 and correction.mode == "ml_corrected":
        return "HIGH",   "HIGH — 높은 신뢰도"
    elif gates and err <= 20:
        return "MEDIUM", "MEDIUM — 보통 신뢰도"
    else:
        return "LOW",    "LOW — 낮은 신뢰도"


def _save_daily_report(args, mc, fem, correction, result, conf_text):
    today = date.today().isoformat()
    R = result.R_total_mean * 1000

    suggestions = []
    if not mc.converged:
        suggestions.append(f"  • Monte Carlo 미수렴(CV={mc.cv_final:.3f}) — --n-runs {args.n_runs * 2} 로 늘리세요")
    if fem.r2 <= 0.95:
        suggestions.append(f"  • FEM R²={fem.r2:.3f} 낮음 — simulation.py 훈련 샘플 300→600 증가 권장")
    if correction.mode == "physics_only":
        suggestions.append("  • ML 보정 비활성 — calibration.json에 실측 데이터 3건 이상 추가하면 정확도 향상")
    if mc.capture_rate < 0.4:
        suggestions.append(f"  • 포획률 낮음({mc.capture_rate:.2f}) — 압력 증가 또는 ACF 입자 크기 재확인 권장")
    if not suggestions:
        suggestions.append("  • 현재 모델 상태 양호 — 추가 조치 불필요")

    report = (
        f"{'━'*50}\n"
        f"📅 ACF 예측 시스템 일일 최적화 보고\n"
        f"날짜: {today}\n"
        f"{'━'*50}\n"
        f"오늘 예측: T={args.T}°C / P={args.P}MPa / t={args.t}s → {R:.2f}mΩ\n"
        f"신뢰도: {conf_text}\n\n"
        f"모델 품질\n"
        f"  Monte Carlo    CV={mc.cv_final:.3f}   {'✅ 수렴' if mc.converged else '⚠️  미수렴'}\n"
        f"  FEM 서로게이트  R²={fem.r2:.4f}  {'✅' if fem.r2 > 0.95 else '⚠️  개선 필요'}\n"
        f"  ML 보정        {correction.mode}  보정계수={correction.correction_factor:.3f}\n\n"
        f"개선 권고\n"
        f"{chr(10).join(suggestions)}\n\n"
        f"다음 조치\n"
        f"  보정 데이터: {'충분 (ML 활성)' if correction.mode == 'ml_corrected' else '추가 필요 — calibration.json에 실측값 입력'}\n"
        f"  소프트웨어 상태: tools/acf_predictor/main.py 존재 (최신)\n"
        f"{'━'*50}\n"
    )

    report_path = Path(__file__).parent / f"daily_report_{today}.txt"
    try:
        report_path.write_text(report, encoding="utf-8")
        return report, str(report_path)
    except Exception:
        return report, None


def main():
    args = parse_args()

    console.print(Panel.fit(
        f"[bold cyan]🔬 ACF 본딩 저항 예측기[/bold cyan]\n"
        f"기판: {args.substrate}  |  범프: [yellow]{args.bump_dia:.0f}μm ø[/yellow]  |  피치: {args.bump_pitch:.0f}μm\n"
        f"[bold yellow]T = {args.T}°C   P = {args.P} MPa   t = {args.t}s[/bold yellow]",
        border_style="cyan", padding=(0, 2),
    ))
    console.print()

    # ── Step 1: Literature params ────────────────────────────────────────────
    console.print("[bold]▶ Step 1/4[/bold]  📚 문헌 파라미터 로드", end="  ")
    lit = LiteratureParams.for_process(args.T, args.P)
    console.print(
        f"[green]✅ 완료[/green]  "
        f"입자 {lit.d_mean:.1f}±{lit.d_std:.1f}μm  |  체적분율 {lit.phi:.2f}  |  출처 {lit.n_sources}건"
    )
    console.print()

    # ── Steps 2+3: Monte Carlo + FEM 병렬 실행 ──────────────────────────────
    A_bump_m2 = np.pi * (args.bump_dia / 2.0 * 1e-6) ** 2
    V_mean = (np.pi / 6.0) * (lit.d_mean * 1e-6) ** 3
    n_est = max(1.0, lit.phi * A_bump_m2 * 25e-6 / V_mean)

    console.print("[bold]▶ Steps 2+3/4[/bold]  🎲 Monte Carlo  ‖  ⚙️  FEM  [dim](병렬 실행)[/dim]")
    with console.status("   두 시뮬레이션 동시 실행 중...", spinner="dots"):
        with ThreadPoolExecutor(max_workers=2) as executor:
            mc_future = executor.submit(run_monte_carlo, lit, args, args.n_runs)
            fem_future = executor.submit(run_fem_surrogate, lit, None, args, n_est)
            mc = mc_future.result()
            fem = fem_future.result()

    mc_icon = "✅" if mc.converged else "⚠️ "
    console.print(
        f"   {mc_icon} Monte Carlo  "
        f"범프당 입자 [cyan]{mc.particles_mean:.1f}±{mc.particles_std:.1f}[/cyan]개  |  "
        f"포획률 [cyan]{mc.capture_rate:.3f}[/cyan]  |  "
        f"{mc.n_runs_actual}회  CV={mc.cv_final:.3f}"
    )
    if not mc.converged:
        console.print(f"   [yellow]⚠ CV 미달 — --n-runs {args.n_runs * 2} 로 늘리면 수렴됩니다.[/yellow]")

    fem_icon = "✅" if fem.r2 > 0.95 else "⚠️ "
    console.print(
        f"   {fem_icon} FEM 서로게이트  "
        f"접촉 반경 [cyan]{fem.contact_radius_mean:.3f}±{fem.contact_radius_std:.3f}μm[/cyan]  |  "
        f"응력 {fem.contact_stress_mean:.1f}MPa  |  R²=[cyan]{fem.r2:.4f}[/cyan]"
    )
    if fem.r2 <= 0.95:
        console.print("   [yellow]⚠ R²<0.95 — simulation.py 훈련 샘플 증가를 권장합니다.[/yellow]")
    console.print()

    # ── Step 4: ML Correction ────────────────────────────────────────────────
    console.print("[bold]▶ Step 4/4[/bold]  🤖 ML 보정")
    with console.status("   XGBoost 보정 계수 계산 중...", spinner="dots"):
        corrector = ACFMLCorrector(calibration_file=args.calibration)
        corr = corrector.correct(mc, fem, args)

    if corr.mode == "ml_corrected":
        loo = f"  LOO-CV R²={corr.loo_cv_r2:.3f}" if corr.loo_cv_r2 else ""
        console.print(
            f"   ✅ ML 보정 완료  보정계수 [cyan]{corr.correction_factor:.3f}[/cyan]"
            f"  신뢰도 {corr.confidence:.0%}{loo}"
        )
    else:
        console.print("   ✅ 물리 모델 직접 사용  [dim](보정 데이터 없음 — ±30% 불확실도 적용)[/dim]")
    console.print()

    # ── Resistance Synthesis ─────────────────────────────────────────────────
    result = compute_resistance(
        lit, mc, fem, args,
        corrected_N_eff=corr.corrected_N_eff,
        corrected_a_um=corr.corrected_a_um,
    )

    def mO(v):
        return f"{v * 1000:.3f}"

    # ── Results Table ─────────────────────────────────────────────────────────
    tbl = Table(title="📊 예측 결과", box=box.ROUNDED, border_style="cyan", padding=(0, 1))
    tbl.add_column("항목",   style="bold", width=28)
    tbl.add_column("값",     justify="right", width=18)
    tbl.add_column("단위",   width=8)
    tbl.add_row("유효 입자 수 (N_eff)",    f"{result.N_eff:.2f}",           "개/범프")
    tbl.add_row("접촉 반경 (a_contact)",   f"{corr.corrected_a_um:.3f}",    "μm")
    tbl.add_row("",                         "",                               "")
    tbl.add_row("접촉 저항 (R_contact)",   mO(result.R_contact_mean),       "mΩ")
    tbl.add_row("퍼짐 저항 (R_spreading)", mO(result.R_spreading),          "mΩ")
    tbl.add_row(
        "[bold]총 저항 (R_total)[/bold]",
        f"[bold green]{mO(result.R_total_mean)}[/bold green]",
        "[bold]mΩ[/bold]",
    )
    tbl.add_row(
        "95% 신뢰구간",
        f"{mO(result.ci_95_lower)} ~ {mO(result.ci_95_upper)}",
        "mΩ",
    )
    console.print(tbl)
    console.print()

    # ── Korean Summary + Daily Report ─────────────────────────────────────────
    conf_text, _ = _confidence(result, corr, mc, fem)
    R = result.R_total_mean * 1000

    if R < 50:
        practical = f"예측 저항 {R:.1f}mΩ는 일반 허용 기준(50~100mΩ) 대비 충분한 여유가 있습니다."
    elif R < 100:
        practical = f"예측 저항 {R:.1f}mΩ는 허용 범위 내이나 마진이 크지 않습니다. 압력 소폭 증가를 검토하세요."
    else:
        practical = f"예측 저항 {R:.1f}mΩ가 기준(100mΩ)을 초과합니다. 공정 조건 재검토가 필요합니다."
    if mc.capture_rate < 0.4:
        practical += " 포획률이 낮으니 입자 직경 또는 압력을 재확인하세요."

    daily_report, saved_path = _save_daily_report(args, mc, fem, corr, result, conf_text)

    step_rows = [
        ("1️⃣ ", "논문 리서치",     f"입자 {lit.d_mean:.1f}μm, 체적분율 {lit.phi:.0%}, {lit.n_sources}건"),
        ("2️⃣ ", "입자 시뮬레이션", f"{mc.particles_mean:.1f}개 포획, 포획률 {mc.capture_rate:.0%}" + (" ✅" if mc.converged else " ⚠️") + "  ← 병렬"),
        ("3️⃣ ", "접촉 해석",       f"접촉 반경 {fem.contact_radius_mean:.2f}μm, R²={fem.r2:.3f}  ← 병렬"),
        ("4️⃣ ", "ML 보정",
         f"보정계수 {corr.correction_factor:.2f}" if corr.mode == "ml_corrected" else "물리 모델 사용"),
    ]

    lines = [
        "═══════════════════════════════════════════════",
        "🔬 ACF 본딩 예측 결과 요약",
        "═══════════════════════════════════════════════",
        f"📌 조건: {args.substrate} | 범프 {args.bump_dia:.0f}μm ø",
        f"   T={args.T}°C / P={args.P}MPa / t={args.t}s",
        "───────────────────────────────────────────────",
        f"⚡ 예측 저항: {R:.2f} mΩ",
        f"   범위: {mO(result.ci_95_lower)} ~ {mO(result.ci_95_upper)} mΩ  (95% 신뢰구간)",
        "───────────────────────────────────────────────",
        "🔎 단계별 결과",
    ] + [f"   {i} {n:<14} {d}" for i, n, d in step_rows] + [
        "───────────────────────────────────────────────",
        f"✅ 신뢰도: {conf_text}",
    ]

    if corr.mode == "physics_only":
        lines.append("⚠️  보정 데이터 없음 — calibration.json 추가 시 정확도 향상 가능")
    if not mc.converged:
        lines.append(f"⚠️  MC 미수렴 (CV={mc.cv_final:.3f}) — --n-runs {args.n_runs * 2} 권장")

    lines += [
        "───────────────────────────────────────────────",
        "💡 실무 해석",
        f"   {practical}",
        "",
        daily_report.strip(),
        "═══════════════════════════════════════════════",
    ]

    console.print(Panel("\n".join(lines), border_style="green", padding=(0, 1)))

    if saved_path:
        console.print(f"\n[dim]📄 일일 보고서 저장됨: {saved_path}[/dim]")


if __name__ == "__main__":
    main()
