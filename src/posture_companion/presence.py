from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PresenceState(str, Enum):
    PRESENT = "present"
    MAYBE_AWAY = "maybe_away"
    AWAY = "away"


@dataclass(frozen=True, slots=True)
class PresenceReading:
    state: PresenceState
    absent_for_seconds: float
    just_left: bool = False
    just_returned: bool = False


class PresenceMonitor:
    def __init__(self, away_after_seconds: float = 30.0) -> None:
        self.away_after_seconds = max(5.0, float(away_after_seconds))
        self._missing_since: float | None = None
        self._was_away = False

    def set_away_after(self, seconds: float) -> None:
        self.away_after_seconds = max(5.0, float(seconds))

    def update(self, person_visible: bool, timestamp: float) -> PresenceReading:
        if person_visible:
            just_returned = self._was_away
            self._missing_since = None
            self._was_away = False
            return PresenceReading(
                PresenceState.PRESENT, 0.0, just_returned=just_returned
            )

        if self._missing_since is None:
            self._missing_since = timestamp
        absent_for = max(0.0, timestamp - self._missing_since)
        if absent_for >= self.away_after_seconds:
            just_left = not self._was_away
            self._was_away = True
            return PresenceReading(
                PresenceState.AWAY, absent_for, just_left=just_left
            )
        return PresenceReading(PresenceState.MAYBE_AWAY, absent_for)
