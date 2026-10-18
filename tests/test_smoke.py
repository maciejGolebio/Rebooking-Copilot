"""Smoke tests: the fixtures parse and the entrypoint runs offline."""

from pathlib import Path

from rebooking_copilot.cli import load_json, main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_fixtures_parse():
    pnrs = load_json(FIXTURES / "pnrs.json")
    fares = load_json(FIXTURES / "fares_feed.json")
    assert pnrs["pnrs"], "expected at least one booking"
    assert fares["offers"], "expected at least one offer"
    assert fares["capturedAt"]


def test_cli_runs_on_fixtures(capsys):
    code = main(["--pnrs", str(FIXTURES / "pnrs.json"), "--fares", str(FIXTURES / "fares_feed.json")])
    assert code == 0
    assert "not implemented yet" in capsys.readouterr().out
