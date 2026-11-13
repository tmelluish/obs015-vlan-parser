"""Synthetic data generator.

Edit the schema below to match the REAL column names and types (names and types
only, never real values). Tests and development use this instead of real files.
"""

import numpy as np
import pandas as pd


def make_fake_df(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame(
        {
            "id": np.arange(n),
            "region": rng.choice(["North", "South", "East", "West"], size=n),
            "category": rng.choice(["A", "B", "C"], size=n),
            "amount": rng.gamma(shape=2.0, scale=100.0, size=n).round(2),
            "date": pd.Timestamp("2025-01-01")
            + pd.to_timedelta(rng.integers(0, 365, size=n), unit="D"),
        }
    )
