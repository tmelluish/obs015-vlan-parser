"""Parse 'show int status' and 'show mac address-table' output captured from many switches
into (switch, port, VLAN, MAC) rows. A port seen with several MACs gets one row per MAC;
a port with none gets one row with a blank MAC.

Pure functions, no file or Excel I/O, so they can be tested on synthetic text.
Every input line gets an outcome and anything unusual gets a log entry, so nothing
is dropped silently.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

# Colour codes, with or without the ESC byte (pasted text often loses it).
ANSI = re.compile(r"(?:\x1b)?\[[0-9;]*m")
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
    mac: str = ""


@dataclass
class MacEntry:
    switch: str
    port: str
    mac: str
    line_no: int
    text: str


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


def parse_text(text: str, progress: Progress | None = None) -> ParseResult:
    res = ParseResult()
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

    lines = text.splitlines()
    total = len(lines)
    for line_no, raw in enumerate(lines, start=1):
        if progress and line_no % PROGRESS_EVERY == 0:
            progress("Parsing", line_no, total)
        line = ANSI.sub("", raw).strip()

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
                    macs.append(MacEntry(switch, port, mm["mac"].lower(), line_no, line))
            section_rows += 1
            mark("parsed")
            continue

        if HEADER.match(line):
            mark("header")
            continue

        if not PORT_START.match(line):
            log(line_no, SKIPPED, "unrecognised line inside 'show int status' section", line)
            mark("skipped")
            continue

        m = ROW.match(line)
        if not m:
            log(line_no, SKIPPED, "port row but no known status word / VLAN found", line)
            mark("skipped")
            continue

        key = (switch, m["port"])
        if key in seen:
            log(line_no, WARNING, f"duplicate port {m['port']} for this switch (kept)", line)
        seen.add(key)
        res.rows.append(Row(switch, m["port"], m["vlan"], line_no))
        section_rows += 1
        mark("parsed")

    close_section()
    _attach_macs(res, macs)
    if progress:
        progress("Parsing", total, total)
    return res


def _attach_macs(res: ParseResult, macs: list[MacEntry]) -> None:
    """Expand res.rows to one row per (port, MAC); log MACs on ports not in 'int status'."""
    by_port: dict[tuple[str, str], list[str]] = {}
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

    expanded: list[Row] = []
    for r in res.rows:
        found = by_port.get((r.switch, r.port.lower()), [""])
        expanded.extend(Row(r.switch, r.port, r.vlan, r.line_no, mac) for mac in found)
    res.rows = expanded


def read_capture(path: str) -> str:
    """Read a text capture, coping with UTF-16 (PowerShell redirects) and stray bytes."""
    with open(path, "rb") as f:
        data = f.read()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")
