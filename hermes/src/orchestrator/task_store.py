from src.message_bus.queue import Task


class TaskStore:
    def __init__(self, db_path: str = "./data/sessions/tasks.db"):
        self.db_path = db_path

    async def save(self, task: Task):
        # TODO: Persist to database
        pass

    async def load(self, task_id: str) -> Task | None:
        # TODO: Load from database
        return None

    async def list_by_user(self, user_id: str, limit: int = 20) -> list[Task]:
        # TODO: Query by user
        return []
