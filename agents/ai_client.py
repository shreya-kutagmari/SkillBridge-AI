"""
agents/ai_client.py

Thin wrapper around the IBM watsonx.ai Python SDK.
All Phase 4 agents import from here; never call the SDK directly.

Falls back gracefully (returns None) when:
  - WATSONX_API_KEY / WATSONX_PROJECT_ID / WATSONX_URL are not set
  - The call exceeds WATSONX_TIMEOUT_SECONDS
  - Any SDK call raises an exception

Timeout behaviour
-----------------
Python threads cannot be forcibly killed, so the timeout here works as follows:
  future.result(timeout=N) raises TimeoutError and returns control to the caller
  immediately. The background thread continues running until the SDK responds or
  errors on its own, then exits silently. For a demo Flask app this is acceptable:
  the user sees a fast fallback response while the stray thread cleans itself up.
  In a production deployment, consider an async framework or a process-level pool
  (concurrent.futures.ProcessPoolExecutor) if hard kill semantics are required.

Retry behaviour
---------------
Up to MAX_RETRIES (default 2) retries are attempted on transient errors
(connection errors, HTTP 429/503/504). Non-transient errors (auth failures,
bad request) are not retried. A short exponential back-off is applied between
retries (RETRY_DELAY_SECONDS × attempt).

Verified models (Nov 2026)
--------------------------
  ibm/granite-4-h-small                  — multitenant, Dallas + Frankfurt only
  ibm/granite-embedding-278m-multilingual — multitenant, 7 regions incl. Dallas
"""

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

logger = logging.getLogger(__name__)

_API_KEY     = os.environ.get("WATSONX_API_KEY", "")
_PROJECT_ID  = os.environ.get("WATSONX_PROJECT_ID", "")
_URL         = os.environ.get("WATSONX_URL", "")
_CHAT_MODEL  = os.environ.get("WATSONX_CHAT_MODEL", "ibm/granite-4-h-small")
_EMBED_MODEL = os.environ.get("WATSONX_EMBED_MODEL", "ibm/granite-embedding-278m-multilingual")

try:
    _TIMEOUT = float(os.environ.get("WATSONX_TIMEOUT_SECONDS", "30"))
except ValueError:
    _TIMEOUT = 30.0

# Transient HTTP status codes that warrant a retry
_RETRYABLE_STATUS = {429, 503, 504}
MAX_RETRIES = 2
RETRY_DELAY_SECONDS = 1.0

_AI_AVAILABLE = bool(_API_KEY and _PROJECT_ID and _URL)

if not _AI_AVAILABLE:
    logger.warning(
        "watsonx.ai credentials not fully configured "
        "(WATSONX_API_KEY / WATSONX_PROJECT_ID / WATSONX_URL). "
        "App will run in rule-based fallback mode."
    )


def is_available() -> bool:
    """Return True if all required watsonx.ai credentials are present."""
    return _AI_AVAILABLE


def _is_retryable(exc: Exception) -> bool:
    """Return True if the exception looks like a transient network/rate error."""
    msg = str(exc).lower()
    if any(str(code) in msg for code in _RETRYABLE_STATUS):
        return True
    transient_keywords = ("connection", "timeout", "rate limit", "service unavailable")
    return any(kw in msg for kw in transient_keywords)


def _run_with_timeout(fn, *args, **kwargs):
    """
    Run fn(*args, **kwargs) in a thread and return its result within _TIMEOUT seconds.

    Raises FuturesTimeoutError if the deadline is exceeded (see module docstring
    for thread-lifecycle caveats). Raises any exception the fn itself raises.
    """
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=_TIMEOUT)
    finally:
        # cancel_futures=True signals the future to be cancelled if not yet started.
        # Running threads cannot be interrupted; they will finish in the background.
        executor.shutdown(wait=False, cancel_futures=True)


def generate_text(prompt: str, max_new_tokens: int = 512) -> str | None:
    """
    Generate text using the configured watsonx.ai foundation model.

    Returns the generated string on success, or None on any failure
    (missing credentials, API error, timeout).

    Retries up to MAX_RETRIES times on transient errors before returning None.

    Args:
        prompt: The full prompt string to send.
        max_new_tokens: Maximum tokens to generate (default 512).

    Returns:
        str | None
    """
    if not _AI_AVAILABLE:
        return None

    def _call() -> str:
        from ibm_watsonx_ai.foundation_models import ModelInference
        model = ModelInference(
            model_id=_CHAT_MODEL,
            credentials={"apikey": _API_KEY, "url": _URL},
            project_id=_PROJECT_ID,
        )
        return model.generate_text(
            prompt=prompt,
            params={"max_new_tokens": max_new_tokens},
        )

    for attempt in range(MAX_RETRIES + 1):
        try:
            return _run_with_timeout(_call)
        except FuturesTimeoutError:
            logger.error(
                "watsonx generate_text timed out after %.0f seconds (attempt %d)",
                _TIMEOUT, attempt + 1,
            )
            return None  # Timeout is never retried — caller gets response immediately
        except Exception as exc:
            if attempt < MAX_RETRIES and _is_retryable(exc):
                delay = RETRY_DELAY_SECONDS * (attempt + 1)
                logger.warning(
                    "watsonx generate_text transient error (attempt %d/%d), "
                    "retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "watsonx generate_text failed (attempt %d): %s", attempt + 1, exc
                )
                return None
    return None  # Should not be reached, but satisfies the type checker


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """
    Embed a list of text strings using the configured watsonx.ai embedding model.

    Returns a list of float vectors (one per input text) on success,
    or None on any failure (missing credentials, API error, timeout).

    The SDK's embed_documents() may return either:
      - list[list[float]]  (flat form, newer SDK versions)
      - list[dict]         ({"embedding": [...]}, older SDK versions)
    Both forms are normalised to list[list[float]].

    Retries up to MAX_RETRIES times on transient errors.

    Args:
        texts: List of strings to embed. Returns [] for empty input.

    Returns:
        list[list[float]] | None
    """
    if not texts:
        return []
    if not _AI_AVAILABLE:
        return None

    def _call() -> list[list[float]]:
        from ibm_watsonx_ai.foundation_models import Embeddings
        embedding = Embeddings(
            model_id=_EMBED_MODEL,
            credentials={"apikey": _API_KEY, "url": _URL},
            project_id=_PROJECT_ID,
        )
        result = embedding.embed_documents(texts=texts)
        # Normalise to list[list[float]] regardless of SDK version
        if result and isinstance(result[0], dict):
            return [item["embedding"] for item in result]
        return result

    for attempt in range(MAX_RETRIES + 1):
        try:
            return _run_with_timeout(_call)
        except FuturesTimeoutError:
            logger.error(
                "watsonx embed_texts timed out after %.0f seconds (attempt %d)",
                _TIMEOUT, attempt + 1,
            )
            return None
        except Exception as exc:
            if attempt < MAX_RETRIES and _is_retryable(exc):
                delay = RETRY_DELAY_SECONDS * (attempt + 1)
                logger.warning(
                    "watsonx embed_texts transient error (attempt %d/%d), "
                    "retrying in %.1fs: %s",
                    attempt + 1, MAX_RETRIES + 1, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "watsonx embed_texts failed (attempt %d): %s", attempt + 1, exc
                )
                return None
    return None
