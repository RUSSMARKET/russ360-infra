# RSM Infra Bot: python bot + Claude Code CLI (subscription-backed AI layer).
FROM node:22-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

COPY *.py ./

# non-root: claude CLI needs a writable HOME
RUN useradd -m -u 10001 bot && mkdir -p /data && chown bot /data
USER bot
ENV HOME=/home/bot

CMD ["/venv/bin/python", "bot.py"]
