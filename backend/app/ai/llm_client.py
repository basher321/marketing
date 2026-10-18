"""Unified LLM provider client (Claude/OpenAI) with a safe mock fallback.

SDKs are imported lazily inside each provider method so that a missing
`anthropic` or `openai` package never breaks app import/boot — it only
breaks the specific provider call, which falls back to the mock provider.

Two entry points:
- `complete()` - legacy, returns text only and silently falls back to the
  mock provider on any failure (kept so the app always boots and existing
  callers such as content_service keep working).
- `complete_with_usage()` (SPEC-BE-027) - returns text plus token usage and
  raises LLMProviderError on provider failure/timeout instead of falling
  back; with no provider configured it returns an explicit is_mock result.
  Every call is logged as one `llm_call` structlog span.
"""
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import structlog
from fastapi import status

from app.config import get_settings
from app.core.exceptions import AppError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

settings = get_settings()

logger = structlog.get_logger(__name__)

DEFAULT_TIMEOUT_S = 30.0


class LLMProviderError(AppError):
    """The LLM provider call failed, timed out, or returned unusable output."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    detail = "The AI provider is unavailable."


@dataclass(frozen=True)
class LLMCompletion:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    is_mock: bool


class LLMClient:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or settings.LLM_PROVIDER
        self.model = model or settings.LLM_MODEL

    def _real_api_key(self) -> str | None:
        api_key = settings.LLM_API_KEY.get_secret_value()
        return api_key if api_key and api_key != "changeme" else None

    def _check_access(self, db: Optional["Session"], tenant_id: Optional[str]) -> None:
        # SPEC-BE-103: a company the Super admin switched AI off for gets no AI
        # at all: not the software chain, not the .env provider, not a mock.
        from app.services import platform_service

        try:
            blocked = not platform_service.allowed(str(tenant_id) if tenant_id else None, "ai", db)
        except Exception:  # noqa: BLE001 - an unreadable store must not break the call
            logger.warning("ai_access_unreadable")
            return
        if blocked:
            raise LLMProviderError(platform_service.BLOCKED["ai"], 403)

    def _tenant_chain(self, db: Optional["Session"], tenant_id: Optional[str]) -> list[tuple[str, str, str]]:
        # PilotSonic's AI models (SPEC-BE-101: the Super admin's keys, the same
        # for every company), in fallback order. With a session they're read in
        # it; without one (callers that pass no company), from the store.
        from app.services.ai_model_service import resolve_chain

        try:
            return resolve_chain(db, str(tenant_id) if tenant_id else None)
        except Exception:  # noqa: BLE001 - an unreadable store must not break the call; .env / mock still apply
            logger.warning("llm_chain_unavailable")
            return []

    def _complete_chain(
        self,
        chain: list[tuple[str, str, str]],
        tenant_id: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        timeout_s: float,
        temperature: float | None = None,
        images: list[tuple[str, bytes]] | None = None,
    ) -> LLMCompletion:
        # Try each enabled provider in order; any failure (error, timeout, 429,
        # 5xx, bad key) moves on to the next. The span records every attempt.
        # A vision call (images) doesn't mark a provider as failing in AI Models:
        # a text-only model refusing an image isn't a broken key.
        from app.ai import providers as llm_providers
        from app.services.ai_model_service import record_outcome

        started = time.perf_counter()
        attempts: list[dict[str, str]] = []
        for provider, api_key, model in chain:
            try:
                text, input_tokens, output_tokens = llm_providers.call(
                    provider, api_key, model, system_prompt, user_prompt, max_tokens, timeout_s, temperature, images
                )
            except llm_providers.ProviderCallError as exc:
                attempts.append({"provider": provider, "error": str(exc)[:200]})
                if not images:
                    record_outcome(tenant_id, provider, str(exc))
                continue
            if not images:
                record_outcome(tenant_id, provider, None)
            completion = LLMCompletion(
                text=text,
                provider=provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                is_mock=False,
            )
            logger.info(
                "llm_call",
                provider=provider,
                model=model,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                outcome="ok",
                attempts=attempts,
            )
            return completion
        logger.warning(
            "llm_call",
            provider="chain",
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            outcome="error",
            attempts=attempts,
        )
        summary = "; ".join(f"{a['provider']}: {a['error']}" for a in attempts)
        raise LLMProviderError(f"All AI models failed — {summary}"[:500])

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
        *,
        db: Optional["Session"] = None,
        tenant_id: Optional[str] = None,
    ) -> str:
        self._check_access(db, tenant_id)
        chain = self._tenant_chain(db, tenant_id)
        if chain:
            try:
                return self._complete_chain(
                    chain, str(tenant_id or ""), system_prompt, user_prompt, max_tokens, DEFAULT_TIMEOUT_S
                ).text
            except LLMProviderError:
                logger.warning("PilotSonic's AI models all failed; falling back to the .env provider.")
        api_key = self._real_api_key()

        if self.provider == "anthropic" and api_key:
            try:
                return self._complete_anthropic(system_prompt, user_prompt, max_tokens, api_key)[0]
            except Exception:
                logger.exception("Anthropic completion failed, falling back to mock.")
        elif self.provider == "openai" and api_key:
            try:
                return self._complete_openai(system_prompt, user_prompt, max_tokens, api_key)[0]
            except Exception:
                logger.exception("OpenAI completion failed, falling back to mock.")

        return self._complete_mock(system_prompt, user_prompt)

    # Providers whose chat API takes images (SPEC-BE-096 FR4). Groq and Ollama
    # are skipped: most of their models are text-only.
    VISION_PROVIDERS = ("anthropic", "openai", "gemini", "openrouter")

    def complete_vision(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[tuple[str, bytes]],
        max_tokens: int = 1500,
        timeout_s: float = 90.0,
        *,
        db: "Session",
        tenant_id: str,
    ) -> LLMCompletion:
        """Text + images [(mime, bytes)] on PilotSonic's vision-capable models,
        in their priority order. Raises LLMProviderError when none is set up or
        all fail; there is no .env or mock fallback (SPEC-BE-088)."""
        self._check_access(db, tenant_id)
        chain = [c for c in self._tenant_chain(db, tenant_id) if c[0] in self.VISION_PROVIDERS]
        if not chain:
            raise LLMProviderError("PilotSonic has no AI model that can read images set up yet (Claude, OpenAI, Gemini or OpenRouter); the Super admin adds it.")
        return self._complete_chain(chain, str(tenant_id), system_prompt, user_prompt, max_tokens, timeout_s, 0.0, images)

    def complete_with_usage(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        *,
        db: Optional["Session"] = None,
        tenant_id: Optional[str] = None,
        temperature: float | None = None,
    ) -> LLMCompletion:
        # 1) PilotSonic's AI models in fallback order (SPEC-BE-053/101); if all
        #    fail, LLMProviderError names each failure.
        # 2) Otherwise the .env provider, unchanged. No mock fallback here: a
        #    failing or timed-out provider raises LLMProviderError so callers
        #    never mistake a mock for a real answer.
        # `temperature` is sent only when given (SPEC-BE-085: 0 for the Command
        # Chat planner); a model that refuses it is asked once more without it.
        if self.provider == "fixture":
            return self._complete_fixture(user_prompt)
        self._check_access(db, tenant_id)
        chain = self._tenant_chain(db, tenant_id)
        if chain:
            return self._complete_chain(
                chain, str(tenant_id or ""), system_prompt, user_prompt, max_tokens, timeout_s, temperature
            )
        api_key = self._real_api_key()
        started = time.perf_counter()
        if self.provider not in ("anthropic", "openai") or not api_key:
            completion = LLMCompletion(
                text=self._complete_mock(system_prompt, user_prompt),
                provider=self.provider,
                model="mock",
                input_tokens=0,
                output_tokens=0,
                is_mock=True,
            )
            self._log_span(completion, started, "mock")
            return completion

        call = self._complete_anthropic if self.provider == "anthropic" else self._complete_openai
        try:
            try:
                text, input_tokens, output_tokens = call(
                    system_prompt, user_prompt, max_tokens, api_key, timeout_s, temperature
                )
            except Exception as exc:
                if temperature is None or "temperature" not in str(exc).lower():
                    raise
                text, input_tokens, output_tokens = call(
                    system_prompt, user_prompt, max_tokens, api_key, timeout_s, None
                )
        except Exception as exc:
            logger.warning(
                "llm_call",
                provider=self.provider,
                model=self.model,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
                input_tokens=0,
                output_tokens=0,
                outcome="error",
                error_type=type(exc).__name__,
            )
            raise LLMProviderError(f"LLM call failed ({type(exc).__name__}).") from exc

        completion = LLMCompletion(
            text=text,
            provider=self.provider,
            model=self.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            is_mock=False,
        )
        self._log_span(completion, started, "ok")
        return completion

    def _log_span(self, completion: LLMCompletion, started: float, outcome: str) -> None:
        # One span per LLM call; never includes prompt or response text.
        logger.info(
            "llm_call",
            provider=completion.provider,
            model=completion.model,
            duration_ms=round((time.perf_counter() - started) * 1000, 1),
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
            outcome=outcome,
        )

    def _complete_anthropic(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        temperature: float | None = None,
    ) -> tuple[str, int, int]:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
        extra = {} if temperature is None else {"temperature": temperature}
        response = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            **extra,
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        return text, response.usage.input_tokens, response.usage.output_tokens

    def _complete_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
        api_key: str,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        temperature: float | None = None,
    ) -> tuple[str, int, int]:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, timeout=timeout_s)
        extra = {} if temperature is None else {"temperature": temperature}
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **extra,
        )
        usage = response.usage
        return (
            response.choices[0].message.content or "",
            usage.prompt_tokens if usage else 0,
            usage.completion_tokens if usage else 0,
        )

    def _complete_fixture(self, user_prompt: str) -> LLMCompletion:
        """Dev-only deterministic provider (LLM_PROVIDER=fixture, refused in
        production): the first entry of LLM_FIXTURE_FILE whose "match" text
        appears in the command (case-insensitive) is returned as the reply."""
        import json
        import re

        path = settings.LLM_FIXTURE_FILE
        if not path:
            raise LLMProviderError("LLM_FIXTURE_FILE isn't set.")
        try:
            with open(path, encoding="utf-8") as fh:
                entries = json.load(fh)
        except (OSError, ValueError) as exc:
            raise LLMProviderError(f"Can't read the LLM fixture file ({type(exc).__name__}).") from None
        command = re.search(r"<command>(.*?)</command>", user_prompt, re.S)
        text = (command.group(1) if command else user_prompt).lower()
        for entry in entries if isinstance(entries, list) else []:
            if str(entry.get("match", "")).lower() in text:
                response = entry.get("response")
                return LLMCompletion(
                    text=response if isinstance(response, str) else json.dumps(response),
                    provider="fixture", model="fixture", input_tokens=0, output_tokens=0, is_mock=False,
                )
        raise LLMProviderError("No LLM fixture matches this command.")

    def _complete_mock(self, system_prompt: str, user_prompt: str) -> str:
        logger.info("Using mock LLM completion.", provider=self.provider)
        return f"[mock response] Acknowledged: {user_prompt[:200]}"


llm_client = LLMClient()
