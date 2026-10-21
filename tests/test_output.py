"""recommendations.json and its JSON Schema (D-05), plus the CLI switches (D-37)."""

import json
from pathlib import Path

import pytest

from factories import fixture_inputs
from rebooking_copilot import cli
from rebooking_copilot.decision import evaluate
from rebooking_copilot.output import SCHEMA_PATH, RecommendationsFile, build_file, schema_json, write_file
from rebooking_copilot.reasoning import UnavailableReasoner

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures"


def test_committed_schema_matches_the_models():
    # Regenerate with: uv run python -m rebooking_copilot.output
    assert SCHEMA_PATH.read_text() == schema_json()


def test_file_round_trips_and_validates(tmp_path):
    pnr_load, snapshot = fixture_inputs()
    recs = evaluate(pnr_load, snapshot)
    path = write_file(tmp_path / "out" / "recommendations.json", build_file(recs, snapshot, reasoner_id="stub"))
    data = json.loads(path.read_text())
    assert data["schemaVersion"] == "1" and len(data["recommendations"]) == 5
    assert data["asOf"] == "2026-07-08T09:00:00Z" and data["capturedAt"] == "2026-07-08T09:00:00Z"
    parsed = RecommendationsFile.model_validate_json(path.read_text())
    assert [r.pnr for r in parsed.recommendations] == ["QX7T2A", "LM9P4C", "RT5K8B", "ZC3N1D", "HB6W9E"]
    rt = data["recommendations"][2]
    assert rt["action"] == "REBOOK" and rt["estimatedNetSaving"] == {"amount": "252.040000", "currency": "EUR"}


def test_output_is_byte_identical_across_runs(tmp_path):
    a = write_file(tmp_path / "a.json", build_file(evaluate(*fixture_inputs()), fixture_inputs()[1], reasoner_id="stub"))
    b = write_file(tmp_path / "b.json", build_file(evaluate(*fixture_inputs()), fixture_inputs()[1], reasoner_id="stub"))
    assert a.read_bytes() == b.read_bytes()


def _args(tmp_path, *extra):
    return ["--pnrs", str(FIXTURES / "pnrs.json"), "--fares", str(FIXTURES / "fares_feed.json"), "--out", str(tmp_path / "r.json"), *extra]


def test_cli_writes_the_file_and_prints_rationales(tmp_path, capsys):
    assert cli.main(_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert (tmp_path / "r.json").exists() and "Wrote 5 recommendations" in out
    assert "travel credit" in out  # QX7T2A's rationale is printed


def test_table_labels_a_saving_that_would_come_back_as_credit(tmp_path, capsys):
    assert cli.main(_args(tmp_path)) == 0
    rows = {line[:6]: line for line in capsys.readouterr().out.splitlines()}
    assert "80.00 USD (credit)" in rows["QX7T2A"]
    assert "252.04 EUR" in rows["RT5K8B"] and "(credit)" not in rows["RT5K8B"]
    assert "140.00 USD" in rows["ZC3N1D"] and "(credit)" not in rows["ZC3N1D"]


@pytest.mark.parametrize(
    "env, flag, expected",
    [(None, None, "stub"), ("claude", None, "claude"), ("claude", "stub", "stub"), (None, "claude", "claude"), ("stub", "claude", "claude")],
)
def test_reasoner_switch_flag_overrides_env(monkeypatch, tmp_path, env, flag, expected):
    chosen = []
    monkeypatch.setattr(cli, "make_claude_reasoner", lambda: chosen.append("claude") or UnavailableReasoner("test"))
    if env is None:
        monkeypatch.delenv("REBOOKING_REASONER", raising=False)
    else:
        monkeypatch.setenv("REBOOKING_REASONER", env)
    assert cli.main(_args(tmp_path, *(["--reasoner", flag] if flag else []))) == 0
    assert (chosen == ["claude"]) is (expected == "claude")


def test_claude_mode_without_credentials_says_so_and_still_works(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "make_claude_reasoner", lambda: UnavailableReasoner("no credentials found"))
    assert cli.main(_args(tmp_path, "--reasoner", "claude")) == 0
    out = capsys.readouterr().out
    assert "falling back" in out.lower() and "no credentials found" in out
    data = json.loads((tmp_path / "r.json").read_text())
    zc = next(r for r in data["recommendations"] if r["pnr"] == "ZC3N1D")
    assert zc["fallbackReason"] == "claude unavailable: no credentials found"
