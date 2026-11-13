"""Convert a captured switch text file into an Excel workbook. Run in YOUR terminal.

    uv run python switch_to_excel.py --input "C:\\path\\to\\capture.txt" --output "C:\\path\\to\\out.xlsx"

Sheets: 'Switch VLANs' (switch, port, VLAN, MAC address, port status, port name), 'Raw data' (every input line + outcome),
'Log' (skipped/odd lines, highlighted), 'Summary' (run time, paths, counts).
Prints counts only, never rows.
Keep --output outside this repo (it contains real data).
"""

import argparse
import sys
from datetime import datetime

from analysis.switch_excel import write_workbook
from analysis.switch_parser import MODES, build_summary, parse_text, read_capture

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
    p.add_argument(
        "--mode",
        choices=MODES,
        default="regex",
        help="regex: anchor on status words (default); fixed: slice columns by header offsets",
    )
    args = p.parse_args()

    run_at = datetime.now().astimezone()
    print("Reading input...")
    text = read_capture(args.input)
    res = parse_text(text, show_progress, args.mode)
    summary = build_summary(res, args.input, args.output, args.mode, run_at)
    write_workbook(res, args.output, show_progress, summary)
    print()

    for item, value in summary:
        print(f"{item}: {value}")


if __name__ == "__main__":
    main()
