from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True, slots=True)
class Todo:
    id: int
    day: str
    title: str
    completed: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class DailyStats:
    day: str
    posture_samples: int = 0
    upright_samples: int = 0
    needs_attention_samples: int = 0
    seated_seconds: int = 0
    away_breaks: int = 0
    manual_breaks: int = 0


class TodoRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT NOT NULL,
                    title TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_todos_day ON todos(day, id)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day TEXT NOT NULL,
                    title TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE(day, title)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_stats (
                    day TEXT PRIMARY KEY,
                    posture_samples INTEGER NOT NULL DEFAULT 0,
                    upright_samples INTEGER NOT NULL DEFAULT 0,
                    needs_attention_samples INTEGER NOT NULL DEFAULT 0,
                    seated_seconds INTEGER NOT NULL DEFAULT 0,
                    away_breaks INTEGER NOT NULL DEFAULT 0,
                    manual_breaks INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def list_for_day(self, day: date) -> list[Todo]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, day, title, completed, created_at "
                "FROM todos WHERE day = ? ORDER BY completed, id",
                (day.isoformat(),),
            ).fetchall()
        return [
            Todo(
                id=row["id"],
                day=row["day"],
                title=row["title"],
                completed=bool(row["completed"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add(self, title: str, day: date) -> Todo:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("待办内容不能为空")
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO todos(day, title, completed, created_at) "
                "VALUES (?, ?, 0, ?)",
                (day.isoformat(), clean_title, created_at),
            )
            todo_id = int(cursor.lastrowid)
        return Todo(todo_id, day.isoformat(), clean_title, False, created_at)

    def set_completed(self, todo_id: int, completed: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE todos SET completed = ? WHERE id = ?",
                (int(completed), todo_id),
            )

    def delete(self, todo_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,))

    def ensure_activities(self, day: date, titles: list[str]) -> None:
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = [
            (day.isoformat(), title.strip(), created_at)
            for title in titles
            if title.strip()
        ]
        with self._connect() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO activities(day, title, completed, created_at) "
                "VALUES (?, ?, 0, ?)",
                rows,
            )

    def list_activities(self, day: date) -> list[Todo]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, day, title, completed, created_at "
                "FROM activities WHERE day = ? ORDER BY completed, id",
                (day.isoformat(),),
            ).fetchall()
        return [
            Todo(
                id=row["id"],
                day=row["day"],
                title=row["title"],
                completed=bool(row["completed"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def add_activity(self, title: str, day: date) -> Todo:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("活动内容不能为空")
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO activities(day, title, completed, created_at) "
                "VALUES (?, ?, 0, ?)",
                (day.isoformat(), clean_title, created_at),
            )
            item_id = int(cursor.lastrowid)
        return Todo(item_id, day.isoformat(), clean_title, False, created_at)

    def set_activity_completed(self, item_id: int, completed: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE activities SET completed = ? WHERE id = ?",
                (int(completed), item_id),
            )

    def delete_activity(self, item_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM activities WHERE id = ?", (item_id,))

    def record_stats(
        self,
        day: date,
        *,
        posture_samples: int = 0,
        upright_samples: int = 0,
        needs_attention_samples: int = 0,
        seated_seconds: int = 0,
        away_breaks: int = 0,
        manual_breaks: int = 0,
    ) -> None:
        values = (
            day.isoformat(),
            posture_samples,
            upright_samples,
            needs_attention_samples,
            seated_seconds,
            away_breaks,
            manual_breaks,
        )
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO daily_stats(
                    day, posture_samples, upright_samples,
                    needs_attention_samples, seated_seconds,
                    away_breaks, manual_breaks
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(day) DO UPDATE SET
                    posture_samples = posture_samples + excluded.posture_samples,
                    upright_samples = upright_samples + excluded.upright_samples,
                    needs_attention_samples = needs_attention_samples + excluded.needs_attention_samples,
                    seated_seconds = seated_seconds + excluded.seated_seconds,
                    away_breaks = away_breaks + excluded.away_breaks,
                    manual_breaks = manual_breaks + excluded.manual_breaks
                """,
                values,
            )

    def list_stats(self, start_day: date, end_day: date) -> list[DailyStats]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM daily_stats WHERE day BETWEEN ? AND ? ORDER BY day",
                (start_day.isoformat(), end_day.isoformat()),
            ).fetchall()
        return [DailyStats(**dict(row)) for row in rows]
