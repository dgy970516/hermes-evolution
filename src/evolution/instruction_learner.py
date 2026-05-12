import logging
from collections import Counter, defaultdict

logger = logging.getLogger("hermes.evolution.instruction_learner")


class ExecutionRecord:
    def __init__(self, instruction: str, intent: str, success: bool, duration: float):
        self.instruction = instruction
        self.intent = intent
        self.success = success
        self.duration = duration


class InstructionLearner:
    def __init__(self):
        self.prompt_templates: dict[str, str] = {}
        self.execution_history: list[ExecutionRecord] = []
        self._intent_counter: Counter = Counter()
        self._success_rate: dict[str, list[bool]] = defaultdict(list)

    def record_execution(self, record: ExecutionRecord):
        self.execution_history.append(record)
        self._intent_counter[record.intent] += 1
        self._success_rate[record.intent].append(record.success)

        if record.success:
            self._reinforce_pattern(record)
        else:
            self._adjust_pattern(record)

    def _reinforce_pattern(self, record: ExecutionRecord):
        logger.debug(f"Reinforcing pattern for intent={record.intent}")

    def _adjust_pattern(self, record: ExecutionRecord):
        logger.debug(f"Adjusting pattern for intent={record.intent} (failed)")

    def suggest_template(self, user_input: str) -> str | None:
        best_match = None
        best_score = 0
        for intent, template in self.prompt_templates.items():
            score = self._match_score(user_input, intent)
            if score > best_score:
                best_score = score
                best_match = template
        return best_match

    def _match_score(self, text: str, pattern: str) -> float:
        keywords = pattern.lower().split()
        text_lower = text.lower()
        matches = sum(1 for kw in keywords if kw in text_lower)
        return matches / max(len(keywords), 1)

    def get_stats(self) -> dict:
        return {
            "total_executions": len(self.execution_history),
            "intent_distribution": dict(self._intent_counter),
            "success_rate": {
                intent: sum(results) / len(results)
                for intent, results in self._success_rate.items()
            },
        }
