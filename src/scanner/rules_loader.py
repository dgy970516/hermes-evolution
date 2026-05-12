"""
Project Rules Loader
====================
Auto-discovers and loads project rules/configs that were previously
used by AI coding tools (Claude Code, Cursor, Windsurf, etc.).

Scans these files in the project root:
  - .rules/          (directory of rule files)
  - AGENTS.md        (agent instructions)
  - CLAUDE.md        (Claude Code instructions)
  - .cursorrules     (Cursor rules)
  - .windsurfrules   (Windsurf rules)
  - GEMINI.md        (Gemini instructions)
"""
import logging
from pathlib import Path

logger = logging.getLogger("hermes.rules")

RULE_FILES_PATTERNS = [
    ".rules",          # directory
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    "GEMINI.md",
]


def load_project_rules(project_path: str) -> str:
    """Load all rules from a project directory and return as a single context string"""
    root = Path(project_path)
    if not root.is_dir():
        return ""

    parts = []

    for pattern in RULE_FILES_PATTERNS:
        target = root / pattern
        if target.is_dir():
            # .rules/ directory - load all .md files
            md_files = sorted(target.glob("*.md"))
            if md_files:
                for f in md_files:
                    content = _read_file(f)
                    if content:
                        parts.append(f"## Rule from {pattern}/{f.name}\n{content}")
        elif target.is_file():
            content = _read_file(target)
            if content:
                parts.append(f"## Rule from {pattern}\n{content}")

    if parts:
        combined = "\n\n".join(parts)
        logger.info(f"  📋 Loaded {len(parts)} rule files from {project_path}")
        return combined

    return ""


def _read_file(filepath: Path) -> str:
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace").strip()
        return content[:3000] if content else ""  # limit per file
    except Exception as e:
        logger.warning(f"  ⚠️  Could not read {filepath}: {e}")
        return ""
