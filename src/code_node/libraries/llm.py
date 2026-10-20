"""
Language models through their SDKs: OpenAI (and Azure OpenAI) and Anthropic. A call names its model; a client made
without a timeout waits the SDK's own (ten minutes, then it tries again twice), which a short-lived function never
lives to see.
"""

from __future__ import annotations

from ..analysis.syntax import _a
from . import Call, Handle, Library, Use

_CLIENTS = {
    "OpenAI": "OpenAI",
    "AsyncOpenAI": "OpenAI",
    "AzureOpenAI": "Azure OpenAI",
    "AsyncAzureOpenAI": "Azure OpenAI",
    "Anthropic": "Anthropic",
    "AsyncAnthropic": "Anthropic",
    "AnthropicBedrock": "Anthropic on Bedrock",
    "AsyncAnthropicBedrock": "Anthropic on Bedrock",
    "AnthropicVertex": "Anthropic on Vertex AI",
    "AsyncAnthropicVertex": "Anthropic on Vertex AI",
}

_PARTS = frozenset(
    {  # a client's attributes that are parts of it, not methods: client.chat.completions.create
        "chat",
        "completions",
        "embeddings",
        "images",
        "audio",
        "speech",
        "transcriptions",
        "translations",
        "moderations",
        "responses",
        "files",
        "batches",
        "models",
        "fine_tuning",
        "jobs",
        "vector_stores",
        "uploads",
        "beta",
        "threads",
        "runs",
        "messages",
        "assistants",
        "realtime",
        "containers",
        "conversations",
        "evals",
        "webhooks",
        "skills",
    }
)

_READS = frozenset({"list", "retrieve", "count_tokens", "content", "results", "get"})

_WRITES = frozenset({"delete", "cancel", "upload"})

_LEGACY = {  # openai < 1.0: module functions -> the call they made
    "openai.ChatCompletion.create": "chat.completions.create",
    "openai.Completion.create": "completions.create",
    "openai.Embedding.create": "embeddings.create",
    "openai.Image.create": "images.generate",
}

_WAITS = "up to 10 minutes a try (the SDK's default timeout), and it tries 3 times"


class LlmLibrary(Library):
    """
    The OpenAI and Anthropic Python SDKs: a client, then client.chat.completions.create(model=...),
    client.responses.create(...), client.messages.create(...), client.embeddings.create(...).
    """

    name = "llm"
    title = "OpenAI and Anthropic"
    modules = ("openai", "anthropic")
    icon = "spark"

    def make(self, name: str, call: Call) -> Handle | Use | None:
        last = name.rsplit(".", 1)[-1]
        if last in _CLIENTS:
            return Handle(
                "client",
                _CLIENTS[last],
                opens=True,
                waits="" if call.given("timeout") else _WAITS,
                fix=f"{last}(timeout=20, max_retries=1)",
            )
        if name in _LEGACY:
            return self._use("OpenAI", _LEGACY[name], call)
        return None

    def attribute(self, handle: Handle, name: str) -> Handle | None:
        if name in _PARTS:
            path = f"{handle.fact('path')}.{name}".lstrip(".")
            return handle.but("client", path=path)
        return None

    def call(self, handle: Handle, method: str, call: Call) -> Handle | Use | None:
        if method in ("with_options", "copy"):
            timed = call.given("timeout")
            return Handle(handle.kind, handle.service, handle.facts, waits="" if timed else handle.waits)
        path = handle.fact("path")
        if not path:
            return None
        return self._use(handle.service, f"{path}.{method}", call)

    def _use(self, service: str, operation: str, call: Call) -> Use:
        method = operation.rsplit(".", 1)[-1]
        model = call.shown(None, "model") or call.shown(None, "engine")
        if method in _READS or operation.startswith("models."):
            return Use(operation, "reads", model, service)
        if method in _WRITES or operation.startswith(("files.", "vector_stores.", "uploads.")):
            return Use(operation, "writes", model, service)
        batch = "" if operation.startswith("batches.") else "the Batch API (half the price, when the answers can wait)"
        return Use(operation, "runs", model, service, batch=batch)

    def describe(self, handle: Handle) -> str:
        path = handle.fact("path")
        return f"{handle.service}'s {path}" if path else f"{_a(handle.service)} {handle.service} client"
