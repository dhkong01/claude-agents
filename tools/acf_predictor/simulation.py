"""
ACF Bonding Simulation Core  v2.0  —  3D Model
3D Monte Carlo (rectangular pad, non-uniform pressure) +
FEM surrogate (Jackson-Green + GP 3-feature: d, F, pos_factor) +
Holm resistance (rectangular spreading)
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable, List
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, WhiteKernel
from sklearn.preprocessing import StandardScaler
from scipy.stats import qmc

R_GAS = 8.314  # J/(mol·K)


# ── Data Classes ──────────────────────────────────────────────────────────────

@dataclass
class LiteratureParams:
    d_mean: float = 5.0
    d_std: float = 0.5
    phi: float = 0.10
    E_particle_GPa: float = 200.0
    H_particle_GPa: float = 2.5
    E_substrate_GPa: float = 110.0
    nu_particle: float = 0.31
    nu_substrate: float = 0.34
    rho_contact: float = 6.3e-12    # Ω·m² interface resistivity (calibrated)
    rho_metal: float = 1.7e-8       # Ω·m Cu pad
    eta0: float = 120.0
    Ea_kJ: float = 58.0
    n_sources: int = 6

    @classmethod
    def for_process(cls, T_C: float, P_MPa: float, substrate: str = "glass", t_s: float = 10.0) -> "LiteratureParams":
        p = cls()
        p.E_particle_GPa = max(155.0, 200.0 - 0.22 * max(0.0, T_C - 25.0))
        p.H_particle_GPa = max(0.7, 2.5 * np.exp(-0.0040 * max(0.0, T_C - 25.0)))
        time_factor = float(np.clip(np.exp(-0.020 * (t_s - 10.0)), 0.60, 1.40))
        p.rho_contact = float(np.clip(
            6.3e-12 * np.exp(-0.022 * (T_C - 180.0)) * time_factor, 2e-12, 2e-11))
        sub = substrate.lower()
        if "youm" in sub or "oled" in sub:
            p.E_substrate_GPa, p.nu_substrate, p.rho_metal = 55.0, 0.34, 2.7e-8
        elif "flex" in sub or "fof" in sub or "fop" in sub or "flexible" in sub:
            p.E_substrate_GPa, p.nu_substrate, p.rho_metal = 40.0, 0.38, 2.7e-8
        elif "pcb" in sub or "cob" in sub or "fr4" in sub:
            p.E_substrate_GPa, p.nu_substrate, p.rho_metal = 50.0, 0.36, 1.7e-8
        return p

    def viscosity(self, T_C: float) -> float:
        return self.eta0 * np.exp(self.Ea_kJ * 1000.0 / (R_GAS * (T_C + 273.15)))

    def E_star(self) -> float:
        inv = ((1 - self.nu_particle ** 2) / (self.E_particle_GPa * 1e9)
               + (1 - self.nu_substrate ** 2) / (self.E_substrate_GPa * 1e9))
        return 1.0 / inv


@dataclass
class MonteCarloResult:
    particles_mean: float
    particles_std: float
    capture_rate: float
    capture_rate_std: float
    contact_area_mean: float
    contact_area_std: float
    n_runs_actual: int
    converged: bool
    cv_final: float
    cap_counts: List[float] = field(default_factory=list)
    captured_xyz: List = field(default_factory=list)   # (x,y,z,d) one sample run
    free_xyz: List = field(default_factory=list)
    pad_dims: tuple = field(default_factory=lambda: (30.0, 30.0))  # (pad_w, pad_h) μm


@dataclass
class FEMResult:
    contact_radius_mean: float
    contact_radius_std: float
    contact_stress_mean: float
    deformation_mean: float
    r2: float
    n_features: int = 3             # 3D: (d, F, pos_factor)


@dataclass
class ResistanceResult:
    R_contact_mean: float
    R_contact_std: float
    R_spreading: float
    R_total_mean: float
    R_total_std: float
    ci_95_lower: float
    ci_95_upper: float
    N_eff: float


# ── 3D Particle Field ─────────────────────────────────────────────────────────

def _particle_field(domain_um, lit: LiteratureParams, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    vol = float(np.prod(domain_um))
    mean_vol = (np.pi / 6.0) * lit.d_mean ** 3
    n = int(rng.poisson(lit.phi * vol / mean_vol))
    if n == 0:
        return np.zeros((0, 4))
    pos = rng.uniform([0, 0, 0], domain_um, size=(n, 3))
    sigma2 = np.log(1 + (lit.d_std / lit.d_mean) ** 2)
    diams = rng.lognormal(np.log(lit.d_mean) - sigma2 / 2, np.sqrt(sigma2), n)
    diams = np.clip(diams, 0.5, 3 * lit.d_mean)
    return np.column_stack([pos, diams])


def _capture_3d(particles: np.ndarray, cx: float, cy: float,
                pad_w: float, pad_h: float, h_final: float,
                k_pressure: float = 0.15):
    """Rectangular capture + position-dependent gap (non-uniform pressure).
    Center: higher pressure → smaller h_eff → more captures.
    Returns (captured, free_in_footprint).
    """
    if len(particles) == 0:
        return particles, particles

    x, y, d = particles[:, 0], particles[:, 1], particles[:, 3]
    half_w, half_h = pad_w / 2.0, pad_h / 2.0
    in_fp = (np.abs(x - cx) <= half_w) & (np.abs(y - cy) <= half_h)

    x_n = np.where(in_fp, (x - cx) / (half_w + 1e-12), 0.0)
    y_n = np.where(in_fp, (y - cy) / (half_h + 1e-12), 0.0)
    p_factor = np.clip(1.0 + k_pressure * (1.0 - x_n ** 2 - y_n ** 2), 0.80, 1.20)
    h_eff = h_final / p_factor

    mask_cap  = in_fp & (d > h_eff)
    mask_free = in_fp & ~(d > h_eff)
    return particles[mask_cap], particles[mask_free]


# ── Monte Carlo ───────────────────────────────────────────────────────────────

def run_monte_carlo(
    lit: LiteratureParams,
    args,
    n_runs: int = 5000,
    cv_threshold: float = 0.05,
    progress_callback: Optional[Callable[[int, float], None]] = None,
) -> MonteCarloResult:
    _bd   = float(getattr(args, "bump_dia", 30.0))
    pad_w = float(getattr(args, "pad_w", _bd))
    pad_h = float(getattr(args, "pad_h", _bd))
    cx, cy = pad_w * 1.5, pad_h * 1.5
    domain = [pad_w * 3, pad_h * 3, 3.0 * lit.d_mean]

    T_ref_mc = 175.0
    visc_ratio = np.exp(
        lit.Ea_kJ * 1000.0 / R_GAS
        * (1.0 / (args.T + 273.15) - 1.0 / (T_ref_mc + 273.15))
    )
    gap_visc_mult  = float(np.clip(visc_ratio ** 0.13, 0.78, 1.35))
    cure_penalty   = float(np.clip(1.0 - 0.012 * max(0.0, args.T - 195.0), 0.55, 1.0))
    flow_time_mult = float(np.clip(1.0 - 0.015 * (args.t - 10.0), 0.75, 1.15))
    h_final = lit.d_mean * max(0.80, 1.15 - 0.05 * args.P) * gap_visc_mult * cure_penalty * flow_time_mult

    cap_counts, footprint_counts, areas = [], [], []
    _saved_cap: List = []
    _saved_free: List = []
    _sample_saved = False

    for i in range(n_runs):
        p = _particle_field(domain, lit, seed=i)

        fp_count = 0
        if len(p) > 0:
            x, y = p[:, 0], p[:, 1]
            in_fp = (np.abs(x - cx) <= pad_w / 2) & (np.abs(y - cy) <= pad_h / 2)
            fp_count = int(np.sum(in_fp))
        footprint_counts.append(fp_count)

        captured, free_fp = _capture_3d(p, cx, cy, pad_w, pad_h, h_final)
        cap_counts.append(len(captured))
        areas.append(float(np.sum(np.pi * (captured[:, 3] / 2) ** 2)) if len(captured) > 0 else 0.0)

        if not _sample_saved and i == 50:
            if len(captured) > 0:
                c = captured.copy(); c[:, 0] -= cx; c[:, 1] -= cy
                _saved_cap = c.tolist()
            if len(free_fp) > 0:
                f = free_fp.copy(); f[:, 0] -= cx; f[:, 1] -= cy
                _saved_free = f.tolist()
            _sample_saved = True

        if i >= 999 and i % 250 == 0:
            sem_rel = float(np.std(cap_counts) / (np.sqrt(len(cap_counts)) * (np.mean(cap_counts) + 1e-9)))
            if progress_callback:
                progress_callback(i + 1, sem_rel)
            if sem_rel < cv_threshold:
                break
        elif progress_callback and i % 50 == 0:
            sem_rel = float(np.std(cap_counts) / (np.sqrt(len(cap_counts)) * (np.mean(cap_counts) + 1e-9)))
            progress_callback(i + 1, sem_rel)

    counts    = np.array(cap_counts, dtype=float)
    fp_counts = np.array(footprint_counts, dtype=float)
    n_actual  = len(counts)
    cv_final  = float(np.std(counts) / (np.sqrt(n_actual) * (np.mean(counts) + 1e-9)))
    fp_mean   = max(1.0, float(np.mean(fp_counts)))
    cap_rate  = float(np.clip(np.mean(counts) / fp_mean, 0.05, 0.99))

    return MonteCarloResult(
        particles_mean=float(np.mean(counts)),
        particles_std=float(np.std(counts)),
        capture_rate=cap_rate,
        capture_rate_std=float(np.std(counts) / fp_mean),
        contact_area_mean=float(np.mean(areas)),
        contact_area_std=float(np.std(areas)),
        n_runs_actual=n_actual,
        converged=cv_final < cv_threshold,
        cv_final=cv_final,
        cap_counts=list(counts),
        captured_xyz=_saved_cap,
        free_xyz=_saved_free,
        pad_dims=(pad_w, pad_h),
    )


# ── FEM Surrogate (3D LHS: d, F, pos_factor) ─────────────────────────────────

def _jackson_green(d_um: float, F_uN: float, E_star_Pa: float, H_Pa: float):
    R = d_um / 2.0 * 1e-6
    F = F_uN * 1e-6
    if F < 1e-18 or R < 1e-15:
        return 0.01, 0.0, 0.0
    F_c = max((np.pi * H_Pa / (2.0 * E_star_Pa)) ** 2 * np.pi * H_Pa * R ** 2 / 6.0, 1e-18)
    if F <= F_c:
        a = (3.0 * F * R / (4.0 * E_star_Pa)) ** (1.0 / 3.0)
    else:
        a_h = (3.0 * F_c * R / (4.0 * E_star_Pa)) ** (1.0 / 3.0)
        a_p = np.sqrt(F / (np.pi * H_Pa))
        t   = float(np.clip((F / F_c - 1.0) / 20.0, 0.0, 1.0))
        a   = a_h * (1.0 - t) + a_p * t
    delta  = a ** 2 / R
    p_mean = F / (np.pi * a ** 2) if a > 1e-15 else 0.0
    return float(a * 1e6), float(p_mean * 1e-6), float(delta * 1e9)


def run_fem_surrogate(
    lit: LiteratureParams,
    mc: Optional[MonteCarloResult],
    args,
    n_est_override: Optional[float] = None,
) -> FEMResult:
    E_star = lit.E_star()
    H_Pa   = lit.H_particle_GPa * 1e9

    _bd   = float(getattr(args, "bump_dia", 30.0))
    pad_w = float(getattr(args, "pad_w", _bd))
    pad_h = float(getattr(args, "pad_h", _bd))
    A_pad = (pad_w * 1e-6) * (pad_h * 1e-6)

    if n_est_override is not None:
        n_particles = max(1.0, n_est_override)
    elif mc is not None:
        n_particles = max(1.0, mc.particles_mean)
    else:
        n_particles = max(1.0, lit.phi * A_pad * 25e-6 / ((np.pi / 6.0) * (lit.d_mean * 1e-6) ** 3))

    F_per_uN = (args.P * 1e6 * A_pad * 1e6) / n_particles

    # 3D LHS: (d, F_base, pos_factor)
    pos_lo, pos_hi = 0.85, 1.15
    sampler = qmc.LatinHypercube(d=3, seed=42)
    raw = sampler.random(n=300)
    d_lo = max(0.5, lit.d_mean - 3 * lit.d_std)
    d_hi = lit.d_mean + 3 * lit.d_std
    F_lo = max(0.01, F_per_uN * 0.2)
    F_hi = F_per_uN * 4.0

    X_tr, y_tr = [], []
    rng = np.random.default_rng(0)
    for s in raw:
        d_s   = d_lo + s[0] * (d_hi - d_lo)
        F_base = F_lo + s[1] * (F_hi - F_lo)
        pos_f  = pos_lo + s[2] * (pos_hi - pos_lo)
        a, _, _ = _jackson_green(d_s, F_base * pos_f, E_star, H_Pa)
        a = max(0.01, a + rng.normal(0, 0.02 * a))
        X_tr.append([d_s, F_base, pos_f])
        y_tr.append(a)

    X = np.array(X_tr); y = np.array(y_tr)
    scaler = StandardScaler()
    X_sc = scaler.fit_transform(X)
    gp = GaussianProcessRegressor(
        kernel=Matern(nu=2.5) + WhiteKernel(noise_level=1e-3),
        n_restarts_optimizer=3, random_state=42,
    )
    gp.fit(X_sc, y)

    rng2 = np.random.default_rng(1)
    sigma2 = np.log(1 + (lit.d_std / lit.d_mean) ** 2)
    d_samp   = np.clip(rng2.lognormal(np.log(lit.d_mean) - sigma2 / 2, np.sqrt(sigma2), 200),
                       0.5, 3 * lit.d_mean)
    pos_samp = rng2.uniform(pos_lo, pos_hi, 200)
    X_pred   = scaler.transform(np.column_stack([d_samp, np.full(200, F_per_uN), pos_samp]))
    a_pred, a_std = gp.predict(X_pred, return_std=True)

    y_tr_pred = gp.predict(X_sc)
    ss_res = float(np.sum((y - y_tr_pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    _, stress, deform = _jackson_green(lit.d_mean, F_per_uN, E_star, H_Pa)

    return FEMResult(
        contact_radius_mean=float(np.mean(np.abs(a_pred))),
        contact_radius_std=float(np.sqrt(np.mean(a_std ** 2) + np.var(a_pred))),
        contact_stress_mean=stress,
        deformation_mean=deform,
        r2=float(1.0 - ss_res / (ss_tot + 1e-15)),
        n_features=3,
    )


# ── Resistance (rectangular spreading) ───────────────────────────────────────

def compute_resistance(
    lit: LiteratureParams,
    mc: MonteCarloResult,
    fem: FEMResult,
    args,
    corrected_N_eff: Optional[float] = None,
    corrected_a_um: Optional[float] = None,
) -> ResistanceResult:
    N = max(0.01, corrected_N_eff if corrected_N_eff is not None else mc.particles_mean * mc.capture_rate)

    _bd   = float(getattr(args, "bump_dia", 30.0))
    pad_w = float(getattr(args, "pad_w", _bd))
    pad_h = float(getattr(args, "pad_h", _bd))
    A_pad = (pad_w * 1e-6) * (pad_h * 1e-6)

    F_per_uN = (args.P * 1e6 * A_pad * 1e6) / N
    a_phys_um, _, _ = _jackson_green(lit.d_mean, F_per_uN, lit.E_star(), lit.H_particle_GPa * 1e9)
    a_phys_um = max(0.01, a_phys_um)

    if corrected_a_um is not None and corrected_a_um > 0.01:
        a_um = a_phys_um * (corrected_a_um / max(0.01, fem.contact_radius_mean))
    else:
        a_um = a_phys_um
    a = max(1e-15, a_um * 1e-6)

    R_c_single = lit.rho_contact / (np.pi * a ** 2)
    R_contact  = R_c_single / N
    sigma_N    = mc.particles_std * mc.capture_rate
    dR_dN      = -R_c_single / N ** 2
    dR_da      = -2.0 * lit.rho_contact / (np.pi * a ** 3 * N)
    R_std      = float(np.sqrt((dR_dN * sigma_N) ** 2 + (dR_da * (fem.contact_radius_std * 1e-6)) ** 2))

    # Rectangular pad: equivalent-area spreading resistance
    R_spreading = lit.rho_metal / (2.0 * np.sqrt(np.pi * A_pad))
    R_total     = R_contact + R_spreading

    return ResistanceResult(
        R_contact_mean=R_contact,
        R_contact_std=R_std,
        R_spreading=R_spreading,
        R_total_mean=R_total,
        R_total_std=R_std,
        ci_95_lower=max(0.0, R_total - 1.96 * R_std),
        ci_95_upper=R_total + 1.96 * R_std,
        N_eff=N,
    )