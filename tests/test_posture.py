import unittest

from posture_companion.posture import (
    Landmark,
    PostureFeatures,
    PostureMonitor,
    PostureState,
    baseline_from_features,
    extract_features,
    posture_score,
    posture_score_breakdown,
)


def landmarks(
    head_top_y: float = 0.30,
    head_scale: float = 0.12,
    shoulder_y: float = 0.55,
    head_z: float = -0.10,
):
    center = 0.5
    points = {
        0: Landmark(center, head_top_y + 0.055, head_z, 0.99),
        1: Landmark(center - head_scale * 0.12, head_top_y + 0.01, head_z, 0.99),
        2: Landmark(center - head_scale * 0.20, head_top_y + 0.005, head_z, 0.99),
        3: Landmark(center - head_scale * 0.26, head_top_y, head_z, 0.99),
        4: Landmark(center + head_scale * 0.12, head_top_y + 0.01, head_z, 0.99),
        5: Landmark(center + head_scale * 0.20, head_top_y + 0.005, head_z, 0.99),
        6: Landmark(center + head_scale * 0.26, head_top_y, head_z, 0.99),
        7: Landmark(center - head_scale / 2, head_top_y + 0.06, head_z, 0.99),
        8: Landmark(center + head_scale / 2, head_top_y + 0.06, head_z, 0.99),
        9: Landmark(center - head_scale * 0.18, head_top_y + 0.10, head_z, 0.99),
        10: Landmark(center + head_scale * 0.18, head_top_y + 0.10, head_z, 0.99),
        11: Landmark(0.40, shoulder_y, 0.00, 0.99),
        12: Landmark(0.60, shoulder_y, 0.00, 0.99),
        23: Landmark(0.43, 0.90, 0.02, 0.99),
        24: Landmark(0.57, 0.90, 0.02, 0.99),
    }
    return points


class PostureFeatureTests(unittest.TestCase):
    def test_extracts_fixed_camera_features(self) -> None:
        features = extract_features(landmarks())
        self.assertIsNotNone(features)
        assert features is not None
        self.assertAlmostEqual(features.head_top_y, 0.30)
        self.assertAlmostEqual(features.head_scale, 0.12)
        self.assertAlmostEqual(features.shoulder_y, 0.55)
        self.assertAlmostEqual(features.torso_height or 0, 0.35)

    def test_rejects_low_visibility(self) -> None:
        points = landmarks()
        points[11] = Landmark(0.40, 0.55, 0.0, 0.1)
        self.assertIsNone(extract_features(points))

    def test_height_drop_and_head_growth_raise_score(self) -> None:
        good = PostureFeatures(0.30, 0.55, 0.12, 0.20, 0.10, 0.35)
        baseline = baseline_from_features([good] * 5)
        slouched = PostureFeatures(0.36, 0.59, 0.145, 0.14, 0.32, 0.31)
        parts = posture_score_breakdown(slouched, baseline)
        self.assertEqual(parts.height_drop, 100)
        self.assertGreater(parts.head_enlargement, 90)
        self.assertGreater(posture_score(slouched, baseline), 70)

    def test_baseline_round_trip(self) -> None:
        baseline = baseline_from_features(
            [PostureFeatures(0.3, 0.55, 0.12, 0.2, 0.1, None)]
        )
        self.assertEqual(type(baseline).from_dict(baseline.to_dict()), baseline)


class PostureMonitorTests(unittest.TestCase):
    def test_requires_calibration_then_delays_alert(self) -> None:
        monitor = PostureMonitor(
            threshold=30,
            alert_after_seconds=2,
            calibration_samples=5,
            smoothing=1,
        )
        self.assertEqual(monitor.update(landmarks(), 0).state, PostureState.NEEDS_CALIBRATION)
        monitor.start_calibration()
        for index in range(5):
            reading = monitor.update(landmarks(), index * 0.1)
        self.assertEqual(reading.state, PostureState.GOOD)

        slouched = landmarks(head_top_y=0.37, head_scale=0.15, shoulder_y=0.60, head_z=-0.3)
        self.assertEqual(monitor.update(slouched, 10).state, PostureState.GOOD)
        self.assertEqual(monitor.update(slouched, 11).state, PostureState.GOOD)
        self.assertEqual(monitor.update(slouched, 12).state, PostureState.BAD)

    def test_losing_person_resets_bad_duration(self) -> None:
        monitor = PostureMonitor(30, 2, 5, 1)
        monitor.start_calibration()
        for index in range(5):
            monitor.update(landmarks(), index)
        slouched = landmarks(head_top_y=0.37, head_scale=0.15, shoulder_y=0.60)
        monitor.update(slouched, 10)
        self.assertEqual(monitor.update(None, 12).state, PostureState.NO_PERSON)
        self.assertEqual(monitor.update(slouched, 13).state, PostureState.GOOD)


if __name__ == "__main__":
    unittest.main()
