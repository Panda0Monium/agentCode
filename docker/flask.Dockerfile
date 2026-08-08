FROM agentcode-base
# Quoted and pinned — see base.Dockerfile. Unquoted `flask>=3.0` was parsed as a
# shell redirection, so the constraint never applied and the version floated.
RUN pip install --no-cache-dir "flask==3.1.3" "requests==2.34.2"
WORKDIR /repo
CMD ["sleep", "infinity"]
