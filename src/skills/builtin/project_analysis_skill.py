"""
Project Analysis Skill — 读取项目结构、分析代码
================================================
用法: "读取一下 zsadmin 项目" / "分析 huihuoke 的代码结构"
"""
import logging
from pathlib import Path

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.project_analysis")


class ProjectAnalysisSkill(Skill):
    name = "project_analysis"
    description = "读取项目结构、分析代码、统计代码量"
    intents = []
    triggers = ["读取", "分析", "查看", "代码结构", "项目结构", "统计", "代码量", "scan"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        text = ctx.text.lower()
        return any(t in text for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes

        # 匹配项目
        proj, reason = await hermes.matcher.match(ctx.text)
        if not proj:
            yield f"⚠️ 未找到匹配项目: {reason}"
            return

        project_path = Path(proj.path)
        if not project_path.exists():
            yield f"❌ 项目目录不存在: {proj.path}"
            return

        yield f"📁 项目: {proj.name} ({proj.language})"
        yield f"📂 路径: {proj.path}"

        # 1. 目录结构
        yield "\n📋 顶层目录:"
        dirs = []
        files = []
        for f in sorted(project_path.iterdir()):
            if f.name.startswith(".") or f.name in ("node_modules", "__pycache__", "venv", ".venv", "target", "dist", "build"):
                continue
            if f.is_dir():
                dirs.append(f.name + "/")
            else:
                files.append(f.name)
        for d in dirs[:15]:
            yield f"  📁 {d}"
        if len(dirs) > 15:
            yield f"  ... 还有 {len(dirs) - 15} 个目录"
        for f in files[:10]:
            yield f"  📄 {f}"
        if len(files) > 10:
            yield f"  ... 还有 {len(files) - 10} 个文件"

        # 2. 代码统计
        yield "\n📊 代码统计:"
        extensions = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".tsx": "React TSX", ".jsx": "React JSX", ".vue": "Vue",
            ".java": "Java", ".go": "Go", ".rs": "Rust", ".cpp": "C++",
            ".c": "C", ".cs": "C#", ".php": "PHP", ".rb": "Ruby",
            ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
        }
        ext_counts = {}
        total_files = 0
        total_lines = 0

        for f in project_path.rglob("*"):
            if f.is_file() and f.suffix in extensions:
                ext_counts[f.suffix] = ext_counts.get(f.suffix, 0) + 1
                total_files += 1
                try:
                    total_lines += len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                except Exception:
                    pass

        if ext_counts:
            for ext, count in sorted(ext_counts.items(), key=lambda x: x[1], reverse=True):
                lang = extensions.get(ext, ext)
                yield f"  {lang:20s} {count:4d} 文件"
            yield f"  {'总计':20s} {total_files:4d} 文件, {total_lines} 行"
        else:
            yield "  (未检测到源代码文件)"

        # 3. 关键配置文件
        configs = [f for f in project_path.iterdir() if f.is_file() and f.suffix in (".json", ".yaml", ".yml", ".toml", ".xml", ".properties")]
        if configs:
            yield "\n⚙️  配置文件:"
            for f in configs[:5]:
                try:
                    size = len(f.read_text(encoding="utf-8", errors="replace").splitlines())
                    yield f"  {f.name} ({size} 行)"
                except Exception:
                    yield f"  {f.name}"

        # 4. README
        readme = project_path / "README.md"
        if readme.exists():
            try:
                content = readme.read_text(encoding="utf-8", errors="replace")[:300]
                yield f"\n📖 README:\n{content.strip()[:200]}"
            except Exception:
                pass

        # 5. 自动总结
        if hermes.llm_client:
            yield "\n🤖 AI 分析:"
            tree = "\n".join(f"  {d}" for d in dirs[:10])
            prompt = (
                f"项目: {proj.name}\n"
                f"语言: {proj.language}\n"
                f"目录: {tree}\n"
                f"文件数: {total_files}, 行数: {total_lines}\n"
                "请用1-2句话总结这个项目是做什么的。"
            )
            try:
                summary = await hermes.llm_client.chat(prompt, f"分析{proj.name}")
                yield summary.strip()[:300]
            except Exception:
                pass
