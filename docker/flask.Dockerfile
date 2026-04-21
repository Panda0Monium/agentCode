FROM agentcode-base
RUN pip install --no-cache-dir flask>=3.0 requests>=2.31
WORKDIR /repo
CMD ["sleep", "infinity"]
