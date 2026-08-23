"""LLM providers: one interface, three ways to reach a model.

* :class:`ClaudeCliProvider` — shells out to the local Claude Code CLI. This is
  the reason AI mode costs no API money: it runs under the subscription the CLI is
  already logged into. Used for synthesis, where quality matters most.
* :class:`OpenRouterProvider` — free models over HTTP, for bulk per-symbol work.
  Weak and rate-limited, so it walks its model list until one answers.
* :class:`AnthropicProvider` — the direct Messages API. Only reached if a chain
  names it, since it bills per token.
* :class:`NullProvider` — always refuses. What offline mode falls back to, so the
  caller degrades rather than branches.

**No provider raises.** Every failure comes back as an :class:`LLMResponse` with
``error`` set and empty text, because the contract above this layer is that AI
trouble degrades to Normal mode with a banner — never an exception in the middle
of a daily run.

Token counts come from the provider when it reports them and from a character
estimate when it doesn't. The estimate is only ever used for budgeting, and it
deliberately errs high so a cap binds early rather than late.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from nepse_trader.config import Settings, get_settings

log = logging.getLogger("nepse_trader.ai.providers")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# Characters per token for providers that report no usage. Real tokenisers land
# near 4; 3.5 overestimates on purpose — see the module docstring.
_CHARS_PER_TOKEN = 3.5

# Longest provider error text kept. Full bodies are megabytes of HTML sometimes.
_MAX_ERROR_CHARS = 300


def estimate_tokens(text: str) -> int:
    """Rough token count for budgeting when a provider reports no usage."""
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


@dataclass
class LLMResponse:
    """What a provider returned — or why it didn't."""

    text: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
    error: str = ""

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def ok(self) -> bool:
        """True when there is usable text and no error."""
        return bool(self.text.strip()) and not self.error

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached": self.cached,
            "ok": self.ok,
            "error": self.error,
        }


class LLMProvider(ABC):
    """Anything that can turn a prompt into text."""

    name: str = "provider"

    @property
    @abstractmethod
    def model(self) -> str:
        """The model this provider would use right now, for the ledger."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when the provider is configured well enough to try.

        Checked without any network or subprocess call — an unavailable provider
        is skipped silently, a failing one is reported.
        """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Claude Code CLI
# ---------------------------------------------------------------------------


def _run_subprocess(argv: list[str], stdin_text: str, timeout: float) -> tuple[int, str, str]:
    """Run *argv*, feed *stdin_text*, return ``(returncode, stdout, stderr)``."""
    proc = subprocess.run(  # noqa: S603 - argv is built from settings, not user input
        argv,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return (proc.returncode, proc.stdout, proc.stderr)


class ClaudeCliProvider(LLMProvider):
    """The local Claude Code CLI, driven as a subprocess.

    The prompt goes in on **stdin**, not argv: a full evidence pack is thousands
    of characters and would risk the argument-length limit.

    ``max_tokens`` and ``temperature`` have no CLI equivalent. They're accepted
    for interface parity and ignored rather than silently faked.
    """

    name = "claude_cli"

    def __init__(self, settings: Settings | None = None, *, runner=None) -> None:
        self.settings = settings or get_settings()
        # Injected in tests so the suite never shells out to a real CLI.
        self._runner = runner or _run_subprocess

    @property
    def model(self) -> str:
        return self.settings.claude_cli_model or "claude-cli-default"

    @property
    def available(self) -> bool:
        path = self.settings.claude_cli_path
        if not path:
            return False
        return bool(shutil.which(path)) or Path(path).is_file()

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        argv = [self.settings.claude_cli_path, "-p", "--output-format", "json"]
        if self.settings.claude_cli_model:
            argv += ["--model", self.settings.claude_cli_model]
        if system:
            argv += ["--append-system-prompt", system]

        try:
            code, out, err = self._runner(argv, prompt, self.settings.llm_timeout)
        except subprocess.TimeoutExpired:
            return self._failed(f"timed out after {self.settings.llm_timeout:.0f}s")
        except (OSError, ValueError) as exc:
            return self._failed(f"could not run {self.settings.claude_cli_path!r}: {exc}")

        if code != 0:
            return self._failed(_short(err) or _short(out) or f"exited {code}")
        return self._parse(out, prompt)

    def _failed(self, reason: str) -> LLMResponse:
        log.warning("claude_cli: %s", reason)
        return LLMResponse(provider=self.name, model=self.model, error=reason)

    def _parse(self, stdout: str, prompt: str) -> LLMResponse:
        """Read ``--output-format json``, tolerating a plain-text CLI too."""
        raw = (stdout or "").strip()
        if not raw:
            return self._failed("empty response")

        payload: object
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # An older or differently-configured CLI may just print the answer.
            return LLMResponse(
                text=raw,
                provider=self.name,
                model=self.model,
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(raw),
            )

        # `--output-format stream-json` emits a list of events; the result is last.
        if isinstance(payload, list):
            payload = next(
                (e for e in reversed(payload) if isinstance(e, dict) and "result" in e),
                {},
            )
        if not isinstance(payload, dict):
            return self._failed("unexpected JSON shape from the CLI")

        if payload.get("is_error") or payload.get("subtype") == "error":
            return self._failed(_short(str(payload.get("result") or payload.get("error") or "")))

        text = str(payload.get("result") or "").strip()
        if not text:
            return self._failed("CLI returned no result text")

        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        model = str(payload.get("model") or self.model)
        return LLMResponse(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("input_tokens") or estimate_tokens(prompt)),
            completion_tokens=int(usage.get("output_tokens") or estimate_tokens(text)),
        )


# ---------------------------------------------------------------------------
# HTTP providers
# ---------------------------------------------------------------------------


class OpenRouterProvider(LLMProvider):
    """OpenAI-compatible chat completions against OpenRouter's free models.

    Free models are rate-limited and sometimes simply down, so the configured
    model list is walked in order and the first one that answers wins. Every
    attempt's failure is kept, and the combined text becomes the error, so a run
    that finds no working model says which ones it tried.
    """

    name = "openrouter"

    def __init__(self, settings: Settings | None = None, *, client=None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def models(self) -> list[str]:
        return [m for m in self.settings.openrouter_models if m.strip()]

    @property
    def model(self) -> str:
        return self.models[0] if self.models else "(none configured)"

    @property
    def available(self) -> bool:
        return bool(self.settings.openrouter_api_key) and bool(self.models)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.available:
            return LLMResponse(provider=self.name, model=self.model, error="no API key or models")

        messages = [{"role": "user", "content": prompt}]
        if system:
            messages.insert(0, {"role": "system", "content": system})

        problems: list[str] = []
        for model in self.models:
            body = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            try:
                data = self._post(
                    f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                    body,
                    {
                        "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                        "X-Title": "nepse-trader",
                    },
                )
            except Exception as exc:  # noqa: BLE001 - try the next model
                problems.append(f"{model}: {_short(str(exc))}")
                continue

            text = _openrouter_text(data)
            if not text:
                problems.append(f"{model}: empty completion")
                continue
            usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
            return LLMResponse(
                text=text,
                provider=self.name,
                model=str(data.get("model") or model),
                prompt_tokens=int(usage.get("prompt_tokens") or estimate_tokens(prompt)),
                completion_tokens=int(usage.get("completion_tokens") or estimate_tokens(text)),
            )

        reason = "; ".join(problems) or "no models tried"
        log.warning("openrouter: %s", reason)
        return LLMResponse(provider=self.name, model=self.model, error=_short(reason))

    def _post(self, url: str, body: dict, headers: dict) -> dict:
        import httpx

        client = self._client
        if client is None:
            with httpx.Client(timeout=self.settings.llm_timeout) as fresh:
                response = fresh.post(url, json=body, headers=headers)
        else:
            response = client.post(url, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response was not a JSON object")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload


class AnthropicProvider(LLMProvider):
    """The Anthropic Messages API. Billed per token, so it is never a default."""

    name = "anthropic"

    def __init__(self, settings: Settings | None = None, *, client=None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def model(self) -> str:
        return self.settings.anthropic_model

    @property
    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.available:
            return LLMResponse(provider=self.name, model=self.model, error="no API key")

        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        try:
            data = self._post(body)
        except Exception as exc:  # noqa: BLE001 - the chain decides what happens next
            reason = _short(str(exc))
            log.warning("anthropic: %s", reason)
            return LLMResponse(provider=self.name, model=self.model, error=reason)

        text = _anthropic_text(data)
        if not text:
            return LLMResponse(provider=self.name, model=self.model, error="empty completion")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or self.model),
            prompt_tokens=int(usage.get("input_tokens") or estimate_tokens(prompt)),
            completion_tokens=int(usage.get("output_tokens") or estimate_tokens(text)),
        )

    def _post(self, body: dict) -> dict:
        import httpx

        headers = {
            "x-api-key": self.settings.anthropic_api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        client = self._client
        if client is None:
            with httpx.Client(timeout=self.settings.llm_timeout) as fresh:
                response = fresh.post(ANTHROPIC_URL, json=body, headers=headers)
        else:
            response = client.post(ANTHROPIC_URL, json=body, headers=headers)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("response was not a JSON object")
        if payload.get("error"):
            raise ValueError(str(payload["error"]))
        return payload


class NullProvider(LLMProvider):
    """Refuses every call. What offline mode resolves to."""

    name = "null"

    def __init__(self, reason: str = "no LLM provider available") -> None:
        self.reason = reason

    @property
    def model(self) -> str:
        return "(none)"

    @property
    def available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ) -> LLMResponse:
        return LLMResponse(provider=self.name, model=self.model, error=self.reason)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, type[LLMProvider]] = {
    ClaudeCliProvider.name: ClaudeCliProvider,
    OpenRouterProvider.name: OpenRouterProvider,
    AnthropicProvider.name: AnthropicProvider,
}


def build_provider(name: str, settings: Settings | None = None) -> LLMProvider:
    """Construct a provider by configuration name."""
    cls = PROVIDERS.get(name.strip().lower())
    if cls is None:
        raise ValueError(f"unknown LLM provider {name!r}; known: {', '.join(sorted(PROVIDERS))}")
    return cls(settings)


# ---------------------------------------------------------------------------
# Response shape helpers — pure, so malformed payloads are testable directly.
# ---------------------------------------------------------------------------


def _openrouter_text(data: dict) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return str(first.get("text") or "").strip()


def _anthropic_text(data: dict) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list):
        return ""
    parts = [
        str(b.get("text") or "")
        for b in blocks
        if isinstance(b, dict) and b.get("type", "text") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()


def _short(text: str) -> str:
    """One-line, length-capped error text fit for a log or a ledger row."""
    flat = " ".join((text or "").split())
    return flat[:_MAX_ERROR_CHARS]
