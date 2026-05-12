"""
Evolution Recorder — 自我进化核心
=================================
记录每次任务执行的全流程，供后续检索和学习。

记录内容：
  - 用户原始需求
  - 匹配的项目
  - 执行模式（hermes 自主 / opencode）
  - 修改的文件
  - 执行结果
  - 耗时
  - 是否成功

检索方式：
  - LLM 语义匹配（零依赖，准确度高）
  - 关键词快速匹配（兜底）
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.evolution.recorder")


class EvolutionRecord:
    def __init__(self, task_id: str = "", user_text: str = "", project: str = "",
                 intent: str = "", mode: str = "", success: bool = True,
                 files_changed: list[str] = None, duration: float = 0,
                 summary: str = "", error: str = ""):
        self.task_id = task_id
        self.user_text = user_text
        self.project = project
        self.intent = intent
        self.mode = mode
        self.success = success
        self.files_changed = files_changed or []
        self.duration = duration
        self.summary = summary
        self.error = error
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "user_text": self.user_text[:500],
            "project": self.project,
            "intent": self.intent,
            "mode": self.mode,
            "success": self.success,
            "files_changed": self.files_changed,
            "duration": round(self.duration, 2),
            "summary": self.summary[:500],
            "error": self.error[:200] if self.error else "",
            "timestamp": self.timestamp,
        }

    def to_search_text(self) -> str:
        """Combined text for similarity search"""
        parts = [
            f"需求: {self.user_text}",
            f"项目: {self.project}",
            f"意图: {self.intent}",
            f"摘要: {self.summary}",
            f"结果: {'成功' if self.success else '失败'}",
        ]
        return "\n".join(parts)


class EvolutionRecorder:
    def __init__(self, data_dir: str = "data/evolution"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self.data_dir / "records.jsonl"
        self._records: list[EvolutionRecord] = []
        self._load()

    def _load(self):
        if self._records_file.exists():
            with open(self._records_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            d = json.loads(line)
                            r = EvolutionRecord(**{k: v for k, v in d.items() if k != "timestamp"})
                            r.timestamp = d.get("timestamp", "")
                            self._records.append(r)
                        except Exception:
                            continue
        logger.info(f"  📚 Loaded {len(self._records)} evolution records")

    async def record(self, record: EvolutionRecord):
        """Record a task execution"""
        self._records.append(record)
        with open(self._records_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        logger.info(f"  📝 Recorded: {record.intent} @ {record.project} ({'✅' if record.success else '❌'})")

    async def search_similar(self, user_text: str, project: str = "",
                             intent: str = "", top_k: int = 3,
                             llm_client=None) -> list[dict]:
        """Find similar past tasks using LLM semantic matching (no vector DB needed)"""
        if not self._records:
            return []

        # If LLM available, use semantic matching
        if llm_client:
            return await self._llm_search(user_text, project, intent, top_k, llm_client)

        # Fallback: keyword matching
        return self._keyword_search(user_text, project, intent, top_k)

    async def _llm_search(self, user_text: str, project: str, intent: str,
                          top_k: int, llm_client) -> list[dict]:
        """Use LLM to find semantically similar past tasks"""
        # Get recent records that match project
        candidates = self._records[-50:]  # Last 50 for efficiency
        if project:
            candidates = [r for r in candidates if project.lower() in r.project.lower()]

        if not candidates:
            return []

        # Let LLM find the most relevant ones
        search_prompt = """你是一个任务匹配专家。用户有一个新需求，请从历史任务列表中找到最相似的任务。

当前需求：{current_text}
当前项目：{current_project}
当前意图：{current_intent}

历史任务：
{history}

请从历史任务中选出最多 {top_k} 个最相似的任务，返回它们的序号（从0开始）。
只返回 JSON 数组，如 [0, 2, 5]
如果没有任何相似，返回 []
"""

        history_text = "\n".join(
            f"[{i}] 需求: {r.user_text[:100]} | 项目: {r.project} | 摘要: {r.summary[:100]} | {'✅成功' if r.success else '❌失败'}"
            for i, r in enumerate(candidates)
        )

        prompt = search_prompt.format(
            current_text=user_text[:200],
            current_project=project or "?",
            current_intent=intent or "?",
            history=history_text,
            top_k=top_k,
        )

        try:
            result = await llm_client.chat_json(prompt, f"查找与「{user_text[:50]}」相似的历史任务")
            indices = result if isinstance(result, list) else []
            matches = []
            for idx in indices:
                if isinstance(idx, (int, float)) and 0 <= int(idx) < len(candidates):
                    r = candidates[int(idx)]
                    matches.append({
                        "score": 1.0,
                        "record": r.to_dict(),
                        "search_text": r.to_search_text(),
                    })
            return matches[:top_k]
        except Exception as e:
            logger.warning(f"LLM search failed: {e}")
            return []

    def _keyword_search(self, user_text: str, project: str, intent: str,
                        top_k: int) -> list[dict]:
        """Fallback: keyword-based similarity"""
        words = set(user_text.lower().split())
        scored = []
        for r in self._records[-100:]:  # Last 100
            score = 0
            r_text = (r.user_text + " " + r.project + " " + r.summary).lower()
            for w in words:
                if w in r_text:
                    score += 1
            if project and project.lower() in r.project.lower():
                score += 3
            if score > 0:
                scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"score": s / max(len(words), 1), "record": r.to_dict(), "search_text": r.to_search_text()}
            for s, r in scored[:top_k]
        ]

    def get_stats(self) -> dict:
        """Get evolution statistics"""
        total = len(self._records)
        if total == 0:
            return {"total": 0}
        success = sum(1 for r in self._records if r.success)
        by_project = {}
        by_intent = {}
        for r in self._records:
            by_project[r.project] = by_project.get(r.project, 0) + 1
            by_intent[r.intent] = by_intent.get(r.intent, 0) + 1
        return {
            "total": total,
            "success_rate": round(success / total * 100, 1),
            "success": success,
            "failed": total - success,
            "projects": len(by_project),
            "intents": by_intent,
        }
