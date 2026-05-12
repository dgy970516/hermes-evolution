"""
Hermes Direct Code Engine
=========================
Hermes uses its own LLM to handle coding tasks directly:
  1. Understand the bug/requirement
  2. Read relevant project files
  3. LLM generates the fix
  4. Apply changes to files
  5. Report results

Advantages over calling opencode CLI:
  - Faster (no subprocess overhead)
  - Has full project context (rules, structure)
  - Self-evolution (each task is a learning opportunity)
  - Can explain changes in natural language
  - Handles simple tasks instantly

Usage:
  Only falls back to opencode/Claude Code for VERY complex tasks
  that need multi-file deep analysis.
"""

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from src.scanner.rules_loader import load_project_rules

logger = logging.getLogger("hermes.engine.direct")

CODE_GEN_PROMPT = """你是一个资深编程专家。用户有一个编程需求，请分析并生成解决方案。

项目信息：
{project_context}

项目规则：
{project_rules}

{similar_tasks}

用户需求：
{user_request}

请分析问题并返回：
1. 问题分析：简要描述问题原因
2. 修改方案：需要修改哪些文件、如何修改
3. 代码修改：具体的代码变更

如果涉及文件修改，请按以下格式返回：

## 修改文件: 相对路径
```语言
修改后的完整文件内容
```

## 执行命令
如果需要在终端执行命令（如 npm install），请列出。
"""


class HermesDirectEngine:
    """Hermes' own code execution engine — no external CLI needed for most tasks"""

    def __init__(self, llm_client=None, evolution_recorder=None):
        self.llm_client = llm_client
        self.evolution = evolution_recorder

    async def execute(self, instruction: str, project_path: str, project_name: str,
                      intent: str = "", user_id: str = ""):
        """Execute a coding task directly using Hermes' LLM.
        Yields action dicts.
        """
        import time
        start_time = time.time()
        files_changed = []
        success = True
        error_msg = ""

        if not self.llm_client:
            yield {"type": "error", "message": "LLM not configured"}
            return

        # Gather context
        project_rules = load_project_rules(project_path)
        project_context = self._gather_project_context(project_path, project_name)

        # ── Evolution: Search similar past tasks ──
        similar_tasks = ""
        if self.evolution:
            similar = await self.evolution.search_similar(
                instruction, project_name, intent,
                top_k=3, llm_client=self.llm_client,
            )
            if similar:
                similar_tasks = "相关的历史任务参考：\n" + "\n---\n".join(
                    f"需求: {s['record']['user_text'][:200]}\n"
                    f"方案摘要: {s['record']['summary'][:200]}"
                    for s in similar
                )
                yield {"type": "info", "message": f"📚 找到 {len(similar)} 条相关历史记录"}

        prompt = CODE_GEN_PROMPT.format(
            project_context=project_context,
            project_rules=project_rules or "无",
            similar_tasks=similar_tasks,
            user_request=instruction,
        )

        yield {"type": "info", "message": "🧠 Hermes 正在分析问题..."}

        # 流式输出 AI 思考过程
        response = ""
        try:
            buffer = ""
            async for token in self.llm_client.chat_stream(prompt, instruction):
                response += token
                buffer += token
                # 每积累一段就推送一次（大约每 50 字符）
                if len(buffer) > 50 and "\n" in buffer:
                    lines = buffer.split("\n")
                    for line in lines[:-1]:
                        if line.strip():
                            yield {"type": "analysis_token", "content": line.strip()}
                    buffer = lines[-1]
            if buffer.strip():
                yield {"type": "analysis_token", "content": buffer.strip()}
        except Exception as e:
            yield {"type": "error", "message": f"LLM 分析失败: {e}"}
            return

        # Parse response for file changes
        changes = self._parse_file_changes(response, project_path)
        commands = self._parse_commands(response)

        # Apply file changes
        if changes:
            yield {"type": "info", "message": f"📝 正在修改 {len(changes)} 个文件..."}
            for change in changes:
                try:
                    filepath = change["path"]
                    filepath.parent.mkdir(parents=True, exist_ok=True)
                    filepath.write_text(change["content"], encoding="utf-8")
                    files_changed.append(str(filepath))
                    yield {"type": "file_changed", "file": str(filepath)}
                    logger.info(f"  📝 Modified: {filepath}")
                except Exception as e:
                    yield {"type": "error", "message": f"写入失败 {change['path']}: {e}"}
                    success = False
                    error_msg = str(e)

        # Record evolution
        if self.evolution:
            from src.evolution.evolution_recorder import EvolutionRecord
            duration = time.time() - start_time
            record = EvolutionRecord(
                user_text=instruction,
                project=project_name,
                intent=intent,
                mode="hermes_direct",
                success=success,
                files_changed=files_changed,
                duration=duration,
                summary=response[:300] if response else "",
                error=error_msg,
            )
            await self.evolution.record(record)

        # Execute commands
        if commands:
            yield {"type": "info", "message": f"⚙️  正在执行 {len(commands)} 个命令..."}
            for cmd in commands:
                yield {"type": "command", "message": f"⚙️ {cmd}", "content": cmd}
                try:
                    proc = await asyncio.create_subprocess_shell(
                        cmd,
                        cwd=project_path,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
                    output = (stdout or b"").decode("utf-8", errors="replace")[:300].strip()
                    err = (stderr or b"").decode("utf-8", errors="replace")[:300].strip()
                    if proc.returncode == 0:
                        yield {"type": "command_ok", "message": f"✅ 命令成功", "content": output or "(无输出)"}
                    else:
                        yield {"type": "command_fail", "message": err or f"Exit: {proc.returncode}", "content": err or "(无错误信息)"}
                except asyncio.TimeoutError:
                    yield {"type": "error", "message": f"命令超时: {cmd}"}

        if not changes and not commands:
            yield {"type": "info", "message": "💡 分析完成。未检测到需要自动修改的内容。"}

    def _gather_project_context(self, project_path: str, project_name: str) -> str:
        root = Path(project_path)
        parts = [f"项目名称: {project_name}"]
        parts.append(f"项目路径: {project_path}")

        # List key directories
        dirs = [d.name for d in root.iterdir() if d.is_dir() and not d.name.startswith(".") and not d.name.startswith("__")]
        if dirs:
            parts.append(f"目录结构: {', '.join(dirs[:20])}")

        # Check package.json, pyproject.toml, pom.xml etc.
        for f in root.iterdir():
            if f.name in ("package.json", "pyproject.toml", "pom.xml", "requirements.txt", "Gemfile"):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")[:2000]
                    parts.append(f"\n{f.name}:\n{content[:500]}")
                except Exception:
                    pass

        return "\n".join(parts)

    def _parse_file_changes(self, response: str, project_path: str) -> list[dict]:
        """Extract file changes from LLM response"""
        import re
        changes = []
        pattern = r"## 修改文件:\s*([^\n]+)\n```(?:\w+)?\n(.*?)```"
        for match in re.finditer(pattern, response, re.DOTALL):
            rel_path = match.group(1).strip()
            content = match.group(2).strip()
            abs_path = Path(project_path) / rel_path
            changes.append({"path": abs_path, "content": content})
        return changes

    def _parse_commands(self, response: str) -> list[str]:
        """Extract shell commands from LLM response"""
        import re
        commands = []
        in_section = False
        for line in response.split("\n"):
            if "## 执行命令" in line or "## 命令" in line:
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.strip().startswith("`"):
                cmd = line.strip().strip("`")
                if cmd:
                    commands.append(cmd)
        return commands
