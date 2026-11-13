# Project template (safe for client-adjacent work)

Create a new project with `..\new-project.ps1 <name>` (from `src`), or copy this folder by hand.

## First-time setup in a new project
1. Edit `pyproject.toml` (`name`) and `analysis/fake.py` (real column names and types only).
2. `uv sync`
3. `git init`, then `uv run pre-commit install`
4. `uv run pytest`

## Working with Claude
- Open VS Code on this project folder, never on the data folder.
- Keep the permission mode on Manual.
- Claude writes and tests code on synthetic data. You run `run.py --input <real file>` yourself.
- Tell Claude column names and types, never values.

## Notes
- Deny rules in `.claude/settings.json` block Claude's file tools; they do not stop code that runs and reads files. The real protection is the separation of code and data, plus approving each run.
- Do not put data files in this repo; `.gitignore` and a pre-commit hook block them.
