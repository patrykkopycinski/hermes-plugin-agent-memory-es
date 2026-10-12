"""prefetch excludes `procedural` by default; override via env / stored config; recall tool unaffected (no network)."""
from __future__ import annotations

import json

import pytest

from test_min_score import ames  # same module loader

Q = "what did we decide about the kibana eval gate"


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.delenv("AMES_PREFETCH_KINDS", raising=False)
    monkeypatch.delenv("AMES_PREFETCH_MIN_SCORE", raising=False)
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    p = ames.AgentMemoryEsProvider()
    p.calls = []
    p.response = {"fused": [{"id": "d1", "text": "m", "visibility": "private"}], "abstained": False}

    def fake_post(path, body, timeout=20):
        p.calls.append((path, body))
        return p.response

    p._post = fake_post
    return p


def _store(tmp_path, value):
    d = tmp_path / "agent_memory_es"
    d.mkdir(exist_ok=True)
    (d / "config.json").write_text(json.dumps({"prefetch_kinds": value}))


def test_default_prefetch_sends_kinds_without_procedural(provider):
    provider.prefetch(Q)
    kinds = provider.calls[0][1]["kinds"]
    assert kinds == ["episodic", "semantic"]
    assert "procedural" not in kinds


def test_env_all_restores_unfiltered(provider, monkeypatch):
    monkeypatch.setenv("AMES_PREFETCH_KINDS", "all")
    provider.prefetch(Q)
    assert "kinds" not in provider.calls[0][1]


def test_stored_all_restores_unfiltered(provider, tmp_path):
    _store(tmp_path, "all")
    provider.prefetch(Q)
    assert "kinds" not in provider.calls[0][1]


def test_env_custom_list(provider, monkeypatch):
    monkeypatch.setenv("AMES_PREFETCH_KINDS", " Semantic , procedural,semantic")
    provider.prefetch(Q)
    assert provider.calls[0][1]["kinds"] == ["semantic", "procedural"]


def test_env_beats_stored(provider, tmp_path, monkeypatch):
    _store(tmp_path, "episodic")
    monkeypatch.setenv("AMES_PREFETCH_KINDS", "semantic")
    provider.prefetch(Q)
    assert provider.calls[0][1]["kinds"] == ["semantic"]


@pytest.mark.parametrize("raw", ["", "bogus", " , "])
def test_unusable_value_falls_back_to_default(provider, monkeypatch, raw):
    monkeypatch.setenv("AMES_PREFETCH_KINDS", raw)
    provider.prefetch(Q)
    assert provider.calls[0][1]["kinds"] == ["episodic", "semantic"]


def test_recall_tool_still_searches_all_kinds(provider):
    provider.handle_tool_call("agent_memory_recall", {"query": "q"})
    assert "kinds" not in provider.calls[0][1]


def test_min_score_still_sent_with_kinds(provider):
    provider.prefetch(Q)
    body = provider.calls[0][1]
    assert body["min_score"] == ames.DEFAULT_PREFETCH_MIN_SCORE and body["size"] == 5
