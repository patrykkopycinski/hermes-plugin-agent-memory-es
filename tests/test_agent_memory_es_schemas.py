from __future__ import annotations

"""Regression: agent_memory_es provider schemas must use the OpenAI ``parameters``
key, not the MCP/Anthropic ``input_schema`` naming. The sanitizer replaces a
missing ``parameters`` with an empty object, which silently strips every
argument (the tool then fails with ``{"error": "'query'"}`` at call time)."""

from agent.memory_manager import normalize_tool_schema
from tools.schema_sanitizer import sanitize_tool_schemas

from plugins.memory import load_memory_provider


def _provider():
    p = load_memory_provider("agent_memory_es", register_skills=False)
    assert p is not None, "agent_memory_es not discoverable (user/project/bundled)"
    return p


def _sanitized_schemas() -> list[dict]:
    tools = [{"type": "function", "function": normalize_tool_schema(s)}
             for s in _provider().get_tool_schemas()]
    return [t["function"] for t in sanitize_tool_schemas(tools)]


def test_uses_parameters_not_input_schema():
    for s in _provider().get_tool_schemas():
        assert s.get("parameters"), f"{s.get('name')}: missing 'parameters'"
        assert "input_schema" not in s, f"{s.get('name')}: stale 'input_schema' key"


def test_schemas_survive_sanitizer_with_args_intact():
    by_name = {s["name"]: s for s in _sanitized_schemas()}
    assert set(by_name) == {"agent_memory_recall", "agent_memory_retain", "agent_memory_reflect"}
    assert by_name["agent_memory_recall"]["parameters"]["properties"]["query"] == {"type": "string"}
    assert "query" in by_name["agent_memory_recall"]["parameters"].get("required", [])
    assert "text" in by_name["agent_memory_retain"]["parameters"]["properties"]
