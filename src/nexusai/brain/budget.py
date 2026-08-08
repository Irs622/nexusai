"""Resource Budget Engine & Decision Maker for NexusAI."""

import time

from nexusai.domain.models import AgentContext, BudgetDecision, BudgetPolicy


class ResourceBudgetEngine:
    """Evaluates resource consumption and outputs operational BudgetDecision."""

    def __init__(self, policy: BudgetPolicy = BudgetPolicy()) -> None:
        self.policy = policy

    def evaluate_budget(self, context: AgentContext) -> BudgetDecision:
        """Evaluate current context metrics against policy rules."""
        elapsed = time.time() - context.start_time

        if context.tokens_used >= self.policy.max_tokens:
            return BudgetDecision.STOP

        if context.tool_calls_count >= self.policy.max_tool_calls:
            return BudgetDecision.STOP

        if context.retries_count >= self.policy.max_retries:
            return BudgetDecision.ASK_USER

        if elapsed >= self.policy.max_duration_seconds:
            return BudgetDecision.WAIT

        return BudgetDecision.ALLOW
