import pandas as pd

from analysis.fake import make_fake_df
from analysis.summarise import MIN_GROUP_SIZE, overview, summarise


def test_summarise_has_one_row_per_group():
    df = make_fake_df()
    out = summarise(df, "region", "amount")
    assert set(out["region"]) == set(df["region"])
    assert out["count"].sum() == len(df)


def test_small_groups_are_suppressed():
    df = pd.DataFrame(
        {"g": ["x"] * (MIN_GROUP_SIZE - 1) + ["y"] * 10, "v": range(MIN_GROUP_SIZE + 9)}
    )
    out = summarise(df, "g", "v").set_index("g")
    assert pd.isna(out.loc["x", "total"])
    assert not pd.isna(out.loc["y", "total"])


def test_overview_reports_shape_only():
    info = overview(make_fake_df(n=20))
    assert info["rows"] == 20
    assert "amount" in info["columns"]
