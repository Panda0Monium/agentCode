"""
Shared machinery for every agent architecture.

The pieces here are deliberately small and boring. An architecture is defined by
*how it orchestrates* these primitives, not by clever behaviour hidden inside
them — so resist the urge to add parameters to ``run_tool_loop`` to serve one
variant. Two variants duplicating a little orchestration is correct; a single
loop with a dozen flags makes the comparison meaningless.

Primitives:
    make_llm()       - build the provider client (one place reading env vars)
    Conversation     - the single choke point through which all LLM calls pass
    run_tool_loop()  - the classic think/act/observe loop, reusable as any
                       variant's "act" phase
    ask()            - a one-shot, tool-free call for planning / reflection /
                       critique text
"""

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from environment.session import Session

from . import toolkit
from .prompts import CONTINUE_NUDGE

if TYPE_CHECKING:  # pragma: no cover
    from .budget import Budget


# ------------------------------------------------------------------
# Context handed to every architecture at build time
# ------------------------------------------------------------------

@dataclass(frozen=True)
class AgentContext:
    """
    Everything an architecture is allowed to know before the episode starts.

    Deliberately does not include the Session — that arrives at call time, so a
    single built agent could in principle be reused across episodes.
    """

    instruction: str
    task_name: str = ""
    difficulty: str = ""
    language: str = "python"
    budget: Optional["Budget"] = None
    options: dict = field(default_factory=dict)

    def opt(self, key: str, default=None):
        return self.options.get(key, default)


# ------------------------------------------------------------------
# Provider client
# ------------------------------------------------------------------

def make_llm(with_tools: bool = True):
    """
    Build the provider client from environment variables.

    AGENTCODE_API_KEY / AGENTCODE_API_URL are required; AGENTCODE_MODEL
    defaults to "default". This is the only place in the package that reads
    them, so swapping providers is a one-function change.
    """
    llm = ChatOpenAI(
        model=os.environ.get("AGENTCODE_MODEL", "default"),
        api_key=os.environ["AGENTCODE_API_KEY"],
        base_url=os.environ["AGENTCODE_API_URL"],
    )
    return llm.bind_tools(toolkit.TOOL_SCHEMAS) if with_tools else llm


def text_of(response) -> str:
    """
    Extract plain text from a response, tolerating providers that return
    content as a list of parts rather than a string.
    """
    content = getattr(response, "content", response)
    if isinstance(content, list):
        parts = [p.get("text", "") for p in content if isinstance(p, dict)]
        return " ".join(p for p in parts if p).strip()
    return (content or "").strip()


# ------------------------------------------------------------------
# Conversation — the single LLM choke point
# ------------------------------------------------------------------

class Conversation:
    """
    Wraps the provider client so that *every* LLM call in an episode is
    counted and logged the same way, no matter which sub-loop of which
    architecture made it.

    Two clients are held: one with tools bound (for act loops) and one without
    (for planning, reflection and critique). Using the tool-free client for
    thinking steps means a planner physically cannot start editing files.
    """

    def __init__(self, session: Session, budget=None, llm=None, tool_llm=None):
        self.session = session
        self.budget = budget
        self._llm = llm
        self._tool_llm = tool_llm

    @property
    def llm(self):
        if self._llm is None:
            self._llm = make_llm(with_tools=False)
        return self._llm

    @property
    def tool_llm(self):
        if self._tool_llm is None:
            self._tool_llm = make_llm(with_tools=True)
        return self._tool_llm

    def invoke(self, messages: list, *, tools: bool = True) -> AIMessage:
        if self.budget is not None:
            # Check before spending, so exhaustion never leaves a half-paid call.
            self.budget.check()

        response = (self.tool_llm if tools else self.llm).invoke(messages)

        usage = None
        if self.budget is not None:
            # messages are passed so the estimate fallback has something to
            # measure when the provider reports no usage.
            usage = self.budget.charge(response, messages)

        self.session.log_llm(messages, response, usage=usage)
        return response


# ------------------------------------------------------------------
# The act loop
# ------------------------------------------------------------------

def run_tool_loop(
    conv: Conversation,
    messages: list,
    max_turns: int,
    stop_when: Optional[Callable[[list], bool]] = None,
) -> list:
    """
    Think → act → observe, until the model stops calling tools or the turn
    budget runs out. Returns the message list, mutated in place.

    This is the original ReAct loop, unchanged: the same turn accounting, the
    same handling of parallel tool calls, and the same nudge-then-give-up
    behaviour when a model returns blank content. Every architecture uses it
    for its "act" phases, which is what keeps them comparable.

    ``stop_when`` is checked after each completed turn, letting a caller end a
    phase early (e.g. once tests pass) without reaching into the loop body.
    """
    empty_turns = 0
    turns = 0

    while turns < max_turns:
        response: AIMessage = conv.invoke(messages)
        messages.append(response)
        turns += 1

        if not response.tool_calls:
            if not text_of(response):
                # Model returned a blank response — nudge it once, then give up
                empty_turns += 1
                if empty_turns < 3:
                    messages.append(HumanMessage(content=CONTINUE_NUDGE))
                    continue
            break

        empty_turns = 0
        for call in response.tool_calls:
            try:
                result = toolkit.dispatch(call["name"], call["args"], conv.session)
            except Exception as exc:
                result = f"Error: {exc}"

            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))

        if stop_when is not None and stop_when(messages):
            break

    return messages


# ------------------------------------------------------------------
# One-shot thinking step
# ------------------------------------------------------------------

def files_written(session: Session) -> list[str]:
    """Paths the agent has written so far, most recent last, de-duplicated."""
    return list(dict.fromkeys(
        a.args["path"] for a in session.trajectory
        if a.tool == "write_file" and "path" in a.args
    ))


def read_current_state(session: Session, paths: list[str], limit: int = 4000) -> str:
    """
    Render the current contents of the given files.

    Architectures that fill in code section by section need the *current* file
    on hand before each step, because write_file replaces whole files — working
    from a stale copy silently discards earlier work.
    """
    blocks = []
    for path in paths:
        try:
            content = session.read_file(path)
        except Exception as exc:
            blocks.append(f"--- {path} ---\n(could not read: {exc})")
            continue
        truncated = content[:limit]
        suffix = "\n... (truncated)" if len(content) > limit else ""
        blocks.append(f"--- {path} ---\n{truncated}{suffix}")
    return "\n\n".join(blocks) if blocks else "(no files written yet)"


def ground_truth(session: Session) -> tuple:
    """
    Run tests and lint directly, without asking the model.

    Architectures that loop on their own output must not trust the model's
    account of whether it succeeded — that is precisely the thing models are
    bad at. Returns (TestResult, LintResult).
    """
    return session.run_tests(), session.run_lint()


def ask(conv: Conversation, messages: list) -> str:
    """
    A single tool-free LLM call returning plain text.

    Used for the reasoning artefacts that distinguish architectures — plans,
    skeletons, reflections, critiques. Tool-free by construction so these steps
    cannot accidentally mutate the repo.
    """
    response = conv.invoke(messages, tools=False)
    return text_of(response)
