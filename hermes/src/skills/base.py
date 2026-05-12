from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class SkillContext:
    text: str
    intent: str
    params: dict
    user_id: str
    hermes: object = None
    context_str: str = ""  # Conversation history context


class Skill(ABC):
    """Base class for all skills"""

    name: str = ""
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)

    @abstractmethod
    async def can_handle(self, ctx: SkillContext) -> bool:
        """Check if this skill should handle the request"""
        ...

    @abstractmethod
    async def execute(self, ctx: SkillContext) -> AsyncIterator[str]:
        """Execute the skill. Yield response chunks."""
        if False:
            yield ""
