from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TimerState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    DUE = "due"


@dataclass(frozen=True, slots=True)
class TimerSnapshot:
    state: TimerState
    elapsed_seconds: float
    remaining_seconds: float


class SittingTimer:
    """Monotonic work timer that is unaffected by system clock changes."""

    def __init__(
        self,
        duration_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._clock = clock
        self._duration = max(1.0, float(duration_seconds))
        self._started_at = self._clock()
        self._elapsed_before_pause = 0.0
        self._paused = False

    def set_duration(self, duration_seconds: float) -> None:
        self._duration = max(1.0, float(duration_seconds))

    def elapsed_seconds(self) -> float:
        if self._paused:
            return self._elapsed_before_pause
        return self._elapsed_before_pause + (self._clock() - self._started_at)

    def snapshot(self) -> TimerSnapshot:
        elapsed = max(0.0, self.elapsed_seconds())
        remaining = max(0.0, self._duration - elapsed)
        if self._paused:
            state = TimerState.PAUSED
        elif elapsed >= self._duration:
            state = TimerState.DUE
        else:
            state = TimerState.RUNNING
        return TimerSnapshot(state, elapsed, remaining)

    def pause(self) -> None:
        if not self._paused:
            self._elapsed_before_pause = self.elapsed_seconds()
            self._paused = True

    def resume(self) -> None:
        if self._paused:
            self._started_at = self._clock()
            self._paused = False

    def reset(self) -> None:
        self._started_at = self._clock()
        self._elapsed_before_pause = 0.0
        self._paused = False
