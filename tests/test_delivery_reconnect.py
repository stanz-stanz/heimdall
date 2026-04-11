"""Tests for delivery runner Redis reconnection logic.

Verifies that _subscribe_and_process() retries after connection failures
instead of silently giving up, and that backoff delays increase with
consecutive failures.

Patching notes:
  - Patch `src.delivery.runner.redis` (whole module), NOT the sub-attribute
    `src.delivery.runner.redis.from_url`. Patching the sub-attribute does not
    replace the reference the already-imported module object holds.
  - Always set `mock_redis.ConnectionError = redis.ConnectionError` so the
    `except redis.ConnectionError` clauses in the runner still catch real
    ConnectionError instances raised by side_effect callables.
  - The test helper `_run_loop` drives the event loop with `_real_sleep(0)`
    — a direct reference to the real `asyncio.sleep` captured before any
    patches are applied. This ensures the runner task actually gets CPU time
    even while `src.delivery.runner.asyncio.sleep` is mocked out.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import redis

from src.delivery.runner import DeliveryRunner

# Capture the real asyncio.sleep BEFORE any test patches touch it.
# _run_loop uses this alias so the event-loop tick `await _real_sleep(0)` is
# never intercepted by the mock on `src.delivery.runner.asyncio.sleep`.
_real_sleep = asyncio.sleep


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_runner() -> DeliveryRunner:
    """Minimal runner — no DB or Telegram wiring needed for pubsub tests."""
    runner = DeliveryRunner()
    runner._app = MagicMock()
    runner._app.bot = AsyncMock()
    runner._app.bot_data = {}
    return runner


async def _run_loop(runner: DeliveryRunner, *, stop_when, max_ticks: int = 200) -> None:
    """Drive _subscribe_and_process() until stop_when() returns True or max_ticks.

    Uses _real_sleep (captured before patching) so event-loop yields work
    even when the runner's asyncio.sleep is mocked out.
    """
    runner._running = True
    task = asyncio.create_task(runner._subscribe_and_process())
    for _ in range(max_ticks):
        await _real_sleep(0)  # real yield — not intercepted by mock
        if stop_when():
            break
    runner._running = False
    for _ in range(10):
        await _real_sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass



def _make_redis_ctx(from_url_factory, sleeps: list | None = None):
    """Context manager: patches `src.delivery.runner.redis` and asyncio.sleep.

    Args:
        from_url_factory: callable returning a mock redis client (or raising).
        sleeps: if provided, a list that records each sleep duration. When
            None, sleeps are instant and unrecorded.

    Returns:
        A context manager that yields the mock_redis object.
    """
    class _Ctx:
        def __init__(self):
            self._rp = None
            self._sp = None
            self.mock_redis = None

        def __enter__(self):
            self._rp = patch("src.delivery.runner.redis")
            self.mock_redis = self._rp.__enter__()
            # Wrap factory so it absorbs kwargs like decode_responses=True
            # that redis.from_url passes; test factories don't need to know.
            _factory = from_url_factory
            self.mock_redis.from_url.side_effect = lambda *a, **_kw: _factory()
            self.mock_redis.ConnectionError = redis.ConnectionError

            # asyncio.sleep must yield to the event loop (even when "instant")
            # so other tasks get CPU time. _real_sleep(0) achieves this without
            # waiting any real time.  A sync side_effect on an AsyncMock records
            # the delay arg before the await completes.
            if sleeps is not None:
                recorded = sleeps

                async def _recording_sleep(delay):
                    recorded.append(delay)
                    await _real_sleep(0)

                sleep_mock = _recording_sleep
            else:
                async def _instant_yield(_delay):
                    await _real_sleep(0)

                sleep_mock = _instant_yield

            self._sp = patch("src.delivery.runner.asyncio.sleep", new=sleep_mock)
            self._sp.__enter__()
            return self.mock_redis

        def __exit__(self, *exc):
            self._sp.__exit__(*exc)
            self._rp.__exit__(*exc)

    return _Ctx()


def _idle_client() -> MagicMock:
    """Redis client whose pubsub always returns None (no messages)."""
    r = MagicMock()
    p = MagicMock()
    p.get_message.return_value = None
    r.pubsub.return_value = p
    return r


def _error_client(exc: Exception | None = None) -> MagicMock:
    """Redis client whose pubsub raises ConnectionError on get_message."""
    r = MagicMock()
    p = MagicMock()
    p.get_message.side_effect = exc or redis.ConnectionError("dropped")
    r.pubsub.return_value = p
    return r


# ---------------------------------------------------------------------------
# Tests: reconnect after disconnect
# ---------------------------------------------------------------------------


class TestRedisReconnectAfterDisconnect:
    """After a Redis disconnect the runner retries — it does not silently stop."""

    def test_reconnects_after_get_message_error(self):
        """
        First connection: get_message raises ConnectionError.
        Second connection: idle (no messages).
        from_url must be called at least twice.
        """
        call_count = {"n": 0}

        def _factory():
            call_count["n"] += 1
            return _error_client() if call_count["n"] == 1 else _idle_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_factory):
                await _run_loop(runner, stop_when=lambda: call_count["n"] >= 2)

        asyncio.run(_run())

        assert call_count["n"] >= 2, (
            f"Expected ≥2 from_url calls (initial + reconnect), got {call_count['n']}"
        )

    def test_initial_connection_failure_does_not_return(self):
        """
        First from_url call raises ConnectionError.
        Old code did `return`; new code sleeps 30s and retries.
        Verifies from_url is called a second time, and 30s sleep was recorded.
        """
        call_count = {"n": 0}
        sleeps: list[float] = []

        def _factory():
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise redis.ConnectionError("initial failure")
            return _idle_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_factory, sleeps=sleeps):
                await _run_loop(runner, stop_when=lambda: call_count["n"] >= 2)

        asyncio.run(_run())

        assert call_count["n"] >= 2, (
            f"Expected retry after initial failure, got {call_count['n']} from_url calls"
        )
        assert 30 in sleeps, (
            f"Expected 30s backoff on initial connection failure; sleeps: {sleeps}"
        )


# ---------------------------------------------------------------------------
# Tests: backoff behaviour
# ---------------------------------------------------------------------------


class TestReconnectBackoff:
    """Backoff delays come from [1, 2, 5, 10, 30] and increase with attempt count."""

    def test_backoff_values_come_from_array(self):
        """
        Every connection immediately raises on get_message.
        Sleep values must come from the defined backoff array.
        """
        _BACKOFF = {1, 2, 5, 10, 30}
        connect_count = {"n": 0}
        sleeps: list[float] = []

        def _always_fails():
            connect_count["n"] += 1
            return _error_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_always_fails, sleeps=sleeps):
                await _run_loop(runner, stop_when=lambda: connect_count["n"] >= 3)

        asyncio.run(_run())

        assert connect_count["n"] >= 2, (
            f"Expected multiple reconnects, got {connect_count['n']}"
        )
        backoff_sleeps = [s for s in sleeps if s in _BACKOFF]
        assert len(backoff_sleeps) >= 1, (
            f"Expected ≥1 sleep from {_BACKOFF}; all sleeps: {sleeps}"
        )

    def test_backoff_increases_with_consecutive_failures(self):
        """
        Three consecutive connections each fail on get_message without recovery.
        Backoff sleep values must be non-decreasing.
        """
        connect_count = {"n": 0}
        sleeps: list[float] = []

        def _always_fails():
            connect_count["n"] += 1
            return _error_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_always_fails, sleeps=sleeps):
                await _run_loop(runner, stop_when=lambda: connect_count["n"] >= 4)

        asyncio.run(_run())

        _BACKOFF = [1, 2, 5, 10, 30]
        backoff_sleeps = [s for s in sleeps if s in _BACKOFF]
        assert len(backoff_sleeps) >= 2, (
            f"Expected ≥2 backoff sleeps; all sleeps: {sleeps}"
        )
        for i in range(len(backoff_sleeps) - 1):
            assert backoff_sleeps[i] <= backoff_sleeps[i + 1], (
                f"Backoff should not decrease: {backoff_sleeps}"
            )

    def test_reconnect_attempt_counter_resets_after_successful_message(self):
        """
        First disconnect → 1s backoff.
        Second connection processes a clean message (resets counter).
        Third disconnect on that same connection → 1s backoff again (not 2s).
        """
        _BACKOFF = [1, 2, 5, 10, 30]
        phase = {"n": 0}
        sleeps: list[float] = []

        def _factory():
            phase["n"] += 1
            if phase["n"] == 1:
                return _error_client()

            if phase["n"] == 2:
                # Clean None (counts as successful iteration), then error
                responses = [None, redis.ConnectionError("lost again")]

                def _side(timeout=None):
                    v = responses.pop(0)
                    if isinstance(v, Exception):
                        raise v
                    return v

                r = MagicMock()
                p = MagicMock()
                p.get_message.side_effect = _side
                r.pubsub.return_value = p
                return r

            return _idle_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_factory, sleeps=sleeps):
                await _run_loop(runner, stop_when=lambda: phase["n"] >= 3)

        asyncio.run(_run())

        backoff_sleeps = [s for s in sleeps if s in _BACKOFF]
        one_second = [s for s in backoff_sleeps if s == 1]
        assert len(one_second) >= 2, (
            f"Expected ≥2 × 1s backoff (counter reset after clean iteration); "
            f"backoff sleeps: {backoff_sleeps}"
        )


# ---------------------------------------------------------------------------
# Tests: no silent give-up (regression for old `except: pass` pattern)
# ---------------------------------------------------------------------------


class TestNoSilentGiveUp:
    """Regression: old code had `except redis.ConnectionError: pass` — silent death."""

    def test_keeps_reconnecting_through_repeated_failures(self):
        """
        Every connection immediately fails on get_message.
        The runner must keep creating new connections — never silently give up.
        """
        connect_count = {"n": 0}

        def _always_errors():
            connect_count["n"] += 1
            return _error_client()

        async def _run():
            runner = _make_runner()
            with _make_redis_ctx(_always_errors):
                await _run_loop(runner, stop_when=lambda: connect_count["n"] >= 4)

        asyncio.run(_run())

        assert connect_count["n"] >= 4, (
            f"Runner gave up silently — only {connect_count['n']} connect attempts made"
        )
