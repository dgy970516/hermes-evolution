import json
import logging

from src.skills.base import Skill, SkillContext

logger = logging.getLogger("hermes.skills.db")


class DatabaseQuerySkill(Skill):
    name = "database_query"
    description = "查询数据库、导出Excel"
    intents = ["db_query", "db_desc", "db_export"]
    triggers = ["查", "查询", "表", "数据", "excel", "导出", "统计"]

    async def can_handle(self, ctx: SkillContext) -> bool:
        if ctx.intent in self.intents:
            return True
        text = ctx.text.lower()
        return any(t in text for t in self.triggers)

    async def execute(self, ctx: SkillContext) -> None:
        hermes = ctx.hermes
        params = ctx.params
        db = hermes.db_client
        llm = hermes.llm_client
        feishu = hermes.feishu_adapter

        db_name = params.get("db_name", "local")
        sql = params.get("sql", "")

        yield f"🗄️  正在查询 {db_name} 数据库..."

        if not sql:
            # 注入对话上下文到 SQL 生成
            query_text = ctx.text
            if ctx.context_str:
                query_text = f"对话上下文：{ctx.context_str[:300]}\n当前需求：{ctx.text}"
            sql = await db.generate_sql(
                query_text,
                table_hint=params.get("table", ""),
                llm_client=llm,
                db_name=db_name,
            )

        result = await db.execute_with_retry(db_name, sql, llm)

        if not result.get("success"):
            yield f"❌ {result.get('message', '查询失败')}"
            return

        data = result.get("data", {})
        columns = data.get("columns", [])
        rows = data.get("rows", [])
        note = result.get("note", "")

        if note:
            yield f"ℹ️ {note}"

        yield f"✅ 查询成功 ({len(rows)} 行)"

        if columns:
            header = " | ".join(columns)
            yield f"```\n{header}"
            yield "-" * min(len(header), 80)
            for row in rows[:15]:
                vals = []
                for v in row:
                    s = str(v) if v is not None else "NULL"
                    vals.append(s[:30])
                yield " | ".join(vals)
            if len(rows) > 15:
                yield f"... 还有 {len(rows) - 15} 行"
            yield "```"

        # Excel 导出
        if ctx.intent == "db_export" or "excel" in ctx.text.lower() or "导出" in ctx.text:
            yield "📊 正在生成 Excel..."
            export = await db.export_to_excel(data)
            if export.get("success"):
                yield f"✅ 已生成 {export['filename']} ({export['row_count']} 行)"
                if feishu and ctx.user_id.startswith("ou_"):
                    s = await feishu.send_file(ctx.user_id, export["filepath"], export["filename"])
                    if s.get("success"):
                        yield "📁 文件已发送到飞书"
                    else:
                        yield f"⚠️ 文件发送失败: {s.get('message', '')}"
                else:
                    yield f"📁 文件路径: {export['filepath']}"
            else:
                yield f"❌ 导出失败: {export['message']}"
