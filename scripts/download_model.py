from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path


MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    destination = project_root / "models" / "pose_landmarker_lite.task"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 1_000_000:
        print(f"模型已存在：{destination}")
        return 0

    temporary = destination.with_suffix(".download")
    print("正在从 Google MediaPipe 下载姿态模型……")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response:
            digest = hashlib.sha256()
            with temporary.open("wb") as output:
                while chunk := response.read(1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if temporary.stat().st_size < 1_000_000:
            raise RuntimeError("下载的模型文件大小异常")
        temporary.replace(destination)
        print(f"模型已保存：{destination}")
        print(f"SHA-256：{digest.hexdigest()}")
        return 0
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        print(f"模型下载失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
