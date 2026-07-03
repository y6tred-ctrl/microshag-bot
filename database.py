import aiosqlite
from datetime import date, datetime
from typing import Optional

from config import settings

DB_PATH = settings.database_path


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                reminder_time TEXT NOT NULL DEFAULT '10:00',
                daily_limit INTEGER NOT NULL DEFAULT 3,
                is_paused INTEGER NOT NULL DEFAULT 0,
                pause_until TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS micro_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                goal_id INTEGER REFERENCES goals(id),
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pool',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                scheduled_date TEXT
            );
        """)
        await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict:
    return dict(row) if row else {}


# ─── Users ──────────────────────────────────────────────

async def get_user(tg_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
        return _row_to_dict(await cursor.fetchone())


async def create_user(tg_id: int, name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (tg_id, name) VALUES (?, ?)",
            (tg_id, name),
        )
        await db.commit()


async def update_user(tg_id: int, **kwargs):
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [tg_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {sets} WHERE tg_id = ?", vals)
        await db.commit()


# ─── Goals ──────────────────────────────────────────────

async def create_goal(tg_id: int, title: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO goals (tg_id, title) VALUES (?, ?)", (tg_id, title)
        )
        await db.commit()
        return cursor.lastrowid


async def get_goals(tg_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM goals WHERE tg_id = ? ORDER BY created_at DESC", (tg_id,)
        )
        return [_row_to_dict(r) for r in await cursor.fetchall()]


# ─── Micro-steps ────────────────────────────────────────

async def add_steps(steps: list[dict]) -> list[int]:
    ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        for s in steps:
            cursor = await db.execute(
                "INSERT INTO micro_steps (tg_id, goal_id, text) VALUES (?, ?, ?)",
                (s["tg_id"], s.get("goal_id"), s["text"]),
            )
            ids.append(cursor.lastrowid)
        await db.commit()
    return ids


async def get_pool_steps(tg_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM micro_steps WHERE tg_id = ? AND status = 'pool' ORDER BY created_at ASC",
            (tg_id,),
        )
        return [_row_to_dict(r) for r in await cursor.fetchall()]


async def get_today_steps(tg_id: int, today: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM micro_steps WHERE tg_id = ? AND scheduled_date = ? AND status = 'scheduled' ORDER BY created_at ASC",
            (tg_id, today),
        )
        return [_row_to_dict(r) for r in await cursor.fetchall()]


async def schedule_steps(tg_id: int, step_ids: list[int], today: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executemany(
            "UPDATE micro_steps SET status = 'scheduled', scheduled_date = ? WHERE id = ? AND tg_id = ?",
            [(today, sid, tg_id) for sid in step_ids],
        )
        await db.commit()


async def complete_step(step_id: int):
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE micro_steps SET status = 'done', completed_at = ? WHERE id = ?",
            (now, step_id),
        )
        await db.commit()


async def skip_step(step_id: int, tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE micro_steps SET status = 'pool', scheduled_date = NULL WHERE id = ? AND tg_id = ?",
            (step_id, tg_id),
        )
        await db.commit()


async def delete_step(step_id: int, tg_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM micro_steps WHERE id = ? AND tg_id = ?", (step_id, tg_id)
        )
        await db.commit()


async def get_stats(tg_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM micro_steps WHERE tg_id = ? AND status = 'done'",
            (tg_id,),
        )
        total_done = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM micro_steps WHERE tg_id = ? AND status = 'pool'",
            (tg_id,),
        )
        in_pool = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM micro_steps WHERE tg_id = ? AND status = 'done' AND date(completed_at) = date('now')",
            (tg_id,),
        )
        today_done = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM micro_steps WHERE tg_id = ? AND status = 'done' AND completed_at >= datetime('now', '-7 days')",
            (tg_id,),
        )
        week_done = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT DISTINCT date(completed_at) as d FROM micro_steps WHERE tg_id = ? AND status = 'done' AND completed_at IS NOT NULL ORDER BY d DESC LIMIT 1",
            (tg_id,),
        )
        row = await cursor.fetchone()
        last_active = row[0] if row else None

    return {
        "total_done": total_done,
        "in_pool": in_pool,
        "today_done": today_done,
        "week_done": week_done,
        "last_active": last_active,
    }


async def get_steps_count(tg_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM micro_steps WHERE tg_id = ? AND status IN ('pool', 'scheduled')",
            (tg_id,),
        )
        return (await cursor.fetchone())[0]


async def reset_unscheduled(tg_id: int, today: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE micro_steps SET status = 'pool', scheduled_date = NULL WHERE tg_id = ? AND status = 'scheduled' AND scheduled_date < ?",
            (tg_id, today),
        )
        await db.commit()
