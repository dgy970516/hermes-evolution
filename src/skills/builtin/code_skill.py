import logging

from src.engines.hermes_engine import HermesDirectEngine
from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.code")


class CodeGenerationSkill(Skill):
    name = "code_generation"
    description = "生成、修改代码，审查代码，修复Bug"
    intents = ["code_generation", "code_modification", "code_review", "bug_fix", "test_write", "refactor"]
    triggers = ["写", "生成", "创建", "加个", "实现", "修改", "添加", "修复", "审查", "重构"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        return ctx.intent in self.intents

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes

        # Find project
        project, reason = await hermes.matcher.match(ctx.text)
        if not project:
            yield f"⚠️ 未找到匹配项目: {reason}"
            return

        # Decide mode: Hermes direct vs opencode CLI
        mode = await self._decide_mode(ctx.text, project.language)

        if mode == "hermes":
            async for msg in self._execute_direct(ctx, hermes, project):
                yield msg
        else:
            async for msg in self._execute_opencode(ctx, hermes, project):
                yield msg

    async def _decide_mode(self, text: str, language: str) -> str:
        """Decide whether to use Hermes direct or opencode CLI.
        Hermes direct: simple changes, single file, bug fixes with clear scope
        opencode: complex multi-file refactors, deep code review
        """
        text_lower = text.lower()
        # Keywords that suggest complex tasks needing opencode
        complex_keywords = ["架构", "重构", "refactor", "review", "审查",
                            "大规模", "跨文件", "多文件", "设计模式",
                            "性能优化", "安全", "迁移", "升级"]
        for kw in complex_keywords:
            if kw in text_lower:
                return "opencode"

        # Short text or simple bug fix → Hermes direct
        if len(text) < 100 or "bug" in text_lower or "修复" in text:
            return "hermes"

        return "hermes"  # default: hermes direct

    async def _execute_direct(self, ctx, hermes, project):
        """Hermes directly handles the coding task using its own LLM"""
        yield f"📁 项目: {project.name}"
        yield "🧠 模式: Hermes 自主执行"

        instruction = ctx.text
        if ctx.context_str:
            instruction = f"对话上下文：\n{ctx.context_str}\n\n当前需求：{ctx.text}"

        engine = HermesDirectEngine(
            llm_client=hermes.llm_client,
            evolution_recorder=hermes.evolution_recorder,
        )

        async for action in engine.execute(
            instruction, project.path, project.name,
            intent=ctx.intent, user_id=ctx.user_id,
        ):
            t = action.get("type", "")
            msg = action.get("message", "")
            content = action.get("content", "")
            file = action.get("file", "")

            if t == "info" and msg:
                yield msg

            elif t == "analysis_token":
                # 流式输出 AI 思考
                yield content

            elif t == "analysis":
                yield "📝 正在分析修改方案..."

            elif t == "file_changed":
                yield f"  ✅ 已修改: {file}"

            elif t == "command":
                yield f"  ⚙️ 执行: {content}" if not msg else msg

            elif t == "command_ok":
                out = content[:200] if content else ""
                if out:
                    yield f"  ✅ 输出: {out}"

            elif t == "command_fail":
                out = content[:200] if content else ""
                yield f"  ❌ 命令失败: {msg} {out}"

            elif t == "error":
                yield f"  ❌ {msg}"

    async def _execute_opencode(self, ctx, hermes, project):
        """Fallback: use opencode CLI for complex tasks"""
        yield f"📁 项目: {project.name}"
        yield "🧠 模式: opencode CLI (复杂任务)"

        engine = hermes.engines.get("opencode")
        if not engine:
            yield "❌ opencode 不可用"
            return

        # Load rules
        from src.scanner.rules_loader import load_project_rules
        rules = load_project_rules(project.path)
        if rules:
            yield "📋 已加载项目规则"
            instruction = f"{rules}\n\n用户需求: {ctx.text}"
        else:
            instruction = ctx.text

        yield f"⚙️  正在 {project.path} 中执行..."

        output = []
        async for chunk in hermes._execute_with_stream(engine, instruction, workspace=project.path):
            output.append(chunk)
            if len(output) <= 3:
                yield chunk

        result = "\n".join(output[-10:])
        yield f"\n✅ 完成\n```\n{result[:1000]}\n```"
