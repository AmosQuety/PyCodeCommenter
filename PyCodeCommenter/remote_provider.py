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
from dataclasses import replace
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional

try:
    from .description_provider import (
        ClassContext,
        ClassDraft,
        ClassSlots,
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
        ClassContext,
        ClassDraft,
        ClassSlots,
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
    """Drafts docstring parts through the hosted backend.

    Attributes:
        backend_url (str): The backend's base URL, without a trailing slash,
            for example ``https://pycodecommenter-backend.onrender.com``.
        timeout_s (float): Per-request timeout, in seconds. Defaults high (90)
            because Render's free tier sleeps an inactive service and pays a
            cold-start cost of tens of seconds on the first request after
            that; the direct providers' shorter timeouts would false-fail here.
        drafts_remaining (Optional[int]): The caller's daily allowance left, as
            last reported by the backend; ``None`` until it has said.
        drafts_limit (Optional[int]): The caller's daily allowance in total, as
            last reported by the backend.
        _on_wait (Optional[Callable[[float], None]]): Told the seconds about to be
            waited out for a rate limit.
        _class_endpoint_missing (bool): Set when the backend has no class endpoint,
            so classes are not asked about again.
    """

    # The backend's per-minute rate limit asks callers to wait; a longer
    # wait than this isn't worth holding a run for.
    MAX_RATE_LIMIT_WAIT_S = 60

    def __init__(
        self,
        backend_url: str,
        timeout_s: float = 90.0,
        on_wait: Optional[Callable[[float], None]] = None,
    ):
        """Create a client for one backend.

        Args:
            backend_url (str): The backend's base URL.
            timeout_s (float): Per-request timeout, in seconds. See the class
                docstring for why this defaults so much higher than a typical HTTP
                client timeout.
            on_wait (Optional[Callable[[float], None]]): Called with the number of
                seconds just before a rate limit is waited out, so the wait can be
                shown instead of looking like a hang.
        """
        self.backend_url = backend_url.rstrip("/")
        self.timeout_s = timeout_s
        self._on_wait = on_wait
        self._class_endpoint_missing = False
        # What the service said about the latest draft (X-AI-Draft-Outcome:
        # "ok" or "failed"); None from an older service that doesn't say.
        self._last_outcome: Optional[str] = None
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
        try:
            payload = self._post_draft("/v2/draft-docstring", body, context.name)
        except _EndpointMissing:
            return super().draft_docstring(context, known, slots)
        draft = self._read_reply(
            payload, draft_from_payload, DocstringDraft(failed=True)
        )
        return replace(draft, failed=True) if self._service_failed() else draft

    def draft_class_docstring(
        self, context: ClassContext, known: Dict[str, str], slots: ClassSlots
    ) -> ClassDraft:
        """Draft a class's summary and attributes via the backend.

        Uses the ``/v2/draft-class-docstring`` endpoint, with the same rate-limit
        and stop handling as :meth:`draft_docstring`. A backend without the
        endpoint (HTTP 404) is remembered and not asked again: the class keeps its gap
        markers.

        Args:
            context (ClassContext): The class's AST-derived facts.
            known (Dict[str, str]): Attribute text already settled.
            slots (ClassSlots): The parts to draft.

        Returns:
            ClassDraft: Whatever the backend drafted; may be empty. ``failed`` is
            set when the request failed or the service reported it could not
            produce a draft.

        Raises:
            DraftingStopped: The daily allowance or shared cap is spent.
        """
        if self._stopped is not None:
            raise self._stopped
        if self._class_endpoint_missing:
            return ClassDraft(failed=True)

        body = _class_payload(context, known, slots)
        try:
            payload = self._post_draft("/v2/draft-class-docstring", body, context.name)
        except _EndpointMissing:
            self._class_endpoint_missing = True
            return ClassDraft(failed=True)
        draft = self._read_reply(
            payload, _class_draft_from_payload, ClassDraft(failed=True)
        )
        return replace(draft, failed=True) if self._service_failed() else draft

    def _service_failed(self) -> bool:
        """Say whether the service reported that it could not produce the last draft.

        That is different from the service answering with nothing: it means no
        model gave a usable answer.

        Returns:
            bool: ``True`` if the last response carried ``X-AI-Draft-Outcome:
            failed``.
        """
        return self._last_outcome == "failed"

    @staticmethod
    def _read_reply(payload: Optional[dict], reader: Callable, empty: Any) -> Any:
        """Turn a reply into a draft, or return ``empty`` if that is not possible.

        Args:
            payload (Optional[dict]): The parsed JSON reply, or ``None`` if the
                request failed.
            reader (Callable): Builds a draft from a payload.
            empty (Any): The failed draft to return when there is no reply or it
                can't be read.

        Returns:
            Any: The draft ``reader`` built, or ``empty``.
        """
        if payload is None:
            return empty
        try:
            return reader(payload)
        except Exception as e:
            logger.warning(f"Hosted AI backend reply could not be read: {e}")
            return empty

    def _post_draft(self, path: str, body: dict, name: str) -> Optional[dict]:
        """POST a draft request, waiting out a per-minute rate limit once.

        Args:
            path (str): The endpoint path, for example ``/v2/draft-docstring``.
            body (dict): The JSON request body.
            name (str): The function or class name, for the log message.

        Returns:
            Optional[dict]: The reply, or ``None`` if the request failed
            (logged; the gaps stay).

        Raises:
            _EndpointMissing: The backend answered 404 (an older version).
            DraftingStopped: The daily allowance or shared cap is spent.
        """
        for attempt in range(2):
            try:
                return self._post_json(path, body)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise _EndpointMissing(path) from e
                if e.code != 429:
                    logger.warning(f"Hosted AI backend returned HTTP {e.code}: {e}")
                    return None
                error = _error_body(e)
                if error.get("error") != "rate_limited":
                    self._stop(error)
                    raise self._stopped
                if attempt == 0:
                    wait = _bounded_wait(e, self.MAX_RATE_LIMIT_WAIT_S)
                    if self._on_wait is not None:
                        self._on_wait(wait)
                    time.sleep(wait)
            except Exception as e:
                logger.warning(f"Hosted AI backend request failed for {name}: {e}")
                return None
        return None

    def _post_json(self, path: str, body: dict) -> dict:
        """POST JSON and return the parsed reply, recording the allowance headers.

        Args:
            path (str): The endpoint path.
            body (dict): The JSON request body.

        Returns:
            dict: The parsed JSON reply.

        Raises:
            ValueError: If the reply is not a JSON object.
            urllib.error.HTTPError: The backend answered with an error status.
            Exception: A network, timeout, or parsing failure.
        """
        self._last_outcome = None
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
        """Remember the allowance and outcome headers of a response.

        Reads ``X-AI-Drafts-Remaining``, ``X-AI-Drafts-Limit`` and
        ``X-AI-Draft-Outcome``. A missing or malformed count leaves the earlier
        value in place.

        Args:
            headers (Any): The response headers.
        """
        remaining = _int_or_none(headers.get("X-AI-Drafts-Remaining"))
        limit = _int_or_none(headers.get("X-AI-Drafts-Limit"))
        if remaining is not None:
            self.drafts_remaining = remaining
        if limit is not None:
            self.drafts_limit = limit
        self._last_outcome = headers.get("X-AI-Draft-Outcome")

    def _stop(self, error: Dict[str, Any]) -> None:
        """Record that drafting must stop for the rest of the run.

        Reads the backend's error body. A ``user_daily_limit_reached`` reason also
        sets ``drafts_remaining`` to zero.

        Args:
            error (Dict[str, Any]): The parsed error body of a 429 response.
        """
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
        """Draft a description via the hosted backend's ``/v1`` endpoint.

        Fails closed to ``None`` on any expected failure mode.

        Args:
            context (FunctionContext): The function's AST-derived facts.

        Returns:
            Optional[str]: The drafted, trimmed text, or ``None`` if the
            backend declined, was rate-limited or capped (HTTP 429), timed out,
            or returned a malformed response.
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
        """Serialize a :class:`FunctionContext` to the backend's wire contract.

        The contract is described in the backend repository's ``docs/API.md``.

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


class _EndpointMissing(Exception):
    """The backend has no such endpoint (it is an older version)."""


def _class_payload(
    context: ClassContext, known: Dict[str, str], slots: ClassSlots
) -> dict:
    """Build the JSON request body for a class draft.

    Args:
        context (ClassContext): The class's AST-derived facts.
        known (Dict[str, str]): Attribute text already settled.
        slots (ClassSlots): The parts to draft.

    Returns:
        dict: The JSON-serializable request body.
    """
    return {
        "name": context.name,
        "bases": list(context.bases),
        "attributes": [
            {"name": a.name, "type_hint": a.type_hint, "default": a.default}
            for a in context.attributes
        ],
        "source": context.source,
        "known": {"attributes": dict(known)},
        "slots": {"summary": slots.summary, "attributes": list(slots.attributes)},
    }


def _class_draft_from_payload(payload: dict) -> ClassDraft:
    """Read a class draft from the backend's reply.

    Anything that is not a string is ignored, so a malformed reply gives an
    empty draft rather than an error.

    Args:
        payload (dict): The parsed JSON reply.

    Returns:
        ClassDraft: The summary and attribute descriptions found.
    """
    summary = payload.get("summary")
    attributes = payload.get("attributes")
    return ClassDraft(
        summary=summary if isinstance(summary, str) else None,
        attributes=(
            {k: v for k, v in attributes.items() if isinstance(v, str)}
            if isinstance(attributes, dict)
            else {}
        ),
    )


def _slots_payload(slots: DraftSlots) -> dict:
    """Describe which function parts are wanted, in the backend's format.

    Args:
        slots (DraftSlots): The parts to draft.

    Returns:
        dict: The ``slots`` member of the request body.
    """
    return {
        "summary": slots.summary,
        "description": slots.description,
        "params": list(slots.params),
        "returns": slots.returns,
        "raises": list(slots.raises),
    }


def _known_payload(known: KnownText) -> dict:
    """Describe the already settled text, in the backend's format.

    Args:
        known (KnownText): Text already settled.

    Returns:
        dict: The ``known`` member of the request body.
    """
    return {
        "params": dict(known.params),
        "returns": known.returns,
        "raises": dict(known.raises),
    }


def _int_or_none(value: Any) -> Optional[int]:
    """Convert a value to an int, or give ``None`` if it can't be.

    Args:
        value (Any): Usually a header value string, or ``None``.

    Returns:
        Optional[int]: The integer, or ``None`` for a missing or malformed
        value.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_body(error: urllib.error.HTTPError) -> Dict[str, Any]:
    """Read the JSON body of an HTTP error response.

    Args:
        error (urllib.error.HTTPError): The error to read.

    Returns:
        Dict[str, Any]: The parsed body, or an empty dict if it is not a JSON
        object or can't be read.
    """
    try:
        body = json.loads(error.read().decode("utf-8"))
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _bounded_wait(error: urllib.error.HTTPError, cap: float) -> float:
    """Read the server's ``Retry-After`` and limit it to a sensible wait.

    Args:
        error (urllib.error.HTTPError): The 429 response.
        cap (float): The longest wait to accept, in seconds.

    Returns:
        float: The requested seconds, clamped to ``[1, cap]``; 1 if the header
        is missing or malformed.
    """
    headers = error.headers or {}
    requested = _int_or_none(headers.get("Retry-After")) or 1
    return max(1, min(requested, cap))


__all__ = ["RemoteDescriptionProvider", "DEFAULT_BACKEND_URL"]
