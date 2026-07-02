"""AI layer: subscription-backed Claude Code CLI in headless mode.

Uses CLAUDE_CODE_OAUTH_TOKEN (from `claude setup-token`, Max subscription) —
no API billing. The model gets a pre-collected data snapshot and NO tools:
the bot gathers all numbers itself, Claude only interprets and phrases.
Everything degrades gracefully: no token / CLI failure -> None, callers
fall back to the deterministic rendering.
"""

import json
import logging
import os
import subprocess

log = logging.getLogger(__name__)

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
AI_TIMEOUT = int(os.environ.get("AI_TIMEOUT", "180"))

SYSTEM_CONTEXT = """Ты — ассистент по инфраструктуре платформы Russmarket 360 (полевые продажи: промоутеры, банковские карты, склады).
Стек: 4 Laravel-сервиса (rusaifin — основной монолит field sales, rusaicore — core-домен, rusaiauth — OAuth2/OIDC SSO, rusaisklad — склад) + 2 Nuxt-фронта. Прод — один сервер, мониторинг Prometheus/Loki/Grafana.
Отвечай по-русски, кратко и по делу, без воды. Числа округляй по-человечески. Если в данных чего-то нет — так и скажи, не выдумывай."""


def available():
    return bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))


def _run(prompt):
    if not available():
        return None
    try:
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", "sonnet",
             "--disallowedTools", "Bash,Edit,Write,WebFetch,WebSearch"],
            capture_output=True,
            text=True,
            timeout=AI_TIMEOUT,
            env={**os.environ, "HOME": os.environ.get("HOME", "/home/bot")},
        )
        if proc.returncode != 0:
            log.warning("claude CLI rc=%s: %s", proc.returncode, proc.stderr[-500:])
            return None
        out = proc.stdout.strip()
        return out or None
    except subprocess.TimeoutExpired:
        log.warning("claude CLI timed out after %ss", AI_TIMEOUT)
        return None
    except FileNotFoundError:
        log.warning("claude CLI not found")
        return None


def report_summary(report_data):
    """3-6 sentence analyst take for the daily report, or None."""
    prompt = (
        SYSTEM_CONTEXT
        + "\n\nНиже — сводка метрик платформы за последние 24 часа (JSON). "
        "Напиши короткое резюме для ежедневного отчёта: 3–6 предложений. "
        "Сначала общий вердикт одним предложением (всё спокойно / есть на что посмотреть / есть проблема). "
        "Потом только то, что реально заслуживает внимания: аномалии, тревожные тренды, странности. "
        "Не пересказывай цифры, которые и так в отчёте. Без заголовков и списков, просто текст.\n\n"
        + json.dumps(report_data, ensure_ascii=False, default=str)
    )
    return _run(prompt)


def answer_question(question, context_data):
    """Free-text Q&A over a pre-collected snapshot, or None."""
    prompt = (
        SYSTEM_CONTEXT
        + "\n\nТебе задали вопрос в Telegram-чате мониторинга. "
        "Ниже — свежий снапшот данных платформы (JSON): статус сервисов за 1ч и 24ч, "
        "воронка входов, алерты, деплои, дрейф репозиториев, хост, последние ошибки из логов. "
        "Ответь на вопрос по этим данным. Если данных для точного ответа нет — скажи, "
        "каких именно, и предложи команду бота (/status /errors /top /disk /alerts /digest) "
        "или запрос в Grafana.\n\n"
        f"ВОПРОС: {question}\n\nДАННЫЕ:\n"
        + json.dumps(context_data, ensure_ascii=False, default=str)
    )
    return _run(prompt)
