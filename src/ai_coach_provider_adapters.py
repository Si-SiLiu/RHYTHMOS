"""Explicit provider-adapter boundary for the RHYTHMOS AI Coach.

The context, contract, safety, and audit layers are provider-independent.  A
provider adapter owns only wire-format details: authentication headers,
request serialization, and response extraction.  Adapters are registered by
an exact provider id; there is deliberately no endpoint guessing or fallback
to an unapproved provider.
"""

from __future__ import annotations

import json
from typing import Any, Mapping, Protocol


class ProviderAdapterError(ValueError):
    """Raised when an adapter cannot safely translate a provider payload."""


class ProviderAdapter(Protocol):
    """Minimal wire-format surface required by the provider runtime."""

    provider_id: str
    credential_env: str

    def auth_headers(self, credential: str) -> dict[str, str]: ...

    def build_request(
        self,
        context: Mapping[str, Any],
        *,
        model: str,
        system_prompt: str,
        output_schema: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def extract_output_text(self, response: Mapping[str, Any]) -> str: ...


class OpenAIResponsesAdapter:
    """OpenAI Responses API adapter with strict structured output."""

    provider_id = "openai"
    credential_env = "OPENAI_API_KEY"

    def auth_headers(self, credential: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def build_request(
        self,
        context: Mapping[str, Any],
        *,
        model: str,
        system_prompt: str,
        output_schema: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "model": model,
            "store": False,
            "reasoning": {"effort": "low"},
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                context,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "rhythmos_ai_coach_output",
                    "description": "A grounded, safety-bounded RHYTHMOS explanation.",
                    "strict": True,
                    "schema": dict(output_schema),
                }
            },
        }

    def extract_output_text(self, response: Mapping[str, Any]) -> str:
        output_text = response.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text
        for item in response.get("output", []):
            if not isinstance(item, Mapping):
                continue
            for content in item.get("content", []):
                if not isinstance(content, Mapping):
                    continue
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    return content["text"]
        raise ProviderAdapterError("AI provider returned no structured output")


_ADAPTERS: dict[str, ProviderAdapter] = {
    OpenAIResponsesAdapter.provider_id: OpenAIResponsesAdapter(),
}


def get_provider_adapter(provider_id: str) -> ProviderAdapter:
    """Return an exact registered adapter or fail closed."""

    if not isinstance(provider_id, str) or not provider_id:
        raise ProviderAdapterError("AI provider adapter is not registered")
    try:
        return _ADAPTERS[provider_id]
    except KeyError as exc:
        raise ProviderAdapterError("AI provider adapter is not registered") from exc


def register_provider_adapter(provider_id: str, adapter: ProviderAdapter) -> None:
    """Register a provider explicitly; replacement is forbidden at runtime."""

    if not isinstance(provider_id, str) or not provider_id:
        raise ProviderAdapterError("AI provider id is invalid")
    if provider_id in _ADAPTERS:
        raise ProviderAdapterError("AI provider adapter is already registered")
    if getattr(adapter, "provider_id", None) != provider_id:
        raise ProviderAdapterError("AI provider adapter id does not match")
    if not isinstance(getattr(adapter, "credential_env", None), str):
        raise ProviderAdapterError("AI provider credential mapping is invalid")
    _ADAPTERS[provider_id] = adapter
