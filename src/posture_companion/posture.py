from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, Mapping


NOSE = 0
LEFT_EYE_OUTER = 3
RIGHT_EYE_OUTER = 6
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_MOUTH = 9
RIGHT_MOUTH = 10
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24


@dataclass(frozen=True, slots=True)
class Landmark:
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0


@dataclass(frozen=True, slots=True)
class PostureFeatures:
    # Absolute image-space values are intentional: calibration assumes the
    # camera stays fixed, so a lower head/shoulder is a strong sitting signal.
    head_top_y: float
    shoulder_y: float
    head_scale: float
    neck_height: float
    head_depth: float
    torso_height: float | None = None


@dataclass(frozen=True, slots=True)
class PostureBaseline:
    head_top_y: float
    shoulder_y: float
    head_scale: float
    neck_height: float
    head_depth: float
    torso_height: float | None = None

    def to_dict(self) -> dict[str, float | None]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "PostureBaseline":
        return cls(
            head_top_y=float(value["head_top_y"]),
            shoulder_y=float(value["shoulder_y"]),
            head_scale=float(value["head_scale"]),
            neck_height=float(value["neck_height"]),
            head_depth=float(value["head_depth"]),
            torso_height=(
                None
                if value.get("torso_height") is None
                else float(value["torso_height"])
            ),
        )


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    height_drop: float
    head_enlargement: float
    shoulder_drop: float
    torso_collapse: float
    neck_compression: float
    depth_advance: float


class PostureState(str, Enum):
    NO_PERSON = "no_person"
    NEEDS_CALIBRATION = "needs_calibration"
    CALIBRATING = "calibrating"
    GOOD = "good"
    BAD = "bad"


@dataclass(frozen=True, slots=True)
class PostureReading:
    state: PostureState
    score: float | None
    bad_for_seconds: float
    calibration_progress: float
    features: PostureFeatures | None = None
    breakdown: ScoreBreakdown | None = None


def _midpoint(a: Landmark, b: Landmark) -> Landmark:
    return Landmark(
        (a.x + b.x) / 2,
        (a.y + b.y) / 2,
        (a.z + b.z) / 2,
        min(a.visibility, b.visibility),
    )


def _distance(a: Landmark, b: Landmark) -> float:
    return math.hypot(b.x - a.x, b.y - a.y)


def _visible(
    landmarks: Mapping[int, Landmark], index: int, minimum: float
) -> Landmark | None:
    point = landmarks.get(index)
    return point if point is not None and point.visibility >= minimum else None


def extract_features(
    landmarks: Mapping[int, Landmark], min_visibility: float = 0.45
) -> PostureFeatures | None:
    left_shoulder = _visible(landmarks, LEFT_SHOULDER, min_visibility)
    right_shoulder = _visible(landmarks, RIGHT_SHOULDER, min_visibility)
    if left_shoulder is None or right_shoulder is None:
        return None
    shoulder_mid = _midpoint(left_shoulder, right_shoulder)

    head_points = [
        point
        for index in range(NOSE, RIGHT_MOUTH + 1)
        if (point := _visible(landmarks, index, min_visibility)) is not None
    ]
    if len(head_points) < 3:
        return None

    # Pose has no crown landmark. The highest reliable face keypoint is a
    # stable proxy for overall seated height when the camera does not move.
    head_top_y = min(point.y for point in head_points)
    head_center_y = statistics.mean(point.y for point in head_points)
    head_center_z = statistics.mean(point.z for point in head_points)

    spans: list[float] = []
    for left_index, right_index in (
        (LEFT_EAR, RIGHT_EAR),
        (LEFT_EYE_OUTER, RIGHT_EYE_OUTER),
        (LEFT_MOUTH, RIGHT_MOUTH),
    ):
        left = _visible(landmarks, left_index, min_visibility)
        right = _visible(landmarks, right_index, min_visibility)
        if left is not None and right is not None:
            spans.append(_distance(left, right))
    if not spans:
        return None
    head_scale = max(spans)
    if head_scale < 0.008:
        return None

    torso_height: float | None = None
    left_hip = _visible(landmarks, LEFT_HIP, min_visibility)
    right_hip = _visible(landmarks, RIGHT_HIP, min_visibility)
    if left_hip is not None and right_hip is not None:
        hip_mid = _midpoint(left_hip, right_hip)
        torso_height = max(0.0, hip_mid.y - shoulder_mid.y)

    return PostureFeatures(
        head_top_y=head_top_y,
        shoulder_y=shoulder_mid.y,
        head_scale=head_scale,
        neck_height=shoulder_mid.y - head_center_y,
        head_depth=shoulder_mid.z - head_center_z,
        torso_height=torso_height,
    )


def _optional_median(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return statistics.median(present) if present else None


def baseline_from_features(samples: Iterable[PostureFeatures]) -> PostureBaseline:
    values = list(samples)
    if not values:
        raise ValueError("校准样本不能为空")
    return PostureBaseline(
        head_top_y=statistics.median(value.head_top_y for value in values),
        shoulder_y=statistics.median(value.shoulder_y for value in values),
        head_scale=statistics.median(value.head_scale for value in values),
        neck_height=statistics.median(value.neck_height for value in values),
        head_depth=statistics.median(value.head_depth for value in values),
        torso_height=_optional_median(value.torso_height for value in values),
    )


def _percent(value: float) -> float:
    return min(100.0, max(0.0, value * 100.0))


def posture_score_breakdown(
    features: PostureFeatures, baseline: PostureBaseline
) -> ScoreBreakdown:
    head_scale_base = max(0.008, baseline.head_scale)
    torso_collapse = 0.0
    if baseline.torso_height is not None and features.torso_height is not None:
        torso_collapse = _percent(
            (baseline.torso_height - features.torso_height) / 0.055
        )
    return ScoreBreakdown(
        height_drop=_percent((features.head_top_y - baseline.head_top_y) / 0.04),
        head_enlargement=_percent(
            (features.head_scale / head_scale_base - 1.0) / 0.12
        ),
        shoulder_drop=_percent((features.shoulder_y - baseline.shoulder_y) / 0.04),
        torso_collapse=torso_collapse,
        neck_compression=_percent(
            (baseline.neck_height - features.neck_height) / 0.045
        ),
        depth_advance=_percent((features.head_depth - baseline.head_depth) / 0.18),
    )


def posture_score(features: PostureFeatures, baseline: PostureBaseline) -> float:
    parts = posture_score_breakdown(features, baseline)
    # Height is primary. Head enlargement and torso/shoulder collapse confirm
    # that the drop is caused by leaning rather than landmark wobble.
    return min(
        100.0,
        0.38 * parts.height_drop
        + 0.22 * parts.head_enlargement
        + 0.13 * parts.shoulder_drop
        + 0.12 * parts.torso_collapse
        + 0.09 * parts.neck_compression
        + 0.06 * parts.depth_advance,
    )


class PostureMonitor:
    def __init__(
        self,
        threshold: float = 36.0,
        alert_after_seconds: float = 5.0,
        calibration_samples: int = 45,
        smoothing: float = 0.28,
        baseline: PostureBaseline | None = None,
    ) -> None:
        self.threshold = float(threshold)
        self.alert_after_seconds = float(alert_after_seconds)
        self.calibration_samples = max(5, int(calibration_samples))
        self.smoothing = min(1.0, max(0.01, float(smoothing)))
        self.baseline = baseline
        self._calibration: list[PostureFeatures] = []
        self._is_calibrating = False
        self._smoothed_score: float | None = None
        self._bad_since: float | None = None

    def start_calibration(self) -> None:
        self._calibration.clear()
        self._is_calibrating = True
        self._smoothed_score = None
        self._bad_since = None

    def set_threshold(self, threshold: float, alert_after_seconds: float) -> None:
        self.threshold = min(90.0, max(10.0, float(threshold)))
        self.alert_after_seconds = min(60.0, max(1.0, float(alert_after_seconds)))

    def update(
        self, landmarks: Mapping[int, Landmark] | None, timestamp: float
    ) -> PostureReading:
        features = extract_features(landmarks or {})
        if features is None:
            self._bad_since = None
            return PostureReading(
                PostureState.NO_PERSON,
                None,
                0.0,
                len(self._calibration) / self.calibration_samples,
            )

        if self._is_calibrating:
            self._calibration.append(features)
            progress = min(1.0, len(self._calibration) / self.calibration_samples)
            if len(self._calibration) >= self.calibration_samples:
                self.baseline = baseline_from_features(self._calibration)
                self._is_calibrating = False
                self._calibration.clear()
                return PostureReading(
                    PostureState.GOOD, 0.0, 0.0, 1.0, features
                )
            return PostureReading(
                PostureState.CALIBRATING, None, 0.0, progress, features
            )

        if self.baseline is None:
            return PostureReading(
                PostureState.NEEDS_CALIBRATION, None, 0.0, 0.0, features
            )

        raw_score = posture_score(features, self.baseline)
        breakdown = posture_score_breakdown(features, self.baseline)
        if self._smoothed_score is None:
            self._smoothed_score = raw_score
        else:
            alpha = self.smoothing
            self._smoothed_score = alpha * raw_score + (1 - alpha) * self._smoothed_score

        if self._smoothed_score >= self.threshold:
            if self._bad_since is None:
                self._bad_since = timestamp
            bad_for = max(0.0, timestamp - self._bad_since)
            state = (
                PostureState.BAD
                if bad_for >= self.alert_after_seconds
                else PostureState.GOOD
            )
        else:
            self._bad_since = None
            bad_for = 0.0
            state = PostureState.GOOD

        return PostureReading(
            state, self._smoothed_score, bad_for, 1.0, features, breakdown
        )
