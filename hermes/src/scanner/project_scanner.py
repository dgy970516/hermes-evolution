import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.scanner")


@dataclass
class ProjectInfo:
    name: str
    dir_name: str  # 目录名（用户通常用这个引用）
    path: str
    language: str = "unknown"
    framework: str = ""
    description: str = ""
    keywords_full: str = ""
    is_sub_project: bool = False

    def to_match_text(self) -> str:
        return f"名称:{self.name} | 目录:{self.dir_name} | 语言:{self.language} | 框架:{self.framework} | 路径:{self.path}"

    def all_names(self) -> list[str]:
        """所有可用名称（目录名和包名）"""
        names = [self.name, self.dir_name]
        if self.name.lower() != self.dir_name.lower():
            names.append(self.dir_name)
        return list(set(names))


class ProjectScanner:
    IGNORE_DIRS = {
        "node_modules", "__pycache__", ".git", ".svn",
        "venv", ".venv", "dist", "build", "target",
        ".idea", ".vscode", ".cursor", ".claude", ".kiro",
        "data", "logs", "tmp", "temp", "cdk.out",
        "coverage", ".next", ".nuxt",
        "images", "image", "sql", "shell", "script",
        "output", "tools", "specs", "temp_pycache",
    }

    # 按优先级排序的项目指示文件
    INDICATOR_FILES = [
        "pom.xml",          # Maven Java
        "package.json",     # Node/JS
        "pyproject.toml",   # Python
        "requirements.txt", # Python
        "go.mod",           # Go
        "cargo.toml",       # Rust
        "build.gradle",     # Gradle
        "Gemfile",          # Ruby
        "Cargo.toml",       # Rust
        "composer.json",    # PHP
        "CMakeLists.txt",   # C++
        "Makefile",         # Generic
        "Dockerfile",       # Docker
        "docker-compose.yml",
        ".opencode.json",   # AI project
        "AGENTS.md",
        "CLAUDE.md",
        ".cursorrules",
        "GEMINI.md",
        ".rules",           # Directory indicator
    ]

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = Path(workspace_root or os.getcwd())
        self._projects: dict[str, ProjectInfo] = {}

    async def scan_all(self, depth: int = 3) -> dict[str, ProjectInfo]:
        """Scan entire workspace for projects"""
        self._projects = {}
        # 扫描主目录
        await self._scan_directory(self.workspace_root, depth=0, max_depth=depth)
        # 如果扫描结果太少，扩大深度
        if len(self._projects) < 5 and depth < 4:
            logger.info(f"Only found {len(self._projects)} projects, scanning deeper...")
            await self._scan_directory(self.workspace_root, depth=0, max_depth=depth + 1)
        logger.info(f"Scanned {len(self._projects)} projects from {self.workspace_root}")
        return self._projects

    async def search_project(self, name_hint: str) -> Optional[ProjectInfo]:
        """Dynamically search for a project by name anywhere in the workspace"""
        name_clean = name_hint.lower().replace("-", "").replace("_", "").replace(" ", "")

        # 1. Check existing: 匹配所有别名
        best = None
        best_score = 0
        for info in self._projects.values():
            for alias in info.all_names():
                alias_clean = alias.lower().replace("-", "").replace("_", "").replace(" ", "")
                score = self._match_score(name_clean, alias_clean)
                if score > best_score:
                    best_score = score
                    best = info

        if best_score >= 0.7:
            return best

        # 2. Search recursively deeper

        # 3. Search recursively deeper
        logger.info(f"🔍 Searching for project: {name_hint}")
        new_projects = {}
        await self._deep_search(self.workspace_root, name_clean, new_projects, depth=0, max_depth=5)

        if new_projects:
            # 找最佳匹配（长度最接近的）
            candidates = sorted(new_projects.values(),
                                key=lambda p: abs(len(p.name) - len(name_hint)))
            if candidates:
                best = candidates[0]
                self._projects[best.name] = best
                return best
        return None

    async def _deep_search(self, directory: Path, name_lower: str,
                           results: dict, depth: int, max_depth: int):
        if depth > max_depth:
            return
        if not directory.is_dir() or directory.name in self.IGNORE_DIRS:
            return
        dir_lower = directory.name.lower().replace("-", "").replace("_", "")
        if name_lower in dir_lower or dir_lower in name_lower:
            if directory.name not in results:
                info = self._build_project_info(directory)
                if info:
                    results[info.name] = info
        for child in sorted(directory.iterdir()):
            if child.is_dir() and child.name not in self.IGNORE_DIRS and not child.name.startswith("."):
                await self._deep_search(child, name_lower, results, depth + 1, max_depth)

    async def _scan_directory(self, directory: Path, depth: int, max_depth: int):
        if depth > max_depth:
            return
        if not directory.is_dir() or directory.name in self.IGNORE_DIRS:
            return
        # 跳过隐藏目录（1层以上）
        if depth >= 1 and directory.name.startswith("."):
            return
        if depth == 0:
            for child in sorted(directory.iterdir()):
                if child.is_dir() and child.name not in self.IGNORE_DIRS and not child.name.startswith("."):
                    await self._scan_directory(child, 1, max_depth)
            return
        # depth >= 1: 检查是否是项目
        info = self._build_project_info(directory)
        if info:
            self._projects[info.name] = info
            # 扫描子项目
            if depth < max_depth:
                for child in sorted(directory.iterdir()):
                    if child.is_dir() and child.name not in self.IGNORE_DIRS and not child.name.startswith("."):
                        sub_info = self._build_project_info(child)
                        if sub_info and sub_info.name not in self._projects:
                            sub_info.is_sub_project = True
                            self._projects[sub_info.name] = sub_info

    def _build_project_info(self, directory: Path) -> Optional[ProjectInfo]:
        """Build project info for any directory, detecting what it can"""
        if not directory.is_dir():
            return None
        indicators = self._detect_indicators(directory)
        name = indicators.get("pkg_name", directory.name)
        dir_name = directory.name
        lang = indicators.get("language", "unknown")
        framework = indicators.get("framework", "")
        desc = self._read_description(directory)
        return ProjectInfo(
            name=name,
            dir_name=dir_name,
            path=str(directory.resolve()),
            language=lang,
            framework=framework,
            description=desc,
            keywords_full=f"{name} {lang} {framework} {desc} {directory.name} {directory.parent.name}",
        )

    def _detect_indicators(self, directory: Path) -> dict:
        """Detect project type from indicator files"""
        ind = {"language": "unknown", "pkg_name": directory.name}
        for f in directory.iterdir():
            name = f.name.lower()
            if f.is_dir() and name == ".rules":
                ind["language"] = "Project"
                ind["framework"] = "AI Rules"
                continue
            if not f.is_file():
                continue
            if name == "pom.xml":
                ind["language"] = "Java"
                ind["framework"] = "Spring"
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    m = re.search(r'<artifactId>([^<]+)', content)
                    if m:
                        ind["pkg_name"] = m.group(1)
                except Exception:
                    pass
            elif name == "package.json":
                ind["language"] = "JavaScript/TypeScript"
                try:
                    pkg = json.loads(f.read_text(encoding="utf-8", errors="replace"))
                    ind["pkg_name"] = pkg.get("name", directory.name)
                except Exception:
                    pass
            elif name in ("pyproject.toml", "setup.py", "requirements.txt"):
                ind["language"] = "Python"
            elif name == "go.mod":
                ind["language"] = "Go"
            elif name == "cargo.toml":
                ind["language"] = "Rust"
            elif name == "build.gradle" or name == "build.gradle.kts":
                ind["language"] = "Java"
                ind["framework"] = "Gradle"
            elif name == "gemfile":
                ind["language"] = "Ruby"
            elif name == "composer.json":
                ind["language"] = "PHP"
            elif name in ("claude.md", "agents.md", "gemini.md", ".cursorrules"):
                if ind["language"] == "unknown":
                    ind["language"] = "Project"
            elif name == ".opencode.json":
                if ind["language"] == "unknown":
                    ind["language"] = "Project"
        # 如果检测不到类型但目录有源文件，标记为 Unknown Project
        if ind["language"] == "unknown":
            has_source = any(
                f.suffix in (".py", ".js", ".ts", ".java", ".go", ".rs", ".cpp", ".c", ".h", ".cs", ".vue", ".jsx", ".tsx")
                for f in directory.rglob("*") if f.is_file()
            )
            if has_source:
                ind["language"] = "Mixed"
        return ind

    def _read_description(self, directory: Path) -> str:
        for name in ("README.md", "readme.md"):
            f = directory / name
            if f.exists():
                try:
                    return f.read_text(encoding="utf-8", errors="replace")[:200].strip()
                except Exception:
                    pass
        return ""

    def find_by_name(self, name: str) -> Optional[ProjectInfo]:
        name_clean = name.lower().replace("-", "").replace("_", "")
        best = None
        best_score = 0.0
        for info in self._projects.values():
            for alias in info.all_names():
                alias_clean = alias.lower().replace("-", "").replace("_", "")
                score = self._match_score(name_clean, alias_clean)
                if score > best_score:
                    best_score = score
                    best = info
            # 也匹配路径
            if name_clean in info.path.lower():
                path_score = len(name_clean) / len(info.path) * 2
                if path_score > best_score:
                    best_score = path_score
                    best = info
        return best if best_score >= 0.6 else None

    def _match_score(self, query: str, target: str) -> float:
        """Score how well query matches target (0.0 to 1.0)"""
        if not query or not target:
            return 0.0
        if query == target:
            return 1.0
        # 前缀匹配
        if target.startswith(query) or query.startswith(target):
            return min(len(query), len(target)) / max(len(query), len(target))
        # 子串匹配（短串在长串中）
        if query in target:
            return len(query) / len(target) * 0.8  # 子串扣分
        if target in query:
            return len(target) / len(query) * 0.7  # 反向子串更低分
        # 字符重叠
        common = sum(1 for c in query if c in target)
        return common / max(len(query), len(target)) * 0.5

    def get_all_projects(self) -> list[ProjectInfo]:
        return sorted(self._projects.values(), key=lambda p: p.name)
