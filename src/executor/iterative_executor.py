"""
Iterative Executor — 多轮迭代执行器
====================================
相比一次性的 PLAN 执行，支持：
  1. 执行命令 → 看结果 → 决定下一步（多轮）
  2. 条件分支（失败时尝试其他方案）
  3. 自动修正（命令错误时重试）
  4. LLM 驱动的自适应规划

使用场景：
  - "提交了吗" → 检查git状态 → 如有未提交文件则add+commit
  - "看下代码逻辑" → 找文件 → 读内容 → 总结
"""
import logging
import re
from typing import AsyncIterator

logger = logging.getLogger("hermes.executor")

EXECUTOR_PROMPT = """你是 Hermes 的任务执行器。用户有一个需求，你需要一步步执行来完成。

规则：
1. 每次输出 NEXT 指令来执行一个 shell 命令
2. 我执行后会返回结果
3. 你根据结果决定下一步做什么
4. 当任务完成时，用 DONE 给出最终回答

格式：
NEXT: 要执行的命令
或
DONE: 最终回答

当前工作目录: {work_dir}

历史执行记录：
{history}

用户需求：{user_request}

请输出 NEXT 或 DONE：
"""


class IterativeExecutor:
    def __init__(self, llm_client=None, system_ops=None):
        self.llm_client = llm_client
        self.system_ops = system_ops

    async def execute(self, user_request: str, work_dir: str = "",
                      max_rounds: int = 5) -> AsyncIterator[str]:
        if not work_dir:
            work_dir = os.getcwd()
        """Iterative execution: LLM plans → execute → feedback → continue"""
        if not self.llm_client:
            yield "❌ LLM not configured"
            return

        history = []
        yield f"🎯 目标: {user_request[:80]}"

        for round_num in range(1, max_rounds + 1):
            # Build prompt with history
            history_text = "\n".join(history[-6:]) if history else "无"
            prompt = EXECUTOR_PROMPT.format(
                work_dir=work_dir,
                history=history_text,
                user_request=user_request,
            )

            try:
                response = await self.llm_client.chat(prompt, f"第{round_num}轮")
            except Exception as e:
                yield f"❌ LLM 错误: {e}"
                return

            # Check for DONE
            done_match = re.search(r"DONE:\s*(.*)", response, re.DOTALL)
            if done_match:
                yield done_match.group(1).strip()
                return

            # Check for NEXT command
            next_match = re.search(r"NEXT:\s*(.+)", response, re.DOTALL)
            if not next_match:
                # No NEXT or DONE found, treat response as answer
                yield response.strip()
                return

            cmd = next_match.group(1).strip().strip("`").strip()
            if not cmd:
                yield "⚠️ 空命令，结束"
                return

            # Execute
            yield f"  ⚡ {cmd[:100]}"
            result = await self.system_ops.run_command(cmd)
            if result.get("success"):
                out = result.get("stdout", "").strip()[:500]
                if out:
                    yield out[:200]
                    history.append(f"命令: {cmd}\n输出: {out}")
                else:
                    history.append(f"命令: {cmd}\n输出: 成功(无输出)")
            else:
                err = result.get("stderr", result.get("error", "")).strip()[:300]
                history.append(f"命令: {cmd}\n错误: {err or '执行失败'}")
                yield f"  ⚠️ {err[:150]}"

        # Max rounds reached
        final_prompt = (
            f"已达最大执行轮数({max_rounds})。请根据已有结果给用户最终回答。\n\n"
            f"执行历史:\n" + "\n".join(history)
        )
        try:
            final = await self.llm_client.chat(final_prompt, "总结结果")
            yield final.strip()[:400]
        except Exception:
            yield "执行完成，结果如上。"
