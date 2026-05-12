"""
用户自定义技能示例
=================
复制这个文件，修改 name/triggers/execute 即可创建自己的技能。
技能文件放在 custom_skills/ 目录下，Hermes 启动时自动加载。

技能触发方式：
- intents: 匹配意图识别结果
- triggers: 匹配用户消息中的关键词
- can_handle: 自定义判断逻辑
"""

import logging
from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.custom_skills")


class MyCustomSkill(Skill):
    name = "my_custom_skill"           # 技能唯一名称
    description = "我的自定义技能"     # 技能描述
    intents = []                        # 匹配的意图（空则不限制）
    triggers = ["自定义", "custom"]    # 触发关键词

    async def can_handle(self, ctx: SkillContext) -> bool:
        """返回 True 表示这个技能可以处理该请求"""
        return any(t in ctx.text.lower() for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        """执行技能逻辑，用 yield 返回结果片段"""
        yield f"🔧 自定义技能 '{self.name}' 已触发"
        yield f"你说了: {ctx.text}"
        yield f"意图: {ctx.intent}"
        yield "你可以在这里写你的业务逻辑..."
