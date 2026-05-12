import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import uuid4


class TaskStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEED_REVIEW = "need_review"


@dataclass
class Task:
    task_id: str = field(default_factory=lambda: uuid4().hex[:16])
    user_id: str = ""
    instruction: str = ""
    intent: str = ""
    params: dict = field(default_factory=dict)
    workspace: str = ""
    engine: str = ""
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    result: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    trace_id: str = field(default_factory=lambda: uuid4().hex)
