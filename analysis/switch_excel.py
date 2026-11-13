"""Write a ParseResult to a three-sheet Excel workbook."""

from __future__ import annotations

import re

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from analysis.switch_parser import INFO, SKIPPED, WARNING, ParseResult

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


def _append(ws, values: list, fill: PatternFill | None = None) -> None:
    ws.append([_clean(v) if isinstance(v, str) else v for v in values])
    for cell in ws[ws.max_row]:
        if isinstance(cell.value, str):
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


def write_workbook(res: ParseResult, path: str) -> None:
    wb = Workbook()

    ws = wb.active
    ws.title = "Switch VLANs"
    ws.append(["switch", "port", "VLAN"])
    for r in res.rows:
        _append(ws, [r.switch, r.port, r.vlan])
    _finish(ws, [28, 16, 12])

    ws = wb.create_sheet("Raw data")
    ws.append(["line", "text", "outcome"])
    for r in res.raw:
        _append(ws, [r.line_no, r.text, r.outcome], OUTCOME_FILL.get(r.outcome))
    _finish(ws, [8, 110, 12])

    ws = wb.create_sheet("Log")
    ws.append(["line", "level", "switch", "message", "text"])
    for e in res.log:
        _append(ws, [e.line_no, e.level, e.switch, e.message, e.text], LEVEL_FILL[e.level])
    _finish(ws, [8, 10, 28, 70, 90])

    wb.save(path)
