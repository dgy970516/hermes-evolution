import logging
from pathlib import Path

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.screenshot")


class ScreenshotSkill(Skill):
    name = "screenshot"
    description = "截图当前桌面并发送到飞书"
    intents = []
    triggers = ["截图", "截屏", "screen", "screenshot", "桌面", "屏幕", "显示", "显示器"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        return any(t in ctx.text.lower() for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        yield "📸 正在准备截图..."

        try:
            import PIL
        except ImportError:
            yield "📦 安装 Pillow..."
            await hermes.upgrader.ensure_dependencies(["pillow"])

        try:
            import pyautogui
        except ImportError:
            yield "📦 安装 pyautogui..."
            await hermes.upgrader.ensure_dependencies(["pyautogui"])
            import pyautogui

        yield "📸 正在截取屏幕..."

        try:
            screenshot = pyautogui.screenshot()
            yield "✅ 截图完成"

            export_dir = Path("data/exports")
            export_dir.mkdir(parents=True, exist_ok=True)
            filepath = export_dir / "screenshot.png"
            screenshot.save(str(filepath))
            size_kb = filepath.stat().st_size // 1024
            yield f"📁 已保存 ({size_kb}KB)"

            if hermes.feishu_adapter and ctx.user_id.startswith("ou_"):
                yield "📤 正在发送到飞书..."
                # 使用图片 API 发送（才能在飞书直接显示）
                result = await hermes.feishu_adapter.send_image(
                    ctx.user_id, str(filepath)
                )
                if result.get("success"):
                    yield "✅ 截图已发送"
                else:
                    # 降级：用文件 API
                    yield f"⚠️ 图片发送失败，尝试文件模式..."
                    result = await hermes.feishu_adapter.send_file(
                        ctx.user_id, str(filepath), "screenshot.png"
                    )
                    if result.get("success"):
                        yield "✅ 截图已发送（文件模式）"
                    else:
                        yield f"❌ 发送失败: {result.get('message', '')}"
            else:
                yield f"📁 {filepath}"

        except Exception as e:
            yield f"❌ 截图失败: {e}"
