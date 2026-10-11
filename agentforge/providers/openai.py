"""openai adapter: lazy official SDK, one dispatch, no hidden retry."""

import os
from typing import Any

from ..exceptions import ConfigurationError, ProviderError
from ..types import ProviderCapabilities, ProviderRequest, ProviderResponse, TokenUsage
from ..utils import safe_request_id


class OpenAIProvider:
    def __init__(self, api_key: str | None = None, client: Any | None = None):
        """Retain explicit credentials/client; constructing the adapter performs no request."""
        self._key = api_key
        self._client = client
        self._owns = client is None
        self._configured = False

    def _get_client(self):
        if self._client is None:
            key = self._key or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ConfigurationError("Set OPENAI_API_KEY privately or inject a client")
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ConfigurationError('Install "agentforge[openai]"') from exc
            self._client = OpenAI(api_key=key, max_retries=0)
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
            "input": [{"role": m.role, "content": m.content} for m in request.messages],
        }

    def count_input_tokens(self, request: ProviderRequest) -> int | None:
        """Count the actual message formatting through the SDK; may raise safe provider errors."""
        try:
            client = self._get_client().with_options(timeout=request.timeout_seconds)
            return client.responses.input_tokens.count(**self._payload(request)).input_tokens
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ProviderError(
                "openai input counting failed", safe_request_id(getattr(exc, "request_id", None))
            ) from exc

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """Dispatch one capped request and normalize usage; never turn SDK failures into success."""
        try:
            client = self._get_client().with_options(timeout=request.timeout_seconds)
            response = client.responses.create(
                **self._payload(request), max_output_tokens=request.max_output_tokens, store=False
            )
            usage = response.usage
            if usage is None:
                normalized = TokenUsage(0, 0, accounting="unknown")
            else:
                details = getattr(usage, "input_tokens_details", None)
                normalized = TokenUsage(
                    usage.input_tokens,
                    usage.output_tokens,
                    (getattr(details, "cached_tokens", 0) or 0),
                )
            text = response.output_text
            reason = response.status
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
                "openai generation failed", safe_request_id(getattr(exc, "request_id", None))
            ) from exc

    def close(self) -> None:
        """Close owned SDK resources; borrowed clients retain caller ownership."""
        if self._owns and self._client is not None:
            self._client.close()
            self._client = None
