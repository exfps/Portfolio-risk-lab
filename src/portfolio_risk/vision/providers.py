"""HTTP clients for vision-capable model APIs, using only the standard library.

Two wire formats cover three providers: the OpenAI Chat Completions format (OpenAI, DeepSeek)
and the Anthropic Messages format. The API key is held in memory for the life of the client, is
sent only in a request header over HTTPS, and is removed from every error message. Nothing is
retried automatically, because each attempt can cost money.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from portfolio_risk.errors import ConfigurationError, ExtractionError

TIMEOUT_SECONDS = 90.0
MAX_OUTPUT_TOKENS = 2048
_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_MAX_DETAIL = 300
BASE_URL_OVERRIDE = "PORTFOLIO_RISK_VISION_BASE_URL"
DISABLE_IMPORT = "PORTFOLIO_RISK_DISABLE_IMPORT"
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    base_url: str
    api: Literal["openai", "anthropic"]
    default_model: str
    token_parameter: str
    note: str


PROVIDERS: tuple[Provider, ...] = (
    Provider(
        "anthropic",
        "Anthropic (Claude)",
        "https://api.anthropic.com",
        "anthropic",
        "claude-sonnet-5-5",
        "max_tokens",
        "Any Claude model that accepts images.",
    ),
    Provider(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1",
        "openai",
        "",
        "max_completion_tokens",
        "Enter the name of a vision-capable model from your OpenAI account.",
    ),
    Provider(
        "deepseek",
        "DeepSeek",
        "https://api.deepseek.com",
        "openai",
        "deepseek-v4-flash-vision-exp",
        "max_tokens",
        "Experimental vision model; ordinary DeepSeek models reject images.",
    ),
)


def _ssl_context() -> ssl.SSLContext:
    """TLS context that verifies certificates, using the ``certifi`` bundle when it is installed.

    Python installed from python.org on macOS ships without root certificates, which makes every
    HTTPS request fail with CERTIFICATE_VERIFY_FAILED. Streamlit installs ``certifi``, so using it
    fixes that without ever disabling verification.
    """
    try:
        import certifi  # noqa: PLC0415 - optional dependency
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def provider_by_key(key: str) -> Provider:
    for provider in PROVIDERS:
        if provider.key == key:
            return provider
    raise ConfigurationError(f"Unknown provider {key!r}.")


def import_disabled() -> bool:
    """True when the operator switched the screenshot feature off (for example on a hosted demo)."""
    return os.environ.get(DISABLE_IMPORT, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class ModelReply:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    truncated: bool


def _tokens(usage: object, *names: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    for name in names:
        value = usage.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


@dataclass(frozen=True)
class VisionClient:
    """One provider, one key, one model. Construct per request; do not store the key elsewhere."""

    provider: Provider
    api_key: str = field(repr=False)
    model: str
    timeout: float = TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ConfigurationError("An API key is required.")
        if any(ch.isspace() or ord(ch) < 32 for ch in self.api_key.strip()):
            raise ConfigurationError("The API key contains spaces or line breaks. Paste it again.")
        if not self.model.strip():
            raise ConfigurationError(f"Enter a model name for {self.provider.label}.")

    # -- request construction -------------------------------------------------------------------

    def _base_url(self) -> str:
        override = os.environ.get(BASE_URL_OVERRIDE, "").strip()
        base = override or self.provider.base_url
        parts = urlsplit(base)
        loopback = parts.hostname in _LOOPBACK
        if parts.scheme != "https" and not (parts.scheme == "http" and loopback):
            raise ConfigurationError(
                "API requests must use HTTPS, so the key is never sent in clear."
            )
        if override and not loopback:
            raise ConfigurationError(f"{BASE_URL_OVERRIDE} may only point at localhost.")
        return base.rstrip("/")

    def _request(
        self, image_b64: str, media_type: str, prompt: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        model = self.model.strip()
        if self.provider.api == "anthropic":
            url = f"{self._base_url()}/v1/messages"
            headers = {"x-api-key": self.api_key.strip(), "anthropic-version": "2023-06-01"}
            body: dict[str, Any] = {
                "model": model,
                self.provider.token_parameter: MAX_OUTPUT_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            }
        else:
            url = f"{self._base_url()}/chat/completions"
            headers = {"Authorization": f"Bearer {self.api_key.strip()}"}
            body = {
                "model": model,
                self.provider.token_parameter: MAX_OUTPUT_TOKENS,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{media_type};base64,{image_b64}"},
                            },
                        ],
                    }
                ],
            }
        return url, headers, body

    # -- transport ------------------------------------------------------------------------------

    def _scrub(self, text: str) -> str:
        cleaned = text.replace(self.api_key.strip(), "[key removed]")
        cleaned = " ".join(cleaned.split())
        return cleaned if len(cleaned) <= _MAX_DETAIL else cleaned[:_MAX_DETAIL] + "..."

    def _provider_message(self, raw: bytes) -> str:
        try:
            error = json.loads(raw.decode("utf-8", "replace")).get("error")
        except (ValueError, AttributeError):
            return ""
        message = error.get("message") if isinstance(error, dict) else error
        return self._scrub(message) if isinstance(message, str) else ""

    def _post(self, url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        name = self.provider.label
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout, context=_ssl_context()
            ) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as error:
            detail = self._provider_message(error.read(_MAX_RESPONSE_BYTES))
            suffix = f" Provider said: {detail}" if detail else ""
            if error.code in {401, 403}:
                raise ExtractionError(
                    f"{name} rejected the API key or its permissions.{suffix}"
                ) from None
            if error.code == 404:
                raise ExtractionError(
                    f"{name} does not know this model or endpoint.{suffix}"
                ) from None
            if error.code == 429:
                raise ExtractionError(
                    f"{name} rate limit or quota reached. Wait, then try again.{suffix}"
                ) from None
            if error.code >= 500:
                raise ExtractionError(
                    f"{name} had a server error ({error.code}). Try again later.{suffix}"
                ) from None
            raise ExtractionError(f"{name} refused the request ({error.code}).{suffix}") from None
        except urllib.error.URLError as error:
            if isinstance(error.reason, ssl.SSLCertVerificationError):
                raise ExtractionError(
                    f"Could not verify {name}'s security certificate, so nothing was sent. "
                    "On macOS with Python from python.org, run 'Install Certificates.command' "
                    "(in /Applications/Python 3.x), or run: python -m pip install --upgrade "
                    "certifi. If you are on a work network that inspects traffic, ask for its "
                    "root certificate."
                ) from None
            reason = self._scrub(str(error.reason))
            raise ExtractionError(f"Could not reach {name}: {reason}.") from None
        except TimeoutError:
            raise ExtractionError(
                f"{name} did not answer within {self.timeout:.0f} seconds."
            ) from None
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ExtractionError(f"{name} returned an unexpectedly large response.")
        try:
            parsed = json.loads(raw)
        except ValueError:
            raise ExtractionError(f"{name} returned something that is not JSON.") from None
        if not isinstance(parsed, dict):
            raise ExtractionError(f"{name} returned an unexpected response.")
        return parsed

    # -- public ---------------------------------------------------------------------------------

    def read_image(self, image: bytes, media_type: str, prompt: str) -> ModelReply:
        """Send one image and prompt; return the model's text and token usage."""
        encoded = base64.b64encode(image).decode("ascii")
        url, headers, body = self._request(encoded, media_type, prompt)
        data = self._post(url, headers, body)
        return self._reply(data)

    def _reply(self, data: dict[str, Any]) -> ModelReply:
        name = self.provider.label
        unexpected = ExtractionError(f"{name} returned an answer in an unexpected shape.")
        if self.provider.api == "anthropic":
            blocks = data.get("content")
            if not isinstance(blocks, list):
                raise unexpected
            text = "".join(
                b["text"] for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str)
            )
            return ModelReply(
                text,
                _tokens(data.get("usage"), "input_tokens"),
                _tokens(data.get("usage"), "output_tokens"),
                data.get("stop_reason") == "max_tokens",
            )
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise unexpected
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        if not isinstance(content, str):
            raise unexpected
        return ModelReply(
            content,
            _tokens(data.get("usage"), "prompt_tokens", "input_tokens"),
            _tokens(data.get("usage"), "completion_tokens", "output_tokens"),
            choices[0].get("finish_reason") == "length",
        )
