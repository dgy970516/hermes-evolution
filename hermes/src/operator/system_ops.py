import asyncio
import logging
import os
import sys
from pathlib import Path
from shutil import which

logger = logging.getLogger("hermes.operator.system")


async def _open_with_default_app(path: str):
    """Cross-platform file/folder open"""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        await asyncio.create_subprocess_exec("open", path)
    else:
        await asyncio.create_subprocess_exec("xdg-open", path)


class SystemOperator:
    async def run_command(self, command: str, cwd: str | None = None) -> dict:
        logger.info(f"Running: {command} (cwd={cwd})")
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=120)
            return {
                "success": process.returncode == 0,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
                "returncode": process.returncode,
            }
        except asyncio.TimeoutError:
            return {"success": False, "error": "命令执行超时 (120s)"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def open_file(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            return {"success": False, "message": f"文件不存在: {file_path}"}

        try:
            if which("code"):
                proc = await asyncio.create_subprocess_exec(
                    "code", str(path.resolve()),
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await asyncio.sleep(1)
                return {"success": True, "message": f"已用 VS Code 打开: {file_path}"}
            else:
                await _open_with_default_app(str(path.resolve()))
                return {"success": True, "message": f"已打开: {file_path}"}
        except Exception as e:
            return {"success": False, "message": f"打开文件失败: {e}"}

    async def open_folder(self, folder_path: str) -> dict:
        path = Path(folder_path)
        if not path.is_dir():
            return {"success": False, "message": f"目录不存在: {folder_path}"}

        try:
            await _open_with_default_app(str(path.resolve()))
            return {"success": True, "message": f"已打开: {folder_path}"}
        except Exception as e:
            return {"success": False, "message": f"打开目录失败: {e}"}

    async def check_env(self, tool: str) -> dict:
        found = which(tool)
        return {"tool": tool, "installed": found is not None, "path": found or ""}
