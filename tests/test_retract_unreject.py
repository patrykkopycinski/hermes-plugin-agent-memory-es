"""agent_memory_delete retract passthrough + agent_memory_unreject (no network)."""
from __future__ import annotations

import json

import pytest

from test_min_score import ames  # same module loader


@pytest.fixture
def provider(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    p = ames.AgentMemoryEsProvider()
    p.calls = []

    def fake_post(path, body, timeout=20):
        p.calls.append((path, body))
        return {"ok": True}

    p._post = fake_post
    return p


def _schema(p, name):
    return next(s for s in p.get_tool_schemas() if s["name"] == name)


def test_delete_sends_retract_only_when_provided(provider):
    provider.handle_tool_call("agent_memory_delete", {"doc_id": "d1"})
    provider.handle_tool_call("agent_memory_delete", {"doc_id": "d1", "retract": True})
    provider.handle_tool_call("agent_memory_delete", {"doc_id": "d1", "retract": False})
    assert provider.calls == [
        ("/memory/delete", {"kind": "semantic", "doc_id": "d1"}),
        ("/memory/delete", {"kind": "semantic", "doc_id": "d1", "retract": True}),
        ("/memory/delete", {"kind": "semantic", "doc_id": "d1", "retract": False}),
    ]


def test_delete_description_no_longer_claims_tombstone_on_plain_delete(provider):
    s = _schema(provider, "agent_memory_delete")
    assert s["parameters"]["properties"]["retract"]["type"] == "boolean"
    assert "plain delete only removes" in s["description"]
    assert "tombstoned" not in s["description"]


def test_unreject_posts_exactly_one_selector(provider):
    provider.handle_tool_call("agent_memory_unreject", {"source_id": "d1"})
    provider.handle_tool_call("agent_memory_unreject", {"text": "wrong fact"})
    assert provider.calls == [("/memory/unreject", {"source_id": "d1"}),
                              ("/memory/unreject", {"text": "wrong fact"})]


@pytest.mark.parametrize("args,msg", [
    ({}, "exactly one of text or source_id"),
    ({"text": "a", "source_id": "b"}, "exactly one of text or source_id"),
    ({"text": "  "}, "text must be a non-empty string"),
    ({"source_id": 5}, "source_id must be a non-empty string"),
])
def test_unreject_validates_client_side(provider, args, msg):
    out = json.loads(provider.handle_tool_call("agent_memory_unreject", args))
    assert msg in out["error"]
    assert provider.calls == []


def test_system_prompt_lists_unreject(provider):
    assert "agent_memory_unreject" in provider.system_prompt_block()
