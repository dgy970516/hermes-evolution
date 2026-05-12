import logging
from collections import Counter, defaultdict

logger = logging.getLogger("hermes.evolution.workflow")


class WorkflowGenerator:
    def __init__(self):
        self._task_sequences: dict[str, list[list[str]]] = defaultdict(list)

    def record_sequence(self, intent: str, steps: list[str]):
        self._task_sequences[intent].append(steps)

        if self._detect_pattern(intent):
            self._generate_workflow(intent)

    def _detect_pattern(self, intent: str) -> bool:
        sequences = self._task_sequences.get(intent, [])
        if len(sequences) < 3:
            return False

        # Check if 80%+ sequences share the same core steps
        step_counter: Counter = Counter()
        for seq in sequences:
            step_counter[tuple(seq)] += 1

        most_common = step_counter.most_common(1)
        if most_common:
            count = most_common[0][1]
            return count >= len(sequences) * 0.8

        return False

    def _generate_workflow(self, intent: str):
        sequences = self._task_sequences.get(intent, [])
        if not sequences:
            return

        # Use the most common sequence as template
        step_counter: Counter = Counter()
        for seq in sequences:
            step_counter[tuple(seq)] += 1

        common_steps = step_counter.most_common(1)[0][0]

        workflow = {
            "name": f"auto-{intent}",
            "intent": intent,
            "steps": [{"name": step, "engine": "opencode"} for step in common_steps],
            "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        }

        logger.info(f"Generated workflow for intent={intent}: {workflow['name']}")
        # TODO: Persist workflow to disk/DB
