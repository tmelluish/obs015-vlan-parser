# Project rules for Claude (read first)

This project may be used against confidential client data. Real data is NEVER available to you.

## Data rules (non-negotiable)
- Real data lives outside this repo, in a separate `data` folder that sits next to the `src` folder holding the code. Convention: code in `C:\Users\<user-name>\src\<project>`, customer data in `C:\Users\<user-name>\data`. Never read, open, search, list, copy or print anything from the data folder, or from any path outside this repo that looks like data.
- Each user's data-folder deny rules live in the git-ignored `.claude/settings.local.json` (template: `.claude/settings.local.json.example`). If that file is missing or doesn't name the user's data folder, stop and tell the user. Do not treat it as permission.
- Never write code or run commands that open real data paths. Scripts take the data path as a `--input` argument; the user runs them in their own terminal.
- Work only from synthetic data: tests build fake switch output as inline strings (see `tests/test_switch_parser.py`). Do not create `.csv`, `.xlsx`, `.parquet` or other data files in the repo.
- Scripts must print aggregates and error messages only, never rows or sample records. Small groups (fewer than 5) are suppressed.
- If you need to know the data's shape, ask the user for column names and types only.
- If a task seems to need real data, stop and ask the user instead.

## Working style
- Ask before running anything that executes code. Prefer `uv run pytest` against synthetic data to check your work.
- Keep changes small and explain what each file does.
- Never put real names, figures or identifiers in code, comments, tests or commit messages.

## Layout
- `analysis/switch_parser.py`: parses a multi-switch capture into one row per port, plus raw-line and log records
- `analysis/switch_excel.py`: writes the Excel workbook (Switch VLANs, Raw data, Log, Summary)
- `switch_to_excel.py`: command-line entry point, run by the user on real data
- `tests/`: tests using only synthetic data
