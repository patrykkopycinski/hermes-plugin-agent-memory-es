"""agent_memory_es declared config surface — rendered by the generic desktop panel."""

from plugins.memory.config_schema import (
    KIND_SECRET, KIND_TEXT,
    ProviderConfigSchema, ProviderField,
)

CONFIG_SCHEMA = ProviderConfigSchema(
    name="agent_memory_es",
    label="agent-memory-es",
    docs_url="https://github.com/patrykkopycinski/agent-memory-es",
    fields=(
        ProviderField(
            key="url", label="Service URL", kind=KIND_TEXT, default="http://localhost:8123",
            description="agent-memory-es FastAPI endpoint.",
            placeholder="http://localhost:8123", env_fallbacks=("AMES_SERVICE_URL",), inline=True,
        ),
        ProviderField(
            key="api_key", label="API key", kind=KIND_SECRET, env_key="AMES_SERVICE_KEY",
            description="Per-profile API key; determines the service-side owner identity. "
                        "Visibility is bound to the key — the profile can never widen it.",
        ),
    ),
)
