"""
插件技能示例 — 放在 plugins/ 下自动加载
"""
import logging
from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.plugins.my_plugin")


class HelloPluginSkill(Skill):
    name = "plugin_hello"
    description = "插件示例：回复hello"
    intents = []
    triggers = ["hello plugin", "插件测试"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        text = ctx.text.lower()
        return any(t in text for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        yield f"🔌 插件技能 '{self.name}' 已触发!"
        yield f"这是从 plugins/my_plugin/ 加载的插件"
        yield "你可以在这里写任何业务逻辑"
