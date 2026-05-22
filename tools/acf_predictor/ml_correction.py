"""
ACF ML Correction Layer
XGBoost correction factor + GP uncertainty. Falls back to physics_only if
fewer than 3 calibration points or xgboost not installed.
"""
import json
import numpy as np
from dataclasses import dataclass
from typing import Optional

from simulation import MonteCarloResult, FEMResult


@dataclass
class CorrectionResult:
    mode: str               # "ml_corrected" | "physics_only"
    correction_factor: float
    cf_lower_95: float
    cf_upper_95: float
    confidence: float
    corrected_N_eff: float
    corrected_a_um: float
    loo_cv_r2: Optional[float] = None


class ACFMLCorrector:
    def __init__(self, calibration_file: Optional[str] = None):
        self.calibration_data = []
        if calibration_file:
            try:
                with open(calibration_file) as f:
                    self.calibration_data = json.load(f)
            except Exception as e:
                print(f"  [ML] 보정 파일 로드 실패: {e} → physics_only 사용")

    def _build_features(self, mc: MonteCarloResult, fem: FEMResult, args) -> list:
        cv = mc.capture_rate_std / (mc.capture_rate + 1e-9)
        return [
            mc.capture_rate,
            mc.particles_mean,
            mc.contact_area_mean,
            cv,
            fem.contact_radius_mean,
            fem.contact_stress_mean,
            fem.deformation_mean,
            fem.r2,
            args.T,
            args.P,
            args.t,
            args.bump_dia,
            args.T * args.P,
            mc.particles_mean * fem.contact_radius_mean ** 2,
        ]

    def correct(self, mc: MonteCarloResult, fem: FEMResult, args) -> CorrectionResult:
        n_cal = len(self.calibration_data)

        if n_cal < 3:
            return CorrectionResult(
                mode="physics_only",
                correction_factor=1.0,
                cf_lower_95=0.7,
                cf_upper_95=1.3,
                confidence=0.5,
                corrected_N_eff=mc.particles_mean * mc.capture_rate,
                corrected_a_um=fem.contact_radius_mean,
            )

        try:
            import xgboost as xgb
            from sklearn.gaussian_process import GaussianProcessRegressor
            from sklearn.gaussian_process.kernels import Matern, WhiteKernel
            from sklearn.preprocessing import StandardScaler
            from sklearn.model_selection import LeaveOneOut, cross_val_score
        except ImportError:
            return CorrectionResult(
                mode="physics_only",
                correction_factor=1.0,
                cf_lower_95=0.7,
                cf_upper_95=1.3,
                confidence=0.5,
                corrected_N_eff=mc.particles_mean * mc.capture_rate,
                corrected_a_um=fem.contact_radius_mean,
            )

        X_feat = self._build_features(mc, fem, args)
        X_train, y_train = [], []
        for cal in self.calibration_data:
            ratio = cal["measured_R_Ohm"] / (cal.get("physics_R_Ohm", cal["measured_R_Ohm"]) + 1e-12)
            X_train.append(X_feat)
            y_train.append(float(ratio))

        X = np.array(X_train)
        y = np.array(y_train)

        model = xgb.XGBRegressor(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            subsample=0.8, reg_alpha=0.1, reg_lambda=1.0,
            random_state=42, verbosity=0,
        )

        loo_r2 = None
        if len(X) >= 5:
            scores = cross_val_score(model, X, y, cv=LeaveOneOut(), scoring="r2")
            loo_r2 = float(np.mean(scores))

        model.fit(X, y)
        cf = float(np.clip(model.predict([X_feat])[0], 0.5, 2.0))

        scaler = StandardScaler()
        X_sc = scaler.fit_transform(X)
        gp = GaussianProcessRegressor(
            kernel=Matern(nu=2.5) + WhiteKernel(noise_level=0.01),
            n_restarts_optimizer=2, random_state=42,
        )
        gp.fit(X_sc, y - model.predict(X))
        x_sc = scaler.transform([X_feat])
        _, cf_std = gp.predict(x_sc, return_std=True)
        cf_std = float(cf_std[0])

        return CorrectionResult(
            mode="ml_corrected",
            correction_factor=cf,
            cf_lower_95=float(np.clip(cf - 1.96 * cf_std, 0.3, 3.0)),
            cf_upper_95=float(np.clip(cf + 1.96 * cf_std, 0.3, 3.0)),
            confidence=float(max(0.0, 1.0 - cf_std / (abs(cf) + 1e-9))),
            corrected_N_eff=mc.particles_mean * mc.capture_rate * float(np.sqrt(cf)),
            corrected_a_um=fem.contact_radius_mean * float(cf ** (1.0 / 3.0)),
            loo_cv_r2=loo_r2,
        )
