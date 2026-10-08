"""Exponential backoff retry policies.

`with_exponential_backoff` wraps both sync and async callables. Scheduler jobs
are async, so the async path must await the call and sleep with
`asyncio.sleep` — a sync wrapper around a coroutine function would return an
un-awaited coroutine (no retry, and APScheduler would no longer see the job as
a coroutine function). Once every attempt fails, the original exception is
re-raised, never swallowed.
"""
import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def _delay_for(attempt: int, base_delay_seconds: float) -> float:
    return base_delay_seconds * (2 ** (attempt - 1))


def with_exponential_backoff(
    max_attempts: int = 6,
    base_delay_seconds: float = 1.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                attempt = 0
                while True:
                    try:
                        return await func(*args, **kwargs)
                    except exceptions:
                        attempt += 1
                        if attempt >= max_attempts:
                            logger.exception(
                                "Max retry attempts reached for %s", func.__name__
                            )
                            raise
                        delay = _delay_for(attempt, base_delay_seconds)
                        logger.warning(
                            "Retrying %s in %.1fs (attempt %d)", func.__name__, delay, attempt
                        )
                        await asyncio.sleep(delay)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            attempt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except exceptions:
                    attempt += 1
                    if attempt >= max_attempts:
                        logger.exception("Max retry attempts reached for %s", func.__name__)
                        raise
                    delay = _delay_for(attempt, base_delay_seconds)
                    logger.warning(
                        "Retrying %s in %.1fs (attempt %d)", func.__name__, delay, attempt
                    )
                    time.sleep(delay)

        return wrapper  # type: ignore[return-value]

    return decorator
