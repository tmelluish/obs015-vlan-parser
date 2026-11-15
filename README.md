# obs015-vlan-parser

Turns a text capture of many network switches into an Excel report showing which VLANs and MAC
addresses are on each port of each switch.

It reads the output of two commands per switch and merges them:

- `show int status` gives each port's name, status and VLAN.
- `show mac address-table` gives the MAC addresses seen on each port and, for trunk ports (where
  `show int status` only says `trunk`), the VLANs carried.

## Input

One text file containing the captured terminal session for many switches. Each switch section
starts with a prompt line such as:

```
sw-example-01#show int status
```

and runs until the next prompt line. Sections for other commands are ignored (and noted in the log).
Terminal clutter such as colour codes, backspaces and `\r\r\n` line endings is cleaned up. UTF-16
files (e.g. from a PowerShell redirect) are detected automatically.

Recognised commands: `show int status` / `show interfaces status`, and `show mac address-table` /
`show mac-address-table` (optionally with extra arguments). Abbreviated commands such as
`sh int stat` are not recognised; the section is skipped and logged.

## Usage

Requires [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run python switch_to_excel.py --input "C:\path\to\capture.txt" --output "C:\path\to\out.xlsx"
```

Optional `--mode`:

- `regex` (default): finds the VLAN by locating the status word (`connected`, `notconnect`, ...).
  Tolerates columns that don't line up, but skips rows with a status word it doesn't know.
- `fixed`: treats the columns as fixed width and slices each row at the column positions of the
  header line. Accepts any status word, but skips rows that don't line up with their header.

If the two modes give different row counts, compare the SKIPPED entries in the Log sheet.

The terminal shows progress and then a summary of counts only (never rows).

## Output workbook

| Sheet | Contents |
| --- | --- |
| Switch VLANs | One row per port: switch, port, VLAN, port status, port name, MAC count, MAC addresses |
| VLANs | One row per distinct numeric VLAN: VLAN, and the switches where it was seen (comma-separated) |
| Raw data | Every input line with how it was handled (parsed, header, blank, noise, ignored, skipped) |
| Log | Lines that were skipped or look odd, highlighted by level (SKIPPED, WARNING, INFO) |
| Summary | Run date/time, source and output file paths, mode, and aggregate counts |

Notes on the Switch VLANs sheet:

- If `show int status` gives a non-numeric VLAN (`trunk`, `routed`, ...), it is replaced by the
  sorted list of VLANs seen on that port in the MAC table, e.g. `5, 20, 100`. If the MAC table
  shows none, the original value is kept and a WARNING is logged.
- MAC addresses on a port are listed sorted and comma-separated. `MAC count` is the true total.
  A list too long for an Excel cell is cut at a whole address, ends with `, ...` and is logged.
- MAC addresses on ports that are not in `show int status` (e.g. `CPU`) appear only in the Log.
- Every port is included regardless of connection status.

## Development

```
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run pre-commit install
```

Tests use only synthetic switch output written inline in `tests/test_switch_parser.py`.

| File | Purpose |
| --- | --- |
| `switch_to_excel.py` | Command-line entry point |
| `analysis/switch_parser.py` | Parsing: sections, rows, MAC and VLAN merge, log, summary |
| `analysis/switch_excel.py` | Writes the Excel workbook |
| `tests/test_switch_parser.py` | Tests |

## Where to put code and data

Best practice is to keep code and customer data in two separate folders, so data can never be
committed or exposed to tools by accident:

```
C:\Users\<user-name>\
    src\                      <- code only: clone this repository (and others) here
        obs015-vlan-parser\
    data\                     <- customer data only: captures and generated workbooks
        <customer>\
```

- Clone into `src` (e.g. `git clone <url>` from inside `C:\Users\<user-name>\src`).
- Put real captures in `data` and write output workbooks there too, using full paths for
  `--input` and `--output`.
- Open VS Code (and Claude Code) on the project folder under `src`, never on `data`.
- Claude Code should also be blocked from the data folder by permission rules. Those rules contain
  your own username, so they live in a personal, git-ignored file rather than in the shared
  `.claude/settings.json`. After cloning, set it up once:
  1. Copy `.claude/settings.local.json.example` to `.claude/settings.local.json`.
  2. Replace `<user-name>` in the two rules with your Windows username (or change the path if your
     data folder is elsewhere).

  `.claude/settings.local.json` is listed in `.gitignore`, so it is never committed. The shared
  `.claude/settings.json` still blocks common data file types (`.csv`, `.xlsx`, ...) for everyone.

## Data handling

Captures and reports may contain confidential client or network information.

- Keep real captures and generated workbooks in the separate `data` folder, outside this repository.
- Do not commit data files. `.gitignore` and a pre-commit hook block common data formats.
- Anything used in tests or issues must be synthetic or anonymised.

## Working with Claude Code

`CLAUDE.md` holds the rules Claude follows in this repo: it never has access to real data, works
from synthetic data, and asks before running code. Run the script on real data yourself, in your
own terminal.
