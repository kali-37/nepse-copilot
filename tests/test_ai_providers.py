"""Tests for the LLM providers.

The contract this file pins down: **a provider never raises.** Everything above
this layer branches on ``LLMResponse.ok``, so a timeout, a 500, a malformed body
or a missing binary must all arrive as data. A provider that raised would abort a
daily run halfway through, which is precisely what AI mode is supposed to avoid.

Nothing here touches the network or a real CLI: the HTTP legs are respx-mocked and
the Claude CLI leg gets an injected runner.
"""

from __future__ import annotations

import json
import subprocess

import httpx
import pytest
import respx

from nepse_trader.ai.providers import (
    ANTHROPIC_URL,
    AnthropicProvider,
    ClaudeCliProvider,
    NullProvider,
    OpenRouterProvider,
    build_provider,
    estimate_tokens,
)
from nepse_trader.config import Settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _settings(**kw) -> Settings:
    base = {"_env_file": None, "llm_timeout": 5.0}
    base.update(kw)
    return Settings(**base)


def _runner(returncode: int = 0, stdout: str = "", stderr: str = "", raises=None):
    """A stand-in for ``_run_subprocess`` that records what it was handed."""
    calls: list[tuple[list[str], str, float]] = []

    def run(argv, stdin_text, timeout):
        calls.append((argv, stdin_text, timeout))
        if raises is not None:
            raise raises
        return (returncode, stdout, stderr)

    run.calls = calls
    return run


def _cli_json(result: str = "hello", **extra) -> str:
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": result,
        "usage": {"input_tokens": 120, "output_tokens": 34},
    }
    payload.update(extra)
    return json.dumps(payload)


def _openrouter_body(content: str = "hi", model: str = "m:free", **extra) -> dict:
    body = {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20},
    }
    body.update(extra)
    return body


class TestEstimateTokens:
    def test_empty_text_costs_nothing(self):
        assert estimate_tokens("") == 0

    def test_scales_with_length(self):
        assert estimate_tokens("x" * 350) > estimate_tokens("x" * 35)

    def test_never_returns_zero_for_real_text(self):
        """A one-character prompt still counts as a call's worth of tokens."""
        assert estimate_tokens("x") >= 1

    def test_overestimates_rather_than_under(self):
        """Budgeting must bind early: 3.5 chars/token beats a real tokeniser's ~4."""
        assert estimate_tokens("a" * 400) > 100


class TestClaudeCliProvider:
    def test_reports_unavailable_when_the_binary_is_missing(self):
        provider = ClaudeCliProvider(_settings(claude_cli_path="definitely-not-a-real-binary"))
        assert provider.available is False

    def test_empty_path_is_unavailable(self):
        assert ClaudeCliProvider(_settings(claude_cli_path="")).available is False

    def test_parses_the_json_output_format(self):
        provider = ClaudeCliProvider(_settings(), runner=_runner(stdout=_cli_json("the answer")))
        response = provider.complete("prompt")
        assert response.ok
        assert response.text == "the answer"
        assert (response.prompt_tokens, response.completion_tokens) == (120, 34)

    def test_prompt_goes_in_on_stdin(self):
        """A full evidence pack on argv would risk the argument-length limit."""
        runner = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(), runner=runner).complete("the whole evidence pack")
        argv, stdin_text, _ = runner.calls[0]
        assert stdin_text == "the whole evidence pack"
        assert "the whole evidence pack" not in argv

    def test_requests_json_output(self):
        runner = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(), runner=runner).complete("p")
        argv = runner.calls[0][0]
        assert argv[1:4] == ["-p", "--output-format", "json"]

    def test_model_flag_only_when_configured(self):
        bare = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(), runner=bare).complete("p")
        assert "--model" not in bare.calls[0][0]

        picked = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(claude_cli_model="claude-opus-5"), runner=picked).complete("p")
        assert picked.calls[0][0][-2:] == ["--model", "claude-opus-5"]

    def test_system_prompt_is_appended(self):
        runner = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(), runner=runner).complete("p", system="be terse")
        assert runner.calls[0][0][-2:] == ["--append-system-prompt", "be terse"]

    def test_timeout_comes_from_settings(self):
        runner = _runner(stdout=_cli_json())
        ClaudeCliProvider(_settings(llm_timeout=42.0), runner=runner).complete("p")
        assert runner.calls[0][2] == 42.0

    def test_nonzero_exit_is_an_error_not_an_exception(self):
        provider = ClaudeCliProvider(_settings(), runner=_runner(1, stderr="not logged in"))
        response = provider.complete("p")
        assert not response.ok
        assert "not logged in" in response.error

    def test_timeout_degrades(self):
        provider = ClaudeCliProvider(
            _settings(), runner=_runner(raises=subprocess.TimeoutExpired("claude", 5))
        )
        response = provider.complete("p")
        assert not response.ok
        assert "timed out" in response.error

    def test_missing_binary_at_call_time_degrades(self):
        provider = ClaudeCliProvider(_settings(), runner=_runner(raises=OSError("no such file")))
        response = provider.complete("p")
        assert not response.ok
        assert "no such file" in response.error

    def test_error_result_is_rejected(self):
        stdout = _cli_json("rate limited", is_error=True)
        response = ClaudeCliProvider(_settings(), runner=_runner(stdout=stdout)).complete("p")
        assert not response.ok
        assert "rate limited" in response.error

    def test_plain_text_output_is_still_usable(self):
        """A CLI that ignores --output-format shouldn't cost us the answer."""
        response = ClaudeCliProvider(_settings(), runner=_runner(stdout="just prose")).complete("p")
        assert response.ok
        assert response.text == "just prose"
        assert response.completion_tokens > 0  # estimated, since no usage was reported

    def test_stream_json_list_takes_the_final_result(self):
        stdout = json.dumps(
            [{"type": "system"}, {"type": "result", "result": "final answer"}]
        )
        response = ClaudeCliProvider(_settings(), runner=_runner(stdout=stdout)).complete("p")
        assert response.text == "final answer"

    def test_empty_output_is_an_error(self):
        assert not ClaudeCliProvider(_settings(), runner=_runner(stdout="   ")).complete("p").ok

    def test_result_without_text_is_an_error(self):
        stdout = _cli_json("")
        assert not ClaudeCliProvider(_settings(), runner=_runner(stdout=stdout)).complete("p").ok

    def test_usage_falls_back_to_an_estimate(self):
        stdout = json.dumps({"result": "answer", "usage": {}})
        response = ClaudeCliProvider(_settings(), runner=_runner(stdout=stdout)).complete("prompt")
        assert response.prompt_tokens > 0
        assert response.completion_tokens > 0


class TestOpenRouterProvider:
    def test_needs_both_a_key_and_a_model(self):
        assert not OpenRouterProvider(_settings(openrouter_api_key="")).available
        assert not OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=[])
        ).available
        assert OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        ).available

    def test_unavailable_provider_refuses_without_calling_out(self):
        response = OpenRouterProvider(_settings()).complete("p")
        assert not response.ok
        assert "no API key" in response.error

    @respx.mock
    def test_returns_the_completion_and_usage(self):
        respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=_openrouter_body("the answer"))
        )
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        )
        response = provider.complete("p")
        assert response.text == "the answer"
        assert (response.prompt_tokens, response.completion_tokens) == (100, 20)

    @respx.mock
    def test_sends_the_key_as_a_bearer_token(self):
        route = respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=_openrouter_body())
        )
        OpenRouterProvider(
            _settings(openrouter_api_key="secret", openrouter_models=["a:free"])
        ).complete("p")
        assert route.calls[0].request.headers["authorization"] == "Bearer secret"

    @respx.mock
    def test_system_prompt_leads_the_messages(self):
        route = respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=_openrouter_body())
        )
        OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        ).complete("p", system="be terse")
        sent = json.loads(route.calls[0].request.content)
        assert [m["role"] for m in sent["messages"]] == ["system", "user"]

    @respx.mock
    def test_walks_the_model_list_past_a_failure(self):
        """Free models are rate-limited; the next one in line should be tried."""
        responses = [
            httpx.Response(429, json={"error": "rate limited"}),
            httpx.Response(200, json=_openrouter_body("second model", model="b:free")),
        ]
        respx.post(OPENROUTER_URL).mock(side_effect=responses)
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free", "b:free"])
        )
        response = provider.complete("p")
        assert response.ok
        assert response.model == "b:free"

    @respx.mock
    def test_every_model_failing_names_them_all(self):
        respx.post(OPENROUTER_URL).mock(return_value=httpx.Response(503))
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free", "b:free"])
        )
        response = provider.complete("p")
        assert not response.ok
        assert "a:free" in response.error
        assert "b:free" in response.error

    @respx.mock
    def test_an_error_field_in_a_200_is_still_a_failure(self):
        """OpenRouter returns 200 with an error body for some upstream faults."""
        respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json={"error": {"message": "upstream down"}})
        )
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        )
        assert not provider.complete("p").ok

    @respx.mock
    def test_empty_completion_is_a_failure(self):
        respx.post(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=_openrouter_body(""))
        )
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        )
        response = provider.complete("p")
        assert not response.ok
        assert "empty" in response.error

    @respx.mock
    def test_transport_error_degrades(self):
        respx.post(OPENROUTER_URL).mock(side_effect=httpx.ConnectError("no route"))
        provider = OpenRouterProvider(
            _settings(openrouter_api_key="k", openrouter_models=["a:free"])
        )
        assert not provider.complete("p").ok

    @respx.mock
    def test_honours_a_custom_base_url(self):
        route = respx.post("https://proxy.test/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_openrouter_body())
        )
        OpenRouterProvider(
            _settings(
                openrouter_api_key="k",
                openrouter_models=["a:free"],
                openrouter_base_url="https://proxy.test/v1/",
            )
        ).complete("p")
        assert route.called


class TestAnthropicProvider:
    def test_availability_tracks_the_key(self):
        assert not AnthropicProvider(_settings()).available
        assert AnthropicProvider(_settings(anthropic_api_key="sk-ant")).available

    @respx.mock
    def test_reads_the_text_block_and_usage(self):
        respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "model": "claude-opus-5",
                    "content": [{"type": "text", "text": "the answer"}],
                    "usage": {"input_tokens": 90, "output_tokens": 12},
                },
            )
        )
        response = AnthropicProvider(_settings(anthropic_api_key="sk-ant")).complete("p")
        assert response.text == "the answer"
        assert response.total_tokens == 102

    @respx.mock
    def test_sends_the_versioned_api_key_header(self):
        route = respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, json={"content": [{"text": "x"}]})
        )
        AnthropicProvider(_settings(anthropic_api_key="sk-ant")).complete("p")
        headers = route.calls[0].request.headers
        assert headers["x-api-key"] == "sk-ant"
        assert headers["anthropic-version"]

    @respx.mock
    def test_non_text_blocks_are_skipped(self):
        respx.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200,
                json={
                    "content": [
                        {"type": "thinking", "text": "hmm"},
                        {"type": "text", "text": "answer"},
                    ]
                },
            )
        )
        response = AnthropicProvider(_settings(anthropic_api_key="sk-ant")).complete("p")
        assert response.text == "answer"

    @respx.mock
    def test_http_error_degrades(self):
        respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
        response = AnthropicProvider(_settings(anthropic_api_key="sk-ant")).complete("p")
        assert not response.ok
        assert response.error

    @respx.mock
    def test_empty_content_is_a_failure(self):
        respx.post(ANTHROPIC_URL).mock(return_value=httpx.Response(200, json={"content": []}))
        assert not AnthropicProvider(_settings(anthropic_api_key="sk-ant")).complete("p").ok


class TestNullProvider:
    def test_is_always_available_and_always_refuses(self):
        provider = NullProvider("offline")
        assert provider.available
        response = provider.complete("p")
        assert not response.ok
        assert response.error == "offline"


class TestBuildProvider:
    @pytest.mark.parametrize("name", ["claude_cli", "openrouter", "anthropic"])
    def test_builds_every_configured_name(self, name: str):
        assert build_provider(name, _settings()).name == name

    def test_name_is_case_insensitive(self):
        assert build_provider("OpenRouter", _settings()).name == "openrouter"

    def test_unknown_name_raises_with_the_known_set(self):
        """This is config-time, not run-time — a typo in .env should be loud."""
        with pytest.raises(ValueError, match="claude_cli"):
            build_provider("gpt5", _settings())


class TestNoProviderRaises:
    """The invariant the whole layer rests on, checked in one place."""

    def test_every_failure_mode_returns_a_response(self):
        failures = [
            ClaudeCliProvider(_settings(), runner=_runner(raises=OSError("boom"))),
            ClaudeCliProvider(_settings(), runner=_runner(1, stderr="nope")),
            OpenRouterProvider(_settings()),
            AnthropicProvider(_settings()),
            NullProvider(),
        ]
        for provider in failures:
            response = provider.complete("p")
            assert not response.ok
            assert response.error, f"{provider.name} failed without saying why"
