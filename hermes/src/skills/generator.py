"""
Skill Generator — AI 自动生成技能工具
======================================
当用户需求没有匹配的已有技能时，由 LLM 分析需求并自动生成技能文件。

流程：
  1. 用户说"整理Excel表格"
  2. 无匹配技能 → 调用 SkillGenerator
  3. LLM 分析需要什么能力，生成 Python 技能代码
  4. 写入 custom_skills/ 目录
  5. 热加载到技能系统
  6. 立即执行

生成的技能文件结构：
  custom_skills/
    _generated_excel_20260512.py   ← 自动命名
"""
import logging
import textwrap
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("hermes.skills.generator")

GENERATOR_PROMPT = """你是一个 Python 技能生成专家。用户有一个需求，你需要创建一个对应的 Hermes 技能。

Hermes 技能是一个 Python 类，继承 Skill 基类，格式如下：

```python
import logging
import asyncio
from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.generated_skills.XXXX")

class XXXXSkill(Skill):
    name = "XXXX"
    description = "..."
    intents = []
    triggers = ["关键词1", "关键词2"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        return any(t in ctx.text.lower() for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        
        yield "正在执行..."
        
        try:
            # 你的业务逻辑
            # 通过 hermes.system_ops.run_command() 执行 shell 命令
            # 通过 hermes.llm_client.chat() 调用 LLM
            # 通过 hermes.db_client.execute_query() 查数据库
            # 通过 hermes.feishu_adapter.send_message() 发消息
            # 通过 hermes.feishu_adapter.send_image() 发图片
            # 通过 hermes.feishu_adapter.send_file() 发文件
            # 通过 hermes.upgrader.ensure_dependencies() 装依赖
            
            yield "✅ 完成"
            
        except Exception as e:
            yield f"❌ 错误: {e}"
```

【重要原则】
1. 代码必须完整可用，不要省略号
2. 优先使用 shell 命令（通过 hermes.system_ops.run_command）
3. 如果依赖第三方包，先自动安装：await hermes.upgrader.ensure_dependencies(["包名"])
4. 生成的技能名 = 需求的关键英文词
5. triggers 写中文关键词
6. 错误处理要完整
7. 给用户清晰的进度反馈

用户需求: {user_request}

请只返回 Python 代码，不要解释。
"""


class SkillGenerator:
    def __init__(self, llm_client=None, skill_registry=None,
                 output_dir: str = "custom_skills"):
        self.llm_client = llm_client
        self.registry = skill_registry
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_and_register(self, user_text: str,
                                     registry=None) -> str | None:
        """Generate a skill from user request, save and register it.
        Returns the skill name if successful."""
        if not self.llm_client:
            return None

        target_registry = registry or self.registry
        if not target_registry:
            return None

        logger.info(f"🤖 Generating skill for: {user_text[:80]}")

        prompt = GENERATOR_PROMPT.format(user_request=user_text)
        try:
            code = await self.llm_client.chat(prompt, f"为需求生成技能: {user_text}")
        except Exception as e:
            logger.warning(f"Skill generation failed: {e}")
            return None

        # Extract Python code from response
        code = self._extract_code(code)
        if not code:
            logger.warning("No valid Python code in generation response")
            return None

        # Extract skill name from code
        skill_name = self._extract_skill_name(code)
        if not skill_name:
            logger.warning("No skill name found in generated code")
            return None

        # Save to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"_auto_{skill_name}_{timestamp}.py"
        filepath = self.output_dir / filename
        filepath.write_text(code, encoding="utf-8")
        logger.info(f"💾 Saved generated skill: {filepath}")

        # Hot-reload: register the new skill
        from src.skills.registry import _load_skill_from_file
        skill = _load_skill_from_file(filepath)
        if skill:
            target_registry.register(skill)
            logger.info(f"✅ Registered and ready: {skill.name}")
            return skill.name

        return None

    def _extract_code(self, text: str) -> str:
        """Extract Python code from LLM response"""
        import re
        # Try to find code block
        m = re.search(r"```python\n(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        m = re.search(r"```\n(.*?)```", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # If no code blocks, assume the whole thing is code
        if text.strip().startswith("import") or "class" in text:
            return text.strip()
        return ""

    def _extract_skill_name(self, code: str) -> str:
        """Extract skill name from code"""
        import re
        m = re.search(r'name\s*=\s*"(\w+)"', code)
        return m.group(1) if m else None
