"""Write a ParseResult to a three-sheet Excel workbook."""

from __future__ import annotations

import re

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from analysis.switch_parser import INFO, PROGRESS_EVERY, SKIPPED, WARNING, ParseResult, Progress

CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="D9D9D9")
LEVEL_FILL = {
    SKIPPED: PatternFill("solid", fgColor="F8CBAD"),
    WARNING: PatternFill("solid", fgColor="FFE699"),
    INFO: None,
}
OUTCOME_FILL = {
    "skipped": LEVEL_FILL[SKIPPED],
    "parsed": PatternFill("solid", fgColor="E2EFDA"),
}


def _clean(value: str) -> str:
    return CONTROL.sub("", value)[:32000]


def _append(ws, row_no: int, values: list, fill: PatternFill | None = None) -> None:
    """Write one row at row_no (row 1 is the header). Avoids ws.max_row, which is O(cells)."""
    for col, v in enumerate(values, start=1):
        cell = ws.cell(row=row_no, column=col, value=_clean(v) if isinstance(v, str) else v)
        if isinstance(v, str):
            cell.data_type = "s"  # never let a leading '=' become a formula
        if fill:
            cell.fill = fill


def _finish(ws, widths: list[int]) -> None:
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def write_workbook(res: ParseResult, path: str, progress: Progress | None = None) -> None:
    def tick(stage: str, i: int, total: int) -> None:
        if progress and (i % PROGRESS_EVERY == 0 or i == total):
            progress(stage, i, total)

    wb = Workbook()

    ws = wb.active
    ws.title = "Switch VLANs"
    ws.append(["switch", "port", "VLAN"])
    for i, r in enumerate(res.rows, start=1):
        _append(ws, i + 1, [r.switch, r.port, r.vlan])
        tick("Writing 'Switch VLANs'", i, len(res.rows))
    _finish(ws, [28, 16, 12])

    ws = wb.create_sheet("Raw data")
    ws.append(["line", "text", "outcome"])
    for i, r in enumerate(res.raw, start=1):
        _append(ws, i + 1, [r.line_no, r.text, r.outcome], OUTCOME_FILL.get(r.outcome))
        tick("Writing 'Raw data'", i, len(res.raw))
    _finish(ws, [8, 110, 12])

    ws = wb.create_sheet("Log")
    ws.append(["line", "level", "switch", "message", "text"])
    for i, e in enumerate(res.log, start=1):
        _append(ws, i + 1, [e.line_no, e.level, e.switch, e.message, e.text], LEVEL_FILL[e.level])
        tick("Writing 'Log'", i, len(res.log))
    _finish(ws, [8, 10, 28, 70, 90])

    if progress:
        progress("Saving file (can take a while)", 0, 0)
    wb.save(path)
