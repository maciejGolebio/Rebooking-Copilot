"""Smoke tests: the fixtures parse and the entrypoint runs offline."""

from pathlib import Path

from rebooking_copilot.cli import main
from rebooking_copilot.loader import read_json

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_fixtures_parse():
    pnrs = read_json(FIXTURES / "pnrs.json")
    fares = read_json(FIXTURES / "fares_feed.json")
    assert pnrs["pnrs"], "expected at least one booking"
    assert fares["offers"], "expected at least one offer"
    assert fares["capturedAt"]


def test_cli_runs_on_fixtures(tmp_path, capsys):
    code = main(["--pnrs", str(FIXTURES / "pnrs.json"), "--fares", str(FIXTURES / "fares_feed.json"), "--out", str(tmp_path / "r.json")])
    out = capsys.readouterr().out
    assert code == 0
    assert "Loaded 5 bookings (0 rejected) and 6 offers (0 rejected)" in out
    rows = {line.split()[0]: line.split()[1] for line in out.splitlines() if line[:6] in {"QX7T2A", "LM9P4C", "RT5K8B", "ZC3N1D", "HB6W9E"}}
    assert rows == {"QX7T2A": "NEEDS_REVIEW", "LM9P4C": "DO_NOT_REBOOK", "RT5K8B": "REBOOK", "ZC3N1D": "NEEDS_REVIEW", "HB6W9E": "DO_NOT_REBOOK"}


def test_cli_reports_unusable_input(tmp_path, capsys):
    broken = tmp_path / "pnrs.json"
    broken.write_text("{not json")
    assert main(["--pnrs", str(broken), "--fares", str(FIXTURES / "fares_feed.json")]) == 2
    assert "error:" in capsys.readouterr().err
