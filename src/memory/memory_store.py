"""
Memory Store — Hermes 长期记忆系统
==================================
基于 SQLite 的持久化记忆存储，支持：
  1. 对话摘要记忆 — 记住之前聊过什么
  2. 任务模式记忆 — 记住修复过什么Bug、改过什么代码
  3. 用户偏好记忆 — 记住用户喜欢的风格、常用项目
  4. 语义检索 — 用 LLM 匹配相似记忆

自动清理：
  - 30天以上的记忆自动归档
  - 最近100条活跃记忆保留
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.memory")


class MemoryStore:
    def __init__(self, db_path: str = "data/memory/hermes.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = None

    async def initialize(self):
        import aiosqlite
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'default',
                type TEXT NOT NULL,
                key TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                importance INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_type_key
            ON memories(type, key)
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_user
            ON memories(user_id, created_at)
        """)
        await self._db.commit()
        logger.info(f"Memory store initialized: {self.db_path}")

    async def remember(self, type_: str, key: str, content: str,
                       user_id: str = "default", importance: int = 1,
                       metadata: dict = None):
        """Store a memory"""
        if not self._db:
            return
        await self._db.execute(
            """INSERT INTO memories (user_id, type, key, content, metadata, importance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, type_, key, content[:2000],
             json.dumps(metadata or {}, ensure_ascii=False), importance),
        )
        await self._db.commit()
        logger.debug(f"Remembered: {type_}/{key}")

    async def recall(self, type_: str, key: str = "",
                     user_id: str = "default") -> Optional[dict]:
        """Recall a specific memory"""
        if not self._db:
            return None
        if key:
            cursor = await self._db.execute(
                """SELECT * FROM memories
                   WHERE user_id=? AND type=? AND key=?
                   ORDER BY created_at DESC LIMIT 1""",
                (user_id, type_, key),
            )
        else:
            cursor = await self._db.execute(
                """SELECT * FROM memories
                   WHERE user_id=? AND type=?
                   ORDER BY importance DESC, created_at DESC LIMIT 5""",
                (user_id, type_),
            )
        row = await cursor.fetchone()
        if row:
            await self._db.execute(
                "UPDATE memories SET accessed_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), row["id"]),
            )
            await self._db.commit()
            return dict(row)
        return None

    async def search(self, query: str, type_: str = "",
                     user_id: str = "default", top_k: int = 5,
                     llm_client=None) -> list[dict]:
        """Search memories by semantic similarity (LLM) or keyword fallback"""
        if not self._db:
            return []

        cursor = await self._db.execute(
            """SELECT * FROM memories
               WHERE user_id=?
               ORDER BY importance DESC, created_at DESC
               LIMIT 50""",
            (user_id,),
        )
        all_memories = [dict(r) for r in await cursor.fetchall()]

        if not all_memories:
            return []

        if llm_client and len(all_memories) > 1:
            return await self._llm_search(query, all_memories, top_k, llm_client)

        return self._keyword_search(query, all_memories, top_k)

    async def _llm_search(self, query: str, memories: list[dict],
                          top_k: int, llm_client) -> list[dict]:
        """LLM-based semantic memory search"""
        texts = "\n".join(
            f"[{i}] ({m['type']}) {m['content'][:100]}"
            for i, m in enumerate(memories)
        )
        prompt = (
            f"用户当前问题: {query}\n\n"
            f"历史记忆:\n{texts}\n\n"
            "请找出最相关的记忆序号，返回JSON数组如[0,2,5]，最多返回"
            f"{top_k}个。如果不相关返回[]"
        )
        try:
            result = await llm_client.chat_json(prompt, "检索相关记忆")
            indices = result if isinstance(result, list) else []
            return [memories[i] for i in indices if isinstance(i, int) and 0 <= i < len(memories)]
        except Exception:
            return self._keyword_search(query, memories, top_k)

    def _keyword_search(self, query: str, memories: list[dict],
                        top_k: int) -> list[dict]:
        words = set(query.lower().split())
        scored = []
        for m in memories:
            score = sum(1 for w in words if w in m["content"].lower())
            score += m.get("importance", 0) * 0.5
            if score > 0:
                scored.append((score, m))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:top_k]]

    async def forget_old(self, days: int = 30):
        """Clean up old memories"""
        if not self._db:
            return
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        await self._db.execute(
            "DELETE FROM memories WHERE created_at < ? AND importance < 3",
            (cutoff,),
        )
        await self._db.commit()

    async def get_stats(self) -> dict:
        if not self._db:
            return {"total": 0}
        cursor = await self._db.execute("SELECT type, COUNT(*) as cnt FROM memories GROUP BY type")
        rows = await cursor.fetchall()
        return {
            "total": sum(r["cnt"] for r in rows),
            "by_type": {r["type"]: r["cnt"] for r in rows},
        }
