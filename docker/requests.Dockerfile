FROM agentcode-base
RUN pip install --no-cache-dir requests>=2.31
WORKDIR /repo
CMD ["sleep", "infinity"]
