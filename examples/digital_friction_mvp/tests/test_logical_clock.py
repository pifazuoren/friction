from __future__ import annotations

import asyncio
from types import SimpleNamespace

from proto.logical_clock import (
    enable_proto_logical_clock,
    is_proto_logical_clock_enabled,
)


class _FakeEnvironment:
    def __init__(self, *, start_tick: int = 6 * 60 * 60):
        self._tick = 0
        self._environment_config = SimpleNamespace(start_tick=start_tick)
        self.original_step_calls = 0
        self.original_metrics_calls = 0
        self._log_list = []

    async def step(self, n: int):
        self.original_step_calls += 1
        self._tick += int(n)

    async def get_metrics(self):
        self.original_metrics_calls += 1
        return [("original.metric", 1.0, self._tick)]

    def get_datetime(self, format_time: bool = False):
        time_value = (self._tick + self._environment_config.start_tick) % (24 * 60 * 60)
        day_value = (self._tick + self._environment_config.start_tick) // (24 * 60 * 60)
        if format_time:
            hours = time_value // 3600
            minutes = (time_value % 3600) // 60
            seconds = time_value % 60
            return day_value, f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return day_value, time_value


class _FakeSimulation:
    def __init__(self, environment: _FakeEnvironment):
        self.environment = environment


def test_enable_proto_logical_clock_patches_step_and_metrics() -> None:
    environment = _FakeEnvironment()
    simulation = _FakeSimulation(environment)

    assert enable_proto_logical_clock(simulation) is True
    assert is_proto_logical_clock_enabled(environment) is True

    asyncio.run(environment.step(1800))
    assert environment._tick == 1800
    assert environment.original_step_calls == 0

    metrics = asyncio.run(environment.get_metrics())
    assert metrics == []
    assert environment.original_metrics_calls == 0


def test_logical_clock_preserves_datetime_progression() -> None:
    environment = _FakeEnvironment()
    simulation = _FakeSimulation(environment)
    enable_proto_logical_clock(simulation)

    assert environment.get_datetime(format_time=True) == (0, "06:00:00")
    asyncio.run(environment.step(1800))
    assert environment.get_datetime(format_time=True) == (0, "06:30:00")


def test_logical_clock_handles_day_rollover() -> None:
    environment = _FakeEnvironment()
    environment._tick = (17 * 60 * 60) + (30 * 60)
    simulation = _FakeSimulation(environment)
    enable_proto_logical_clock(simulation)

    assert environment.get_datetime(format_time=True) == (0, "23:30:00")
    asyncio.run(environment.step(1800))
    assert environment.get_datetime(format_time=True) == (1, "00:00:00")


def test_enable_proto_logical_clock_is_idempotent() -> None:
    environment = _FakeEnvironment()
    simulation = _FakeSimulation(environment)

    assert enable_proto_logical_clock(simulation) is True
    first_step_ref = environment.step
    first_original_step = environment._proto_original_step
    first_metrics_ref = environment.get_metrics
    first_original_metrics = environment._proto_original_get_metrics

    assert enable_proto_logical_clock(simulation) is True
    assert environment.step is first_step_ref
    assert environment.get_metrics is first_metrics_ref
    assert environment._proto_original_step is first_original_step
    assert environment._proto_original_get_metrics is first_original_metrics
