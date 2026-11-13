import tempfile
import unittest
from datetime import date
from pathlib import Path

from posture_companion.storage import TodoRepository


class TodoRepositoryTests(unittest.TestCase):
    def test_crud_and_day_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TodoRepository(Path(directory) / "todos.sqlite3")
            first = repository.add("写周报", date(2026, 9, 11))
            repository.add("明天的任务", date(2026, 9, 12))
            items = repository.list_for_day(date(2026, 9, 11))
            self.assertEqual([item.title for item in items], ["写周报"])

            repository.set_completed(first.id, True)
            self.assertTrue(repository.list_for_day(date(2026, 9, 11))[0].completed)
            repository.delete(first.id)
            self.assertEqual(repository.list_for_day(date(2026, 9, 11)), [])

    def test_rejects_blank_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TodoRepository(Path(directory) / "todos.sqlite3")
            with self.assertRaises(ValueError):
                repository.add("   ", date.today())

    def test_daily_activities_complete_independently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TodoRepository(Path(directory) / "todos.sqlite3")
            day = date(2026, 9, 12)
            repository.ensure_activities(day, ["接水", "肩颈操 10 分钟", "远眺 10 分钟"])
            items = repository.list_activities(day)
            self.assertEqual(len(items), 3)
            repository.set_activity_completed(items[1].id, True)
            updated = repository.list_activities(day)
            self.assertEqual(sum(item.completed for item in updated), 1)
            self.assertTrue(next(item for item in updated if item.title.startswith("肩颈操")).completed)

    def test_accumulates_daily_stats(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = TodoRepository(Path(directory) / "todos.sqlite3")
            day = date(2026, 9, 12)
            repository.record_stats(day, posture_samples=1, upright_samples=1, seated_seconds=5)
            repository.record_stats(day, posture_samples=1, needs_attention_samples=1, away_breaks=1)
            stats = repository.list_stats(day, day)[0]
            self.assertEqual(stats.posture_samples, 2)
            self.assertEqual(stats.upright_samples, 1)
            self.assertEqual(stats.needs_attention_samples, 1)
            self.assertEqual(stats.seated_seconds, 5)
            self.assertEqual(stats.away_breaks, 1)


if __name__ == "__main__":
    unittest.main()
