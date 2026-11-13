from __future__ import annotations

import os
import threading
from collections.abc import Callable


def play_alert() -> None:
    """Play a short, non-blocking system alert when available."""
    if os.name != "nt":
        return

    def _beep() -> None:
        try:
            import winsound

            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except (ImportError, RuntimeError):
            pass

    threading.Thread(target=_beep, daemon=True).start()


class AlertThrottle:
    def __init__(self, cooldown_seconds: float, action: Callable[[], None]) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.action = action
        self._last_alert_at = float("-inf")

    def trigger(self, now: float) -> bool:
        if now - self._last_alert_at < self.cooldown_seconds:
            return False
        self._last_alert_at = now
        self.action()
        return True
