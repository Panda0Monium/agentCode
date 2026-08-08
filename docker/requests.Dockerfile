FROM agentcode-base
# Quoted and pinned — see base.Dockerfile. Unquoted `requests>=2.31` was parsed
# as a shell redirection, so the constraint never applied.
RUN pip install --no-cache-dir "requests==2.34.2"
WORKDIR /repo
CMD ["sleep", "infinity"]
