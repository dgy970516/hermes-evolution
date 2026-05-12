from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class MessageType(Enum):
    TEXT = "text"
    IMAGE = "image"
    CARD_CALLBACK = "card_callback"
    SYSTEM = "system"


@dataclass
class NormalizedMessage:
    msg_id: str = field(default_factory=lambda: uuid4().hex[:16])
    user_id: str = ""
    content: str = ""
    msg_type: MessageType = MessageType.TEXT
    im_source: str = ""
    raw: dict | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RoutedMessage:
    message: NormalizedMessage
    intent: str = ""
    confidence: float = 0.0
    params: dict = field(default_factory=dict)
    context: dict | None = None
