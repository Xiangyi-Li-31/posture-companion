import json
import tempfile
import unittest
from pathlib import Path

from posture_companion.config import AppSettings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory) / "settings.json")
            expected = AppSettings(work_minutes=30, activity_text="接水")
            store.save(expected)
            self.assertEqual(store.load().work_minutes, 30)
            self.assertEqual(store.load().activity_text, "接水")

    def test_ignores_unknown_keys_and_clamps_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps({"work_minutes": 999, "unknown": "ignored"}),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
            self.assertEqual(loaded.work_minutes, 240)

    def test_cleans_activity_templates(self) -> None:
        settings = AppSettings(activity_templates=[" 接水 ", "接水", "远眺 10 分钟", ""])
        settings.validate()
        self.assertEqual(settings.activity_templates, ["接水", "远眺 10 分钟"])

    def test_migrates_v2_default_threshold_and_adds_pet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(
                json.dumps({"posture_sensitivity": 45, "work_minutes": 45}),
                encoding="utf-8",
            )
            loaded = SettingsStore(path).load()
            self.assertEqual(loaded.posture_sensitivity, 40)
            self.assertEqual(loaded.posture_popup_seconds, 60)
            self.assertTrue(loaded.pet_enabled)
            self.assertEqual(loaded.pet_kind, "cat")


if __name__ == "__main__":
    unittest.main()
