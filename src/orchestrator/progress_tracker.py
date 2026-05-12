import asyncio
import logging
from collections.abc import Callable

from src.message_bus.queue import Task

logger = logging.getLogger("hermes.progress")


class ProgressTracker:
    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, task_id: str, callback: Callable[[int, str], None]):
        self._subscribers.setdefault(task_id, []).append(callback)

    async def update(self, task: Task, progress: int, status: str = ""):
        task.progress = progress
        if status:
            logger.info(f"Task {task.task_id}: {progress}% - {status}")

        for cb in self._subscribers.get(task.task_id, []):
            if asyncio.iscoroutinefunction(cb):
                await cb(progress, status)
            else:
                cb(progress, status)
