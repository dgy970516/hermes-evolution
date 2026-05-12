import logging

from src.message_bus.queue import Task
from src.processor.project_matcher import ProjectMatcher
from src.scanner.project_scanner import ProjectInfo

logger = logging.getLogger("hermes.planner")

# Intents that don't need a project directory
NO_PROJECT_INTENTS = {
    "chat", "open_ide", "open_file", "run_command",
    "db_query", "db_desc", "db_export",
}


class TaskPlanner:
    def __init__(self, project_matcher: ProjectMatcher | None = None, tool_provisioner=None):
        self.project_matcher = project_matcher
        self.tool_provisioner = tool_provisioner

    async def plan(self, instruction: str, intent: str, params: dict, user_id: str) -> tuple[Task, str]:
        task = Task(
            user_id=user_id,
            instruction=instruction,
            intent=intent,
            params=params,
        )

        status_parts = []

        # ── Route: 不需要项目的操作 ──
        if intent in ("db_query", "db_desc"):
            task.engine = "db"
            task.workspace = ""
            task.params["db_name"] = params.get("db_name", "default")
            status_parts.append(f"🗄️  数据库操作: {params.get('db_name', 'default')}")
            status_parts.append(f"🔧 引擎: {task.engine}")
            return task, " | ".join(status_parts)

        if intent in ("open_ide", "open_file", "run_command"):
            task.engine = "system"
            task.workspace = ""
            if intent == "open_ide":
                task.params["ide_name"] = params.get("ide_name", "")
                status_parts.append(f"🖥️  IDE操作")
            elif intent == "open_file":
                task.params["file_path"] = params.get("file_path", "")
                status_parts.append(f"📄 文件操作")
            else:
                status_parts.append(f"⚙️  系统命令")
            status_parts.append(f"🔧 引擎: system")
            return task, " | ".join(status_parts)

        # ── Step 1: 自动匹配项目 ──
        project, match_reason = await self._resolve_project(instruction, params)
        if project:
            task.workspace = project.path
            task.params["project_name"] = project.name
            task.params["project_language"] = project.language
            logger.info(f"Auto-matched project: {project.name} ({project.path})")
            status_parts.append(f"📁 项目: {project.name}")
        else:
            task.workspace = f"./data/workspaces/{task.task_id}"
            task.params["project_name"] = "unknown"
            status_parts.append(f"⚠️  未匹配到项目 (将在临时目录执行)")
            logger.warning(f"No project matched: {match_reason}")

        # ── Step 2: 选择执行引擎 ──
        task.engine = self._select_engine(intent, project)
        status_parts.append(f"🔧 引擎: {task.engine}")

        # ── Step 3: 工具自供应检查 ──
        if self.tool_provisioner:
            tools_needed = await self.tool_provisioner.plan_for_task(task)
            if tools_needed:
                names = [t.get("name", t.get("id", "?")) for t in tools_needed]
                status_parts.append(f"📦 待安装: {', '.join(names)}")

        logger.info(
            f"Task {task.task_id}: intent={intent}, "
            f"engine={task.engine}, "
            f"project={task.params.get('project_name', '?')}"
        )

        return task, " | ".join(status_parts)

    async def _resolve_project(self, instruction: str, params: dict) -> tuple[ProjectInfo | None, str]:
        explicit_path = params.get("project_path", "")
        if explicit_path and self.project_matcher:
            for p in self.project_matcher.scanner.get_all_projects():
                if p.path == explicit_path:
                    return p, ""

        if self.project_matcher:
            return await self.project_matcher.match(instruction)

        return None, "project_matcher 未初始化"

    def _select_engine(self, intent: str, project: ProjectInfo | None) -> str:
        engine_map = {
            "code_generation": "opencode",
            "code_modification": "opencode",
            "code_review": "claude_code",
            "bug_fix": "opencode",
            "explain": "claude_code",
            "test_write": "opencode",
            "refactor": "opencode",
        }
        return engine_map.get(intent, "opencode")
