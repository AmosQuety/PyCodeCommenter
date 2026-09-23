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
import urllib.error
import urllib.request
from typing import Optional

try:
    from .description_provider import DescriptionProvider, FunctionContext
except (ImportError, ValueError):
    from description_provider import DescriptionProvider, FunctionContext

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


__all__ = ["RemoteDescriptionProvider", "DEFAULT_BACKEND_URL"]
