from abc import ABC, abstractmethod

from src.message_bus.queue import Task


class ExecutionResult:
    def __init__(self, success: bool, output: str = "", error: str = ""):
        self.success = success
        self.output = output
        self.error = error


class ExecutionEngine(ABC):
    @abstractmethod
    async def execute(self, task: Task) -> ExecutionResult:
        ...

    @abstractmethod
    async def cancel(self, task_id: str):
        ...

    @property
    @abstractmethod
    def supported_intents(self) -> list[str]:
        ...
