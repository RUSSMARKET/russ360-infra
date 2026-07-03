# obs-agent — hardened read-only investigator. Claude Code CLI + a tiny stdlib
# HTTP server (no pip deps). Runs as a non-root user; the model-facing filesystem
# is only /prod (ro-mounted prod code) + an empty /work cwd, so read tools reach
# nothing sensitive. HOME (claude config/token cache) sits OUTSIDE the workspace,
# so the Read tool — confined to cwd + --add-dir /prod — cannot reach it.
FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code

# venv for the MCP servers (FastMCP) + HTTP/DB clients
RUN python3 -m venv /venv \
    && /venv/bin/pip install --no-cache-dir mcp requests pymysql cryptography psycopg2-binary

RUN useradd -m -u 10002 agent \
    && mkdir -p /work \
    && chown agent:agent /work

WORKDIR /work
COPY agent.py mcp_obs.py mcp_db.py mcp.json /app/

ENV HOME=/home/agent
USER agent
EXPOSE 8080
CMD ["/venv/bin/python", "/app/agent.py"]
