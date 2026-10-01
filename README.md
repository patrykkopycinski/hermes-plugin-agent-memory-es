# agent_memory_es — Hermes memory provider plugin

Standalone [Hermes Agent](https://github.com/NousResearch/hermes-agent) memory
plugin that backs Hermes long-term memory with the
[agent-memory-es](https://github.com/patrykkopycinski/agent-memory-es) service
(ES-native memory bank with `private` / `team` / `common` visibility tiers).

Adds three agent tools:

| Tool | Purpose |
|---|---|
| `agent_memory_recall` | Search the long-term memory bank |
| `agent_memory_retain` | Store a durable fact (with visibility tier) |
| `agent_memory_reflect` | Answer a question from memory with citations |

Owner identity is the service-side owner bound to the API key; the profile can
never widen visibility by argument.

## Architecture

![agent-memory-es topology](https://raw.githubusercontent.com/patrykkopycinski/agent-memory-es/main/docs/diagrams/architecture.svg)

This plugin is a thin HTTP client — all memory logic (hybrid recall, visibility
filtering, promotion guard, consolidation) lives in the
[agent-memory-es](https://github.com/patrykkopycinski/agent-memory-es) service:

```
Hermes Agent ── this plugin ──HTTP── FastAPI :8123 ── Elasticsearch
                                     (auth: X-API-Key → owner_id)
```

- On every turn, `sync_turn` mirrors the user's words into the **episodic** tier
- Built-in Hermes memory writes are mirrored into the **semantic** tier
  (`on_memory_write`)
- Prompts get a lightweight **prefetch** recall (top-5) before the model answers
- Full architecture walkthrough: [docs/ARCHITECTURE.md](https://github.com/patrykkopycinski/agent-memory-es/blob/main/docs/ARCHITECTURE.md)
  · interactive explainer: [docs/explainer.html](https://github.com/patrykkopycinski/agent-memory-es/blob/main/docs/explainer.html)


## Install

```bash
# 1. run the agent-memory-es service (see its repo) and mint a profile API key

# 2. drop this plugin into user plugins (dir name MUST stay agent_memory_es)
git clone https://github.com/patrykkopycinski/hermes-plugin-agent-memory-es.git \
  ~/.hermes/plugins/agent_memory_es

# 3. point Hermes at it
#    ~/.hermes/config.yaml:
#      memory:
#        provider: agent_memory_es
export AMES_SERVICE_URL=http://localhost:8123   # default
export AMES_SERVICE_KEY=<your-key>

# 4. verify
hermes memory status
```

## Config

| Key | Env fallback | Default | Description |
|---|---|---|---|
| `url` | `AMES_SERVICE_URL` | `http://localhost:8123` | FastAPI service endpoint |
| `api_key` | `AMES_SERVICE_KEY` | — | Per-profile API key (determines owner identity) |

## Development

```bash
cd ~/.hermes/hermes-agent   # any hermes-agent checkout provides the contract
python -m pytest ~/.hermes/plugins/agent_memory_es/tests -q
```

The regression test pins the OpenAI `parameters` schema key — the sanitizer
silently empties MCP-style `input_schema`, which strips every tool argument.
