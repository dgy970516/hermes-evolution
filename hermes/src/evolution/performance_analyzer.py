import logging
from collections import defaultdict

logger = logging.getLogger("hermes.evolution.performance")


class PerformanceAnalyzer:
    def __init__(self):
        self.metrics = {
            "avg_execution_time": 0.0,
            "success_rate": 0.0,
            "retry_rate": 0.0,
        }
        self._execution_times: list[float] = []
        self._results: list[bool] = []
        self._retries: list[bool] = []
        self._engine_stats: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "success": 0, "total_time": 0.0}
        )

    def record_execution(self, engine: str, duration: float, success: bool, retried: bool = False):
        self._execution_times.append(duration)
        self._results.append(success)
        if retried:
            self._retries.append(True)

        stats = self._engine_stats[engine]
        stats["count"] += 1
        stats["total_time"] += duration
        if success:
            stats["success"] += 1

        self._update_metrics()

    def _update_metrics(self):
        n = len(self._results)
        if n == 0:
            return

        self.metrics["avg_execution_time"] = sum(self._execution_times) / len(self._execution_times)
        self.metrics["success_rate"] = sum(self._results) / n
        self.metrics["retry_rate"] = len(self._retries) / n if n > 0 else 0.0

    def get_engine_performance(self, engine: str) -> dict:
        stats = self._engine_stats.get(engine, {})
        if stats.get("count", 0) == 0:
            return {"success_rate": 0.0, "avg_time": 0.0}

        return {
            "success_rate": stats["success"] / stats["count"],
            "avg_time": stats["total_time"] / stats["count"],
            "total_runs": stats["count"],
        }

    def suggest_engine(self, intent: str) -> str | None:
        # Based on historical performance
        # TODO: Implement smarter selection
        return None

    def get_metrics(self) -> dict:
        return {**self.metrics}
