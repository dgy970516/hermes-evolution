import logging
import re

from src.scanner.project_scanner import ProjectInfo, ProjectScanner

logger = logging.getLogger("hermes.matcher")

MATCHER_PROMPT = """你是一个项目匹配专家。用户说了一个需求，其中提到了一个项目。
请从项目列表中找出最匹配的项目。

用户需求: {user_text}

项目列表:
{project_list}

规则：
1. 匹配项目名（name）
2. 匹配目录名（路径最后一部分）
3. 匹配语言和框架
4. 如果用户说"后端" → 优先 Java/Python/Go
5. 如果用户说"前端" → 优先 JS/TS
6. 如果用户说"管理后台" → 优先 admin/管理类项目
7. 如果完全无法匹配，返回 null

返回 JSON:
{{"matched": "项目名" or null, "confidence": 0.0-1.0, "reason": "简短的匹配理由"}}
"""


class ProjectMatcher:
    def __init__(self, scanner: ProjectScanner, llm_client=None):
        self.scanner = scanner
        self.llm_client = llm_client

    async def match(self, instruction: str) -> tuple[ProjectInfo | None, str]:
        projects = self.scanner.get_all_projects()
        if not projects:
            return None, "未发现任何项目"

        # 1. 精确匹配项目名
        proj = self._exact_match(instruction, projects)
        if proj:
            return proj, ""

        # 2. 关键词匹配（目录名、文件名片段）
        proj = self._keyword_match(instruction, projects)
        if proj:
            return proj, ""

        # 3. LLM 语义匹配（处理"给后端加接口"这种）
        if self.llm_client:
            proj, reason = await self._llm_match(instruction, projects)
            if proj and reason:
                return proj, reason

        # 4. 动态搜索（可能不在已扫描列表中）
        name_hint = self._extract_name_hint(instruction)
        if name_hint:
            found = await self.scanner.search_project(name_hint)
            if found:
                logger.info(f"🔍 Dynamically found project: {found.name} at {found.path}")
                return found, f"动态发现项目: {found.name}"

        return None, f"未找到匹配项目: {instruction[:50]}"

    def _exact_match(self, instruction: str, projects: list[ProjectInfo]) -> ProjectInfo | None:
        text_lower = instruction.lower().replace("-", "").replace("_", "").replace(" ", "")
        for proj in projects:
            for alias in proj.all_names():
                alias_clean = alias.lower().replace("-", "").replace("_", "")
                if alias_clean in text_lower or alias_clean == text_lower:
                    return proj
            # 路径匹配
            path_lower = proj.path.lower()
            path_parts = path_lower.replace("\\", "/").split("/")
            for part in path_parts:
                if part and len(part) > 2 and part in text_lower:
                    return proj
        return None

    def _keyword_match(self, instruction: str, projects: list[ProjectInfo]) -> ProjectInfo | None:
        """Match by extracting project-like words from instruction"""
        # 提取所有可能的项目名候选项
        text = instruction
        # 移除常见动词
        for w in ["帮我", "给", "在", "把", "用", "修复", "修改", "添加", "加个", "看看", "查一下", "读取", "分析"]:
            text = text.replace(w, "")
        words = set(re.findall(r'[a-zA-Z][a-zA-Z0-9_-]{2,}', text))
        words.update(re.findall(r'[\u4e00-\u9fff]{2,}', text))

        scored = []
        for proj in projects:
            score = 0
            name_lower = proj.name.lower()
            path_lower = proj.path.lower()
            # 匹配英文名
            for w in words:
                if w.lower() in name_lower:
                    score += 5
                if w.lower() in path_lower:
                    score += 3
            # 中文名匹配
            for w in words:
                if w in proj.description:
                    score += 2
            if score > 0:
                scored.append((score, proj))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1] if scored else None

    async def _llm_match(self, instruction: str, projects: list[ProjectInfo]) -> tuple[ProjectInfo | None, str]:
        project_list = "\n".join(
            f"- name: {p.name} | path: {p.path} | lang: {p.language}"
            for p in projects
        )
        prompt = MATCHER_PROMPT.format(user_text=instruction, project_list=project_list)
        try:
            result = await self.llm_client.chat_json(prompt, f"匹配项目: {instruction[:60]}")
            name = result.get("matched")
            if name:
                for p in projects:
                    if p.name == name:
                        return p, result.get("reason", "")
            return None, ""
        except Exception as e:
            logger.warning(f"LLM match failed: {e}")
            return None, ""

    def _extract_name_hint(self, instruction: str) -> str | None:
        """Extract a possible project name from instruction for dynamic search"""
        text = instruction.lower().replace("-", "").replace("_", "")
        # 常见项目名模式
        patterns = [
            r'(?:给|在|打开|修复|修改|读|查看)\s*([a-zA-Z][a-zA-Z0-9_-]{2,})',
            r'(?:项目|工程)\s*[`"\'】]?([a-zA-Z][a-zA-Z0-9_-]{2,})',
            r'([a-zA-Z][a-zA-Z0-9_-]{2,})(?:项目|工程|模块)',
            r'd[：:].*?([a-zA-Z][a-zA-Z0-9_-]{3,})',  # D:\xx\yy\zz 中的 zz
        ]
        for p in patterns:
            m = re.search(p, instruction)
            if m:
                return m.group(1)
        return None
