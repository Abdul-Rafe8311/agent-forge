"""anthropic adapter: lazy official SDK, one dispatch, no hidden retry."""

import os
from typing import Any

from ..exceptions import ConfigurationError, ProviderError
from ..types import ProviderCapabilities, ProviderRequest, ProviderResponse, TokenUsage
from ..utils import safe_request_id


class AnthropicProvider:
    def __init__(self, api_key: str | None = None, client: Any | None = None):
        """Retain explicit credentials/client; constructing the adapter performs no request."""
        self._key = api_key
        self._client = client
        self._owns = client is None
        self._configured = False

    def _get_client(self):
        if self._client is None:
            key = self._key or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise ConfigurationError("Set ANTHROPIC_API_KEY privately or inject a client")
            try:
                from anthropic import Anthropic
            except ImportError as exc:
                raise ConfigurationError('Install "agentforge-coding[anthropic]"') from exc
            self._client = Anthropic(api_key=key, max_retries=0)
        if not self._configured:
            self._client = self._client.with_options(max_retries=0)
            self._configured = True
        return self._client

    def capabilities(self, model: str) -> ProviderCapabilities:
        """No unverified model limit catalog is provided."""
        return ProviderCapabilities()

    def supports_strict_budget(self, request: ProviderRequest) -> bool:
        """Live accounting assumptions were not verified; strict mode fails before remote calls."""
        return False

    def _payload(self, request: ProviderRequest) -> dict:
        return {
            "model": request.model,
            "system": "\n".join(m.content for m in request.messages if m.role == "system"),
            "messages": [
                {"role": m.role, "content": m.content}
                for m in request.messages
                if m.role != "system"
            ],
        }

    def count_input_tokens(self, request: ProviderRequest) -> int | None:
        """Count the actual message formatting through the SDK; may raise safe provider errors."""
        try:
            client = self._get_client().with_options(timeout=request.timeout_seconds)
            return client.messages.count_tokens(**self._payload(request)).input_tokens
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ProviderError(
                "anthropic input counting failed", safe_request_id(getattr(exc, "request_id", None))
            ) from exc

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Dispatch one capped request and normalize usage; never turn SDK failures into success."""
        try:
            client = self._get_client().with_options(timeout=request.timeout_seconds)
            response = client.messages.create(
                **self._payload(request), max_tokens=request.max_output_tokens
            )
            usage = response.usage
            if usage is None:
                normalized = TokenUsage(0, 0, accounting="unknown")
            else:
                cached = getattr(usage, "cache_read_input_tokens", 0) or 0
                created = getattr(usage, "cache_creation_input_tokens", 0) or 0
                normalized = TokenUsage(
                    usage.input_tokens + cached + created, usage.output_tokens, cached
                )
            text = "\n".join(b.text for b in response.content if b.type == "text")
            reason = response.stop_reason
            return ProviderResponse(
                text,
                normalized,
                request.model,
                reason,
                safe_request_id(getattr(response, "_request_id", None)),
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ProviderError(
                "anthropic generation failed", safe_request_id(getattr(exc, "request_id", None))
            ) from exc

    def close(self) -> None:
        """Close owned SDK resources; borrowed clients retain caller ownership."""
        if self._owns and self._client is not None:
            self._client.close()
            self._client = None
