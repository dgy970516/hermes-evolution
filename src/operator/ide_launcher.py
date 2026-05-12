import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which

logger = logging.getLogger("hermes.operator.ide")


@dataclass
class IDEInfo:
    name: str
    command: str
    display_name: str
    windows_paths: list[str] = field(default_factory=list)

    def is_installed(self) -> bool:
        if which(self.command):
            return True
        for p in self.windows_paths:
            resolved = p.replace("{USERPROFILE}", os.environ.get("USERPROFILE", ""))
            if Path(resolved).exists():
                return True
        return False

    def resolve_command(self) -> str:
        if which(self.command):
            return self.command
        for p in self.windows_paths:
            resolved = p.replace("{USERPROFILE}", os.environ.get("USERPROFILE", ""))
            if Path(resolved).exists():
                return resolved
        return self.command


def _detect_installed_ides() -> list[IDEInfo]:
    userprofile = os.environ.get("USERPROFILE", "C:\\Users\\Default")

    candidates = [
        IDEInfo(name="intellij", command="idea", display_name="IntelliJ IDEA", windows_paths=[
            "C:\\Program Files\\JetBrains\\IntelliJ IDEA\\bin\\idea64.exe",
            "C:\\Program Files\\JetBrains\\IntelliJ IDEA Community Edition\\bin\\idea64.exe",
        ]),
        IDEInfo(name="vscode", command="code", display_name="VS Code", windows_paths=[
            "C:\\Program Files\\Microsoft VS Code\\Code.exe",
            f"{userprofile}\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe",
        ]),
        IDEInfo(name="pycharm", command="pycharm", display_name="PyCharm", windows_paths=[
            "C:\\Program Files\\JetBrains\\PyCharm\\bin\\pycharm64.exe",
            "C:\\Program Files\\JetBrains\\PyCharm Community Edition\\bin\\pycharm64.exe",
        ]),
        IDEInfo(name="webstorm", command="webstorm", display_name="WebStorm", windows_paths=[
            "C:\\Program Files\\JetBrains\\WebStorm\\bin\\webstorm64.exe",
        ]),
        IDEInfo(name="goland", command="goland", display_name="GoLand", windows_paths=[
            "C:\\Program Files\\JetBrains\\GoLand\\bin\\goland64.exe",
        ]),
        IDEInfo(name="clion", command="clion", display_name="CLion", windows_paths=[
            "C:\\Program Files\\JetBrains\\CLion\\bin\\clion64.exe",
        ]),
    ]

    return [ide for ide in candidates if ide.is_installed()]


class IDELauncher:
    def __init__(self):
        self._installed = _detect_installed_ides()
        logger.info(f"Detected IDEs: {[ide.name for ide in self._installed]}")

    async def open_project(self, project_path: str, ide_name: str | None = None) -> dict:
        path = Path(project_path)
        if not path.is_dir():
            return {"success": False, "message": f"项目目录不存在: {project_path}"}

        if ide_name:
            target = next((ide for ide in self._installed if ide.name == ide_name.lower()), None)
        else:
            target = self._installed[0] if self._installed else None

        if not target:
            names = [ide.name for ide in self._installed]
            return {"success": False, "message": f"未找到IDE或指定的IDE。已安装: {names}"}

        cmd = target.resolve_command()
        logger.info(f"Opening {project_path} with {target.name} ({cmd})")

        try:
            process = await asyncio.create_subprocess_exec(
                cmd, str(path.resolve()),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.sleep(2)

            if process.returncode is None:
                return {
                    "success": True,
                    "message": f"已用 {target.display_name} 打开项目: {project_path}",
                    "ide": target.name,
                }
            return {"success": False, "message": f"IDE 启动失败，返回码: {process.returncode}"}

        except FileNotFoundError:
            return {"success": False, "message": f"命令不存在: {cmd}，请确认IDE已安装并加入PATH"}
        except Exception as e:
            return {"success": False, "message": f"启动IDE异常: {e}"}

    def list_installed(self) -> list[dict]:
        return [
            {"name": ide.name, "display_name": ide.display_name, "command": ide.command}
            for ide in self._installed
        ]
