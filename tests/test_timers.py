import unittest

from posture_companion.timers import SittingTimer, TimerState


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class SittingTimerTests(unittest.TestCase):
    def test_reaches_due_and_resets(self) -> None:
        clock = FakeClock()
        timer = SittingTimer(60, clock=clock)
        clock.value = 59
        self.assertEqual(timer.snapshot().state, TimerState.RUNNING)
        self.assertEqual(timer.snapshot().remaining_seconds, 1)
        clock.value = 60
        self.assertEqual(timer.snapshot().state, TimerState.DUE)
        timer.reset()
        self.assertEqual(timer.snapshot().remaining_seconds, 60)

    def test_pause_does_not_count_time(self) -> None:
        clock = FakeClock()
        timer = SittingTimer(100, clock=clock)
        clock.value = 20
        timer.pause()
        clock.value = 80
        self.assertEqual(timer.snapshot().elapsed_seconds, 20)
        timer.resume()
        clock.value = 90
        self.assertEqual(timer.snapshot().elapsed_seconds, 30)


if __name__ == "__main__":
    unittest.main()
