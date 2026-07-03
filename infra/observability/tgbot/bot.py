"""RSM Infra Bot — interactive observability bot for the Russ360 stack.

Long-polls the same telegram bot Grafana uses for alert delivery (Grafana only
calls sendMessage, so polling does not conflict). Features:
  - commands: /status /errors /top /disk /alerts /digest /selfcheck /help
  - daily report at 17:20 MSK (deterministic numbers + optional AI summary)
  - proactive messages: deploy/drift events from the host-side checker,
    watchdog state changes (obs components down/up)
  - free-text questions answered by the AI layer (reply/mention in the group,
    or any text in private chat with a group member)
"""

import asyncio
import datetime
import html
import json
import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import aihelper
import datasources as ds
import report as report_mod

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tgbot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TG_CHAT_ID"])
DATA_DIR = os.environ.get("BOT_DATA_DIR", "/data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
MSK = datetime.timezone(datetime.timedelta(hours=3))
REPORT_TIME = datetime.time(hour=17, minute=20, tzinfo=MSK)


# ---- state ---------------------------------------------------------------

def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE_PATH)


# ---- access control ------------------------------------------------------

async def allowed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat = update.effective_chat
    if chat is None:
        return False
    if chat.id == CHAT_ID:
        return True
    if chat.type == "private" and update.effective_user:
        try:
            member = await context.bot.get_chat_member(CHAT_ID, update.effective_user.id)
            return member.status in ("creator", "administrator", "member")
        except Exception:
            return False
    return False


# ---- formatting helpers ---------------------------------------------------

def esc(s):
    return html.escape(str(s), quote=False)


PROGRESS_PHRASES = [
    "🤔 Думаю…",
    "⚙️ Обрабатываю…",
    "🧠 Размышляю…",
    "😤 Напрягаюсь…",
    "🔥 Сжигаю токены…",
    "📚 Поднимаю архивы…",
    "🔍 Разбираюсь…",
]

# Global cursor into PROGRESS_PHRASES, persisted across messages so each new
# response picks up where the previous left off instead of restarting the cycle.
_phrase_cursor = 0


def _next_phrase():
    global _phrase_cursor
    phrase = PROGRESS_PHRASES[_phrase_cursor % len(PROGRESS_PHRASES)]
    _phrase_cursor += 1
    return phrase


async def _animate(bot, chat_id, message):
    """Advance the placeholder phrase + refresh 'typing…' every 10s until cancelled
    (the Telegram typing indicator expires after ~5s, so refresh faster than that)."""
    try:
        while True:
            await asyncio.sleep(5)
            try:
                await bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            await asyncio.sleep(5)  # 10s total between phrase changes
            try:
                await bot.send_chat_action(chat_id, "typing")
                await message.edit_text(_next_phrase())
            except Exception:
                pass  # message unchanged / rate limit — keep going
    except asyncio.CancelledError:
        pass


async def send_long(bot, chat_id, text, parse_mode=ParseMode.HTML):
    for chunk_start in range(0, len(text), 4000):
        chunk = text[chunk_start : chunk_start + 4000]
        try:
            await bot.send_message(
                chat_id, chunk, parse_mode=parse_mode, disable_web_page_preview=True,
            )
        except BadRequest as e:
            # Never let a stray unescaped <...> in dynamic content swallow the whole
            # answer — fall back to plain text so the user still gets the content.
            log.warning("HTML send failed (%s); resending as plain text", e)
            await bot.send_message(chat_id, chunk, disable_web_page_preview=True)


async def run_with_progress(update, context, work, empty="Пусто."):
    """Standard response mechanic for every command that does real work.

    Shows an animated placeholder (cycling phrases + typing), runs `work` (a sync
    callable returning the final HTML string) in a thread, then DELETES the
    placeholder and sends the answer as a FRESH message — the disappear+appear
    reads as a clean reveal. Any new long-running command gets this for free by
    routing through here.
    """
    chat_id = update.effective_chat.id
    placeholder = await update.message.reply_text(_next_phrase())
    anim = asyncio.create_task(_animate(context.bot, chat_id, placeholder))
    try:
        result = await asyncio.to_thread(work)
    except Exception:
        log.exception("command work failed")
        result = "⚠️ Ошибка при выполнении команды (залогировано). Попробуй ещё раз или /selfcheck"
    finally:
        anim.cancel()
    try:
        await placeholder.delete()
    except Exception:
        pass
    await send_long(context.bot, chat_id, result or empty)


def fmt_status():
    snap = ds.service_snapshot(hours=1)
    host = ds.host_snapshot()
    alerts = ds.grafana_active_alerts()
    down = ds.scrape_targets_down()

    lines = ["<b>Статус (prod, за час)</b>", ""]
    for svc, m in snap.items():
        p95 = f"{m['p95']:.2f}s" if m["p95"] is not None else "–"
        mark = "🟢"
        if m["errors_5xx"] > 0 or m["exceptions"] > 0:
            mark = "🟡"
        if any(j == svc for j, _ in down):
            mark = "🔴"
        extra = []
        if m["errors_5xx"]:
            extra.append(f"5xx: {int(m['errors_5xx'])}")
        if m["exceptions"]:
            extra.append(f"exc: {int(m['exceptions'])}")
        extra_s = (" ⚠️ " + ", ".join(extra)) if extra else ""
        lines.append(f"{mark} {svc}: {int(m['requests'])} req, p95 {p95}{extra_s}")

    lines.append("")
    if alerts:
        lines.append(f"🔥 Активных алертов: {len(alerts)}")
        for a in alerts[:5]:
            tgt = "/".join(x for x in (a["service"], a["env"]) if x)
            lines.append(f"• {esc(a['name'])}{f' ({tgt})' if tgt else ''}")
    elif alerts is not None:
        lines.append("✅ Алертов нет")
    else:
        lines.append("⚠️ Grafana недоступна")
    if down:
        lines.append("🔴 Не скрейпятся: " + ", ".join(f"{j}/{e}" for j, e in down))

    bits = []
    if host["disk_used_pct"] is not None:
        bits.append(f"диск {host['disk_used_pct']:.0f}%")
    if host["mem_used_pct"] is not None:
        bits.append(f"RAM {host['mem_used_pct']:.0f}%")
    if host["active_sessions"] is not None:
        bits.append(f"онлайн ~{int(host['active_sessions'])}")
    if bits:
        lines.append("")
        lines.append("Хост: " + ", ".join(bits))
    return "\n".join(lines)


def build_ai_context():
    """Snapshot handed to the AI layer for free-text questions."""
    return {
        "now_msk": datetime.datetime.now(tz=MSK).isoformat(timespec="minutes"),
        "services_1h": ds.service_snapshot(hours=1),
        "services_24h": ds.service_snapshot(hours=24),
        "logins_24h": ds.login_snapshot(hours=24),
        "host": ds.host_snapshot(),
        "active_alerts": ds.grafana_active_alerts(),
        "alert_history_24h": ds.grafana_alert_history(hours=24),
        "targets_down": ds.scrape_targets_down(),
        "top_slow_routes_1h": ds.top_routes(minutes=60),
        "recent_errors_rusaifin": [l for _, l in ds.recent_errors("rusaifin", 60, 10)],
        "recent_errors_rusaiauth": [l for _, l in ds.recent_errors("rusaiauth", 60, 10)],
        "drift": report_mod.read_drift(),
    }


# ---- command handlers ------------------------------------------------------

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    ai_note = (
        "\n\nМожно спросить свободным текстом (в группе — реплаем на меня или с упоминанием, "
        "в личке — просто текстом): «сколько логинов упало вчера?», «что с латенси финтеха?»"
        if aihelper.available()
        else "\n\nAI-режим выключен (нет токена) — доступны только команды."
    )
    await update.message.reply_text(
        "<b>Команды:</b>\n"
        "/status — сводка по сервисам за час\n"
        "/digest — полный отчёт за 24ч (как ежедневный)\n"
        "/errors &lt;сервис&gt; [минут] — последние ошибки из логов (rusaifin 60 по умолчанию)\n"
        "/top — самые медленные роуты rusaifin за час\n"
        "/alerts — активные алерты\n"
        "/disk — диск/память/load\n"
        "/selfcheck — здоровье самого мониторинга\n"
        "/help — это сообщение" + ai_note,
        parse_mode=ParseMode.HTML,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, fmt_status)


async def cmd_digest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, lambda: build_report_text(with_ai=True))


def _errors_text(service, minutes):
    lines = ds.recent_errors(service, minutes, 12)
    if not lines:
        return f"✅ {service}: ошибок в логах за {minutes} мин не найдено"
    out = [f"<b>{service}: ошибки за {minutes} мин</b> (новые сверху)\n"]
    for ts, line in lines:
        t = datetime.datetime.fromtimestamp(ts, tz=MSK).strftime("%H:%M")
        out.append(f"<code>{t}</code> {esc(line[:300])}")
    return "\n".join(out)


async def cmd_errors(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    args = context.args or []
    service = args[0] if args else "rusaifin"
    if service not in ds.SERVICES:
        await update.message.reply_text("Не знаю такой сервис. Есть: " + ", ".join(ds.SERVICES))
        return
    minutes = 60
    if len(args) > 1 and args[1].isdigit():
        minutes = min(int(args[1]), 24 * 60)
    await run_with_progress(update, context, lambda: _errors_text(service, minutes))


def _top_text():
    routes = ds.top_routes(60, 8)
    if not routes:
        return "Недостаточно трафика за час для топа."
    lines = ["<b>Самые медленные роуты rusaifin (за час, avg)</b>", ""]
    for r in routes:
        lines.append(f"• <code>{esc(r['route'])}</code> — {r['avg_s']:.2f}s ({int(r['count'])} req)")
    return "\n".join(lines)


async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, _top_text)


def _alerts_text():
    alerts = ds.grafana_active_alerts()
    if alerts is None:
        return "⚠️ Grafana недоступна"
    if not alerts:
        return "✅ Активных алертов нет"
    lines = [f"<b>Активные алерты: {len(alerts)}</b>", ""]
    for a in alerts[:15]:
        tgt = "/".join(x for x in (a["service"], a["env"]) if x)
        sev = f" [{a['severity']}]" if a["severity"] else ""
        lines.append(f"🔥 {esc(a['name'])}{f' ({tgt})' if tgt else ''}{sev}")
        if a["summary"]:
            lines.append(f"   {esc(a['summary'])}")
    return "\n".join(lines)


async def cmd_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, _alerts_text)


def _disk_text():
    h = ds.host_snapshot()
    parts = []
    if h["disk_used_pct"] is not None:
        parts.append(f"💾 Диск: {h['disk_used_pct']:.1f}% занято")
    if h["mem_used_pct"] is not None:
        parts.append(f"🧠 RAM: {h['mem_used_pct']:.0f}%")
    if h["load15"] is not None:
        parts.append(f"⚙️ load15: {h['load15']:.2f}")
    return "\n".join(parts) or "Метрики хоста недоступны ⚠️"


async def cmd_disk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, _disk_text)


def _selfcheck_text():
    checks = ds.health()
    state = load_state()
    lines = ["<b>Self-check мониторинга</b>", ""]
    for name, ok in checks.items():
        lines.append(f"{'✅' if ok else '🔴'} {name}")
    lines.append(f"{'✅' if aihelper.available() else '⚪'} AI-слой "
                 f"({'включён' if aihelper.available() else 'нет токена'})")

    drift = report_mod.read_drift()
    if drift and drift.get("checked_at"):
        age_min = (datetime.datetime.now(tz=MSK).timestamp() - drift["checked_at"]) / 60
        mark = "✅" if age_min < 60 else "🔴"
        lines.append(f"{mark} drift-checker: обновлялся {age_min:.0f} мин назад")
    else:
        lines.append("🔴 drift-checker: данных нет")

    last_report = state.get("last_report_ts")
    if last_report:
        dt = datetime.datetime.fromtimestamp(last_report, tz=MSK)
        lines.append(f"✅ последний дневной отчёт: {dt.strftime('%d.%m %H:%M')}")
    else:
        lines.append("⚪ дневной отчёт ещё не отправлялся")

    down = ds.scrape_targets_down()
    if down:
        lines.append("🔴 не скрейпятся: " + ", ".join(f"{j}/{e}" for j, e in down))
    return "\n".join(lines)


async def cmd_selfcheck(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, _selfcheck_text)


# ---- free-text (AI) --------------------------------------------------------

def _mentions_bot(msg, me):
    """True if the message @mentions the bot — matched via entities (robust to
    formatting) with a plain-substring fallback."""
    text = msg.text or ""
    handle = f"@{me}".lower()
    for ent in (msg.entities or []):
        if ent.type == "mention":
            frag = text[ent.offset : ent.offset + ent.length].lower()
            if frag == handle:
                return True
    return handle in text.lower()


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None or not msg.text or msg.text.startswith("/"):
        return
    if not await allowed(update, context):
        return

    chat = update.effective_chat
    me = context.bot.username or ""
    is_reply_to_bot = (
        msg.reply_to_message is not None
        and msg.reply_to_message.from_user is not None
        and msg.reply_to_message.from_user.id == context.bot.id
    )
    mentioned = _mentions_bot(msg, me) if me else False

    if chat.id == CHAT_ID:
        if not (is_reply_to_bot or mentioned):
            return  # group chatter the bot isn't addressed in — ignore quietly
        question = msg.text.replace(f"@{me}", "").strip() if me else msg.text.strip()
    else:
        question = msg.text.strip()
    log.info("engaging: chat=%s reply=%s mention=%s q=%r",
             chat.id, is_reply_to_bot, mentioned, question[:60])

    if not question:
        return
    if not aihelper.available():
        await msg.reply_text("AI-режим выключен (нет токена). Доступны команды — /help")
        return

    def work():
        answer = aihelper.answer_question(question, build_ai_context())
        return esc(answer) if answer else "Не смог получить ответ от AI-слоя, попробуй ещё раз или /status"

    await run_with_progress(update, context, work)


# ---- report (shared by /digest and the scheduled job) ----------------------

def build_report_text(with_ai=True):
    """Full daily-report text (deterministic numbers + optional AI summary).
    Sync — safe to run in a thread from run_with_progress or the scheduled job."""
    data = report_mod.collect()
    text = report_mod.render(data)
    if with_ai and aihelper.available():
        ai_part = aihelper.report_summary(data)
        if ai_part:
            text += "\n\n🤖 <i>" + esc(ai_part) + "</i>"
    return text


# ---- scheduled jobs ---------------------------------------------------------

async def job_daily_report(context: ContextTypes.DEFAULT_TYPE):
    try:
        text = await asyncio.to_thread(build_report_text, True)
        await send_long(context.bot, CHAT_ID, text)
        state = load_state()
        state["last_report_ts"] = datetime.datetime.now(tz=MSK).timestamp()
        save_state(state)
    except Exception:
        log.exception("daily report failed")
        try:
            await context.bot.send_message(CHAT_ID, "⚠️ Не смог собрать дневной отчёт, см. логи obs-tgbot")
        except Exception:
            pass


async def job_watchdog(context: ContextTypes.DEFAULT_TYPE):
    """Report obs-stack component state CHANGES (quiet while everything is fine)."""
    checks = await asyncio.to_thread(ds.health)
    state = load_state()
    prev = state.get("watchdog", {})
    changed = []
    for name, ok in checks.items():
        was_ok = prev.get(name, True)
        if ok != was_ok:
            changed.append((name, ok))
    if changed:
        lines = []
        for name, ok in changed:
            lines.append(f"{'✅' if ok else '🔴'} {name}: {'снова доступен' if ok else 'НЕДОСТУПЕН'}")
        try:
            await context.bot.send_message(
                CHAT_ID, "🩺 <b>Watchdog</b>\n" + "\n".join(lines), parse_mode=ParseMode.HTML
            )
        except Exception:
            log.exception("watchdog notify failed")
    state["watchdog"] = checks
    save_state(state)


async def job_events(context: ContextTypes.DEFAULT_TYPE):
    """Push new deploy/drift events written by the host-side checker."""
    path = os.path.join(DATA_DIR, "events.jsonl")
    state = load_state()
    offset = state.get("events_offset", 0)
    try:
        size = os.path.getsize(path)
    except FileNotFoundError:
        return
    if size < offset:  # rotated/truncated: skip history, don't repost it
        state["events_offset"] = size
        save_state(state)
        return
    if size == offset:
        return
    with open(path) as f:
        f.seek(offset)
        new_lines = f.read()
        state["events_offset"] = f.tell()
    save_state(state)

    msgs = []
    for line in new_lines.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = e.get("type")
        if etype == "deploy":
            msgs.append(f"🚀 <b>Деплой:</b> {esc(e.get('repo', '?'))} — {esc(e.get('detail', ''))}")
        elif etype == "drift":
            msgs.append(f"⚠️ <b>Дрейф репо:</b> {esc(e.get('repo', '?'))} — {esc(e.get('detail', ''))}")
    if msgs:
        try:
            await send_long(context.bot, CHAT_ID, "\n".join(msgs[:20]))
        except Exception:
            log.exception("events notify failed")


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Never let a handler exception kill a command silently (2-week unattended run)."""
    log.exception("handler error", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Не смог выполнить команду (ошибка залогирована). Попробуй ещё раз или /selfcheck"
            )
        except Exception:
            pass


async def post_init(app: Application):
    log.info("bot started, AI layer: %s", "on" if aihelper.available() else "off")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("report", cmd_digest))
    app.add_handler(CommandHandler("errors", cmd_errors))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("disk", cmd_disk))
    app.add_handler(CommandHandler("selfcheck", cmd_selfcheck))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    jq = app.job_queue
    jq.run_daily(job_daily_report, time=REPORT_TIME, name="daily_report")
    jq.run_repeating(job_watchdog, interval=600, first=60, name="watchdog")
    jq.run_repeating(job_events, interval=60, first=30, name="events")

    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
