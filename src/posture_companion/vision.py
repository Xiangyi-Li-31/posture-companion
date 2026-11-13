from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .posture import Landmark


POSE_EDGES = (
    (7, 8),
    (7, 11),
    (8, 12),
    (11, 12),
    (11, 23),
    (12, 24),
    (23, 24),
)


@dataclass(slots=True)
class VisionResult:
    frame_bgr: Any
    landmarks: dict[int, Landmark] | None
    timestamp: float


class PoseCamera:
    """Small adapter around OpenCV and MediaPipe Tasks."""

    def __init__(self, camera_index: int, model_path: Path, mirror: bool = True) -> None:
        try:
            import cv2
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "缺少摄像头依赖，请先运行 setup.ps1 安装。"
            ) from exc

        if not model_path.exists():
            raise RuntimeError(
                f"找不到姿态模型：{model_path}。请先运行 setup.ps1。"
            )

        self.cv2 = cv2
        self.mp = mp
        self.mirror = mirror
        if hasattr(cv2, "CAP_DSHOW"):
            self.capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        else:
            self.capture = cv2.VideoCapture(camera_index)
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.capture.isOpened():
            self.capture.release()
            raise RuntimeError(f"无法打开摄像头 {camera_index}")

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._last_timestamp_ms = 0

    def read(self) -> VisionResult | None:
        ok, frame = self.capture.read()
        if not ok:
            return None
        if self.mirror:
            frame = self.cv2.flip(frame, 1)

        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        mp_image = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        timestamp_ms = max(int(time.monotonic() * 1000), self._last_timestamp_ms + 1)
        self._last_timestamp_ms = timestamp_ms
        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        landmarks: dict[int, Landmark] | None = None
        if result.pose_landmarks:
            landmarks = {
                index: Landmark(
                    point.x,
                    point.y,
                    point.z,
                    getattr(point, "visibility", 1.0) or 0.0,
                )
                for index, point in enumerate(result.pose_landmarks[0])
            }
        return VisionResult(frame, landmarks, timestamp_ms / 1000.0)

    def draw_overlay(
        self,
        frame: Any,
        landmarks: dict[int, Landmark] | None,
        color: tuple[int, int, int],
        baseline_head_y: float | None = None,
    ) -> Any:
        if not landmarks:
            return frame
        height, width = frame.shape[:2]
        for start, end in POSE_EDGES:
            if start not in landmarks or end not in landmarks:
                continue
            a, b = landmarks[start], landmarks[end]
            if min(a.visibility, b.visibility) < 0.5:
                continue
            start_point = (int(a.x * width), int(a.y * height))
            end_point = (int(b.x * width), int(b.y * height))
            self.cv2.line(frame, start_point, end_point, color, 3)
        for index in (0, 3, 6, 7, 8, 11, 12, 23, 24):
            if index in landmarks and landmarks[index].visibility >= 0.5:
                point = landmarks[index]
                self.cv2.circle(
                    frame, (int(point.x * width), int(point.y * height)), 6, color, -1
                )
        if baseline_head_y is not None:
            y = int(baseline_head_y * height)
            self.cv2.line(frame, (0, y), (width, y), (245, 190, 60), 2)
            self.cv2.putText(
                frame,
                "upright baseline",
                (12, max(22, y - 8)),
                self.cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (245, 190, 60),
                2,
                self.cv2.LINE_AA,
            )
        return frame

    def close(self) -> None:
        self.capture.release()
        self.landmarker.close()


def list_available_cameras(limit: int = 6) -> list[tuple[int, str]]:
    """Probe camera indexes only when the user explicitly requests a refresh."""
    try:
        import cv2
    except ImportError:
        return []
    found: list[tuple[int, str]] = []
    for index in range(max(1, limit)):
        backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
        capture = cv2.VideoCapture(index, backend)
        try:
            if capture.isOpened():
                ok, _ = capture.read()
                if ok:
                    found.append((index, f"摄像头 {index}"))
        finally:
            capture.release()
    return found
