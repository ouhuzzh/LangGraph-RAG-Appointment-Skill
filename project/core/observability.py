import logging
import time
import json
import functools
from typing import Any, Callable

import config

logger = logging.getLogger(__name__)

# Dedicated structured logger for node tracing (JSON lines)
_trace_logger = logging.getLogger("node_trace")


def trace_node(node_name: str) -> Callable:
    """Decorator that emits a structured JSON span for a graph node execution.

    Records node_name, duration_ms, thread_id (correlation ID), and error
    (if any) to the ``node_trace`` logger at INFO/ERROR level.

    Usage::

        @trace_node("rewrite_query")
        def rewrite_query(state, llm):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract thread_id from state (first positional arg)
            state = args[0] if args else kwargs.get("state", {})
            thread_id = ""
            if isinstance(state, dict):
                thread_id = state.get("thread_id", "")

            start = time.perf_counter()
            error_info: str | None = None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:
                error_info = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                duration_ms = round((time.perf_counter() - start) * 1000, 2)
                span = {
                    "event": "node_span",
                    "node_name": node_name,
                    "duration_ms": duration_ms,
                    "thread_id": thread_id,
                }
                if error_info:
                    span["error"] = error_info
                    _trace_logger.error(json.dumps(span, ensure_ascii=False))
                else:
                    _trace_logger.info(json.dumps(span, ensure_ascii=False))

        return wrapper
    return decorator


class Observability:

    def __init__(self):
        self._enabled = config.LANGFUSE_ENABLED
        self._handler = None
        self._client = None

        if not self._enabled:
            return

        if not config.LANGFUSE_PUBLIC_KEY or not config.LANGFUSE_SECRET_KEY:
            logger.warning("Langfuse enabled but API keys are missing — skipping")
            self._enabled = False
            return

        try:
            from langfuse import get_client
            from langfuse.langchain import CallbackHandler

            self._client = get_client()

            if self._client.auth_check():
                logger.info("Langfuse client is authenticated and ready.")
            else:
                logger.warning("Langfuse authentication failed. Please check credentials and host.")
                self._enabled = False
                return

            self._handler = CallbackHandler()
        except Exception as exc:
            logger.warning("Could not initialize Langfuse: %s", exc)
            self._enabled = False

    def get_handler(self):
        return self._handler

    def flush(self):
        if self._client is not None:
            try:
                self._client.flush()
            except Exception:
                logger.warning("Could not flush Langfuse client", exc_info=True)
