import logging

from src.skills.base import Skill, SkillContext
from src.skills.generator import SkillGenerator

logger = logging.getLogger("hermes.skills.chat")


class ChatSkill(Skill):
    name = "chat"
    description = "兜底技能：对话、自动创建工具"
    intents = ["chat"]
    triggers = ["你好", "嗨", "hello", "hi"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        return True

    def _detect_work_dir(self, text: str) -> str:
        import re
        from pathlib import Path
        m = re.search(r'([A-Za-z]:\\[^\s,，。]*)', text)
        if m:
            p = Path(m.group(1))
            if p.exists():
                return str(p)
        root = Path("D:\\project")
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and child.name.lower() in text.lower():
                    return str(child)
        return "D:\\project"

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        text_lower = ctx.text.lower()

        # Help
        if any(kw in text_lower for kw in ["帮助", "help", "能做什么", "怎么用", "功能"]):
            yield ("🤖 Hermes 编程助手\n\n"
                   "💻 编程: 给 zsadmin 加个接口\n"
                   "🗄️  数据库: 查一下 users 表\n"
                   "🖥️  IDE: 用 idea 打开 agent\n"
                   "📸 截图: 截图我的桌面\n"
                   "📦 安装: 安装 pandas\n"
                   "🔄 修复: 报错了，修复一下\n\n"
                   "💡 新技能自动生成:\n"
                   "  帮我整理一份 Excel 表格\n"
                   "  搜索一下 Python 教程\n"
                   "  生成一个 Word 文档\n"
                   "  汇总项目代码量")
            return

        if not hermes.llm_client:
            yield "🤖 Hermes 已就绪。"
            return

        # ── 检查是否有匹配的技能 ──
        has_skill = hermes.skill_registry.has_skill_for(ctx.text)

        # ── 无匹配技能 → 自动生成 ──
        if not has_skill and hermes.skill_generator:
            yield "🤔 没有找到现成的技能，正在为你自动创建..."

            skill_name = await hermes.skill_generator.generate_and_register(
                ctx.text,
                registry=hermes.skill_registry,
            )

            if skill_name:
                yield f"✅ 已创建新技能: {skill_name}"
                # 重新找技能执行
                new_skill = hermes.skill_registry.get(skill_name)
                if new_skill:
                    async for chunk in new_skill.execute(ctx):
                        yield chunk
                    return
                yield "请再说一遍，新技能已就绪。"
                return
            else:
                yield "⚠️ 技能自动生成失败，请描述得更具体一些。"
                # 降级到普通对话
                prompt = (
                    "你叫 Hermes。用户的需求无法直接处理。"
                    "请解释需要更具体的信息，并给出可执行的建议。"
                )
                answer = await hermes.llm_client.chat(prompt, ctx.text)
                yield answer.strip()[:400]
                return

        # ── 迭代执行（查信息类任务） ──
        needs_iteration = any(kw in text_lower for kw in [
            "提交", "git", "代码", "检查", "看看", "为什么",
            "找一下", "查找", "搜索", "分析", "对比",
        ])
        if needs_iteration and hermes.iterative_executor:
            work_dir = self._detect_work_dir(ctx.text)
            async for chunk in hermes.iterative_executor.execute(
                ctx.text, work_dir=work_dir,
            ):
                yield chunk
            if hermes.memory:
                await hermes.memory.remember(
                    type_="task", key=f"exec_{abs(hash(ctx.text)) % 10000}",
                    content=f"需求: {ctx.text[:200]}",
                    user_id=ctx.user_id, importance=2,
                )
            return

        # ── 普通对话 ──
        context_part = ""
        if ctx.context_str:
            context_part = f"\n对话历史：\n{ctx.context_str[:300]}\n"

        prompt = (
            "你叫 Hermes，一个 AI 编程信使系统。\n"
            "你可以做：编程、查库、截图、启动IDE、安装包。\n"
            "需要具体操作时引导用户说清楚。\n"
            f"{context_part}"
        )
        try:
            answer = await hermes.llm_client.chat(prompt, ctx.text)
            yield answer.strip()[:500]
        except Exception:
            yield "🤖 请再说一遍？"
