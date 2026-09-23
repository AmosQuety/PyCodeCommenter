"""HTTP-client :class:`DescriptionProvider` that talks to the hosted
AI-drafting backend (the separate ``pycodecommenter-ai-backend`` project).

This module carries no AI/Gemini-specific knowledge at all -- no model
names, no API keys, no circuit breakers. It only knows how to serialize a
:class:`~PyCodeCommenter.description_provider.FunctionContext` to the
backend's JSON contract, POST it, and interpret the response. All of the
"how to call Gemini reliably" logic (multi-key failover, circuit breakers,
live model discovery) lives exclusively in the backend repo -- see that
project's ``gemini_client.py`` -- so this package never needs its own
Gemini API key or dependency.

Fails closed at every layer, matching the same contract every
:class:`DescriptionProvider` implementation follows: a malformed response,
a network error, a timeout, a 429 (the backend's daily cap or per-IP rate
limit), or an explicit ``{"description": null}`` all resolve to
:meth:`RemoteDescriptionProvider.draft_function_description` returning
``None`` -- never a partial answer, never a raised exception escaping to
the caller under an expected failure mode.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

try:
    from .description_provider import (
        DescriptionProvider,
        DocstringDraft,
        DraftingStopped,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
    from .ai_drafting import draft_from_payload
except (ImportError, ValueError):
    from description_provider import (
        DescriptionProvider,
        DocstringDraft,
        DraftingStopped,
        DraftSlots,
        FunctionContext,
        KnownText,
    )
    from ai_drafting import draft_from_payload

logger = logging.getLogger(__name__)

# The real, live Render deployment (pycodecommenter-ai-backend repo),
# confirmed reachable at this URL. Override for local/staging testing with
# the PYCODECOMMENTER_AI_BACKEND_URL environment variable instead of
# editing this constant.
DEFAULT_BACKEND_URL = "https://pycodecommenter-backend.onrender.com"


class RemoteDescriptionProvider(DescriptionProvider):
    """Drafts function descriptions via the hosted backend.

    Attributes:
        backend_url (str): The backend's base URL (no trailing slash),
            e.g. ``https://pycodecommenter-backend.onrender.com``.
        timeout_s (float): Per-request timeout, in seconds. Defaults high
            (90s) specifically because Render's free tier sleeps an
            inactive service and pays a real cold-start cost -- tens of
            seconds -- on the first request after that; the direct-Gemini
            provider's much shorter default would false-fail here.
    """

    # The backend's per-minute rate limit asks callers to wait; a longer
    # wait than this isn't worth holding a run for.
    MAX_RATE_LIMIT_WAIT_S = 60

    def __init__(self, backend_url: str, timeout_s: float = 90.0):
        """
        Args:
            backend_url (str): The backend's base URL.
            timeout_s (float): Per-request timeout, in seconds. See the
                class docstring for why this defaults so much higher than
                a typical HTTP client timeout.
        """
        self.backend_url = backend_url.rstrip("/")
        self.timeout_s = timeout_s
        # The caller's daily allowance, as last reported by the backend.
        self.drafts_remaining: Optional[int] = None
        self.drafts_limit: Optional[int] = None
        self._stopped: Optional[DraftingStopped] = None

    def draft_docstring(
        self, context: FunctionContext, known: KnownText, slots: DraftSlots
    ) -> DocstringDraft:
        """Drafts the requested parts via the backend's /v2 endpoint.

        Fails closed to an empty draft on network errors and malformed
        replies. A per-minute rate limit is waited out once (up to
        ``MAX_RATE_LIMIT_WAIT_S``); a spent daily allowance or shared cap
        stops drafting for the rest of the run. A backend without /v2
        (HTTP 404) falls back to the /v1 description.

        Args:
            context (FunctionContext): The function's AST-derived facts.
            known (KnownText): Text already settled, for consistency.
            slots (DraftSlots): The parts to draft.

        Returns:
            DocstringDraft: Whatever the backend drafted; may be empty.

        Raises:
            DraftingStopped: The daily allowance or shared cap is spent.
        """
        if self._stopped is not None:
            raise self._stopped

        body = dict(self._to_payload(context), known=_known_payload(known))
        body["slots"] = _slots_payload(slots)
        for attempt in range(2):
            try:
                payload = self._post_json("/v2/draft-docstring", body)
                return draft_from_payload(payload)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return super().draft_docstring(context, known, slots)
                if e.code != 429:
                    logger.warning(f"Hosted AI backend returned HTTP {e.code}: {e}")
                    return DocstringDraft()
                error = _error_body(e)
                if error.get("error") != "rate_limited":
                    self._stop(error)
                    raise self._stopped
                if attempt == 0:
                    time.sleep(_bounded_wait(e, self.MAX_RATE_LIMIT_WAIT_S))
            except Exception as e:
                logger.warning(
                    f"Hosted AI backend request failed for {context.name}: {e}"
                )
                return DocstringDraft()
        return DocstringDraft()

    def _post_json(self, path: str, body: dict) -> dict:
        """POSTs JSON and returns the parsed reply, recording the allowance
        headers.

        Raises:
            urllib.error.HTTPError: The backend answered with an error status.
            Exception: A network, timeout, or parsing failure.
        """
        request = urllib.request.Request(
            f"{self.backend_url}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            self._record_allowance(getattr(response, "headers", None) or {})
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Backend reply is not a JSON object")
        return payload

    def _record_allowance(self, headers: Any) -> None:
        remaining = _int_or_none(headers.get("X-AI-Drafts-Remaining"))
        limit = _int_or_none(headers.get("X-AI-Drafts-Limit"))
        if remaining is not None:
            self.drafts_remaining = remaining
        if limit is not None:
            self.drafts_limit = limit

    def _stop(self, error: Dict[str, Any]) -> None:
        reason = str(error.get("error") or "limit_reached")
        if reason == "user_daily_limit_reached":
            self.drafts_remaining = 0
        self._stopped = DraftingStopped(
            reason,
            str(
                error.get("message")
                or "The hosted AI service's daily limit is reached."
            ),
        )

    def draft_function_description(self, context: FunctionContext) -> Optional[str]:
        """Attempts to draft a description via the hosted backend, failing
        closed to ``None`` on any expected failure mode.

        Args:
            context (FunctionContext): The function's AST-derived facts.

        Returns:
            Optional[str]: The drafted, trimmed text, or ``None`` if the
                backend declined, was rate-limited/capped (HTTP 429),
                timed out, or returned a malformed response.
        """
        body = json.dumps(self._to_payload(context)).encode("utf-8")
        request = urllib.request.Request(
            f"{self.backend_url}/v1/draft-description",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning(
                    f"Hosted AI backend is rate-limited or has reached its "
                    f"daily cap; skipping AI draft for {context.name}."
                )
            else:
                logger.warning(
                    f"Hosted AI backend returned HTTP {e.code} for "
                    f"{context.name}: {e}"
                )
            return None
        except Exception as e:
            logger.warning(f"Hosted AI backend request failed for {context.name}: {e}")
            return None

        description = payload.get("description")
        if not description:
            return None
        return description.strip()

    @staticmethod
    def _to_payload(context: FunctionContext) -> dict:
        """Serializes a :class:`FunctionContext` to the backend's wire
        contract (see the backend repo's docs/API.md).

        Args:
            context (FunctionContext): The function's AST-derived facts.

        Returns:
            dict: The JSON-serializable request body.
        """
        return {
            "name": context.name,
            "parameters": [
                {"name": p.name, "type_hint": p.type_hint, "default": p.default}
                for p in context.parameters
            ],
            "return_type": context.return_type,
            "is_generator": context.is_generator,
            "raised_exceptions": context.raised_exceptions,
            "source": context.source,
        }


def _slots_payload(slots: DraftSlots) -> dict:
    return {
        "summary": slots.summary,
        "description": slots.description,
        "params": list(slots.params),
        "returns": slots.returns,
        "raises": list(slots.raises),
    }


def _known_payload(known: KnownText) -> dict:
    return {
        "params": dict(known.params),
        "returns": known.returns,
        "raises": dict(known.raises),
    }


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_body(error: urllib.error.HTTPError) -> Dict[str, Any]:
    try:
        body = json.loads(error.read().decode("utf-8"))
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _bounded_wait(error: urllib.error.HTTPError, cap: float) -> float:
    """The server's Retry-After, clamped to ``[1, cap]`` seconds."""
    headers = error.headers or {}
    requested = _int_or_none(headers.get("Retry-After")) or 1
    return max(1, min(requested, cap))


__all__ = ["RemoteDescriptionProvider", "DEFAULT_BACKEND_URL"]
