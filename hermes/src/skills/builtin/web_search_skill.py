"""
Web Search Skill — 浏览器搜索 + 抓取网页内容
=============================================
用法: "搜索一下 Python 教程" / "查一下 DeepSeek API 文档"
"""
import logging

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.web_search")


class WebSearchSkill(Skill):
    name = "web_search"
    description = "搜索引擎搜索、抓取网页内容"
    intents = []
    triggers = ["搜索", "搜一下", "查一下", "查找", "google", "baidu", "bing", "搜索一下"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        text = ctx.text.lower()
        return any(t in text for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        text = ctx.text

        # 提取搜索关键词
        keywords = text
        for prefix in ["搜索一下", "搜一下", "搜索", "查一下", "查找", "帮我查", "search for", "search"]:
            keywords = keywords.replace(prefix, "")
        keywords = keywords.strip().strip(":：，。").strip()

        if not keywords or len(keywords) < 2:
            yield "请指定搜索关键词，例如: 搜索 Python 教程"
            return

        yield f"🔍 正在搜索: {keywords}"

        # 自动安装依赖
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            yield "📦 安装 duckduckgo_search..."
            await hermes.upgrader.ensure_dependencies(["duckduckgo_search"])
            from duckduckgo_search import DDGS

        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(keywords, max_results=5):
                    results.append(r)

            if results:
                yield f"✅ 找到 {len(results)} 条结果:"
                for i, r in enumerate(results, 1):
                    title = r.get("title", "无标题")
                    href = r.get("href", "")
                    body = r.get("body", "")[:100]
                    yield f"\n{i}. {title}"
                    yield f"   {href}"
                    if body:
                        yield f"   {body}..."

                # LLM 总结
                if hermes.llm_client:
                    yield "\n📋 AI 摘要:"
                    snippets = "\n".join(f"- {r.get('body', '')[:200]}" for r in results if r.get('body'))
                    prompt = f"用户搜索: {keywords}\n\n搜索结果:\n{snippets}\n\n请用中文总结这些搜索结果的核心内容。"
                    try:
                        summary = await hermes.llm_client.chat(prompt, f"总结搜索: {keywords}")
                        yield summary.strip()[:400]
                    except Exception:
                        pass
            else:
                yield "❌ 未找到相关结果"

        except Exception as e:
            yield f"❌ 搜索失败: {e}"
            yield "提示: 如需更准确的搜索，可以指定更具体的关键词"
