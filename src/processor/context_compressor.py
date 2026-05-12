from abc import ABC, abstractmethod

from src.processor.context_manager import ConversationTurn

SUMMARY_SYSTEM_PROMPT = """你是一个对话摘要专家。将以下多轮对话压缩为结构化摘要，保留关键信息。

输出格式：
{
  "summary": "用户的核心需求摘要",
  "completed_steps": ["已完成的步骤列表"],
  "current_state": "当前进度状态",
  "pending_items": ["待办事项列表"]
}
"""


class CompressionStrategy(ABC):
    @abstractmethod
    async def compress(self, turns: list[ConversationTurn], budget: int) -> list[ConversationTurn]:
        ...


class SlidingWindowStrategy(CompressionStrategy):
    def __init__(self, window_size: int = 20):
        self.window_size = window_size

    async def compress(self, turns: list[ConversationTurn], budget: int) -> list[ConversationTurn]:
        return turns[-self.window_size:]


class SummaryCompressionStrategy(CompressionStrategy):
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def compress(self, turns: list[ConversationTurn], budget: int) -> list[ConversationTurn]:
        if len(turns) <= budget:
            return turns

        keep_recent = budget // 2
        to_summarize = turns[:-keep_recent]

        summary = await self._summarize(to_summarize)
        return [ConversationTurn(role="system", content=f"[历史摘要] {summary}")] + turns[-keep_recent:]

    async def _summarize(self, turns: list[ConversationTurn]) -> str:
        if not self.llm_client:
            return f"用户共发送 {len(turns)} 条消息，涉及多次交互。"

        text = "\n".join(f"[{t.role}]: {t.content}" for t in turns)
        try:
            result = await self.llm_client.chat_json(SUMMARY_SYSTEM_PROMPT, text)
            parts = [
                f"需求: {result.get('summary', '')}",
            ]
            completed = result.get("completed_steps", [])
            if completed:
                parts.append(f"已完成: {' → '.join(completed)}")
            pending = result.get("pending_items", [])
            if pending:
                parts.append(f"待办: {' → '.join(pending)}")
            return " | ".join(parts)
        except Exception:
            return f"共 {len(turns)} 条历史消息"


class ContextCompressor:
    def __init__(self, llm_client=None):
        self.strategies = {
            "sliding_window": SlidingWindowStrategy(),
            "summary": SummaryCompressionStrategy(llm_client=llm_client),
        }

    async def compress(self, turns: list[ConversationTurn], budget: int) -> list[ConversationTurn]:
        if len(turns) <= budget:
            return turns
        return await self.strategies["summary"].compress(turns, budget)
