# Project rules for Claude (read first)

This project may be used against confidential client data. Real data is NEVER available to you.

## Data rules (non-negotiable)
- Real data lives outside this repo (under `C:\Users\Tom.Melluish\data`). Never read, open, search, list, copy or print anything from there.
- Never write code or run commands that open real data paths. Scripts take the data path as a `--input` argument; the user runs them in their own terminal.
- Work only from synthetic data: `analysis/fake.py` builds fake frames in memory. Do not create `.csv`, `.xlsx`, `.parquet` or other data files in the repo.
- Scripts must print aggregates and error messages only, never rows or sample records. Small groups (fewer than 5) are suppressed.
- If you need to know the data's shape, ask the user for column names and types only.
- If a task seems to need real data, stop and ask the user instead.

## Working style
- Ask before running anything that executes code. Prefer `uv run pytest` against synthetic data to check your work.
- Keep changes small and explain what each file does.
- Never put real names, figures or identifiers in code, comments, tests or commit messages.

## Layout
- `analysis/fake.py`: synthetic data generator (edit the schema to match the real columns)
- `analysis/summarise.py`: aggregate-only summaries with small-group suppression
- `run.py`: command-line entry point, run by the user on real data
- `tests/`: tests using only synthetic data
