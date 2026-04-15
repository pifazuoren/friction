from __future__ import annotations

from types import MethodType
from typing import Any


def is_proto_logical_clock_enabled(environment: Any) -> bool:
    return bool(getattr(environment, "_proto_logical_clock_enabled", False))


def enable_proto_logical_clock(agentsociety: Any) -> bool:
    environment = getattr(agentsociety, "environment", None)
    if environment is None:
        raise ValueError("agentsociety.environment is not initialized")
    if is_proto_logical_clock_enabled(environment):
        return True

    original_step = getattr(environment, "step", None)
    original_get_metrics = getattr(environment, "get_metrics", None)
    if original_step is None or original_get_metrics is None:
        raise ValueError("environment does not expose step/get_metrics")

    async def _logical_step(self, n: int) -> None:
        normalized_ticks = int(n)
        assert normalized_ticks > 0, "`n` must >=1!"
        self._tick += normalized_ticks

    async def _logical_get_metrics(self) -> list[tuple[str, float, int]]:
        return []

    environment._proto_original_step = original_step
    environment._proto_original_get_metrics = original_get_metrics
    environment.step = MethodType(_logical_step, environment)
    environment.get_metrics = MethodType(_logical_get_metrics, environment)
    environment._proto_logical_clock_enabled = True
    environment._proto_logical_clock_mode = "step_jump"
    return True
