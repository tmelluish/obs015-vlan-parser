"""Tests use only synthetic switch text built inline (no data files)."""

from openpyxl import load_workbook

from analysis.switch_excel import write_workbook
from analysis.switch_parser import INFO, SKIPPED, WARNING, clean_line, parse_text

SAMPLE = """\
\x1b[0m\x1b[33mConnection closed.
[0m[33m---- ############ AAA00001 ############ ----
[0m[33m
sw-aaa-01#Show int status

Port         Name               Status       Vlan       Duplex  Speed Type
Te1/0/1      BTCM Link to skfl- connected    trunk        full   1000 1000BaseSX SFP
Te1/0/2      Server access      monitoring   99         a-full a-1000 10/100/1000BaseTX SFP
Te1/0/3                         notconnect   1          auto   auto  Not Present

Port         Name               Status       Vlan       Duplex  Speed Type
Gi2/0/1      uplink disabled x  disabled     4094         full    10G SFP-10GBase-SR
Te2/0/9      weird              mystery      5          full   1000 SFP
something odd here
sw-aaa-01#Show version
Cisco IOS Software
more version text
sw-bbb-02#show interfaces status
Port         Name               Status       Vlan       Duplex  Speed Type
Te1/0/1      x                  connected    20         full   1000 SFP
"""


def test_rows_extracted_with_all_statuses():
    res = parse_text(SAMPLE)
    got = [(r.switch, r.port, r.vlan) for r in res.rows]
    assert got == [
        ("sw-aaa-01", "Te1/0/1", "trunk"),
        ("sw-aaa-01", "Te1/0/2", "99"),
        ("sw-aaa-01", "Te1/0/3", "1"),
        ("sw-aaa-01", "Gi2/0/1", "4094"),
        ("sw-bbb-02", "Te1/0/1", "20"),
    ]


def test_skipped_lines_are_logged_not_dropped():
    res = parse_text(SAMPLE)
    skipped = [e for e in res.log if e.level == SKIPPED]
    assert len(skipped) == 2
    outcomes = {r.outcome for r in res.raw}
    assert {"parsed", "skipped", "header", "blank", "noise"} <= outcomes
    assert len(res.raw) == len(SAMPLE.splitlines())


def test_other_command_section_ignored_and_logged():
    res = parse_text(SAMPLE)
    assert any("Show version" in e.message for e in res.log)
    assert [r.outcome for r in res.raw if r.text.startswith(("Cisco", "more version"))] == [
        "ignored",
        "ignored",
    ]


def test_empty_status_section_and_duplicates_warn():
    res = parse_text("s1#show int status\ns2#show int status\nTe1/0/1 a connected 1 full 1000 x\n")
    warns = [e for e in res.log if e.level == WARNING]
    assert len(warns) == 1  # s1 had no rows
    dup = parse_text(
        "s#show int status\nTe1/0/1 a connected 1 f 1 x\nTe1/0/1 a connected 1 f 1 x\n"
    )
    assert len(dup.rows) == 2
    assert any("duplicate" in e.message for e in dup.log)


def test_workbook_has_three_sheets(tmp_path):
    out = tmp_path / "out.xlsx"
    write_workbook(parse_text(SAMPLE), str(out))
    wb = load_workbook(out)
    assert wb.sheetnames == ["Switch VLANs", "Raw data", "Log"]
    assert [c.value for c in wb["Switch VLANs"][1]] == [
        "switch",
        "port",
        "VLAN",
        "MAC address",
        "port status",
        "port name",
    ]
    assert wb["Switch VLANs"].max_row == 1 + 5
    assert wb["Raw data"].max_row == 1 + len(SAMPLE.splitlines())


def test_progress_callbacks_report_stages(tmp_path):
    big = "s#show int status\n" + "Te1/0/1 a connected 1 full 1000 x\n" * 4500
    calls = []
    res = parse_text(big, lambda *a: calls.append(a))
    assert calls[-1] == ("Parsing", 4501, 4501)
    write_workbook(res, str(tmp_path / "o.xlsx"), lambda *a: calls.append(a))
    stages = {c[0] for c in calls}
    assert {
        "Writing 'Switch VLANs'",
        "Writing 'Raw data'",
        "Saving file (can take a while)",
    } <= stages


MAC_SAMPLE = """sw-a#Show int status
Port         Name               Status       Vlan       Duplex  Speed Type
Gi3/0/15     x                  connected    99         full   1000 SFP
Gi3/0/19     y                  connected    99         full   1000 SFP
Gi3/0/23     z                  notconnect   trunk      full   1000 SFP
sw-a#show mac address-table
          Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
 All    aaaa.bbbb.0001    STATIC      CPU
  99    aaaa.bbbb.0002    STATIC      Gi3/0/15
  99    AAAA.BBBB.0003    DYNAMIC     Gi3/0/19
  10    aaaa.bbbb.0004    DYNAMIC     Gi3/0/19
  20    aaaa.bbbb.0004    DYNAMIC     Gi3/0/19
  20    aaaa.bbbb.0005    DYNAMIC     Gi3/0/15,Gi3/0/99
not a mac row
Total Mac Addresses for this criterion: 6
"""


def test_macs_attached_one_row_per_mac():
    res = parse_text(MAC_SAMPLE)
    got = [(r.port, r.vlan, r.mac) for r in res.rows]
    assert got == [
        ("Gi3/0/15", "99", "aaaa.bbbb.0002"),
        ("Gi3/0/15", "99", "aaaa.bbbb.0005"),
        ("Gi3/0/19", "99", "aaaa.bbbb.0003"),
        ("Gi3/0/19", "99", "aaaa.bbbb.0004"),  # duplicate across VLANs collapsed
        ("Gi3/0/23", "trunk", ""),  # no MAC seen: still listed
    ]


def test_unmatched_macs_and_bad_lines_are_logged():
    res = parse_text(MAC_SAMPLE)
    msgs = [e.message for e in res.log]
    assert any("aaaa.bbbb.0001" in m and "CPU" in m for m in msgs)
    assert any("Gi3/0/99" in m for m in msgs)
    assert [e.level for e in res.log if "unrecognised" in e.message] == [SKIPPED]
    assert len(res.raw) == len(MAC_SAMPLE.splitlines())


def test_status_and_name_captured():
    res = parse_text(SAMPLE)
    got = [(r.port, r.status, r.name) for r in res.rows]
    assert got[:4] == [
        ("Te1/0/1", "connected", "BTCM Link to skfl-"),
        ("Te1/0/2", "monitoring", "Server access"),
        ("Te1/0/3", "notconnect", ""),
        ("Gi2/0/1", "disabled", "uplink disabled x"),
    ]


def _fw(port, name, status, vlan, duplex="full", tail="1000 SFP"):
    return f"{port:<10}{name:<19}{status:<13}{vlan:<11}{duplex:<8}{tail}"


FIXED_SAMPLE = "\n".join(
    [
        "sw-f#show int status",
        _fw("Port", "Name", "Status", "Vlan", "Duplex", "Speed Type"),
        _fw("Te1/0/1", "BTCM Link to skfl-", "connected", "trunk"),
        _fw("Te1/0/2", "", "linkFlapE", "99"),
        _fw("Te1/0/3", "disabled by hand", "notconnect", "1"),
        _fw("Te1/0/4", "x", "connected", "5").replace("connected", "conn  ected  "),
        "Te1/0/5 misaligned connected 7 full 1000 SFP",
        _fw("Port", "Name", "Status", "Vlan", "Duplex", "Speed Type"),
        _fw("Te1/0/6", "repeated hdr", "connected", "42"),
    ]
)


def test_fixed_mode_slices_by_header_columns():
    res = parse_text(FIXED_SAMPLE, mode="fixed")
    got = [(r.port, r.vlan, r.status, r.name) for r in res.rows]
    assert got == [
        ("Te1/0/1", "trunk", "connected", "BTCM Link to skfl-"),
        ("Te1/0/2", "99", "linkFlapE", ""),  # unknown status word is fine in fixed mode
        ("Te1/0/3", "1", "notconnect", "disabled by hand"),
        ("Te1/0/6", "42", "connected", "repeated hdr"),
    ]
    skipped = [e for e in res.log if e.level == SKIPPED]
    assert len(skipped) == 2  # the garbled row and the misaligned row


def test_fixed_mode_row_without_header_is_logged():
    res = parse_text("s#show int status\nTe1/0/1 a connected 1 full 1000 x\n", mode="fixed")
    assert res.rows == []
    assert any("no usable header" in e.message for e in res.log)


def test_unknown_mode_rejected():
    import pytest

    with pytest.raises(ValueError):
        parse_text("", mode="nope")


# Terminal echo of typing "show ap upt", erasing 6 chars, typing "int stats", erasing 1, "us".
ERASE = "\b \b"
GARBLED_CMD = "show ap upt" + ERASE * 6 + "int stats" + ERASE + "us"
EDITED_SAMPLE = "\n".join(
    [
        "sw-name#" + GARBLED_CMD,
        "",
        "Port      Name               Status       Vlan       Duplex  Speed Type",
        "Gi1/0/1   Connected to Prima notconnect   1            auto   auto 10/100/1000BaseTX",
        "Gi1/0/2   User access        notconnect   99           auto   auto 10/100/1000BaseTX",
        "Gi1/0/5   Connected to PRI S connected    trunk      a-full a-1000 10/100/1000BaseTX",
        "",
    ]
)


def test_clean_line_replays_backspaces():
    assert clean_line("sw-name#" + GARBLED_CMD) == "sw-name#show int status"
    assert clean_line("\x1b[0m\x1b[33mabc\x1b[K\x07") == "abc"


def test_backspace_edited_command_still_parsed_in_both_modes():
    for mode in ("regex", "fixed"):
        res = parse_text(EDITED_SAMPLE, mode=mode)
        got = [(r.switch, r.port, r.vlan, r.status, r.name) for r in res.rows]
        assert got == [
            ("sw-name", "Gi1/0/1", "1", "notconnect", "Connected to Prima"),
            ("sw-name", "Gi1/0/2", "99", "notconnect", "User access"),
            ("sw-name", "Gi1/0/5", "trunk", "connected", "Connected to PRI S"),
        ], mode
        assert not [e for e in res.log if e.level != INFO or "skipped" in e.message]
        assert len(res.raw) == 6  # one per editor line (the trailing newline adds none)
