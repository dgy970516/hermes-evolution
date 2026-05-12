import asyncio
import logging
import os
from enum import Enum
from pathlib import Path

logger = logging.getLogger("hermes.evolution.provisioner")


class ToolType(Enum):
    MCP_SERVER = "mcp_server"
    SKILL = "skill"
    NPM_PACKAGE = "npm_package"
    PIP_PACKAGE = "pip_package"
    CLI_TOOL = "cli_tool"


class ToolRegistry:
    def __init__(self):
        userprofile = os.environ.get("USERPROFILE", str(Path.home()))
        self._known_tools: dict[str, dict] = {
            "code-review-graph": {
                "type": ToolType.MCP_SERVER,
                "name": "code-review-graph",
                "description": "Code review with knowledge graph",
                "install_command": "npm install -g @anthropic/mcp-server-code-review-graph",
            },
            "backend-code-review": {
                "type": ToolType.SKILL,
                "name": "backend-code-review",
                "description": "Backend code review skill",
                "source": str(Path(userprofile) / ".claude" / "skills" / "backend-code-review" / "SKILL.md"),
            },
            "graphify": {
                "type": ToolType.SKILL,
                "name": "graphify",
                "description": "Knowledge graph generation skill",
                "source": str(Path(userprofile) / ".config" / "opencode" / "skills" / "graphify" / "SKILL.md"),
            },
        }

    def match(self, requirements: dict) -> list[dict]:
        matched = []
        text = str(requirements).lower()

        for tool_id, tool_info in self._known_tools.items():
            desc = tool_info["description"].lower()
            if any(word in text for word in desc.split()):
                matched.append({"id": tool_id, **tool_info})

        return matched


class ToolProvisioner:
    def __init__(self):
        self.registry = ToolRegistry()
        self.installed_tools: dict[str, bool] = {}
        self.installation_log: list[dict] = []

    async def plan_for_task(self, task) -> list[dict]:
        requirements = {
            "instruction": task.instruction,
            "intent": task.intent,
            "params": task.params,
        }
        needed_tools = self.registry.match(requirements)

        to_install = [
            t for t in needed_tools
            if t["id"] not in self.installed_tools
        ]

        return to_install

    async def execute_plan(self, to_install: list[dict], task_id: str):
        for tool in to_install:
            logger.info(f"Installing {tool['name']} ({tool['type'].value})...")

            try:
                await self._install(tool)
                self.installed_tools[tool["id"]] = True
                self.installation_log.append({
                    "tool": tool["name"],
                    "task_id": task_id,
                    "success": True,
                })
                logger.info(f"Installed {tool['name']} successfully")
            except Exception as e:
                logger.error(f"Failed to install {tool['name']}: {e}")

    async def _install(self, tool: dict):
        cmd = tool.get("install_command", "")
        if cmd:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

    def get_installed_tools(self) -> list[str]:
        return [tid for tid, installed in self.installed_tools.items() if installed]
