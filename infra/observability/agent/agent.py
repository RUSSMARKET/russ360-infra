"""obs-agent — hardened read-only investigator for the Russ360 stack.

Exposes an internal-only HTTP endpoint `POST /ask {question, context?} -> {answer}`.
On each request it runs Claude Code CLI headless with ONLY read-only file tools
(Read/Grep/Glob) over the production source code, which is bind-mounted read-only
under /prod (secrets — .env, keys — are never mounted).

Deliberately powerless in every other direction:
  - no Telegram token (cannot message anyone),
  - no outbound network except the claude subprocess via the Anthropic proxy,
  - Bash/Write/Edit/WebFetch/WebSearch are disallowed,
  - the model-facing filesystem is just this container (only /prod + an empty /work),
    so even an absolute-path Read hits nothing sensitive.

The telegram-facing bot (obs-tgbot) calls this over the internal observability
network and delivers the answer to the already access-controlled chat.
"""

import json
import logging
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("obs-agent")

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
MODEL = os.environ.get("AGENT_MODEL", "sonnet")
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "240"))
CODE_ROOT = os.environ.get("CODE_ROOT", "/prod")
PORT = int(os.environ.get("AGENT_PORT", "8080"))
# api.anthropic.com is geo-blocked from the prod host; the claude subprocess (and only
# it) is routed through the out-of-RU forward proxy. Kept off the container env so nothing
# else can use it as an egress path.
ANTHROPIC_PROXY = os.environ.get("ANTHROPIC_PROXY")

MCP_CONFIG = os.environ.get("MCP_CONFIG", "/app/mcp.json")
ALLOWED_TOOLS = (
    "Read,Grep,Glob,"
    "mcp__obs__metrics,mcp__obs__logs,mcp__obs__list_metrics,"
    "mcp__db__query"
)
DISALLOWED_TOOLS = "Bash,Edit,Write,WebFetch,WebSearch,NotebookEdit"

SYSTEM_CONTEXT = """Ты — read-only SRE-агент платформы Russmarket 360 (полевые продажи: промоутеры, банковские карты, склады).
Стек: 4 Laravel-сервиса — rusaifin (основной монолит field sales), rusaicore (core-домен: Employee/Project/Membership/Location), rusaiauth (OAuth2/OIDC SSO), rusaisklad (склад) — плюс 2 Nuxt-фронта. Прод — один сервер, мониторинг Prometheus/Loki/Grafana.

У тебя есть ИНСТРУМЕНТЫ (только чтение):
1. Код прода — Read, Grep, Glob. Код под {code_root}/: бэкенды rusaifin/, rusaicore/, rusaiauth/, rusaisklad/ (каталоги app/ config/ routes/ database/ resources/); фронты fintech-front/src/, sklad-front/src/ (Nuxt, OIDC/PKCE-клиент в src/shared/lib/); infra/ (репо мониторинга). Секретов (.env, ключи) там нет — не смонтированы.
2. Метрики — mcp__obs__metrics(promql): любой PromQL к Prometheus. list_metrics(prefix) — найти метрику.
3. Логи — mcp__obs__logs(service, filter, minutes): строки из Loki по сервису.
4. БД прода (read-only SELECT) — mcp__db__query(datasource, sql): fintech_base (MySQL rusaifin — промоутеры/смены/карты/оформление), rusaicore_prod (PG Core — employees/projects/memberships/locations), rusaisklad_prod_db (PG склад — остатки/перемещения/инвентаризации). Схему смотри через information_schema. В БД есть PII — это ок. (auth-БД недоступна намеренно.)

Когда вопрос про поведение кода/роуты/логику — НЕ гадай, сходи Grep/Glob/Read, отвечай по факту, указывай файл:строку.
Когда вопрос про метрики/латенси/ошибки/тренды — не ограничивайся снапшотом ниже, сам дотяни нужное через metrics()/logs().
Когда вопрос про бизнес-данные (сколько промоутеров/карт/смен/остатков, кто в каком проекте) — сходи в БД через db.query, при незнании схемы сначала посмотри information_schema.

Отвечай по-русски, кратко и по делу, без воды. Не выдумывай: если данных или кода не нашёл — так и скажи.
Формат — Telegram-чат, не Markdown-документ: без таблиц, без ** и __, без заголовков #. Обычный текст, списки короткими строками."""


def build_prompt(question, context):
    parts = [SYSTEM_CONTEXT.format(code_root=CODE_ROOT)]
    parts.append(
        "\nТебе задали вопрос в чате мониторинга. Ниже — свежий снапшот метрик платформы (JSON): "
        "статус сервисов за 1ч и 24ч, воронка входов, алерты, деплои, дрейф, хост, последние ошибки логов. "
        "Ответь по снапшоту И, если нужно, по коду прода через Read/Grep/Glob."
    )
    parts.append(f"\nВОПРОС: {question}")
    if context is not None:
        parts.append("\nСНАПШОТ:\n" + json.dumps(context, ensure_ascii=False, default=str))
    return "\n".join(parts)


def run_claude(prompt):
    if not os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        log.warning("no CLAUDE_CODE_OAUTH_TOKEN — agent disabled")
        return None
    env = {**os.environ, "HOME": os.environ.get("HOME", "/home/agent")}
    if ANTHROPIC_PROXY:
        env["HTTPS_PROXY"] = ANTHROPIC_PROXY
        env["HTTP_PROXY"] = ANTHROPIC_PROXY
        # the MCP obs server (spawned by claude, inherits this env) must reach the
        # internal obs stack directly, not via the Anthropic proxy.
        env["NO_PROXY"] = "obs-prometheus,obs-loki,obs-grafana,localhost,127.0.0.1"
    try:
        proc = subprocess.run(
            [
                CLAUDE_BIN, "-p", prompt,
                "--model", MODEL,
                "--add-dir", CODE_ROOT,
                "--mcp-config", MCP_CONFIG,
                "--strict-mcp-config",
                "--allowedTools", ALLOWED_TOOLS,
                "--disallowedTools", DISALLOWED_TOOLS,
            ],
            capture_output=True, text=True, timeout=AI_TIMEOUT, env=env, cwd="/work",
        )
        if proc.returncode != 0:
            log.warning("claude rc=%s: %s", proc.returncode, proc.stderr[-800:])
            return None
        return proc.stdout.strip() or None
    except subprocess.TimeoutExpired:
        log.warning("claude timed out after %ss", AI_TIMEOUT)
        return None
    except FileNotFoundError:
        log.warning("claude CLI not found")
        return None


class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"ok": True, "ai": bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))})
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/ask":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._json(400, {"error": "bad json"})
            return
        question = (body.get("question") or "").strip()
        if not question:
            self._json(400, {"error": "no question"})
            return
        log.info("ask: %r", question[:80])
        answer = run_claude(build_prompt(question, body.get("context")))
        self._json(200, {"answer": answer})

    def log_message(self, *args):
        pass  # keep stdout clean; we log what matters ourselves


def main():
    log.info("obs-agent on :%s, model=%s, proxy=%s", PORT, MODEL, "on" if ANTHROPIC_PROXY else "off")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
