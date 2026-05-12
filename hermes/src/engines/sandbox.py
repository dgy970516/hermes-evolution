import tempfile
from pathlib import Path


class Sandbox:
    def __init__(self, base_dir: str = "./data/workspaces"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, task_id: str) -> Path:
        workspace = self.base_dir / task_id
        workspace.mkdir(parents=True, exist_ok=True)
        return workspace

    def cleanup(self, task_id: str):
        workspace = self.base_dir / task_id
        if workspace.exists():
            import shutil
            shutil.rmtree(workspace)
