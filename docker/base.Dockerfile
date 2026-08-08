FROM python:3.12-slim

# Versions are quoted AND exact, both deliberately.
#
# Quoted: `pip install pytest>=8.0` in a shell RUN is parsed as a redirection —
# it installs unpinned pytest and creates a file called `=8.0`. Every constraint
# here was silently inert, and the stray files are still visible at / in images
# built before this was fixed.
#
# Exact: the installed ruff decides lint_score, and pytest decides what counts
# as a passing test, so both are part of the reward function. Floating them
# means an image rebuilt on a different day scores the same agent differently —
# ruff in particular has widened its default rule set over time, which silently
# reprices every task. Bump these deliberately, and re-baseline when you do.
RUN pip install --no-cache-dir \
    "pytest==9.1.1" \
    "pytest-json-report==1.5.0" \
    "ruff==0.16.2"
WORKDIR /repo
CMD ["sleep", "infinity"]
