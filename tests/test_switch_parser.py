"""Tests use only synthetic switch text built inline (no data files)."""

from openpyxl import load_workbook

from analysis.switch_excel import write_workbook
from analysis.switch_parser import SKIPPED, WARNING, parse_text

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
        ("sw-aaa-01#", "Te1/0/1", "trunk"),
        ("sw-aaa-01#", "Te1/0/2", "99"),
        ("sw-aaa-01#", "Te1/0/3", "1"),
        ("sw-aaa-01#", "Gi2/0/1", "4094"),
        ("sw-bbb-02#", "Te1/0/1", "20"),
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
    dup = parse_text("s#show int status\nTe1/0/1 a connected 1 f 1 x\nTe1/0/1 a connected 1 f 1 x\n")
    assert len(dup.rows) == 2
    assert any("duplicate" in e.message for e in dup.log)


def test_workbook_has_three_sheets(tmp_path):
    out = tmp_path / "out.xlsx"
    write_workbook(parse_text(SAMPLE), str(out))
    wb = load_workbook(out)
    assert wb.sheetnames == ["Switch VLANs", "Raw data", "Log"]
    assert [c.value for c in wb["Switch VLANs"][1]] == ["switch", "port", "VLAN"]
    assert wb["Switch VLANs"].max_row == 1 + 5
    assert wb["Raw data"].max_row == 1 + len(SAMPLE.splitlines())
