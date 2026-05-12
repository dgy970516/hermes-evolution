import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("hermes.evolution.knowledge")


class KnowledgeBase:
    def __init__(self, db_path: str = "./data/knowledge"):
        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict] = []

    async def add_entry(self, entry_type: str, content: str, metadata: dict | None = None):
        entry = {
            "id": len(self._entries),
            "type": entry_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
        }
        self._entries.append(entry)
        await self._persist()
        logger.debug(f"Knowledge entry added: type={entry_type}")

    async def search(self, query: str, top_k: int = 5) -> list[dict]:
        # Basic keyword search; TODO: replace with vector search
        query_lower = query.lower()
        scored = []
        for entry in self._entries:
            score = self._keyword_score(entry["content"], query_lower)
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def _keyword_score(self, text: str, query: str) -> float:
        text_lower = text.lower()
        words = query.split()
        matches = sum(1 for w in words if w in text_lower)
        return matches / max(len(words), 1)

    async def _persist(self):
        path = self.db_path / "knowledge.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(self._entries[-1], ensure_ascii=False) + "\n")
