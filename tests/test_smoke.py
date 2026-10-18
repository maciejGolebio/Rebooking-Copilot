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


def test_cli_runs_on_fixtures(capsys):
    code = main(["--pnrs", str(FIXTURES / "pnrs.json"), "--fares", str(FIXTURES / "fares_feed.json")])
    out = capsys.readouterr().out
    assert code == 0
    assert "Loaded 5 bookings (0 rejected) and 6 offers (0 rejected)" in out
    assert "not implemented yet" in out


def test_cli_reports_unusable_input(tmp_path, capsys):
    broken = tmp_path / "pnrs.json"
    broken.write_text("{not json")
    assert main(["--pnrs", str(broken), "--fares", str(FIXTURES / "fares_feed.json")]) == 2
    assert "error:" in capsys.readouterr().err
