"""Aggregate-only summaries. Never returns or prints individual rows."""

import pandas as pd

MIN_GROUP_SIZE = 5


def summarise(df: pd.DataFrame, by: str, value: str) -> pd.DataFrame:
    """Count, mean and total of `value` per `by`, hiding groups smaller than MIN_GROUP_SIZE."""
    out = df.groupby(by)[value].agg(count="count", mean="mean", total="sum").reset_index()
    small = out["count"] < MIN_GROUP_SIZE
    out.loc[small, ["mean", "total"]] = float("nan")
    return out.round(2)


def overview(df: pd.DataFrame) -> dict:
    """Shape and column types only."""
    return {
        "rows": len(df),
        "columns": {c: str(t) for c, t in df.dtypes.items()},
        "missing": {c: int(n) for c, n in df.isna().sum().items() if n},
    }
