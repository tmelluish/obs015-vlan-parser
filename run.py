"""Run on real data in YOUR terminal, not through Claude.

    uv run python run.py --input "C:\\Users\\Tom.Melluish\\data\\client\\file.csv" --by region --value amount

Prints aggregates only. Use `--fake` to try it on synthetic data.
"""

import argparse

import pandas as pd

from analysis.fake import make_fake_df
from analysis.summarise import overview, summarise


def load(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)


def main() -> None:
    p = argparse.ArgumentParser()
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--input", help="path to the real data file")
    src.add_argument("--fake", action="store_true", help="use synthetic data")
    p.add_argument("--by", default="region")
    p.add_argument("--value", default="amount")
    args = p.parse_args()

    df = make_fake_df() if args.fake else load(args.input)

    info = overview(df)
    print(f"rows: {info['rows']}")
    print(f"columns: {info['columns']}")
    if info["missing"]:
        print(f"missing values: {info['missing']}")
    print()
    print(summarise(df, args.by, args.value).to_string(index=False))


if __name__ == "__main__":
    main()
