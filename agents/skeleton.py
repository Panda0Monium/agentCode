"""
Skeleton-of-thought.

Outline the whole solution first — signatures and docstrings with `...` bodies
— write that skeleton, then fill in one section at a time. Committing to the
shape of the answer before any detail is meant to stop the agent painting
itself into a corner on the first function it writes.

There is a structural hazard here worth stating plainly. The only editing tool
is write_file, which replaces an entire file; there is no patch tool. So every
fill step can clobber sections filled earlier. Two mitigations: the file's
current contents are read by the harness and injected before each fill step, so
the model is never working from a stale copy, and the prompt insists on
re-emitting the complete file. If this variant still underperforms ReAct, a
real patch_file tool is the honest fix rather than more prompt engineering.
"""

import re
from collections.abc import Callable

from langchain_core.messages import HumanMessage, SystemMessage

from environment.session import Session

from .base import (
    AgentContext,
    Conversation,
    ask,
    files_written,
    read_current_state,
    run_tool_loop,
)
from .prompts import (
    ORIENT_SYSTEM,
    SECTION_FILL_SYSTEM,
    SKELETON_PROMPT,
    SKELETON_WRITE_SYSTEM,
    VERIFY_SYSTEM,
)
from .registry import AgentSpec, register

ORIENT_TURNS = 4
WRITE_TURNS = 3
FILL_TURNS = 4
VERIFY_TURNS = 8
MAX_SECTIONS = 8

# Top-level or indented def/class, capturing the name.
_SECTION_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")


def parse_sections(skeleton: str, max_sections: int = MAX_SECTIONS) -> list[str]:
    """
    Names of the functions and classes to fill in, in source order.

    Dunder methods are skipped — they are usually trivial and not worth a whole
    fill round each.
    """
    names = []
    for line in skeleton.splitlines():
        m = _SECTION_RE.match(line)
        if not m:
            continue
        name = m.group(1)
        if name.startswith("__") and name.endswith("__"):
            continue
        if name not in names:
            names.append(name)
    return names[:max_sections]


def build(ctx: AgentContext) -> Callable[[Session], None]:
    def _agent(session: Session) -> None:
        conv = Conversation(session, budget=ctx.budget)

        # 1. Orient.
        run_tool_loop(
            conv,
            [SystemMessage(content=ORIENT_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("orient_turns", ORIENT_TURNS),
        )

        # 2. Outline the whole solution, tool-free.
        skeleton = ask(conv, [HumanMessage(content=SKELETON_PROMPT.format(instruction=ctx.instruction))])
        sections = parse_sections(skeleton, ctx.opt("max_sections", MAX_SECTIONS))
        session.log_note("skeleton", skeleton, sections=len(sections))

        # 3. Write the skeleton out.
        run_tool_loop(
            conv,
            [
                SystemMessage(content=SKELETON_WRITE_SYSTEM.format(skeleton=skeleton)),
                HumanMessage(content="Write the skeleton to the appropriate file(s)."),
            ],
            max_turns=ctx.opt("write_turns", WRITE_TURNS),
        )

        # 4. Fill section by section, always against freshly-read contents.
        for idx, section in enumerate(sections, start=1):
            targets = files_written(session)
            if not targets:
                break  # nothing landed; the verify phase will have to recover
            state = read_current_state(session, targets)
            session.log_note("phase", section, section=idx, of=len(sections))

            run_tool_loop(
                conv,
                [
                    SystemMessage(content=SECTION_FILL_SYSTEM.format(section=section, state=state)),
                    HumanMessage(content=f"Implement `{section}` now."),
                ],
                max_turns=ctx.opt("fill_turns", FILL_TURNS),
            )

        # 5. Verify — catches any section a later write clobbered.
        run_tool_loop(
            conv,
            [SystemMessage(content=VERIFY_SYSTEM), HumanMessage(content=ctx.instruction)],
            max_turns=ctx.opt("verify_turns", VERIFY_TURNS),
        )

    return _agent


register(
    AgentSpec(
        name="skeleton",
        label="Skeleton of thought",
        description="Outlines the full solution structure first, then fills in each section.",
        build=build,
        default_options={
            "orient_turns": ORIENT_TURNS,
            "write_turns": WRITE_TURNS,
            "fill_turns": FILL_TURNS,
            "verify_turns": VERIFY_TURNS,
            "max_sections": MAX_SECTIONS,
        },
        time_multiplier=2.0,
    )
)
