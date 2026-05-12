import asyncio
import logging
from collections.abc import Callable

from src.message_bus.queue import Task, TaskStatus

logger = logging.getLogger("hermes.task_queue")


class TaskQueue:
    def __init__(self):
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._tasks: dict[str, Task] = {}
        self._on_complete: list[Callable] = []

    async def enqueue(self, task: Task):
        task.status = TaskStatus.QUEUED
        self._tasks[task.task_id] = task
        await self._queue.put(task)
        logger.info(f"Task {task.task_id} queued")

    async def dequeue(self) -> Task:
        task = await self._queue.get()
        task.status = TaskStatus.RUNNING
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def on_complete(self, callback: Callable):
        self._on_complete.append(callback)

    async def mark_complete(self, task: Task, result: str | None = None):
        task.status = TaskStatus.COMPLETED
        task.result = result
        for cb in self._on_complete:
            await cb(task)

    async def mark_failed(self, task: Task, error: str):
        task.status = TaskStatus.FAILED
        task.error = error
        for cb in self._on_complete:
            await cb(task)
