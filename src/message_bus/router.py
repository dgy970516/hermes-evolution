import asyncio
import logging
from collections.abc import Callable, Coroutine

from src.message_bus.models import NormalizedMessage, RoutedMessage

logger = logging.getLogger("hermes.router")


class MessageRouter:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._queue: asyncio.Queue[NormalizedMessage] = asyncio.Queue()

    def register(self, intent: str, handler: Callable[[RoutedMessage], Coroutine]):
        self._handlers.setdefault(intent, []).append(handler)

    async def route(self, message: NormalizedMessage, routed: RoutedMessage):
        intent = routed.intent
        handlers = self._handlers.get(intent, [])
        if not handlers:
            handlers = self._handlers.get("unknown", [])

        for handler in handlers:
            asyncio.create_task(handler(routed))

    async def start(self):
        logger.info("Message router started")
        while True:
            msg = await self._queue.get()
            # TODO: Process through processor layer
            self._queue.task_done()
