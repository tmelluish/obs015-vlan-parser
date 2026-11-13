"""Convert a captured switch text file into an Excel workbook. Run in YOUR terminal.

    uv run python switch_to_excel.py --input "C:\\path\\to\\capture.txt" --output "C:\\path\\to\\out.xlsx"

Sheets: 'Switch VLANs' (switch, port, VLAN, MAC address), 'Raw data' (every input line + outcome),
'Log' (skipped/odd lines, highlighted). Prints counts only, never rows.
Keep --output outside this repo (it contains real data).
"""

import argparse
import sys
from collections import Counter

from analysis.switch_excel import write_workbook
from analysis.switch_parser import parse_text, read_capture

_last_stage = ""


def show_progress(stage: str, done: int, total: int) -> None:
    """Overwrite one terminal line with the current stage; counts only."""
    global _last_stage
    if stage != _last_stage and _last_stage:
        sys.stdout.write("\n")
    _last_stage = stage
    if total:
        sys.stdout.write(f"\r{stage}: {done:,}/{total:,} ({done * 100 // total}%)   ")
    else:
        sys.stdout.write(f"\r{stage}...   ")
    sys.stdout.flush()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="path to the text capture")
    p.add_argument("--output", required=True, help="path of the .xlsx to write")
    args = p.parse_args()

    print("Reading input...")
    text = read_capture(args.input)
    res = parse_text(text, show_progress)
    write_workbook(res, args.output, show_progress)
    print()

    print(f"input lines: {len(res.raw)}")
    print(f"switches with ports: {len({r.switch for r in res.rows})}")
    print(f"output rows: {len(res.rows)}")
    print(f"distinct ports: {len({(r.switch, r.port) for r in res.rows})}")
    print(f"rows with a MAC: {sum(1 for r in res.rows if r.mac)}")
    for level, n in sorted(Counter(e.level for e in res.log).items()):
        print(f"log {level}: {n}")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
