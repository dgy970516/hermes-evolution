import logging
import re

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.install")


class InstallSkill(Skill):
    name = "install_package"
    description = "安装 Python 依赖包"
    intents = []
    triggers = ["安装"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        return "安装" in ctx.text[:10]

    async def execute(self, ctx: SkillContext) -> None:
        pkg = re.sub(r"^安装\s*", "", ctx.text).strip()
        if not pkg:
            yield "请指定要安装的包名，例如：安装 pandas"
            return

        upgrader = ctx.hermes.upgrader
        results = await upgrader.ensure_dependencies([pkg])
        for r in results:
            icon = "✅" if r.get("success") else ("ℹ️" if r.get("action") == "skipped" else "❌")
            yield f"{icon} {r['package']}: {r.get('reason', r['action'])}"
