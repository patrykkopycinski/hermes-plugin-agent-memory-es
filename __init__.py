"""agent_memory_es — Hermes MemoryProvider backed by the agent-memory-es service.

Talks HTTP to the FastAPI service (retain/recall/reflect/promote/consolidate) with a
per-profile API key. Owner identity is the service-side owner bound to the key; the
profile never widens visibility by argument.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt


# Calibrated on 130 real prompts replayed against prod recall (docs/min-score-calibration.md).
# Fused score = RRF + recency, so it spans ~0.0179-0.0189 and tracks rank, not relevance.
DEFAULT_PREFETCH_MIN_SCORE = 0.0184

# Server memory kinds. Prefetch skips `procedural` by default: 144/650 top-5 hits on 130 real prompts
# were procedural, all 2 distinct team project-profile blobs, 0/11 labelled relevant
# (docs/min-score-calibration.md). The explicit agent_memory_recall tool still searches every kind.
KINDS = ("episodic", "semantic", "procedural")
DEFAULT_PREFETCH_KINDS = ("episodic", "semantic")

RECALL_PROPERTIES: Dict[str, Any] = {
    "query": {"type": "string"},
    "min_score": {"type": "number",
                  "description": "Optional floor on the fused score; if nothing clears it the "
                                 "result is {abstained: true}. Default off."},
    "filter": {"type": "object",
               "description": "Optional tag filter {all, any, none, narrow_any}, applied in ES. "
                              "A filter matching nothing abstains; it never falls back to unfiltered."},
}


def _stored_prefetch_min_score() -> Optional[str]:
    return _stored_config_value("prefetch_min_score")


def prefetch_min_score() -> Optional[float]:
    """min_score sent with every prefetch.

    Precedence: AMES_PREFETCH_MIN_SCORE env > stored config key `prefetch_min_score` > default.
    ''/off/none/false disables; an unparseable value falls back to the default.
    """
    raw = os.environ.get("AMES_PREFETCH_MIN_SCORE")
    if raw is None:
        raw = _stored_prefetch_min_score()
    if raw is None:
        return DEFAULT_PREFETCH_MIN_SCORE
    raw = raw.strip().lower()
    if raw in ("", "off", "none", "false"):
        return None
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PREFETCH_MIN_SCORE


def _stored_config_value(key: str) -> Optional[str]:
    """Value saved by the desktop panel in <HERMES_HOME>/agent_memory_es/config.json, if any."""
    try:
        from hermes_constants import get_hermes_home
        data = json.loads((get_hermes_home() / "agent_memory_es" / "config.json").read_text("utf-8-sig"))
    except Exception:
        return None
    val = data.get(key) if isinstance(data, dict) else None
    return None if val is None else str(val)


def prefetch_kinds() -> Optional[List[str]]:
    """`kinds` sent with every prefetch, or None for all kinds (server default).

    Precedence: AMES_PREFETCH_KINDS env > stored config key `prefetch_kinds` > default
    (every kind except `procedural`). Value is a comma list of kinds; `all` restores the
    unfiltered behaviour. Empty, or a list with no known kind, falls back to the default.
    """
    raw = os.environ.get("AMES_PREFETCH_KINDS")
    if raw is None:
        raw = _stored_config_value("prefetch_kinds")
    if raw is None:
        return list(DEFAULT_PREFETCH_KINDS)
    raw = raw.strip().lower()
    if raw == "all":
        return None
    kinds = [k for k in dict.fromkeys(p.strip() for p in raw.split(",")) if k in KINDS]
    return kinds or list(DEFAULT_PREFETCH_KINDS)


# Every separator a model renders as a line break, not just \n (same set as the MCP server's fmt).
_LINE_SPLIT = re.compile(r"\r\n|[\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029]")
_FENCE_FRAGMENT = re.compile(r"<\s*/?\s*memory-context\s*>?|memory-context\s*>", re.IGNORECASE)


def _fence_safe(text: str) -> str:
    """Stored text is untrusted: it must not close the harness's <memory-context> fence or mint a
    column-0 "[id]" hit line. The harness strips fence tags in one pass, so nested fragments
    ("</memory-context</memory-context>>") reassemble into a real tag; remove to a fixpoint here.
    """
    prev = None
    while prev != text:
        prev, text = text, _FENCE_FRAGMENT.sub("", text)
    first, *rest = _LINE_SPLIT.split(text)
    return "\n".join([first, *("  | " + ln for ln in rest)])


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
            self._post("/memory/recall", {"query": "identity probe", "size": 1})
            self._owner = "ok"
        except Exception:
            self._owner = ""

    # -- Hermes hooks -----------------------------------------------------
    def system_prompt_block(self) -> str:
        return ("External memory: agent-memory-es (ES-native bank with private/team/common "
                "visibility). Tools: agent_memory_recall, agent_memory_retain, "
                "agent_memory_reflect, agent_memory_update, agent_memory_delete, agent_memory_unreject.")

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if is_trivial_prompt(query):
            return ""
        body: Dict[str, Any] = {"query": query, "size": 5}
        min_score = prefetch_min_score()
        if min_score is not None:
            body["min_score"] = min_score
        kinds = prefetch_kinds()
        if kinds is not None:
            body["kinds"] = kinds
        try:
            r = self._post("/memory/recall", body)
            # abstained => nothing cleared the floor: inject nothing (no empty header, no stale hits)
            self._last = [] if r.get("abstained") else r.get("fused", [])
            return "\n".join(f"[{_fence_safe(str(h['id']))}] {_fence_safe(str(h['text']))}"
                             for h in self._last[:5])
        except Exception:
            self._last = []
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
             "parameters": {"type": "object", "properties": RECALL_PROPERTIES,
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
            {"name": "agent_memory_update", "description": "Fix a memory in place by id (typo/stale value); owner-only",
             "parameters": {"type": "object",
                              "properties": {"doc_id": {"type": "string"},
                                             "text": {"type": "string", "description": "Replacement text (whole doc)"},
                                             "visibility": {"type": "string",
                                                            "enum": ["private", "team", "common"]}},
                              "required": ["doc_id"]}},
            {"name": "agent_memory_delete",
             "description": "Delete a memory (whole doc_group) by id; owner-only. A plain delete only removes it: "
                            "the same text can be retained again. Set retract=true when the memory is wrong and "
                            "must never be recorded again (also tombstones the text; undo with agent_memory_unreject).",
             "parameters": {"type": "object",
                              "properties": {"doc_id": {"type": "string"},
                                             "retract": {"type": "boolean",
                                                         "description": "true = wrong, never record it again "
                                                                        "(tombstone the text); omit for a plain delete"}},
                              "required": ["doc_id"]}},
            {"name": "agent_memory_unreject",
             "description": "Lift tombstones left by agent_memory_delete with retract=true so the value can be "
                            "retained again; owner-only. Pass exactly one of text or source_id (the doc id the "
                            "retracting delete was called with). Returns {lifted, source_ids, by}.",
             "parameters": {"type": "object",
                              "properties": {"text": {"type": "string",
                                                      "description": "Rejected text that should be retainable again"},
                                             "source_id": {"type": "string",
                                                           "description": "Doc id of the retracted memory (max 512 chars)"}}}},
        ]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        try:
            if tool_name == "agent_memory_recall":
                body = {"query": args["query"], "size": 8}
                # explicit tool calls stay unfiltered unless the caller opts in
                for opt in ("min_score", "filter"):
                    if args.get(opt) is not None:
                        body[opt] = args[opt]
                r = self._post("/memory/recall", body)
                if r.get("abstained"):
                    return json.dumps({"abstained": True, "results": []})
                return json.dumps([{"id": h["id"], "text": h["text"],
                                    "visibility": h["visibility"]} for h in r["fused"]])
            if tool_name == "agent_memory_retain":
                r = self._post("/memory/retain", {"kind": "semantic", "text": args["text"],
                                                  "visibility": args.get("visibility", "private")})
                return json.dumps({"stored": r["_id"]})
            if tool_name == "agent_memory_reflect":
                # reflect runs multi-round LLM synthesis server-side (~60s+);
                # default 20s _post timeout killed every reflect call
                r = self._post("/memory/reflect", {"question": args["question"]}, timeout=150)
                return json.dumps(r)
            if tool_name == "agent_memory_update":
                body = {"kind": args.get("kind", "semantic"), "doc_id": args["doc_id"]}
                for opt in ("text", "tags", "visibility"):
                    if args.get(opt) is not None:
                        body[opt] = args[opt]
                r = self._post("/memory/update", body)
                return json.dumps(r)
            if tool_name == "agent_memory_delete":
                body = {"kind": args.get("kind", "semantic"), "doc_id": args["doc_id"]}
                # only when provided; a non-bool is passed through so the backend's 422 surfaces
                if args.get("retract") is not None:
                    body["retract"] = args["retract"]
                r = self._post("/memory/delete", body)
                return json.dumps(r)
            if tool_name == "agent_memory_unreject":
                has_text, has_source = args.get("text") is not None, args.get("source_id") is not None
                if has_text == has_source:
                    return json.dumps({"error": "pass exactly one of text or source_id"})
                key = "text" if has_text else "source_id"
                v = args[key]
                if not isinstance(v, str) or not v.strip():
                    return json.dumps({"error": f"{key} must be a non-empty string"})
                return json.dumps(self._post("/memory/unreject", {key: v}))
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


def register(ctx) -> None:
    """Register the agent-memory-es provider with the plugin system."""
    ctx.register_memory_provider(AgentMemoryEsProvider())
