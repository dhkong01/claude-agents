"""
ACF 본딩 저항 예측기 v1.0
GUI-based standalone desktop application
Monte Carlo + FEM surrogate + ML correction
"""
import sys
import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import queue
from datetime import datetime

# Windows UTF-8 fix
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# frozen(exe) 모드와 스크립트 모드 모두 지원
if getattr(sys, "frozen", False):
    _dir = os.path.dirname(sys.executable)
else:
    _dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _dir)

try:
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    matplotlib.rcParams["font.family"] = "Malgun Gothic"
    matplotlib.rcParams["axes.unicode_minus"] = False
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    import matplotlib.patches as mpatches
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
    from simulation import LiteratureParams, run_monte_carlo, run_fem_surrogate, compute_resistance
    from ml_correction import ACFMLCorrector
    from concurrent.futures import ThreadPoolExecutor
except ImportError as exc:
    _root = tk.Tk()
    _root.withdraw()
    messagebox.showerror(
        "모듈 오류",
        f"필요한 라이브러리를 찾을 수 없습니다:\n{exc}\n\n"
        "명령 프롬프트에서 실행하세요:\n  pip install -r requirements.txt",
    )
    sys.exit(1)


# ── Color + font palette  (Fluent / Office 365 Modern) ────────────────────────
C = {
    "header":    "#1e1b4b",  # deep indigo — banner bg
    "header2":   "#312e81",  # indigo-800  — banner right accent
    "side":      "#f0f4ff",  # lavender-50 — sidebar bg
    "accent":    "#4f46e5",  # indigo-600  — primary CTA
    "accent_l":  "#818cf8",  # indigo-400  — light accent
    "accent_bg": "#eef2ff",  # indigo-50   — tinted bg
    "green":     "#059669",  "green_bg":  "#d1fae5",
    "orange":    "#d97706",  "orange_bg": "#fef3c7",
    "red":       "#dc2626",  "red_bg":    "#fee2e2",
    "bg":        "#f8fafc",  # slate-50
    "card":      "#ffffff",
    "border":    "#e2e8f0",  # slate-200
    "text":      "#0f172a",  # slate-900
    "muted":     "#64748b",  # slate-500
    "label":     "#6366f1",  # indigo-500 — section caps label
}
FT   = ("Malgun Gothic", 13, "bold")
FH   = ("Malgun Gothic",  9, "bold")
FB   = ("Malgun Gothic",  9)
FM   = ("Consolas",       9)
FNUM = ("Malgun Gothic", 30, "bold")
FLBL = ("Malgun Gothic",  7, "bold")  # micro-label (section caps)


class _Args:
    """Namespace passed to simulation functions."""
    T: float = 180.0
    P: float = 2.0
    t: float = 10.0
    pad_w: float = 13.0
    pad_h: float = 110.0
    bump_dia: float = 37.8
    bump_pitch: float = 14.0
    substrate: str = "glass (COG)"
    n_runs: int = 2000


def _card(parent, title="", stripe=None):
    """Return (outer_frame, content_frame). Left-accent stripe + micro-label header."""
    sc = stripe or C["accent"]
    outer = tk.Frame(parent, bg=C["border"], bd=0)
    tk.Frame(outer, bg=sc, width=3).pack(side="left", fill="y")
    body = tk.Frame(outer, bg=C["card"], padx=10, pady=8)
    body.pack(fill="both", expand=True, padx=(0, 1), pady=1)
    if title:
        tk.Label(body, text=title.upper(), font=FLBL,
                 bg=C["card"], fg=C["label"]).pack(anchor="w", pady=(0, 5))
    content = tk.Frame(body, bg=C["card"])
    content.pack(fill="both", expand=True)
    return outer, content


def _setup_style():
    s = ttk.Style()
    s.theme_use("clam")
    s.configure("TNotebook",        background=C["bg"],       borderwidth=0, tabmargins=0)
    s.configure("TNotebook.Tab",    background=C["border"],   foreground=C["muted"],
                padding=[14, 6],    font=FB)
    s.map("TNotebook.Tab",
          background=[("selected", C["card"])],
          foreground=[("selected", C["accent"])])
    s.configure("TProgressbar",     background=C["accent"],   troughcolor=C["border"],
                borderwidth=0,      thickness=5)
    s.configure("TEntry",           fieldbackground=C["card"],borderwidth=1,
                relief="solid",     padding=3)
    s.configure("TCombobox",        fieldbackground=C["card"],borderwidth=1,
                relief="solid",     padding=3)
    s.map("TCombobox",              fieldbackground=[("readonly", C["card"])])
    s.configure("TScale",           background=C["side"],     troughcolor=C["border"],
                sliderlength=14,    sliderrelief="flat")


def _row(parent, row, label, var, unit="", width=9):
    """Place label + entry + unit in a grid row."""
    tk.Label(parent, text=label, font=FB, bg=C["card"],
             fg=C["muted"], anchor="w").grid(row=row, column=0, sticky="w", pady=3)
    ttk.Entry(parent, textvariable=var, width=width).grid(
        row=row, column=1, padx=(4, 2), pady=3)
    if unit:
        tk.Label(parent, text=unit, font=("Malgun Gothic", 8), bg=C["card"],
                 fg=C["label"]).grid(row=row, column=2, sticky="w")


# ── Application ────────────────────────────────────────────────────────────────

class ACFApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("ACF 본딩 저항 예측기  v2.0  [3D]")
        self.geometry("1080x720")
        self.minsize(860, 600)
        self.configure(bg=C["bg"])
        _setup_style()

        self._q       = queue.Queue()
        self._running = False
        self._last    = None          # last result dict (for Save)

        self._build_menu()
        self._build_ui()
        self._poll()

    # ── Menu ──────────────────────────────────────────────────────────────────

    def _build_menu(self):
        mb = tk.Menu(self, tearoff=False)

        fm = tk.Menu(mb, tearoff=False)
        fm.add_command(label="결과 저장...",   command=self._save)
        fm.add_separator()
        fm.add_command(label="종료",           command=self.destroy)
        mb.add_cascade(label="파일", menu=fm)

        hm = tk.Menu(mb, tearoff=False)
        hm.add_command(label="사용법",     command=self._help)
        hm.add_command(label="버전 정보",  command=lambda: messagebox.showinfo(
            "버전 정보",
            "ACF 본딩 저항 예측기  v2.0  [3D 모델]\n\n"
            "3D Monte Carlo (직사각형 패드 + 비균일 압력)\n"
            "FEM 서로게이트 3-특징 (d, F, pos_factor)\n"
            "Holm 저항 (직사각형 spreading)\n\n"
            "© 2026"))
        mb.add_cascade(label="도움말", menu=hm)

        self.config(menu=mb)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Banner ────────────────────────────────────────────────────────────
        banner = tk.Frame(self, bg=C["header"], height=60)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        # right accent strip
        tk.Frame(banner, bg=C["header2"], width=200).pack(side="right", fill="y")
        # logo dot
        tk.Label(banner, text="●", font=("Malgun Gothic", 16),
                 fg=C["accent_l"], bg=C["header"]).pack(side="left", padx=(14, 4), pady=16)
        tk.Label(banner, text="ACF 본딩 저항 예측기",
                 font=("Malgun Gothic", 14, "bold"),
                 fg="white", bg=C["header"]).pack(side="left", pady=16)
        tk.Label(banner, text="   3D Monte Carlo  ·  FEM Surrogate (3-feat)  ·  ML Correction",
                 font=("Malgun Gothic", 8), fg="#a5b4fc", bg=C["header"]).pack(side="left")

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True)

        # LEFT sidebar (fixed 282 px, lavender tint)
        left = tk.Frame(body, bg=C["side"], width=282)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Frame(left, bg=C["border"], width=1).pack(side="right", fill="y")
        inner_left = tk.Frame(left, bg=C["side"])
        inner_left.pack(fill="both", expand=True, padx=10, pady=8)
        self._build_input(inner_left)

        # RIGHT panel
        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="right", fill="both", expand=True)
        inner_right = tk.Frame(right, bg=C["bg"])
        inner_right.pack(fill="both", expand=True, padx=10, pady=8)
        self._build_results(inner_right)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = tk.Frame(self, bg=C["header"], height=22)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        self._sv = tk.StringVar(value="  준비됨")
        tk.Label(sb, textvariable=self._sv, font=("Malgun Gothic", 7),
                 bg=C["header"], fg="#a5b4fc", anchor="w").pack(side="left", padx=10)

    # ── Input panel ───────────────────────────────────────────────────────────

    def _build_input(self, p):
        # Substrate / bump geometry
        o, c = _card(p, "기판 / 범프 형상", stripe=C["accent"])
        o.pack(fill="x", pady=(0, 5))

        tk.Label(c, text="기판 종류", font=FB, bg=C["card"],
                 fg=C["muted"]).grid(row=0, column=0, sticky="w", pady=3)
        self.v_sub = tk.StringVar(value="glass (COG)")
        ttk.Combobox(c, textvariable=self.v_sub,
                     values=["glass (COG)", "YOUM (OLED)", "Flexible (FOP)", "flex (FOF)", "PCB (COB)"],
                     state="readonly", width=16).grid(
                         row=0, column=1, columnspan=2, padx=(4, 0), pady=3, sticky="w")

        self.v_pad_w  = tk.DoubleVar(value=13.0)
        self.v_pad_h  = tk.DoubleVar(value=110.0)
        self.v_pitch  = tk.DoubleVar(value=14.0)
        _row(c, 1, "패드 폭  (W)", self.v_pad_w,  "μm")
        _row(c, 2, "패드 높이 (H)", self.v_pad_h, "μm")
        _row(c, 3, "범프 피치",    self.v_pitch,  "μm")

        # Process conditions
        o2, c2 = _card(p, "공정 조건", stripe=C["accent_l"])
        o2.pack(fill="x", pady=(0, 5))

        self.v_T = tk.DoubleVar(value=180.0)
        self.v_P = tk.DoubleVar(value=2.0)
        self.v_t = tk.DoubleVar(value=10.0)
        _row(c2, 0, "본딩 온도", self.v_T, "°C")
        _row(c2, 1, "본딩 압력", self.v_P, "MPa")
        _row(c2, 2, "접합 시간", self.v_t, "s")

        # MC settings
        o3, c3 = _card(p, "시뮬레이션 설정", stripe=C["accent_l"])
        o3.pack(fill="x", pady=(0, 5))

        tk.Label(c3, text="Monte Carlo 횟수", font=FB,
                 bg=C["card"], fg=C["muted"]).pack(anchor="w")
        self.v_nr = tk.IntVar(value=2000)
        sr = tk.Frame(c3, bg=C["card"])
        sr.pack(fill="x", pady=(3, 0))
        ttk.Scale(sr, from_=500, to=10000, variable=self.v_nr,
                  orient="horizontal").pack(side="left", fill="x", expand=True)
        self._nrlbl = tk.Label(sr, text="2000", width=5, font=FM,
                                bg=C["card"], fg=C["accent"])
        self._nrlbl.pack(side="left")
        self.v_nr.trace_add("write",
            lambda *_: self._nrlbl.config(text=str(self.v_nr.get())))

        # ── Action buttons ────────────────────────────────────────────────────
        tk.Frame(p, bg=C["border"], height=1).pack(fill="x", pady=(6, 6))
        self.btn_run = tk.Button(
            p, text="▶   예측 시작",
            font=("Malgun Gothic", 11, "bold"),
            bg=C["accent"], fg="white",
            activebackground="#3730a3", activeforeground="white",
            relief="flat", cursor="hand2", pady=9, command=self._start)
        self.btn_run.pack(fill="x", pady=(0, 3))

        self.btn_save = tk.Button(
            p, text="↓   결과 저장",
            font=FH, bg=C["green"], fg="white",
            activebackground="#047857", activeforeground="white",
            relief="flat", cursor="hand2", pady=6, state="disabled",
            command=self._save)
        self.btn_save.pack(fill="x", pady=(0, 6))

        # ── Threshold guide (compact colored chips) ───────────────────────────
        o4, c4 = _card(p, "판정 기준", stripe=C["muted"])
        o4.pack(fill="x")
        for dot, txt, bg, fg in [
            ("●", " 우수   R < 2 Ω",    C["green_bg"],  C["green"]),
            ("●", " 양호   2 ~ 3 Ω",    C["orange_bg"], C["orange"]),
            ("●", " 불량   R ≥ 3 Ω",    C["red_bg"],    C["red"]),
        ]:
            chip = tk.Frame(c4, bg=bg, padx=6, pady=3)
            chip.pack(fill="x", pady=2)
            tk.Label(chip, text=dot, font=("Malgun Gothic", 9), bg=bg, fg=fg).pack(side="left")
            tk.Label(chip, text=txt,  font=FB,                  bg=bg, fg=fg).pack(side="left")

    # ── Results panel ─────────────────────────────────────────────────────────

    def _build_results(self, p):
        # ── Top row ───────────────────────────────────────────────────────────
        top = tk.Frame(p, bg=C["bg"])
        top.pack(fill="x", pady=(0, 6))

        # ── Progress stepper (left) ───────────────────────────────────────────
        po, pc = _card(top, "분석 파이프라인", stripe=C["accent"])
        po.pack(side="left", fill="y", padx=(0, 6), ipadx=4)

        self._icons = {}
        STEPS = [
            ("lit", "1", "논문 파라미터 로드"),
            ("mc",  "2", "Monte Carlo  (병렬)"),
            ("fem", "3", "FEM 접촉 해석  (병렬)"),
            ("ml",  "4", "ML 보정"),
        ]
        for key, num, lbl in STEPS:
            r = tk.Frame(pc, bg=C["card"])
            r.pack(fill="x", pady=3)
            # Numbered circle indicator
            icon = tk.Label(r, text=num, font=FLBL,
                            bg=C["border"], fg=C["muted"],
                            width=2, relief="flat", pady=2)
            icon.pack(side="left", padx=(0, 6))
            tk.Label(r, text=lbl, font=FB, bg=C["card"],
                     fg=C["muted"]).pack(side="left")
            self._icons[key] = icon

        self._pbar = ttk.Progressbar(pc, mode="indeterminate", length=210)
        self._pbar.pack(fill="x", pady=(8, 2))

        # ── Big resistance KPI (right) ────────────────────────────────────────
        ro, rc = _card(top, "예측 저항", stripe=C["accent"])
        ro.pack(side="right", fill="both", expand=True)

        kpi = tk.Frame(rc, bg=C["card"])
        kpi.pack(expand=True)
        self.lbl_val = tk.Label(kpi, text="--", font=FNUM,
                                 bg=C["card"], fg=C["accent"])
        self.lbl_val.pack()
        tk.Label(kpi, text="Ω", font=("Malgun Gothic", 11),
                 bg=C["card"], fg=C["muted"]).pack()
        self.lbl_ci = tk.Label(kpi, text="95% CI: --",
                                font=("Malgun Gothic", 8), bg=C["card"], fg=C["muted"])
        self.lbl_ci.pack(pady=(2, 0))
        self.lbl_verdict = tk.Label(kpi, text="",
                                     font=("Malgun Gothic", 10, "bold"), bg=C["card"])
        self.lbl_verdict.pack(pady=(4, 6))

        # ── Metric chips (2×3 grid) ───────────────────────────────────────────
        mo, mc_ = _card(p, "세부 분석 결과", stripe=C["accent_l"])
        mo.pack(fill="x", pady=(0, 6))

        self._mv = {}
        metrics = [
            ("N_eff",       "유효 입자 수", "n_eff"),
            ("R_contact",   "접촉 저항",    "r_con"),
            ("R_spread",    "퍼짐 저항",    "r_spr"),
            ("MC SEM",      "MC 수렴도",    "mc_cv"),
            ("FEM R²",      "FEM 정확도",   "fem_r2"),
            ("ML Mode",     "ML 보정 모드", "ml_mode"),
        ]
        for col in range(3):
            mc_.columnconfigure(col * 2, weight=1)
        for i, (short, label, key) in enumerate(metrics):
            col = (i % 3) * 2
            row = i // 3
            chip = tk.Frame(mc_, bg=C["accent_bg"], padx=7, pady=5)
            chip.grid(row=row, column=col, sticky="ew", padx=3, pady=3)
            tk.Label(chip, text=short.upper(), font=FLBL,
                     bg=C["accent_bg"], fg=C["label"]).pack(anchor="w")
            var = tk.StringVar(value="--")
            self._mv[key] = var
            tk.Label(chip, textvariable=var, font=("Malgun Gothic", 9, "bold"),
                     bg=C["accent_bg"], fg=C["text"]).pack(anchor="w")

        # ── Notebook ──────────────────────────────────────────────────────────
        nb = ttk.Notebook(p)
        nb.pack(fill="both", expand=True)

        tab_sum = tk.Frame(nb, bg=C["card"])
        tab_vis = tk.Frame(nb, bg=C["card"])
        tab_3d  = tk.Frame(nb, bg=C["card"])
        tab_sch = tk.Frame(nb, bg=C["card"])
        nb.add(tab_sum, text="  예측 요약  ")
        nb.add(tab_vis, text="  포획 분포  ")
        nb.add(tab_3d,  text="  3D 입자 분포  ")
        nb.add(tab_sch, text="  공정 개략도  ")

        self.txt = scrolledtext.ScrolledText(
            tab_sum, height=9, font=("Malgun Gothic", 9),
            state="disabled", wrap="word",
            bg=C["bg"], fg=C["text"],
            relief="flat", bd=0, insertbackground=C["accent"])
        self.txt.pack(fill="both", expand=True, padx=6, pady=6)

        self._build_hist_tab(tab_vis)
        self._build_3d_tab(tab_3d)
        self._build_schematic_tab(tab_sch)

    # ── Visualization tabs ────────────────────────────────────────────────────

    def _build_3d_tab(self, parent):
        """3D scatter of captured vs uncaptured particles in rectangular pad."""
        self._fig_3d = Figure(figsize=(5, 2.8), dpi=90, facecolor=C["bg"])
        self._ax_3d  = self._fig_3d.add_subplot(111, projection="3d")
        self._ax_3d.set_facecolor(C["bg"])
        self._ax_3d.text2D(0.5, 0.5, "예측 실행 후 표시됩니다",
                           ha="center", va="center",
                           transform=self._ax_3d.transAxes,
                           color=C["muted"], fontsize=10)
        self._fig_3d.tight_layout(pad=1.0)
        cv = FigureCanvasTkAgg(self._fig_3d, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        self._canvas_3d = cv

    def _update_3d(self, mc):
        ax = self._ax_3d
        ax.clear()
        ax.set_facecolor(C["bg"])
        self._fig_3d.set_facecolor(C["bg"])
        pad_w, pad_h = mc.pad_dims

        if mc.captured_xyz:
            cp = np.array(mc.captured_xyz)
            sz = np.clip(cp[:, 3] ** 2 * 4, 10, 120)
            ax.scatter(cp[:, 0], cp[:, 1], cp[:, 2],
                       c=C["green"], s=sz, alpha=0.85,
                       label=f"포획 ({len(cp)}개)", depthshade=True)

        if mc.free_xyz:
            fp = np.array(mc.free_xyz)
            sz = np.clip(fp[:, 3] ** 2 * 4, 5, 60)
            ax.scatter(fp[:, 0], fp[:, 1], fp[:, 2],
                       c=C["muted"], s=sz, alpha=0.35,
                       label="미포획", depthshade=True)

        # Rectangular pad boundary at z=0
        hw, hh = pad_w / 2, pad_h / 2
        corners_x = [-hw,  hw,  hw, -hw, -hw]
        corners_y = [-hh, -hh,  hh,  hh, -hh]
        ax.plot(corners_x, corners_y, [0] * 5,
                color=C["accent"], lw=1.5, linestyle="--", label=f"Pad {pad_w:.0f}×{pad_h:.0f} μm")

        ax.set_xlabel("X (μm)", fontsize=7, color=C["muted"])
        ax.set_ylabel("Y (μm)", fontsize=7, color=C["muted"])
        ax.set_zlabel("Z (μm)", fontsize=7, color=C["muted"])  # type: ignore[attr-defined]
        ax.tick_params(labelsize=6, colors=C["muted"])
        ax.set_title("3D 입자 분포 (샘플 1회)", fontsize=8, color=C["header"])
        ax.legend(fontsize=7, framealpha=0.7, loc="upper left")
        self._fig_3d.tight_layout(pad=1.0)
        self._canvas_3d.draw()

    def _build_hist_tab(self, parent):
        """Particle capture count histogram (matplotlib embedded)."""
        self._fig_hist = Figure(figsize=(5, 2.8), dpi=90, facecolor=C["bg"])
        self._ax_hist  = self._fig_hist.add_subplot(111)
        self._ax_hist.set_facecolor(C["bg"])
        self._ax_hist.text(0.5, 0.5, "예측 실행 후 표시됩니다",
                           ha="center", va="center",
                           transform=self._ax_hist.transAxes,
                           color=C["muted"], fontsize=10)
        self._ax_hist.set_axis_off()
        self._fig_hist.tight_layout(pad=1.2)
        cv = FigureCanvasTkAgg(self._fig_hist, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        self._canvas_hist = cv

    def _build_schematic_tab(self, parent):
        """ACF bonding process cross-section schematic."""
        self._fig_sch = Figure(figsize=(5, 2.8), dpi=90, facecolor=C["bg"])
        self._ax_sch  = self._fig_sch.add_subplot(111)
        self._draw_schematic(substrate="glass (COG)", n_captured=5)
        cv = FigureCanvasTkAgg(self._fig_sch, master=parent)
        cv.get_tk_widget().pack(fill="both", expand=True)
        self._canvas_sch = cv

    def _draw_schematic(self, substrate="glass (COG)", n_captured=5,
                        n_free=12, bump_dia=30.0):
        ax = self._ax_sch
        ax.clear()
        ax.set_xlim(0, 10); ax.set_ylim(0, 7)
        ax.set_aspect("equal"); ax.axis("off")
        ax.set_facecolor(C["bg"])
        self._fig_sch.set_facecolor(C["bg"])

        sub = substrate.lower()
        if "youm" in sub or "oled" in sub:
            sub_color, sub_label = "#7c3aed", "YOUM (PI/Al)"
        elif "flex" in sub or "fop" in sub or "fof" in sub:
            sub_color, sub_label = "#0891b2", "Flexible (PI)"
        elif "pcb" in sub or "cob" in sub:
            sub_color, sub_label = "#065f46", "PCB (FR4/Cu)"
        else:
            sub_color, sub_label = "#475569", "Glass (COG)"

        # Bottom substrate
        ax.add_patch(mpatches.FancyBboxPatch((0.3, 0.2), 9.4, 1.0,
            boxstyle="round,pad=0.05", fc=sub_color, ec="none", alpha=0.85, zorder=1))
        # Bottom pad (Au/Al)
        ax.add_patch(mpatches.FancyBboxPatch((3.5, 1.2), 3.0, 0.4,
            boxstyle="square,pad=0", fc="#fbbf24", ec="#b45309", lw=1, zorder=2))

        # ACF film layer
        ax.add_patch(mpatches.FancyBboxPatch((0.3, 1.6), 9.4, 2.2,
            boxstyle="round,pad=0.05", fc="#bfdbfe", ec="#93c5fd", lw=0.8,
            alpha=0.55, zorder=3))

        # Top bump (IC side)
        bx, bw, bh = 4.0, 2.0, 1.1
        ax.add_patch(mpatches.FancyBboxPatch((bx, 3.8), bw, bh,
            boxstyle="round,pad=0.06", fc="#fde68a", ec="#b45309", lw=1.2, zorder=4))
        ax.add_patch(mpatches.FancyBboxPatch((0.3, 4.9), 9.4, 0.9,
            boxstyle="round,pad=0.05", fc="#94a3b8", ec="none", alpha=0.7, zorder=4))

        # Captured particles (under bump — green)
        rng = np.random.default_rng(42)
        for _ in range(max(1, n_captured)):
            cx = rng.uniform(bx + 0.15, bx + bw - 0.15)
            cy = rng.uniform(1.75, 3.65)
            r  = rng.uniform(0.14, 0.22)
            ax.add_patch(mpatches.Circle((cx, cy), r,
                fc="#16a34a", ec="#166534", lw=0.7, zorder=5))

        # Free (non-captured) particles (gray)
        for _ in range(n_free):
            cx = rng.choice(
                [rng.uniform(0.5, bx - 0.15), rng.uniform(bx + bw + 0.15, 9.8)])
            cy = rng.uniform(1.75, 3.65)
            r  = rng.uniform(0.10, 0.18)
            ax.add_patch(mpatches.Circle((cx, cy), r,
                fc="#94a3b8", ec="#475569", lw=0.5, alpha=0.7, zorder=5))

        # Labels
        ax.text(5.0, 5.35, "IC 칩 (상부 전극)", ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold", zorder=6)
        ax.text(5.0, 4.25, f"금속 범프  ({bump_dia:.0f} μm 등가)", ha="center", va="center",
                fontsize=7, color="#78350f", zorder=6)
        ax.text(5.0, 2.65, "ACF 필름", ha="center", va="center",
                fontsize=7, color="#1e40af", alpha=0.8, zorder=6)
        ax.text(5.0, 0.70, sub_label, ha="center", va="center",
                fontsize=7.5, color="white", fontweight="bold", zorder=6)

        # Legend
        handles = [
            mpatches.Patch(fc="#16a34a", ec="#166534", label=f"포획 입자 (~{n_captured}개)"),
            mpatches.Patch(fc="#94a3b8", ec="#475569", alpha=0.8, label="미포획 입자"),
        ]
        ax.legend(handles=handles, loc="upper left", fontsize=6.5,
                  framealpha=0.8, edgecolor="#cbd5e1")

        # Arrows (pressure direction)
        for xp in [1.2, 8.8]:
            ax.annotate("", xy=(xp, 4.95), xytext=(xp, 5.5),
                        arrowprops=dict(arrowstyle="->", color="#1a2f4a", lw=1.2))
        ax.text(1.05, 5.65, "P↓", fontsize=7, color="#1a2f4a")
        ax.text(8.65, 5.65, "P↓", fontsize=7, color="#1a2f4a")

        self._fig_sch.tight_layout(pad=0.8)
        self._canvas_sch.draw() if hasattr(self, "_canvas_sch") else None

    # ── Simulation ────────────────────────────────────────────────────────────

    def _start(self):
        if self._running:
            return
        self._running = True
        self.btn_run.config(state="disabled", text="  실행 중...")
        self.btn_save.config(state="disabled")
        self._pbar.start(12)
        self._status("예측 실행 중...")

        for k in self._icons:
            self._icon(k, "wait")
        self.lbl_val.config(text="--", fg=C["text"])
        self.lbl_ci.config(text="95% CI: --")
        self.lbl_verdict.config(text="")
        for v in self._mv.values():
            v.set("--")
        self._write("시뮬레이션 실행 중입니다. 잠시 기다려 주세요...")

        a = _Args()
        a.T          = self.v_T.get()
        a.P          = self.v_P.get()
        a.t          = self.v_t.get()
        a.pad_w      = self.v_pad_w.get()
        a.pad_h      = self.v_pad_h.get()
        a.bump_dia   = float(np.sqrt(a.pad_w * a.pad_h))  # area-equiv (compat)
        a.bump_pitch = self.v_pitch.get()
        a.substrate  = self.v_sub.get()
        a.n_runs     = self.v_nr.get()

        threading.Thread(target=self._worker, args=(a,), daemon=True).start()

    def _worker(self, args):
        try:
            # Step 1 — Literature
            self._q.put(("step", "lit", "run"))
            lit = LiteratureParams.for_process(args.T, args.P, args.substrate, args.t)
            self._q.put(("step", "lit", "ok"))

            # Steps 2 + 3 — Parallel
            self._q.put(("step", "mc",  "run"))
            self._q.put(("step", "fem", "run"))

            A_m2   = (args.pad_w * 1e-6) * (args.pad_h * 1e-6)   # rectangular pad
            V_mean = (np.pi / 6.0) * (lit.d_mean * 1e-6) ** 3
            n_est  = max(1.0, lit.phi * A_m2 * 25e-6 / V_mean)

            with ThreadPoolExecutor(max_workers=2) as ex:
                mc_f  = ex.submit(run_monte_carlo,  lit, args, args.n_runs)
                fem_f = ex.submit(run_fem_surrogate, lit, None, args, n_est)
                mc    = mc_f.result()
                fem   = fem_f.result()

            self._q.put(("step", "mc",  "ok" if mc.converged  else "warn"))
            self._q.put(("step", "fem", "ok" if fem.r2 > 0.95 else "warn"))

            # Step 4 — ML correction
            self._q.put(("step", "ml", "run"))
            cal = os.path.join(_dir, "calibration.json")
            corr = ACFMLCorrector(cal if os.path.exists(cal) else None).correct(mc, fem, args)
            self._q.put(("step", "ml", "ok"))

            res = compute_resistance(lit, mc, fem, args,
                                     corr.corrected_N_eff, corr.corrected_a_um)
            self._q.put(("done", lit, mc, fem, corr, res, args))

        except Exception as exc:
            import traceback
            self._q.put(("error", traceback.format_exc()))

    # ── Queue poll ────────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                m = self._q.get_nowait()
                if m[0] == "step":
                    self._icon(m[1], m[2])
                elif m[0] == "done":
                    self._show(*m[1:])
                elif m[0] == "error":
                    messagebox.showerror("시뮬레이션 오류", m[1])
                    self._done()
        except queue.Empty:
            pass
        self.after(40, self._poll)

    # ── Result display ────────────────────────────────────────────────────────

    _STEP_NUMS = {"lit": "1", "mc": "2", "fem": "3", "ml": "4"}
    _STEP_STYLE = {
        "wait": (C["border"],   C["muted"]),
        "run":  (C["accent"],   "white"),
        "ok":   (C["green"],    "white"),
        "warn": (C["orange"],   "white"),
        "fail": (C["red"],      "white"),
    }

    def _icon(self, key, state):
        num = self._STEP_NUMS.get(key, "?")
        bg, fg = self._STEP_STYLE.get(state, self._STEP_STYLE["wait"])
        self._icons[key].config(text=num, bg=bg, fg=fg)

    def _show(self, lit, mc, fem, corr, res, args):
        R   = res.R_total_mean   # Ω
        lo  = res.ci_95_lower
        hi  = res.ci_95_upper

        if R < 2.0:
            clr, verdict, vbg = C["green"],  "✅  우수  —  2 Ω 미만, 최적",         C["green_bg"]
        elif R < 3.0:
            clr, verdict, vbg = C["orange"], "🔶  양호  —  목표 기준 이내 (≤ 3 Ω)", C["orange_bg"]
        else:
            clr, verdict, vbg = C["red"],    "❌  불량  —  3 Ω 초과, 공정 재검토",   C["red_bg"]

        self.lbl_val.config(text=f"{R:.2f}", fg=clr)
        self.lbl_ci.config(text=f"95% CI :  {lo:.2f} ~ {hi:.2f} Ω")
        self.lbl_verdict.config(text=verdict, fg=clr, bg=vbg, padx=8, pady=3)

        self._mv["n_eff"].set(   f"{res.N_eff:.2f}개 / 범프")
        self._mv["r_con"].set(   f"{res.R_contact_mean:.3f} Ω")
        self._mv["r_spr"].set(   f"{res.R_spreading*1000:.3f} mΩ")
        self._mv["mc_cv"].set(   f"{mc.cv_final:.4f}  {'✅' if mc.converged else '⚠️'}")
        self._mv["fem_r2"].set(  f"{fem.r2:.4f}  {'✅' if fem.r2>0.95 else '⚠️'}")
        self._mv["ml_mode"].set( corr.mode)

        quality = ("높음"  if mc.converged and fem.r2 > 0.95 and corr.mode == "ml_corrected"
               else "보통" if mc.converged and fem.r2 > 0.95
               else "낮음")

        warns = []
        if not mc.converged:
            warns.append(f"Monte Carlo 미수렴 — MC 횟수를 늘리세요 (현재 {args.n_runs}회)")
        if fem.r2 <= 0.95:
            warns.append(f"FEM 정확도 낮음 (R²={fem.r2:.3f})")
        if corr.mode != "ml_corrected":
            warns.append("ML 보정 비활성 — calibration.json에 실측 데이터 추가 시 정확도 향상")

        if R < 2.0:
            advice = (f"예측 저항 {R:.2f} Ω로 최적 수준(< 2 Ω)입니다. "
                      "현재 공정 조건이 우수합니다.")
        elif R < 3.0:
            advice = (f"예측 저항 {R:.2f} Ω로 목표 기준(≤ 3 Ω) 이내입니다. "
                      f"압력 {args.P+2:.0f} MPa 또는 온도 {args.T+5:.0f}°C 조정 시 2 Ω 미만 달성 가능합니다.")
        else:
            advice = (f"예측 저항 {R:.2f} Ω로 불량 기준(≥ 3 Ω)을 초과합니다. "
                      "압력 증가, 본딩 온도 상향(~185°C), 또는 입자 체적분율 재검토가 필요합니다.")

        summary = (
            f"■ 분석 조건  [3D 모델]\n"
            f"  기판: {args.substrate}  |  패드: {args.pad_w:.0f}×{args.pad_h:.0f} μm  |  "
            f"피치: {args.bump_pitch:.0f} μm\n"
            f"  T = {args.T:.0f}°C  /  P = {args.P:.1f} MPa  /  t = {args.t:.0f} s\n\n"
            f"■ 예측 결과\n"
            f"  총 저항     :  {R:.2f} Ω\n"
            f"  신뢰구간   :  {lo:.2f} ~ {hi:.2f} Ω  (95%)\n"
            f"  유효 입자  :  {res.N_eff:.1f}개 / 범프  "
            f"(포획률 {mc.capture_rate*100:.0f}%)\n\n"
            f"■ 모델 품질  :  {quality}\n"
        )
        if warns:
            summary += "\n⚠ 주의 사항\n" + "\n".join(f"  • {w}" for w in warns)
        summary += f"\n\n💡 {advice}"

        self._write(summary)
        self._update_hist(mc)
        self._update_3d(mc)
        self._update_schematic(mc, args)
        self._status(f"예측 완료  —  총 저항 {R:.2f} Ω")

        self._last = dict(lit=lit, mc=mc, fem=fem, corr=corr, res=res,
                          args=args, summary=summary, R=R, lo=lo, hi=hi)
        self.btn_save.config(state="normal")
        self._done()

    def _update_hist(self, mc):
        ax = self._ax_hist
        ax.clear()
        counts = mc.cap_counts if mc.cap_counts else []
        if counts:
            ax.hist(counts, bins=30, color=C["accent"], edgecolor=C["accent_l"],
                    alpha=0.80, rwidth=0.88)
            ax.axvline(mc.particles_mean, color=C["red"], lw=1.5,
                       linestyle="--", label=f"평균 {mc.particles_mean:.1f}개")
            ax.set_xlabel("포획 입자 수 (개/범프)", fontsize=8, color=C["text"])
            ax.set_ylabel("빈도 (runs)", fontsize=8, color=C["text"])
            ax.set_title(
                f"Monte Carlo 입자 포획 분포  (n={mc.n_runs_actual}, "
                f"포획률 {mc.capture_rate*100:.0f}%)",
                fontsize=8.5, color=C["header"])
            ax.legend(fontsize=8, framealpha=0.7)
            ax.tick_params(labelsize=7, colors=C["muted"])
            for spine in ax.spines.values():
                spine.set_edgecolor(C["border"])
        else:
            ax.text(0.5, 0.5, "데이터 없음", ha="center", va="center",
                    transform=ax.transAxes, color=C["muted"])
        ax.set_facecolor(C["bg"])
        self._fig_hist.set_facecolor(C["bg"])
        self._fig_hist.tight_layout(pad=1.2)
        self._canvas_hist.draw()

    def _update_schematic(self, mc, args):
        self._draw_schematic(
            substrate=args.substrate,
            n_captured=max(1, int(round(mc.particles_mean))),
            n_free=max(2, int(round(mc.particles_mean / max(0.01, mc.capture_rate) * (1 - mc.capture_rate)))),
            bump_dia=args.bump_dia,  # area-equiv for schematic scale
        )

    def _done(self):
        self._running = False
        self._pbar.stop()
        self.btn_run.config(state="normal", text="▶   예측 시작")

    def _write(self, txt):
        self.txt.config(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.insert("end", txt)
        self.txt.config(state="disabled")

    def _status(self, msg):
        self._sv.set(f"  {msg}")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self):
        if not self._last:
            return
        d    = self._last
        args = d["args"]; mc = d["mc"]; fem = d["fem"]
        res  = d["res"];  corr = d["corr"]
        ts   = datetime.now().strftime("%Y%m%d_%H%M%S")

        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
            initialfile=f"ACF_결과_{ts}.txt",
            title="결과 파일 저장")
        if not path:
            return

        report = (
            f"ACF 본딩 저항 예측 결과 보고서\n"
            f"생성 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"{'='*54}\n\n"
            f"[입력 조건]  (3D 직사각형 패드 모델)\n"
            f"  기판       : {args.substrate}\n"
            f"  패드 치수  : {args.pad_w:.0f} × {args.pad_h:.0f} μm\n"
            f"  범프 피치  : {args.bump_pitch} μm\n"
            f"  본딩 온도  : {args.T} °C\n"
            f"  본딩 압력  : {args.P} MPa\n"
            f"  접합 시간  : {args.t} s\n\n"
            f"[예측 결과]\n"
            f"  총 저항    : {d['R']:.2f} Ω\n"
            f"  95% CI     : {d['lo']:.2f} ~ {d['hi']:.2f} Ω\n"
            f"  접촉 저항  : {res.R_contact_mean:.3f} Ω\n"
            f"  퍼짐 저항  : {res.R_spreading*1000:.3f} mΩ\n"
            f"  유효 입자  : {res.N_eff:.2f}개 / 범프\n"
            f"  포획률     : {mc.capture_rate*100:.1f} %\n"
            f"  MC 수렴도  : {mc.cv_final:.4f}  ({'수렴' if mc.converged else '미수렴'})\n"
            f"  FEM R²     : {fem.r2:.4f}\n"
            f"  ML 모드    : {corr.mode}\n\n"
            f"[요약]\n{d['summary']}\n"
        )
        try:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(report)
            messagebox.showinfo("저장 완료", f"결과가 저장되었습니다:\n{path}")
        except Exception as e:
            messagebox.showerror("저장 실패", str(e))

    # ── Help ──────────────────────────────────────────────────────────────────

    def _help(self):
        messagebox.showinfo(
            "사용법",
            "1. 기판 종류 및 범프 형상을 입력하세요.\n"
            "2. 공정 조건 (온도 / 압력 / 시간) 을 설정하세요.\n"
            "3. Monte Carlo 횟수를 조절하세요 (기본 2000회).\n"
            "4. '예측 시작' 버튼을 누르면 자동으로 계산됩니다.\n\n"
            "● 정확도를 높이려면 calibration.json에\n"
            "  실측 저항 데이터를 3건 이상 추가하세요.\n\n"
            "판정 기준\n"
            "  ✅ 우수 : R < 2 Ω\n"
            "  🔶 양호 : 2 ~ 3 Ω  (목표 이내)\n"
            "  ❌ 불량 : R ≥ 3 Ω"
        )


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = ACFApp()
    app.mainloop()
