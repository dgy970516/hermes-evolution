import importlib
import inspect
import logging
import sys as _sys
from pathlib import Path

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills")


def _load_skill_from_file(filepath: Path) -> Skill | None:
    """Load a single skill from a file and return the instance.
    Used for hot-reloading generated skills."""
    try:
        abs_path = filepath.resolve()
        cwd = Path.cwd().resolve()
        rel = abs_path.relative_to(cwd) if abs_path != cwd else Path(filepath.name)
        module_path = str(rel.with_suffix("")).replace("\\", ".").replace("/", ".")

        # Force reload if already imported
        if module_path in _sys.modules:
            del _sys.modules[module_path]

        mod = importlib.import_module(module_path)
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, Skill) and obj is not Skill and not inspect.isabstract(obj):
                return obj()
    except Exception as e:
        logger.warning(f"  ⚠️  Failed to load {filepath.name}: {e}")
    return None


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        self._skills[skill.name] = skill
        logger.info(f"  📦 Registered skill: {skill.name}")

    def unregister(self, name: str):
        if name in self._skills:
            del self._skills[name]
            logger.info(f"  🗑️  Unregistered skill: {name}")

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def get_all(self) -> list[Skill]:
        return list(self._skills.values())

    def has_skill_for(self, text: str) -> bool:
        """Check if any skill (except chat) can handle this text"""
        text_lower = text.lower()
        for skill in self._skills.values():
            if skill.name == "chat":
                continue
            if hasattr(skill, "triggers"):
                for t in skill.triggers:
                    if t in text_lower:
                        return True
        return False

    async def find_skill(self, ctx: SkillContext) -> Skill | None:
        """Find the best matching skill for the context"""
        # 1. Match by trigger keywords
        for skill in self._skills.values():
            if ctx.intent not in skill.intents and skill.name != "chat":
                if await skill.can_handle(ctx):
                    return skill

        # 2. Match by intent (排除 chat)
        for skill in self._skills.values():
            if skill.name != "chat" and ctx.intent in skill.intents:
                if await skill.can_handle(ctx):
                    return skill

        # 3. Fallback to chat
        return self._skills.get("chat")

    def discover(self, *paths: str):
        """Auto-discover skills from Python files"""
        for base_path in paths:
            p = Path(base_path)
            if not p.exists():
                continue
            for f in sorted(p.rglob("*.py")):
                if f.name.startswith("_") and f.name != "__init__.py":
                    continue
                skill = _load_skill_from_file(f)
                if skill:
                    self.register(skill)

    def hot_reload_files(self, *filepaths: str):
        """Hot-reload skills from specific file paths.
        Used after auto-generation to immediately make skills available."""
        count = 0
        for fp in filepaths:
            p = Path(fp)
            if p.exists():
                skill = _load_skill_from_file(p)
                if skill:
                    self.register(skill)
                    count += 1
        return count
