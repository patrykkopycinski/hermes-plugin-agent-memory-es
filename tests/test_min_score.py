"""min_score gating on prefetch + min_score/filter passthrough on the recall tool (no network)."""
from __future__ import annotations

import importlib.util
import json
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "ames_under_test", _ROOT / "__init__.py", submodule_search_locations=[str(_ROOT)])
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ames = _load()

HIT = {"id": "d1", "text": "some memory", "visibility": "private"}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.delenv("AMES_PREFETCH_MIN_SCORE", raising=False)
    p = ames.AgentMemoryEsProvider()
    p.calls = []
    p.response = {"fused": [HIT], "abstained": False}

    def fake_post(path, body, timeout=20):
        p.calls.append((path, body))
        return p.response

    p._post = fake_post
    return p


def test_prefetch_payload_includes_calibrated_min_score(provider):
    provider.prefetch("what did we decide about the kibana eval gate")
    _, body = provider.calls[0]
    assert body["min_score"] == ames.DEFAULT_PREFETCH_MIN_SCORE
    assert body["size"] == 5


def test_prefetch_min_score_env_override(provider, monkeypatch):
    monkeypatch.setenv("AMES_PREFETCH_MIN_SCORE", "0.0187")
    provider.prefetch("what did we decide about the kibana eval gate")
    assert provider.calls[0][1]["min_score"] == 0.0187


@pytest.mark.parametrize("raw", ["", "off", "none"])
def test_prefetch_min_score_can_be_disabled(provider, monkeypatch, raw):
    monkeypatch.setenv("AMES_PREFETCH_MIN_SCORE", raw)
    provider.prefetch("what did we decide about the kibana eval gate")
    assert "min_score" not in provider.calls[0][1]


def test_prefetch_injects_hits_when_not_abstained(provider):
    out = provider.prefetch("what did we decide about the kibana eval gate")
    assert out == "[d1] some memory"
    assert provider.recall_status().count == 1


def test_abstained_response_injects_nothing(provider):
    # even if a server shipped hits alongside abstained, the abstain flag wins
    provider.response = {"fused": [HIT], "abstained": True}
    out = provider.prefetch("what did we decide about the kibana eval gate")
    assert out == ""
    assert provider.recall_status() is None


def test_abstain_clears_previous_recall_status(provider):
    provider.prefetch("what did we decide about the kibana eval gate")
    assert provider.recall_status() is not None
    provider.response = {"fused": [], "abstained": True}
    provider.prefetch("what did we decide about the kibana eval gate")
    assert provider.recall_status() is None


def test_recall_tool_default_sends_no_min_score_or_filter(provider):
    provider.handle_tool_call("agent_memory_recall", {"query": "q"})
    _, body = provider.calls[0]
    assert "min_score" not in body and "filter" not in body


def test_recall_tool_passes_min_score_and_filter_through(provider):
    flt = {"all": ["catalog:elastic"], "none": ["kind:noise"]}
    provider.handle_tool_call("agent_memory_recall", {"query": "q", "min_score": 0.0185, "filter": flt})
    _, body = provider.calls[0]
    assert body["min_score"] == 0.0185
    assert body["filter"] == flt


def test_recall_tool_reports_abstain_and_never_relaxes(provider):
    provider.response = {"fused": [], "abstained": True}
    out = json.loads(provider.handle_tool_call(
        "agent_memory_recall", {"query": "q", "filter": {"all": ["nope:x"]}}))
    assert out == {"abstained": True, "results": []}
    assert len(provider.calls) == 1, "must not retry without the filter"


def test_recall_schema_exposes_min_score_and_filter(provider):
    props = {s["name"]: s for s in provider.get_tool_schemas()}["agent_memory_recall"]["parameters"]["properties"]
    assert props["min_score"]["type"] == "number"
    assert props["filter"]["type"] == "object"

