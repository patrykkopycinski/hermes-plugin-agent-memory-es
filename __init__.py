"""agent_memory_es — Hermes MemoryProvider backed by the agent-memory-es service.

Talks HTTP to the FastAPI service (retain/recall/reflect/promote/consolidate) with a
per-profile API key. Owner identity is the service-side owner bound to the key; the
profile never widens visibility by argument.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt


class AgentMemoryEsProvider(MemoryProvider):
    DEFAULT_URL = "http://localhost:8123"

    def __init__(self):
        self._base = os.environ.get("AMES_SERVICE_URL", self.DEFAULT_URL)
        self._key = os.environ.get("AMES_SERVICE_KEY", "")
        self._owner = ""
        self._last: List[Dict[str, Any]] = []

    # -- plumbing ---------------------------------------------------------
    @property
    def name(self) -> str:
        return "agent_memory_es"

    def is_available(self) -> bool:
        try:
            urllib.request.urlopen(self._base + "/health", timeout=3)
            return True
        except Exception:
            return False

    def unavailable_reason(self) -> str:
        return f"service unreachable at {self._base}"

    def _post(self, path: str, body: dict, timeout: int = 20) -> dict:
        req = urllib.request.Request(
            self._base + path, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-API-Key": self._key})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)

    def initialize(self, session_id: str, **kwargs) -> None:
        # owner is whatever the service says the key is; cache for prompt block
        try:
            who = self._post("/memory/recall", {"query": "identity probe", "size": 1})
            self._owner = "ok"
        except Exception:
            self._owner = ""

    # -- Hermes hooks -----------------------------------------------------
    def system_prompt_block(self) -> str:
        return ("External memory: agent-memory-es (ES-native bank with private/team/common "
                "visibility). Tools: agent_memory_recall, agent_memory_retain, "
                "agent_memory_reflect.")

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if is_trivial_prompt(query):
            return ""
        try:
            r = self._post("/memory/recall", {"query": query, "size": 5})
            self._last = r.get("fused", [])
            return "\n".join(f"[{h['id']}] {h['text']}" for h in self._last[:5])
        except Exception:
            return ""

    def recall_status(self) -> Optional[RecallStatus]:
        if self._last:
            return RecallStatus(provider_label="agent-memory-es", count=len(self._last))
        return None

    def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None:
        # episodic evidence tier: the user's words, never the assistant's prose
        try:
            self._post("/memory/retain", {"kind": "episodic", "text": user_content[:4000]})
        except Exception:
            pass

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [
            {"name": "agent_memory_recall", "description": "Search the long-term memory bank",
             "parameters": {"type": "object", "properties": {"query": {"type": "string"}},
                              "required": ["query"]}},
            {"name": "agent_memory_retain", "description": "Store a durable fact in memory",
             "parameters": {"type": "object",
                              "properties": {"text": {"type": "string"},
                                             "visibility": {"type": "string",
                                                            "enum": ["private", "team", "common"]}},
                              "required": ["text"]}},
            {"name": "agent_memory_reflect", "description": "Answer a question from memory with citations",
             "parameters": {"type": "object", "properties": {"question": {"type": "string"}},
                              "required": ["question"]}},
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        try:
            if tool_name == "agent_memory_recall":
                r = self._post("/memory/recall", {"query": args["query"], "size": 8})
                return json.dumps([{"id": h["id"], "text": h["text"],
                                    "visibility": h["visibility"]} for h in r["fused"]])
            if tool_name == "agent_memory_retain":
                r = self._post("/memory/retain", {"kind": "semantic", "text": args["text"],
                                                  "visibility": args.get("visibility", "private")})
                return json.dumps({"stored": r["_id"]})
            if tool_name == "agent_memory_reflect":
                r = self._post("/memory/reflect", {"question": args["question"]})
                return json.dumps(r)
        except urllib.error.HTTPError as e:
            return json.dumps({"error": f"service {e.code}: {e.read().decode()[:200]}"})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)[:200]})
        return json.dumps({"error": f"unknown tool {tool_name}"})

    def on_memory_write(self, action: str, target: str, content: str,
                        metadata: Optional[Dict[str, Any]] = None) -> None:
        # mirror built-in memory writes into the semantic tier
        try:
            self._post("/memory/retain", {"kind": "semantic", "text": f"{target}: {content}"[:4000]})
        except Exception:
            pass
