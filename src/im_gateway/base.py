from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Coroutine


@dataclass
class Message:
    user_id: str
    content: str
    im_type: str
    raw: dict | None = None


@dataclass
class Card:
    title: str
    content: str
    buttons: list[dict] | None = None


class IMAdapter(ABC):
    @abstractmethod
    async def send_message(self, user_id: str, content: str): ...

    @abstractmethod
    async def send_card(self, user_id: str, card: Card): ...

    @abstractmethod
    async def on_message(self, handler: Callable[[Message], Coroutine]): ...
