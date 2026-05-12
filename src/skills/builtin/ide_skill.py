import logging

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.ide")


class IDELaunchSkill(Skill):
    name = "ide_launch"
    description = "启动 IntelliJ IDEA / VS Code / PyCharm 打开项目"
    intents = ["open_ide"]
    triggers = ["打开", "启动", "idea", "vscode", "pycharm", "ide"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent in self.intents:
            return True
        text = ctx.text.lower()
        return any(t in text for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        params = ctx.params

        ide_name = params.get("ide_name", "")
        project_name = ""

        # Find project from text
        proj, reason = await hermes.matcher.match(ctx.text)
        if proj:
            project_name = proj.name

        if not project_name:
            yield "请指定项目，例如：用 idea 打开 zsadmin"
            return

        project_path = ""
        found = hermes.scanner.find_by_name(project_name)
        if found:
            project_path = found.path

        if not project_path:
            yield f"找不到项目: {project_name}"
            return

        result = await hermes.ide_launcher.open_project(project_path, ide_name)
        yield f"{'✅' if result['success'] else '❌'} {result['message']}"
