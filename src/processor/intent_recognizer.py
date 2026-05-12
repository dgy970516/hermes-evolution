INTENT_SYSTEM_PROMPT = """你是一个任务意图识别专家。分析用户输入，识别其意图。

可选意图：
[编程任务]
- code_generation: 生成新代码
- code_modification: 修改现有代码
- code_review: 代码审查
- bug_fix: 修复 Bug
- explain: 解释代码
- test_write: 编写测试
- refactor: 重构代码

[IDE/系统操作]
- open_ide: 打开 IDE 并加载项目 (如"用 idea 打开 agent 项目")
- open_file: 打开文件 (如"打开 src/main.py")
- run_command: 执行系统命令

[数据库操作]
- db_query: 查询数据库 (如"查一下 users 表的数据")
- db_desc: 查看表结构 (如"看看 orders 表结构")
- db_export: 导出数据为 Excel/CSV (如"导出 users 表为excel"、"下载订单统计表格")

可用数据库：
- "online": 线上环境 (用户提到"线上"、"生产"、"prod"时使用)
- "local": 本地环境 (用户没有特别指定时，默认使用)

[其他]
- chat: 普通对话

返回 JSON 格式：
{"intent": "...", "confidence": 0.0-1.0, "params": {...}}

params 可选字段：
- language: 检测到的编程语言
- file_path: 涉及的文件路径
- db_name: 涉及的数据库名（数据库操作必填，默认 "local"）
- sql: 识别到的 SQL 查询
- ide_name: 指定的 IDE 名称 (idea/vscode/pycharm)
- description: 任务简要描述
"""


class IntentRecognizer:
    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    async def recognize(self, text: str, context: str | None = None) -> dict:
        if not self.llm_client:
            return {"intent": "chat", "confidence": 0.5, "params": {}}

        user_prompt = text
        if context:
            user_prompt = f"上下文:\n{context}\n\n用户输入:\n{text}"

        try:
            result = await self.llm_client.chat_json(INTENT_SYSTEM_PROMPT, user_prompt)
            params = result.get("params", {})
            intent = result.get("intent", "chat")

            # DB 操作默认走本地
            if intent in ("db_query", "db_desc") and not params.get("db_name"):
                params["db_name"] = "local"

            return {
                "intent": intent,
                "confidence": float(result.get("confidence", 0.5)),
                "params": params,
            }
        except Exception as e:
            import logging
            logging.getLogger("hermes.intent").warning(f"Intent recognition failed: {e}")
            return {"intent": "chat", "confidence": 0.0, "params": {}}
