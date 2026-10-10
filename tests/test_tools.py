"""Tool-level tests on the real processed table, with the live API stubbed (no network)."""
import pytest

from agent import live_apis, tools

FAKE_LIVE = {"update_time": "test", "active_events": [], "status": "no FAA delay program active"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(live_apis, "faa_nas_status", lambda code: dict(FAKE_LIVE, code=code))


def test_compare_attaches_live_now_without_changing_scores():
    out = tools.run_tool("compare_airports", {"codes": ["LAX", "SNA"]})
    data = out["data"]
    assert set(data["live_now"]) == {"LAX", "SNA"}
    assert data["live_now"]["SNA"]["code"] == "SNA"
    assert any("live_now" in a for a in out["assumptions"])
    # Same scores as the score table computed without any live call.
    scored = tools._scored(tools.ScoringParams()).set_index("code")
    for c in ("LAX", "SNA"):
        assert data["metrics"]["expansion_score"][c]["value"] == round(float(scored.loc[c, "expansion_score"]), 4)


def test_unmet_demand_attaches_live_now():
    out = tools.run_tool("unmet_demand", {"code": "SFO"})
    assert out["data"]["live_now"]["code"] == "SFO"
    assert out["data"]["verdict"] in {"weak", "moderate", "strong"}


def test_live_failure_does_not_break_tool(monkeypatch):
    monkeypatch.setattr(live_apis, "faa_nas_status", lambda code: {"error": "FAA NAS Status request failed: timeout"})
    out = tools.run_tool("unmet_demand", {"code": "SFO"})
    assert "error" not in out
    assert "error" in out["data"]["live_now"]
