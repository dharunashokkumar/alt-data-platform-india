"""Factor model + factor diagnostics (idea.md "turning features into signals").

- information_coefficient: cross-sectional Spearman corr of feature vs forward
  return, per date; the mean IC and its t-stat tell you if a feature predicts.
- FactorModel: linear combination of standardized features into one score.
  Deliberately an interface — swapping in gradient boosting later means one new
  class, not a rewrite (idea.md: linear OR ML combine).
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _zscore(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and not np.isnan(sd) else s * 0.0


def information_coefficient(
    features: pd.DataFrame, forward_returns: pd.DataFrame
) -> pd.DataFrame:
    """features: [feature_date, ticker, value]; forward_returns:
    [feature_date, ticker, fwd_ret]. Returns per-date IC + a summary attr.
    """
    m = features.merge(
        forward_returns, on=["feature_date", "ticker"], how="inner"
    )
    ics = (
        m.groupby("feature_date")
        .apply(
            lambda g: g["value"].corr(g["fwd_ret"], method="spearman")
            if len(g) >= 3
            else np.nan,
            include_groups=False,
        )
        .dropna()
        .rename("ic")
        .reset_index()
    )
    if not ics.empty:
        mean_ic = ics["ic"].mean()
        std_ic = ics["ic"].std(ddof=1)
        n = len(ics)
        ics.attrs["mean_ic"] = mean_ic
        ics.attrs["ic_ir"] = mean_ic / std_ic if std_ic else np.nan
        ics.attrs["t_stat"] = (
            mean_ic / std_ic * np.sqrt(n) if std_ic else np.nan
        )
        ics.attrs["n_periods"] = n
    return ics


class FactorModel:
    """Linear z-score blend. weights: {feature_name: weight}."""

    def __init__(self, weights: dict[str, float], model_version: str = "v1"):
        if not weights:
            raise ValueError("weights must be non-empty")
        self.weights = weights
        self.model_version = model_version

    def score(self, feature_panel: pd.DataFrame) -> pd.DataFrame:
        """feature_panel: [feature_date, ticker, feature_name, value]
        -> [feature_date, ticker, score] (cross-sectionally standardized)."""
        wide = feature_panel.pivot_table(
            index=["feature_date", "ticker"],
            columns="feature_name",
            values="value",
        ).reset_index()
        score = pd.Series(0.0, index=wide.index)
        for fname, w in self.weights.items():
            if fname not in wide:
                continue
            z = wide.groupby("feature_date")[fname].transform(_zscore)
            score = score + w * z.fillna(0.0)
        out = wide[["feature_date", "ticker"]].copy()
        out["score"] = score.values
        return out
