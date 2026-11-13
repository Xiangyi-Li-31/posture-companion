import unittest

from posture_companion.presence import PresenceMonitor, PresenceState


class PresenceMonitorTests(unittest.TestCase):
    def test_confirms_away_and_reports_return(self) -> None:
        monitor = PresenceMonitor(30)
        self.assertEqual(monitor.update(True, 0).state, PresenceState.PRESENT)
        self.assertEqual(monitor.update(False, 10).state, PresenceState.MAYBE_AWAY)
        self.assertEqual(monitor.update(False, 39).state, PresenceState.MAYBE_AWAY)
        away = monitor.update(False, 40)
        self.assertEqual(away.state, PresenceState.AWAY)
        self.assertTrue(away.just_left)
        self.assertFalse(monitor.update(False, 45).just_left)
        returned = monitor.update(True, 46)
        self.assertEqual(returned.state, PresenceState.PRESENT)
        self.assertTrue(returned.just_returned)

    def test_short_detection_loss_is_not_away(self) -> None:
        monitor = PresenceMonitor(10)
        monitor.update(False, 0)
        returned = monitor.update(True, 9)
        self.assertFalse(returned.just_returned)


if __name__ == "__main__":
    unittest.main()
