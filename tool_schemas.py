"""OpenAI function-calling schemas for the agent_memory_es tools (pure data).

Contract note: Hermes memory-provider schemas use the OpenAI ``parameters`` key.
The MCP/Anthropic ``input_schema`` naming is silently emptied by the schema
sanitizer (tools/schema_sanitizer.py replaces missing ``parameters`` with an
empty object), which strips every argument — see the regression test in tests/.
"""

from __future__ import annotations

from typing import Any


TOOL_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "name": "agent_memory_recall",
        "description": "Search the long-term memory bank",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                       "required": ["query"]},
    },
    {
        "name": "agent_memory_retain",
        "description": "Store a durable fact in memory",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"},
                                      "visibility": {"type": "string",
                                                     "enum": ["private", "team", "common"]}},
                       "required": ["text"]},
    },
    {
        "name": "agent_memory_reflect",
        "description": "Answer a question from memory with citations",
        "parameters": {"type": "object", "properties": {"question": {"type": "string"}},
                       "required": ["question"]},
    },
)
