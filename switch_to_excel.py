"""Convert a captured switch text file into an Excel workbook. Run in YOUR terminal.

    uv run python switch_to_excel.py --input "C:\\path\\to\\capture.txt" --output "C:\\path\\to\\out.xlsx"

Sheets: 'Switch VLANs' (switch, port, VLAN), 'Raw data' (every input line + outcome),
'Log' (skipped/odd lines, highlighted). Prints counts only, never rows.
Keep --output outside this repo (it contains real data).
"""

import argparse
from collections import Counter

from analysis.switch_excel import write_workbook
from analysis.switch_parser import parse_text, read_capture


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="path to the text capture")
    p.add_argument("--output", required=True, help="path of the .xlsx to write")
    args = p.parse_args()

    res = parse_text(read_capture(args.input))
    write_workbook(res, args.output)

    print(f"input lines: {len(res.raw)}")
    print(f"switches with ports: {len({r.switch for r in res.rows})}")
    print(f"port rows extracted: {len(res.rows)}")
    for level, n in sorted(Counter(e.level for e in res.log).items()):
        print(f"log {level}: {n}")
    print(f"wrote: {args.output}")


if __name__ == "__main__":
    main()
