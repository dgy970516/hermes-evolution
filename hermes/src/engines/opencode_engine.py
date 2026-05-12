import asyncio
import logging
import sys
from pathlib import Path

from src.engines.base import ExecutionEngine, ExecutionResult
from src.message_bus.queue import Task

logger = logging.getLogger("hermes.opencode")


def _win_quote(arg: str) -> str:
    """Windows-safe quoting: wrap in double quotes, escape embedded double quotes."""
    arg = arg.replace('"', '\\"')
    return f'"{arg}"'


def _build_cmd(project_dir: str, executable: str, instruction: str) -> str:
    """Build a Windows cmd.exe compatible command string."""
    if sys.platform == "win32":
        return f'cd /d "{project_dir}" && {executable} {_win_quote(instruction)}'
    else:
        import shlex
        return f'cd "{project_dir}" && {executable} {shlex.quote(instruction)}'


class OpencodeEngine(ExecutionEngine):
    def __init__(self, executable: str = "opencode", timeout: int = 600):
        self.executable = executable
        self.timeout = timeout
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def execute(self, task: Task) -> ExecutionResult:
        project_dir = Path(task.workspace)
        if not project_dir.exists():
            return ExecutionResult(success=False, error=f"项目目录不存在: {task.workspace}")

        try:
            cmd = _build_cmd(task.workspace, self.executable, task.instruction)
            logger.info(f"Executing in {task.workspace}: opencode ...")

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            self._processes[task.task_id] = process

            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError:
                process.kill()
                return ExecutionResult(success=False, error=f"opencode 执行超时 ({self.timeout}s)")

            output = stdout.decode("utf-8", errors="replace") if stdout else ""

            if process.returncode == 0:
                return ExecutionResult(success=True, output=output)
            return ExecutionResult(success=False, output=output, error=f"Exit code: {process.returncode}")

        except FileNotFoundError:
            return ExecutionResult(success=False, error=f"opencode 未安装或不在 PATH 中: {self.executable}")
        except Exception as e:
            return ExecutionResult(success=False, error=f"执行异常: {e}")
        finally:
            self._processes.pop(task.task_id, None)

    async def execute_with_progress(self, task: Task, progress_callback=None) -> ExecutionResult:
        project_dir = Path(task.workspace)
        if not project_dir.exists():
            return ExecutionResult(success=False, error=f"项目目录不存在: {task.workspace}")

        output_lines = []
        try:
            cmd = _build_cmd(task.workspace, self.executable, task.instruction)

            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            self._processes[task.task_id] = process

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                output_lines.append(text)
                if progress_callback:
                    await progress_callback(text)

            await process.wait()
            output = "\n".join(output_lines)

            if process.returncode == 0:
                return ExecutionResult(success=True, output=output)
            return ExecutionResult(success=False, output=output, error=f"Exit code: {process.returncode}")

        except FileNotFoundError:
            return ExecutionResult(success=False, error="opencode 未安装或不在 PATH 中")
        except Exception as e:
            return ExecutionResult(success=False, error=f"执行异常: {e}")
        finally:
            self._processes.pop(task.task_id, None)

    async def cancel(self, task_id: str):
        process = self._processes.get(task_id)
        if process:
            process.kill()

    @property
    def supported_intents(self) -> list[str]:
        return ["code_generation", "code_modification", "bug_fix", "test_write", "refactor"]
