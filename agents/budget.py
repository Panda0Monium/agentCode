"""
Token accounting and per-run spend limits.

Architectures differ enormously in cost — a reflexion or critic-actor run can
spend five to ten times what a single ReAct pass does. Without a shared meter,
"which architecture is better" is unanswerable, because the expensive ones win
on reward for reasons that have nothing to do with being better designed.

One Budget is created per run and threaded through the Conversation, so every
LLM call from every sub-loop of an architecture is charged to the same pot.
"""

from dataclasses import dataclass, field

# Rough per-run ceilings by task difficulty. Generous enough that a well-behaved
# ReAct run never notices, tight enough to stop a runaway multi-round loop.
DIFFICULTY_TOKEN_BUDGETS = {
    "easy": 120_000,
    "medium": 250_000,
    "hard": 500_000,
}

DEFAULT_TOKEN_BUDGET = 250_000

# Fallback when the provider reports no usage at all. Deliberately crude: the
# point is that an unreported response still costs *something*, so budgets stay
# enforceable against providers with patchy usage reporting.
CHARS_PER_TOKEN = 4


class BudgetExhausted(Exception):
    """
    Raised when a run has spent its token allowance.

    Callers should treat this as a normal end-of-episode, not a failure — the
    repo still holds whatever the agent wrote, and that work deserves grading.
    """


def default_budget_for(task) -> int:
    """
    Resolve a task's token budget.

    Precedence: an explicit ``max_tokens`` in task.yaml, then the difficulty
    table, then the global default. A per-run override (CLI flag or web form)
    is applied by the caller and beats all of these.
    """
    explicit = getattr(task, "max_tokens", None)
    if explicit:
        return int(explicit)
    difficulty = getattr(task, "difficulty", "") or ""
    return DIFFICULTY_TOKEN_BUDGETS.get(difficulty.lower(), DEFAULT_TOKEN_BUDGET)


def _estimate_tokens(messages_or_text) -> int:
    """Character-count estimate, used only when the provider reports nothing."""
    if isinstance(messages_or_text, str):
        chars = len(messages_or_text)
    else:
        chars = 0
        for m in messages_or_text or []:
            content = getattr(m, "content", m)
            chars += len(content) if isinstance(content, str) else len(str(content))
    return max(1, chars // CHARS_PER_TOKEN)


@dataclass
class Budget:
    """
    A per-run token meter.

    ``max_tokens=None`` means unlimited, which is what the pre-budget behaviour
    was — useful for one-off debugging, not for benchmark runs.
    """

    max_tokens: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    sources: dict = field(default_factory=dict)
    exhausted: bool = False

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def remaining(self) -> float:
        if self.max_tokens is None:
            return float("inf")
        return max(0, self.max_tokens - self.total_tokens)

    def check(self) -> None:
        """Raise if the allowance is gone. Called before spending, not after."""
        if self.max_tokens is not None and self.total_tokens >= self.max_tokens:
            self.exhausted = True
            raise BudgetExhausted(
                f"Token budget of {self.max_tokens} exhausted "
                f"({self.total_tokens} used across {self.calls} calls)"
            )

    def charge(self, response, messages=None) -> dict:
        """
        Record the cost of one LLM call and return its usage dict.

        Providers report usage inconsistently, so three sources are tried in
        order of trustworthiness. The estimate is a last resort but not
        optional: silently charging zero would make budgets a no-op against any
        provider that omits usage, which is exactly the case where a runaway
        loop is most likely.
        """
        usage, source = self._extract(response, messages)
        self.input_tokens += usage["input_tokens"]
        self.output_tokens += usage["output_tokens"]
        self.calls += 1
        self.sources[source] = self.sources.get(source, 0) + 1
        usage["source"] = source
        return usage

    @staticmethod
    def _extract(response, messages=None) -> tuple[dict, str]:
        meta = getattr(response, "usage_metadata", None)
        if meta:
            return (
                {
                    "input_tokens": int(meta.get("input_tokens", 0) or 0),
                    "output_tokens": int(meta.get("output_tokens", 0) or 0),
                },
                "usage_metadata",
            )

        resp_meta = getattr(response, "response_metadata", None) or {}
        token_usage = resp_meta.get("token_usage") or resp_meta.get("usage") or {}
        if token_usage:
            return (
                {
                    "input_tokens": int(token_usage.get("prompt_tokens", 0) or 0),
                    "output_tokens": int(token_usage.get("completion_tokens", 0) or 0),
                },
                "response_metadata",
            )

        return (
            {
                "input_tokens": _estimate_tokens(messages) if messages else 0,
                "output_tokens": _estimate_tokens(getattr(response, "content", "") or ""),
            },
            "estimated",
        )

    def snapshot(self) -> dict:
        """Serializable summary for reports and the Run record."""
        return {
            "max_tokens": self.max_tokens,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "sources": dict(self.sources),
            "exhausted": self.exhausted,
        }
