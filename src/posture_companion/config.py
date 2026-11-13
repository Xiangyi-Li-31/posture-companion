from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


APP_NAME = "PostureCompanion"
CURRENT_SETTINGS_VERSION = 3


def default_data_dir() -> Path:
    """Return a per-user data directory without writing anything."""
    if os.name == "nt":
        root = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        root = Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / APP_NAME


def resource_path(*parts: str) -> Path:
    """Resolve bundled assets in source and PyInstaller builds."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    root = Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[2]
    return root.joinpath(*parts)


@dataclass(slots=True)
class AppSettings:
    settings_version: int = CURRENT_SETTINGS_VERSION
    work_minutes: int = 45
    activity_text: str = "起身走动 3 分钟，喝点水，活动肩颈"
    activity_templates: list[str] = field(
        default_factory=lambda: [
            "起身接一杯水",
            "做肩颈操 10 分钟",
            "远眺 10 分钟",
        ]
    )
    posture_alert_seconds: float = 5.0
    posture_popup_seconds: float = 60.0
    posture_sensitivity: int = 40
    camera_index: int = 0
    mirror_camera: bool = True
    show_camera_preview: bool = True
    auto_away_detection: bool = True
    away_seconds: int = 30
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    pet_enabled: bool = True
    pet_kind: str = "cat"

    def validate(self) -> "AppSettings":
        self.work_minutes = min(240, max(1, int(self.work_minutes)))
        self.posture_alert_seconds = min(
            60.0, max(1.0, float(self.posture_alert_seconds))
        )
        self.posture_popup_seconds = min(
            600.0, max(10.0, float(self.posture_popup_seconds))
        )
        self.posture_sensitivity = min(90, max(10, int(self.posture_sensitivity)))
        self.camera_index = min(20, max(0, int(self.camera_index)))
        self.activity_text = self.activity_text.strip() or "起身活动一下"
        cleaned_templates: list[str] = []
        source_templates = (
            self.activity_templates
            if isinstance(self.activity_templates, list)
            else [self.activity_text]
        )
        for item in source_templates:
            clean = str(item).strip()
            if clean and clean not in cleaned_templates:
                cleaned_templates.append(clean)
        self.activity_templates = cleaned_templates or [self.activity_text]
        self.mirror_camera = bool(self.mirror_camera)
        self.show_camera_preview = bool(self.show_camera_preview)
        self.auto_away_detection = bool(self.auto_away_detection)
        self.away_seconds = min(600, max(10, int(self.away_seconds)))
        self.start_with_windows = bool(self.start_with_windows)
        self.minimize_to_tray = bool(self.minimize_to_tray)
        self.pet_enabled = bool(self.pet_enabled)
        self.pet_kind = self.pet_kind if self.pet_kind in {"cat", "dog"} else "cat"
        self.settings_version = CURRENT_SETTINGS_VERSION
        return self


class SettingsStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> AppSettings:
        if not self.path.exists():
            return AppSettings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return AppSettings()
            if int(raw.get("settings_version", 1)) < CURRENT_SETTINGS_VERSION:
                # V2 used 45 as its default. Move untouched installations to
                # the more responsive V3 default while preserving custom values.
                if int(raw.get("posture_sensitivity", 45)) == 45:
                    raw["posture_sensitivity"] = 40
                raw.setdefault("posture_popup_seconds", 60.0)
                raw.setdefault("pet_enabled", True)
                raw.setdefault("pet_kind", "cat")
                raw["settings_version"] = CURRENT_SETTINGS_VERSION
            allowed = {field.name for field in fields(AppSettings)}
            values: dict[str, Any] = {
                key: value for key, value in raw.items() if key in allowed
            }
            return AppSettings(**values).validate()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return AppSettings()

    def save(self, settings: AppSettings) -> None:
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(
            json.dumps(asdict(settings), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.path)


class CalibrationStore:
    """Persist one posture baseline per camera index."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read_all(self) -> dict[str, dict[str, float | None]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def load(self, camera_index: int) -> dict[str, float | None] | None:
        value = self._read_all().get(str(camera_index))
        return value if isinstance(value, dict) else None

    def save(self, camera_index: int, baseline: dict[str, float | None]) -> None:
        values = self._read_all()
        values[str(camera_index)] = baseline
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(self.path)
