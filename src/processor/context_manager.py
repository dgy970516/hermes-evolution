"""
Context Manager — 按用户隔离的多轮会话管理
===========================================
特性：
  - 按 user_id 隔离（多人不会混乱）
  - SQLite 持久化（重启不丢失）
  - 超过24小时自动清理
  - 每用户最多20轮对话窗口
"""
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

logger = logging.getLogger("hermes.context")


@dataclass
class ConversationTurn:
    role: str
    content: str
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()


@dataclass
class SessionContext:
    user_id: str = ""
    turns: list[ConversationTurn] = dataclass_field(default_factory=list)
    window_size: int = 20
    last_active: str = ""

    def __post_init__(self):
        if not self.last_active:
            self.last_active = datetime.utcnow().isoformat()

    def add_turn(self, role: str, content: str):
        self.turns.append(ConversationTurn(role=role, content=content))
        self.last_active = datetime.utcnow().isoformat()
        if len(self.turns) > self.window_size:
            self.turns.pop(0)

    def get_recent(self, n: int = 5) -> list[ConversationTurn]:
        return self.turns[-n:]

    def to_system_prompt(self) -> str:
        if not self.turns:
            return ""
        recent = self.get_recent(5)
        parts = ["最近对话:"]
        for t in recent[-3:]:
            prefix = "你" if t.role == "user" else "Hermes"
            parts.append(f"  [{prefix}]: {t.content[:200]}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "last_active": self.last_active,
            "turns": [{"role": t.role, "content": t.content, "timestamp": t.timestamp} for t in self.turns],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SessionContext":
        session = cls(user_id=d.get("user_id", ""), last_active=d.get("last_active", ""))
        for t in d.get("turns", []):
            session.turns.append(ConversationTurn(
                role=t.get("role", ""),
                content=t.get("content", ""),
                timestamp=t.get("timestamp", ""),
            ))
        return session


class ContextManager:
    def __init__(self, db_path: str = "data/context/sessions.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = None
        self._cache: dict[str, SessionContext] = {}
        self._max_sessions = 100
        self._session_ttl_hours = 24

    async def initialize(self):
        """Initialize SQLite and load sessions"""
        import aiosqlite
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                user_id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                last_active TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        await self._cleanup_old_sessions()
        await self._load_active_sessions()
        logger.info(f"Context manager ready: {self._get_stats()}")

    async def _cleanup_old_sessions(self):
        """Remove sessions older than ttl"""
        cutoff = (datetime.utcnow() - timedelta(hours=self._session_ttl_hours)).isoformat()
        await self._db.execute("DELETE FROM sessions WHERE last_active < ?", (cutoff,))
        await self._db.commit()

    async def _load_active_sessions(self):
        """Load recent sessions into memory cache"""
        cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        cursor = await self._db.execute(
            "SELECT * FROM sessions WHERE last_active > ? ORDER BY last_active DESC LIMIT ?",
            (cutoff, self._max_sessions),
        )
        rows = await cursor.fetchall()
        for row in rows:
            try:
                data = json.loads(row["data"])
                session = SessionContext.from_dict(data)
                self._cache[session.user_id] = session
            except Exception:
                continue

    def _get_stats(self) -> str:
        return f"{len(self._cache)} cached sessions, {self._session_ttl_hours}h TTL"

    def get_or_create_session(self, user_id: str) -> SessionContext:
        if user_id not in self._cache:
            self._cache[user_id] = SessionContext(user_id=user_id)
            if len(self._cache) > self._max_sessions:
                self._cache.pop(next(iter(self._cache)))
        return self._cache[user_id]

    def add_turn(self, user_id: str, role: str, content: str):
        session = self.get_or_create_session(user_id)
        session.add_turn(role, content)

    async def persist_session(self, user_id: str):
        """Save session to SQLite"""
        if not self._db:
            return
        session = self._cache.get(user_id)
        if not session:
            return
        data = json.dumps(session.to_dict(), ensure_ascii=False)
        await self._db.execute(
            """INSERT OR REPLACE INTO sessions (user_id, data, last_active)
               VALUES (?, ?, ?)""",
            (user_id, data, session.last_active),
        )
        await self._db.commit()

    async def persist_all(self):
        """Save all sessions (called on shutdown)"""
        if not self._db:
            return
        for user_id in list(self._cache.keys()):
            await self.persist_session(user_id)
        logger.info(f"Persisted {len(self._cache)} sessions")

    async def close(self):
        await self.persist_all()
        if self._db:
            await self._db.close()
