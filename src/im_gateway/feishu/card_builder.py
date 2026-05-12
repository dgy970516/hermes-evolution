from src.im_gateway.base import Card


class FeishuCardBuilder:
    @staticmethod
    def task_progress(task_id: str, progress: int, status: str) -> Card:
        return Card(
            title=f"任务进度 ({task_id[:8]}...)",
            content=f"状态: {status}\n进度: {progress}%",
            buttons=[{"text": "查看详情", "action": f"task_detail:{task_id}"}],
        )

    @staticmethod
    def confirm_action(action_desc: str, confirm_text: str = "确认", cancel_text: str = "取消") -> Card:
        return Card(
            title="操作确认",
            content=f"⚠️ {action_desc}\n\n确认执行此操作吗？",
            buttons=[
                {"text": confirm_text, "action": "confirm"},
                {"text": cancel_text, "action": "cancel"},
            ],
        )

    @staticmethod
    def task_result(task_id: str, result: str) -> Card:
        return Card(
            title="任务完成",
            content=result,
            buttons=[{"text": "查看文件", "action": f"task_result:{task_id}"}],
        )
