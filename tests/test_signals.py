import numpy as np
import pandas as pd

from adp.signals.model import FactorModel, information_coefficient


def test_ic_detects_strong_positive_relationship():
    rng = np.random.default_rng(0)
    rows = []
    for d in pd.date_range("2025-01-01", periods=10, freq="MS"):
        for i in range(20):
            v = rng.normal()
            rows.append(
                {
                    "feature_date": d.date(),
                    "ticker": f"T{i}",
                    "value": v,
                    "fwd_ret": v * 0.1 + rng.normal(0, 0.005),
                }
            )
    df = pd.DataFrame(rows)
    ic = information_coefficient(
        df[["feature_date", "ticker", "value"]],
        df[["feature_date", "ticker", "fwd_ret"]],
    )
    assert ic.attrs["mean_ic"] > 0.7
    assert ic.attrs["n_periods"] == 10


def test_factor_model_blends_and_standardizes():
    panel = pd.DataFrame(
        {
            "feature_date": ["2025-01-01"] * 4,
            "ticker": ["A", "B", "C", "D"],
            "feature_name": ["f1"] * 4,
            "value": [1.0, 2.0, 3.0, 4.0],
        }
    )
    out = FactorModel({"f1": 1.0}).score(panel)
    assert set(out.columns) == {"feature_date", "ticker", "score"}
    assert abs(out["score"].mean()) < 1e-9  # z-scored -> mean ~0
