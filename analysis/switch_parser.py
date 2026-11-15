"""Parse 'show int status' and 'show mac address-table' output captured from many switches
into one row per port: (switch, port, VLAN, status, name, MAC count, MACs). MACs seen on a port
are joined into one comma-and-space-separated cell; a port with none has a blank list and a count of 0.

Pure functions, no file or Excel I/O, so they can be tested on synthetic text.
Every input line gets an outcome and anything unusual gets a log entry, so nothing
is dropped silently.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

# Colour codes, with or without the ESC byte (pasted text often loses it).
CSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\[[0-9;]*m")
# Leftover control characters (not tab). Backspace is replayed by clean_line before this.
CONTROL = re.compile(r"[\x00-\x07\x0b-\x1f\x7f]")


def clean_line(raw: str) -> str:
    """Render a captured terminal line as plain text.

    Strips escape sequences, replays backspaces the way a terminal does (cursor moves left,
    typed characters overwrite), drops other control characters and trailing whitespace.
    """
    s = CSI.sub("", raw)
    if "\b" in s:
        buf: list[str] = []
        cur = 0
        for ch in s:
            if ch == "\b":
                cur = max(0, cur - 1)
                continue
            if cur < len(buf):
                buf[cur] = ch
            else:
                buf.append(ch)
            cur += 1
        s = "".join(buf)
    return CONTROL.sub("", s).rstrip()


def split_lines(text: str) -> list[str]:
    """Split on newlines only (str.splitlines also splits on odd control characters),
    so line numbers match what an editor shows."""
    if not text:
        return []
    lines = [ln.removesuffix("\r") for ln in text.split("\n")]
    if lines[-1] == "":
        lines.pop()
    return lines


# 'hostname#command ...' (the '#' is the prompt character and is not part of the switch name)
PROMPT = re.compile(r"^(?P<switch>[\w.\-]+)#\s*(?P<cmd>.*)$")
INT_STATUS = re.compile(r"^show\s+int(?:erfaces?)?\s+status$", re.IGNORECASE)
# Lines that are known session noise, not data.
NOISE = re.compile(r"^(?:-{2,}.*-{2,}|connection closed\.?)$", re.IGNORECASE)
MAC_TABLE = re.compile(r"^show\s+mac[\s-]*address[\s-]*table(?:\s.*)?$", re.IGNORECASE)
HEADER = re.compile(r"^Port\s+Name\s+Status\s+Vlan\b", re.IGNORECASE)
MAC_HEADER = re.compile(
    r"^(?:Vlan\s+Mac\s+Address\s+Type\s+Ports|Mac\s+Address\s+Table|Total\s+Mac\s+Addresses\b.*)",
    re.IGNORECASE,
)
# 'All  aaaa.bbbb.cccc  STATIC  Gi1/0/1' (ports may be a comma-separated list)
MAC_ROW = re.compile(
    r"^(?P<vlan>\S+)\s+(?P<mac>[0-9a-f]{4}\.[0-9a-f]{4}\.[0-9a-f]{4})\s+\S+\s+(?P<ports>.+)$",
    re.IGNORECASE,
)
PORT_START = re.compile(r"^[A-Za-z][A-Za-z\-]*\d+(?:/\d+)*(?:\.\d+)?\s")

STATUSES = (
    "connected",
    "notconnect",
    "disabled",
    "err-disabled",
    "inactive",
    "monitoring",
    "suspended",
    "faulty",
    "routed",
    "sfp-config-mismatch",
)
# The Name column may hold spaces (or be empty), so anchor on the status word instead.
# Greedy name group => the right-most status word wins if a name happens to contain one.
ROW = re.compile(
    r"^(?P<port>\S+)\s+(?P<name>.*)(?:^|\s)(?P<status>" + "|".join(STATUSES) + r")"
    r"\s+(?P<vlan>\S+)\s+\S+\s+\S+",
    re.IGNORECASE,
)

# Log levels
INFO, WARNING, SKIPPED = "INFO", "WARNING", "SKIPPED"


@dataclass
class Row:
    switch: str
    port: str
    vlan: str
    line_no: int
    macs: str = ""  # comma-joined, sorted MACs seen on the port
    status: str = ""
    name: str = ""
    mac_count: int = 0  # true number of MACs, even if the list was truncated


@dataclass
class MacEntry:
    switch: str
    port: str
    mac: str
    line_no: int
    text: str
    vlan: str = ""  # VLAN column of the MAC table row ('All' for static entries)


@dataclass
class RawLine:
    line_no: int
    text: str
    outcome: str  # parsed / header / blank / noise / skipped / ignored


@dataclass
class LogEntry:
    line_no: int
    level: str
    switch: str
    message: str
    text: str


@dataclass
class ParseResult:
    rows: list[Row] = field(default_factory=list)
    raw: list[RawLine] = field(default_factory=list)
    log: list[LogEntry] = field(default_factory=list)


# progress(stage, done, total) is called periodically by the long-running steps.
Progress = Callable[[str, int, int], None]
PROGRESS_EVERY = 2000


MODES = ("regex", "fixed")
# Header words whose start positions define the fixed-width columns of 'show int status'.
HEADER_WORDS = ("Port", "Name", "Status", "Vlan", "Duplex")


def header_columns(header: str) -> list[int] | None:
    """Start offsets of the Port/Name/Status/Vlan/Duplex columns in a header line."""
    pos, start = [], 0
    for word in HEADER_WORDS:
        i = header.find(word, start)
        if i < 0:
            return None
        pos.append(i)
        start = i + len(word)
    return pos


def fixed_fields(line: str, cols: list[int]) -> tuple[str, str, str, str] | None:
    """Slice a row by header offsets -> (port, name, status, vlan), or None if misaligned.

    Each column start must be preceded by a space (or lie past the end of the line),
    otherwise some value spans the boundary and the row doesn't line up with the header.
    """
    for c in cols[1:]:
        if c <= len(line) and line[c - 1] != " ":
            return None
    port = line[: cols[1]].strip()
    name = line[cols[1] : cols[2]].strip()
    status = line[cols[2] : cols[3]].strip()
    vlan = line[cols[3] : cols[4]].strip()
    if not (port and status and vlan) or any(" " in v for v in (port, status, vlan)):
        return None
    return port, name, status, vlan


def parse_text(text: str, progress: Progress | None = None, mode: str = "regex") -> ParseResult:
    """Parse a multi-switch capture into port rows, a raw-line record and a log.

    Args:
        text: the whole capture as one string.
        progress: optional callback, called as progress("Parsing", lines_done, lines_total)
            every PROGRESS_EVERY lines and once more at the end. It is only used to report
            how far through the file the parser is (counts, never content); pass None
            to run silently.
        mode: how the fields of each 'show int status' row are located. It has no effect
            on 'show mac address-table' rows, which are read the same way in both modes.

            "regex" (default): the Name column can contain spaces or be empty, so the row
                is matched from the status word onwards (connected, notconnect, ...); the
                token after it is the VLAN. Tolerates columns that don't line up, but a
                status word that isn't in STATUSES is treated as unparseable and skipped.
            "fixed": assumes fixed-width columns. The start offsets of Port, Name, Status,
                Vlan and Duplex are read from the most recent header line in the section,
                and each row is sliced at those offsets. Accepts any status word, but a
                row that doesn't line up with its header is skipped and logged.

    Returns:
        ParseResult with rows (one per port), raw (every input line with its
        outcome) and log (anything skipped or unusual).

    Raises:
        ValueError: if mode is not one of MODES.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    res = ParseResult()
    cols: list[int] | None = None
    switch = ""
    cmd = ""
    kind = ""  # "status", "mac" or "" (other command)
    in_section = False
    section_start = 0
    section_lines = 0
    section_rows = 0
    seen: set[tuple[str, str]] = set()
    macs: list[MacEntry] = []

    def log(line_no: int, level: str, message: str, line: str = "") -> None:
        res.log.append(LogEntry(line_no, level, switch, message, line))

    def close_section() -> None:
        if not in_section:
            return
        if kind and section_rows == 0:
            log(section_start, WARNING, f"'{cmd}' section produced no rows")
        elif not kind:
            log(
                section_start,
                INFO,
                f"section skipped (not 'show int status' / 'show mac address-table'): '{cmd}' "
                f"({section_lines} lines)",
            )

    # Section detection
    # -----------------
    # The capture is a flat stream of lines from many switches. A line shaped like
    # 'hostname#command' (PROMPT) starts a new section and ends the previous one; every
    # following line belongs to that section until the next prompt. The hostname (without
    # the '#') becomes the switch name for all rows in the section. The command, with
    # whitespace collapsed, decides how the section's lines are read (`kind`):
    #
    #   'status'  command is 'show int status'          -> rows become Port/VLAN/status/name
    #   'mac'     command is 'show mac address-table'   -> rows become MAC entries
    #   ''        any other command                     -> lines are ignored, and one INFO
    #                                                      entry records the skipped section
    #
    # Each line is first rendered to plain text by clean_line (escape codes stripped,
    # backspaces replayed), so an edited command line is matched as typed. Within a
    # section, blank lines, session noise (dashed banners, 'Connection closed.') and
    # column headers are recognised and set aside. Anything else that doesn't parse is
    # logged as SKIPPED, so no line is dropped silently. A section with a recognised
    # command that yields no rows logs a WARNING. Non-noise text before the first prompt
    # is outside any section and is logged as INFO.
    #
    # The MAC table can appear before or after 'show int status' for the same switch, so
    # MACs are collected during this pass and attached to ports afterwards (_attach_macs).
    lines = split_lines(text)
    total = len(lines)
    for line_no, raw in enumerate(lines, start=1):
        if progress and line_no % PROGRESS_EVERY == 0:
            progress("Parsing", line_no, total)
        clean = clean_line(raw)
        line = clean.strip()

        def mark(outcome: str, raw: str = raw, line_no: int = line_no) -> None:
            res.raw.append(RawLine(line_no, raw, outcome))

        if not line:
            mark("blank")
            continue

        prompt = PROMPT.match(line)
        if prompt:
            close_section()
            switch = prompt["switch"]
            cmd = " ".join(prompt["cmd"].split())
            kind = "status" if INT_STATUS.match(cmd) else "mac" if MAC_TABLE.match(cmd) else ""
            in_section = True
            cols = None
            section_start, section_lines, section_rows = line_no, 0, 0
            mark("ignored")
            continue

        section_lines += 1

        if NOISE.match(line):
            mark("noise")
            continue

        if not in_section:
            log(line_no, INFO, "line outside any switch section ignored", line)
            mark("ignored")
            continue

        if not kind:
            mark("ignored")
            continue

        if kind == "mac":
            if MAC_HEADER.match(line):
                mark("header")
                continue
            mm = MAC_ROW.match(line)
            if not mm:
                log(line_no, SKIPPED, "unrecognised line inside MAC table section", line)
                mark("skipped")
                continue
            for port in re.split(r"[,\s]+", mm["ports"].strip()):
                if port:
                    macs.append(
                        MacEntry(switch, port, mm["mac"].lower(), line_no, line, mm["vlan"])
                    )
            section_rows += 1
            mark("parsed")
            continue

        if HEADER.match(line):
            if mode == "fixed":
                cols = header_columns(clean)
                if cols is None:
                    log(line_no, WARNING, "header lacks Port/Name/Status/Vlan/Duplex", line)
            mark("header")
            continue

        if not PORT_START.match(line):
            log(line_no, SKIPPED, "unrecognised line inside 'show int status' section", line)
            mark("skipped")
            continue

        if mode == "fixed":
            fields = fixed_fields(clean, cols) if cols else None
            if fields is None:
                why = "no usable header above row" if not cols else "row not aligned with header"
                log(line_no, SKIPPED, f"fixed-width: {why}", line)
                mark("skipped")
                continue
            port, name, status, vlan = fields
        else:
            m = ROW.match(line)
            if not m:
                log(line_no, SKIPPED, "port row but no known status word / VLAN found", line)
                mark("skipped")
                continue
            port, name, status, vlan = m["port"], m["name"].strip(), m["status"], m["vlan"]

        key = (switch, port)
        if key in seen:
            log(line_no, WARNING, f"duplicate port {port} for this switch (kept)", line)
        seen.add(key)
        res.rows.append(Row(switch, port, vlan, line_no, "", status, name))
        section_rows += 1
        mark("parsed")

    close_section()
    _attach_macs(res, macs)
    if progress:
        progress("Parsing", total, total)
    return res


# Excel allows 32,767 characters per cell; stay under the writer's own 32,000 cap.
MAC_CELL_LIMIT = 32000
# Separator for the MAC and VLAN lists in a cell.
LIST_SEP = ", "


def _join_macs(macs: list[str]) -> tuple[str, int]:
    """Join MACs with LIST_SEP; if too long for a cell, keep whole MACs that fit and end with
    LIST_SEP + '...'.

    Returns (text, number of MACs included).
    """
    text = LIST_SEP.join(macs)
    if len(text) <= MAC_CELL_LIMIT:
        return text, len(macs)
    kept: list[str] = []
    used = 0
    for m in macs:
        extra = len(m) + (len(LIST_SEP) if kept else 0)
        if used + extra > MAC_CELL_LIMIT - len(LIST_SEP + "..."):
            break
        kept.append(m)
        used += extra
    return LIST_SEP.join(kept) + LIST_SEP + "...", len(kept)


def _vlan_sort_key(vlan: str) -> tuple[int, int, str]:
    """Numeric VLANs in numeric order, then anything else (e.g. 'All') alphabetically."""
    return (0, int(vlan), "") if vlan.isdigit() else (1, 0, vlan.lower())


def _attach_macs(res: ParseResult, macs: list[MacEntry]) -> None:
    """Add each port's sorted MAC list and VLAN list to res.rows (still one row per port).

    MACs on ports not in 'int status' (e.g. CPU) are logged instead. A MAC list too long for an
    Excel cell is truncated with a WARNING; mac_count always holds the true total.

    'show int status' gives only a word such as 'trunk' for ports carrying many VLANs. When a
    port's VLAN is not a plain number, it is replaced by the sorted, comma-joined (LIST_SEP) VLANs seen
    on that port in the MAC table (the same list on every row for the port). If the MAC table
    shows none, the original value is kept and a WARNING is logged.
    """
    by_port: dict[tuple[str, str], list[str]] = {}
    vlans_by_port: dict[tuple[str, str], set[str]] = {}
    known = {(r.switch, r.port.lower()) for r in res.rows}
    for e in macs:
        key = (e.switch, e.port.lower())
        if key not in known:
            res.log.append(
                LogEntry(
                    e.line_no,
                    INFO,
                    e.switch,
                    f"MAC {e.mac} on port '{e.port}' not in this switch's 'int status' (e.g. CPU)",
                    e.text,
                )
            )
            continue
        found = by_port.setdefault(key, [])
        if e.mac not in found:
            found.append(e.mac)
        if e.vlan:
            vlans_by_port.setdefault(key, set()).add(e.vlan)

    expanded: list[Row] = []
    for r in res.rows:
        key = (r.switch, r.port.lower())
        vlan = r.vlan
        if not vlan.isdigit():
            seen_vlans = vlans_by_port.get(key)
            if seen_vlans:
                vlan = LIST_SEP.join(sorted(seen_vlans, key=_vlan_sort_key))
            else:
                res.log.append(
                    LogEntry(
                        r.line_no,
                        WARNING,
                        r.switch,
                        f"port {r.port} VLAN is '{r.vlan}' and no VLANs were found in the MAC "
                        "table, so it is left as is",
                        "",
                    )
                )
        found = sorted(by_port.get(key, []))
        text, kept = _join_macs(found)
        if kept < len(found):
            res.log.append(
                LogEntry(
                    r.line_no,
                    WARNING,
                    r.switch,
                    f"port {r.port}: {len(found)} MACs exceed the Excel cell limit; list "
                    f"truncated to {kept} (MAC count column shows the true total)",
                    "",
                )
            )
        expanded.append(Row(r.switch, r.port, vlan, r.line_no, text, r.status, r.name, len(found)))
    res.rows = expanded


def read_capture(path: str) -> str:
    """Read a text capture, coping with UTF-16 (PowerShell redirects) and stray bytes."""
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def build_summary(
    res: ParseResult, source: str, output: str, mode: str, run_at: datetime
) -> list[tuple[str, str | int]]:
    """Run details and aggregate counts only, shared by the terminal and the Summary sheet."""
    log_counts = Counter(e.level for e in res.log)
    return [
        ("run date/time", run_at.isoformat(sep=" ", timespec="seconds")),
        ("source file", source),
        ("output file", output),
        ("mode", mode),
        ("input lines", len(res.raw)),
        ("switches with ports", len({r.switch for r in res.rows})),
        ("output rows", len(res.rows)),
        ("distinct ports", len({(r.switch, r.port) for r in res.rows})),
        ("ports with a MAC", sum(1 for r in res.rows if r.mac_count)),
        ("MAC addresses seen on ports", sum(r.mac_count for r in res.rows)),
        *((f"log {lvl}", log_counts.get(lvl, 0)) for lvl in (SKIPPED, WARNING, INFO)),
    ]
