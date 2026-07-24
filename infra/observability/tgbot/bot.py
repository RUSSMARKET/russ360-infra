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
import inspect
import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import requests

import aihelper
import datasources as ds
import report as report_mod
import tgformat

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("tgbot")

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = int(os.environ["TG_CHAT_ID"])
AGENT_URL = os.environ.get("AGENT_URL", "http://obs-agent:8080")
AGENT_TIMEOUT = int(os.environ.get("AGENT_TIMEOUT", "255"))
DATA_DIR = os.environ.get("BOT_DATA_DIR", "/data")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
MEM_DIR = os.environ.get("MEM_DIR", "/memory")  # shared with obs-agent (episodic capture)
MEDIA_DIR = os.environ.get("MEDIA_DIR", "/media")  # shared with obs-agent (downloaded photos)
MEDIA_TTL = 6 * 3600
MSK = datetime.timezone(datetime.timedelta(hours=3))
REPORT_TIME = datetime.time(hour=17, minute=20, tzinfo=MSK)

# A chat "session" is the run of messages with no gap longer than this; any activity
# (including colleagues talking to each other) keeps it alive, a longer silence starts fresh.
SESSION_GAP = int(os.environ.get("SESSION_GAP_SEC", "1800"))  # 30 min
SESSION_MAX_MSGS = 25

# Grafana delivers alerts here (webhook contact point -> POST /alert) instead of
# straight to telegram; the bot pre-filters obvious noise, sends the rest to the
# agent for triage, and posts only a short human-readable verdict with links.
ALERT_PORT = int(os.environ.get("ALERT_PORT", "8090"))
ALERT_DEBOUNCE_SEC = int(os.environ.get("ALERT_DEBOUNCE_SEC", "900"))  # 15 min
GRAFANA_BASE = os.environ.get("GRAFANA_PUBLIC_URL", "https://observability.rusaifin.ru").rstrip("/")
GLITCHTIP_BASE = os.environ.get("GLITCHTIP_PUBLIC_URL", "https://glitchtip.rusaifin.ru").rstrip("/")


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


CRUMB_LINES = 7  # how many recent steps to show (transcript-style)


def _read_last_crumbs(path, n=CRUMB_LINES):
    """Last n live breadcrumbs the agent wrote for this request (oldest→newest)."""
    if not path:
        return []
    try:
        with open(path) as f:
            lines = [ln for ln in f if ln.strip()]
    except (FileNotFoundError, OSError):
        return []
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln).get("text", ""))
        except json.JSONDecodeError:
            continue
    return [t for t in out if t]


async def _animate(bot, chat_id, message, req_id=None):
    """Live progress. Filler phrases cycle every 10s UNTIL the first real step from
    the agent appears; from then on the placeholder shows a growing transcript of
    what the agent is actually doing (📖 читаю…, 🗄 SQL…, 💭 наррация), like Claude
    Code, throttled to respect Telegram edit limits."""
    progress_path = os.path.join(MEM_DIR, "progress", f"{req_id}.jsonl") if req_id else None
    last_shown, got_crumb = None, False
    last_edit = 0.0
    last_phrase = time.monotonic()
    try:
        while True:
            await asyncio.sleep(1.5)
            try:
                await bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            now = time.monotonic()
            crumbs = _read_last_crumbs(progress_path)
            if crumbs:
                view = "\n".join(crumbs)[:3500]
                if view != last_shown and now - last_edit > 1.2:
                    last_shown, got_crumb, last_edit = view, True, now
                    try:
                        await message.edit_text(view)
                    except Exception:
                        pass
            elif not got_crumb and now - last_phrase >= 10:
                last_phrase = now
                try:
                    await message.edit_text(_next_phrase())
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass


def _work_takes_arg(work):
    try:
        return len(inspect.signature(work).parameters) >= 1
    except (TypeError, ValueError):
        return False


SEND_RETRIES = 3
SEND_BACKOFF = 3.0  # seconds, doubles each attempt


async def _send_message_resilient(bot, chat_id, chunk, parse_mode):
    """Send one chunk, retrying transient timeouts/network errors with backoff.

    The link timeweb→api.telegram.org flakes intermittently (TimedOut) — a single
    send must not silently drop the whole message (this ate the 23.07 daily report).
    """
    delay = SEND_BACKOFF
    for attempt in range(1, SEND_RETRIES + 1):
        try:
            await bot.send_message(
                chat_id, chunk, parse_mode=parse_mode, disable_web_page_preview=True,
            )
            return
        except BadRequest as e:
            # Never let a stray unescaped <...> in dynamic content swallow the whole
            # answer — fall back to plain text (still retried on network flake).
            if parse_mode is not None:
                log.warning("HTML send failed (%s); resending as plain text", e)
                await _send_message_resilient(bot, chat_id, chunk, None)
                return
            raise
        except (TimedOut, NetworkError) as e:
            if attempt == SEND_RETRIES:
                raise
            log.warning(
                "send timed out (attempt %d/%d): %s; retry in %.0fs",
                attempt, SEND_RETRIES, e, delay,
            )
            await asyncio.sleep(delay)
            delay *= 2


async def send_long(bot, chat_id, text, parse_mode=ParseMode.HTML):
    for chunk_start in range(0, len(text), 4000):
        chunk = text[chunk_start : chunk_start + 4000]
        await _send_message_resilient(bot, chat_id, chunk, parse_mode)


async def run_with_progress(update, context, work, empty="Пусто."):
    """Standard response mechanic for every command that does real work.

    Shows an animated placeholder (cycling phrases + typing), runs `work` (a sync
    callable returning the final HTML string) in a thread, then DELETES the
    placeholder and sends the answer as a FRESH message — the disappear+appear
    reads as a clean reveal. Any new long-running command gets this for free by
    routing through here.
    """
    chat_id = update.effective_chat.id
    req_id = uuid.uuid4().hex[:16]
    placeholder = await update.message.reply_text(_next_phrase())
    anim = asyncio.create_task(_animate(context.bot, chat_id, placeholder, req_id))
    try:
        # AI workers accept the req_id (to stream breadcrumbs); plain command workers don't.
        if _work_takes_arg(work):
            result = await asyncio.to_thread(work, req_id)
        else:
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


def ask_agent(question, context, session=None, images=None, req_id=None):
    """Ask the hardened read-only investigator (obs-agent). Returns the answer
    string, or None if the agent is unreachable/disabled so callers can fall back."""
    try:
        r = requests.post(
            f"{AGENT_URL}/ask",
            json={"question": question, "context": context, "session": session,
                  "images": images, "req_id": req_id},
            timeout=AGENT_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("answer")
    except Exception as e:
        log.warning("obs-agent /ask failed: %s", e)
        return None


# ---- alert triage (Grafana webhook -> pre-filter -> agent -> chat) --------
#
# Grafana routes alerts to POST /alert (see grafana/provisioning/alerting). The
# raw-alert firehose was pure noise (~84% dev + self-resolving warning flaps), so:
#   1. a cheap deterministic pre-filter drops dev + non-critical resolves + repeats
#      (no tokens spent),
#   2. survivors go to the agent, which investigates and returns {verdict, title,
#      summary, action} — a short human verdict instead of a raw metric dump,
#   3. only "real" verdicts are posted (with wrapped links); "noise" is recorded
#      for the daily digest. If the agent is unreachable the raw alert is posted
#      anyway — an alert is never silently lost.

_bot_app = None
_bot_loop = None


def _esc_url(u):
    return html.escape(str(u), quote=True)


def _alert_links(alert):
    """Wrapped, tappable links for the chat: service dashboard, silence, GlitchTip."""
    labels = alert.get("labels", {}) or {}
    service = labels.get("service", "")
    env = labels.get("env", "") or "prod"
    name = labels.get("alertname", "")
    links = []
    if service:
        dash = (f"{GRAFANA_BASE}/d/russ360-service-debug/service-debug"
                f"?var-service={service}&var-env={env}")
        links.append(f'<a href="{_esc_url(dash)}">дашборд</a>')
    silence = alert.get("silenceURL")
    if silence:
        links.append(f'<a href="{_esc_url(silence)}">заглушить</a>')
    if "xception" in name.lower() or "critical" in name.lower():
        links.append(f'<a href="{_esc_url(GLITCHTIP_BASE)}">GlitchTip</a>')
    return "🔗 " + " · ".join(links) if links else ""


def _alert_target(labels):
    return "/".join(x for x in (labels.get("service", ""), labels.get("env", "")) if x)


def _record_suppressed(name, service, env, reason, title=None):
    """Count a suppressed alert for the daily digest (keeps a short sample, 3 days)."""
    st = load_state()
    day = datetime.datetime.now(tz=MSK).strftime("%Y-%m-%d")
    sup = st.setdefault("suppressed", {})
    d = sup.setdefault(day, {"count": 0, "items": []})
    d["count"] += 1
    tgt = "/".join(x for x in (service, env) if x)
    d["items"].append((title or name) + (f" ({tgt})" if tgt else "") + f" [{reason}]")
    d["items"] = d["items"][-40:]
    for old in sorted(sup.keys())[:-3]:  # keep only the last 3 calendar days
        del sup[old]
    save_state(st)


def _debounce(alert):
    """True if this exact alert+status fired again within the debounce window — skip
    it so Grafana group re-sends don't re-trigger a triage. Real 1h critical repeats
    still pass (window is 15 min)."""
    labels = alert.get("labels", {}) or {}
    key = alert.get("fingerprint") or json.dumps(labels, sort_keys=True, ensure_ascii=False)
    key = f"{key}:{alert.get('status', 'firing')}"
    st = load_state()
    db = st.setdefault("alert_debounce", {})
    now = int(time.time())
    for k in [k for k, v in db.items() if now - v > 6 * 3600]:
        del db[k]
    recent = now - db.get(key, 0) < ALERT_DEBOUNCE_SEC
    db[key] = now
    save_state(st)
    return recent


def _alert_for_agent(alert):
    """Compact view of the alert handed to the agent for triage."""
    labels = alert.get("labels", {}) or {}
    return {
        "alertname": labels.get("alertname", ""),
        "severity": labels.get("severity", ""),
        "service": labels.get("service", ""),
        "env": labels.get("env", ""),
        "status": alert.get("status", "firing"),
        "summary": (alert.get("annotations", {}) or {}).get("summary", ""),
        "value": alert.get("valueString", ""),
        "starts_at": alert.get("startsAt", ""),
    }


def _triage_alert(alert, req_id):
    try:
        r = requests.post(
            f"{AGENT_URL}/triage",
            json={"alert": _alert_for_agent(alert), "req_id": req_id},
            timeout=AGENT_TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("triage")
    except Exception as e:
        log.warning("obs-agent /triage failed: %s", e)
        return None


async def _post_alert_message(head_lines, alert):
    links = _alert_links(alert)
    if links:
        head_lines = head_lines + ["", links]
    await send_long(_bot_app.bot, CHAT_ID, "\n".join(head_lines))


async def _post_triaged(alert, triage):
    labels = alert.get("labels", {}) or {}
    emoji = "🔴" if labels.get("severity") == "critical" else "🟡"
    title = esc(triage.get("title") or labels.get("alertname", "Алерт"))
    lines = [f"{emoji} <b>{title}</b>"]
    summary = (triage.get("summary") or "").strip()
    if summary:
        lines.append(esc(summary))
    action = (triage.get("action") or "").strip()
    if action:
        lines += ["", "⚡ " + esc(action)]
    await _post_alert_message(lines, alert)


async def _post_raw_alert(alert):
    """Fallback when the agent is unreachable: post the alert as-is, never drop it."""
    labels = alert.get("labels", {}) or {}
    emoji = "🔴" if labels.get("severity") == "critical" else "🟡"
    name = esc(labels.get("alertname", "Алерт"))
    tgt = _alert_target(labels)
    lines = [f"{emoji} <b>{name}</b>" + (f" ({esc(tgt)})" if tgt else "")]
    summary = (alert.get("annotations", {}) or {}).get("summary", "")
    if summary:
        lines.append(esc(summary))
    await _post_alert_message(lines, alert)


async def _post_resolved(alert):
    labels = alert.get("labels", {}) or {}
    name = esc(labels.get("alertname", "Алерт"))
    tgt = _alert_target(labels)
    await send_long(_bot_app.bot, CHAT_ID,
                    f"✅ <b>Восстановилось:</b> {name}" + (f" ({esc(tgt)})" if tgt else ""))


async def handle_alert(alert):
    """One alert from the Grafana webhook: pre-filter, triage, deliver."""
    labels = alert.get("labels", {}) or {}
    name = labels.get("alertname", "?")
    severity = labels.get("severity", "")
    service = labels.get("service", "")
    env = labels.get("env", "")
    status = alert.get("status", "firing")

    # 1. dev noise — nobody acts on dev flaps
    if env == "dev":
        _record_suppressed(name, service, env, "dev")
        return
    # 2. resolves: only critical outages clearing are worth a (cheap) note
    if status == "resolved":
        if severity == "critical":
            await _post_resolved(alert)
        else:
            _record_suppressed(name, service, env, "resolve")
        return
    # 3. debounce Grafana group re-sends
    if _debounce(alert):
        return

    req_id = uuid.uuid4().hex[:16]
    triage = await asyncio.to_thread(_triage_alert, alert, req_id)

    if triage is None:  # agent down/disabled — never lose the alert
        await _post_raw_alert(alert)
        return
    # Safety rail: a critical is never fully silenced even if the agent calls it
    # noise (misjudging a real outage must not swallow it) — it's still posted, just
    # with the agent's short summary. Only warnings can be suppressed as noise.
    if triage.get("verdict") == "noise" and severity != "critical":
        _record_suppressed(name, service, env, "agent-noise", triage.get("title"))
        _episodic_append(CHAT_ID, f"[алерт-шум] {name} {_alert_target(labels)}",
                         (triage.get("summary") or "подавлен как шум"))
        return
    await _post_triaged(alert, triage)


class _AlertHandler(BaseHTTPRequestHandler):
    """Internal-only HTTP endpoint for the Grafana webhook contact point. Acks fast
    and schedules each alert onto the bot's event loop (triage is slow)."""

    def do_POST(self):
        if self.path != "/alert":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self.send_response(400)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        alerts = payload.get("alerts") or []
        for a in alerts:
            if _bot_loop is not None:
                asyncio.run_coroutine_threadsafe(handle_alert(a), _bot_loop)
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


def _start_alert_server():
    srv = ThreadingHTTPServer(("0.0.0.0", ALERT_PORT), _AlertHandler)
    threading.Thread(target=srv.serve_forever, daemon=True, name="alert-http").start()
    log.info("alert webhook listening on :%s", ALERT_PORT)


# ---- ambient session buffer (thread continuity, activity-based) -----------

def _buffer_append(chat_id, who, text, bot=False):
    """Record every chat message (addressed to the bot or not) so the bot can pick
    up the surrounding conversation when it's finally engaged."""
    st = load_state()
    sessions = st.setdefault("sessions", {})
    buf = sessions.setdefault(str(chat_id), [])
    buf.append({"ts": int(time.time()), "who": who, "text": text[:400], "bot": bot})
    cutoff = int(time.time()) - 6 * 3600
    sessions[str(chat_id)] = [m for m in buf if m["ts"] >= cutoff][-60:]
    save_state(st)


def _session_context(chat_id):
    """Author-tagged current session = messages since the last gap > SESSION_GAP.
    Any activity resets the gap, so an ongoing discussion stays in context and a
    long silence starts a fresh thread automatically (no manual reset needed)."""
    buf = load_state().get("sessions", {}).get(str(chat_id), [])
    if not buf:
        return ""
    sess, prev = [], None
    for m in buf:
        if prev is not None and m["ts"] - prev > SESSION_GAP:
            sess = []  # silence longer than the gap -> new session
        sess.append(m)
        prev = m["ts"]
    sess = sess[-SESSION_MAX_MSGS:]
    return "\n".join(f'{m["who"]}: {m["text"][:200]}' for m in sess)


def _episodic_append(chat_id, q, a):
    """Auto-capture the Q/A into shared episodic memory for the daily consolidator."""
    try:
        os.makedirs(MEM_DIR, exist_ok=True)
        with open(os.path.join(MEM_DIR, "episodic.jsonl"), "a") as f:
            f.write(json.dumps(
                {"ts": int(time.time()), "chat": str(chat_id), "q": q[:400], "a": a[:600]},
                ensure_ascii=False,
            ) + "\n")
    except Exception as e:
        log.warning("episodic write failed: %s", e)


# ---- media (level 1: capture; level 2: photo understanding) ---------------

def _describe_media(msg):
    """Short placeholder for the ambient buffer + the media kind."""
    if msg.photo:
        return "[фото]", "photo"
    if msg.video:
        return "[видео]", "video"
    if msg.video_note:
        return "[кружок]", "video_note"
    if msg.voice:
        return "[голосовое]", "voice"
    if msg.audio:
        return "[аудио]", "audio"
    if msg.document:
        return f"[документ: {msg.document.file_name or 'файл'}]", "document"
    if msg.sticker:
        return f"[стикер {msg.sticker.emoji or ''}]".replace(" ]", "]"), "sticker"
    return "[вложение]", "other"


def _prune_media():
    try:
        now = time.time()
        for name in os.listdir(MEDIA_DIR):
            p = os.path.join(MEDIA_DIR, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > MEDIA_TTL:
                    os.remove(p)
            except OSError:
                pass
    except FileNotFoundError:
        pass


async def _download_photo(context, msg):
    """Download the largest photo size into the shared media volume; returns path."""
    try:
        _prune_media()
        os.makedirs(MEDIA_DIR, exist_ok=True)
        photo = msg.photo[-1]
        f = await context.bot.get_file(photo.file_id)
        path = os.path.join(MEDIA_DIR, f"{photo.file_unique_id}.jpg")
        await f.download_to_drive(path)
        return path
    except Exception as e:
        log.warning("photo download failed: %s", e)
        return None


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
        "в личке — просто текстом): «сколько логинов упало вчера?», «что с латенси финтеха?». "
        "Можно прислать скриншот с вопросом в подписи — гляну, что на нём."
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
        "/suppressed — что триаж задавил (шумовые алерты за сутки)\n"
        "/disk — диск/память/load\n"
        "/selfcheck — здоровье самого мониторинга\n"
        "/forget — сбросить контекст беседы (обычно сбрасывается сам после паузы)\n"
        "/help — это сообщение" + ai_note,
        parse_mode=ParseMode.HTML,
    )


async def cmd_forget(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    st = load_state()
    sessions = st.get("sessions", {})
    if str(update.effective_chat.id) in sessions:
        del sessions[str(update.effective_chat.id)]
        save_state(st)
    await update.message.reply_text(
        "Сбросил контекст беседы 🧹 (обычно он сбрасывается сам после паузы; долгую память не трогаю)"
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


def _suppressed_text():
    """What the triage pre-filter/agent swallowed — on-demand visibility so it's
    trusted (and so a real alert wrongly suppressed can be spotted and re-tuned)."""
    sup = load_state().get("suppressed", {})
    if not sup:
        return "✅ Пока ничего не задавлено (или бот недавно поднялся)."
    lines = ["<b>Задавленные алерты</b> (триаж/пре-фильтр)", ""]
    for day in sorted(sup.keys(), reverse=True)[:2]:
        d = sup[day]
        lines.append(f"<b>{esc(day)}</b> — {int(d.get('count', 0))}")
        for it in d.get("items", [])[-12:]:
            lines.append(f"• {esc(it)}")
        lines.append("")
    lines.append("<i>Причины: dev / resolve / agent-noise. Если тут реальный алерт — скажи, подкручу порог.</i>")
    return "\n".join(lines).strip()


async def cmd_suppressed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await allowed(update, context):
        return
    await run_with_progress(update, context, _suppressed_text)


# ---- free-text (AI) --------------------------------------------------------

def _display_name(user):
    if user is None:
        return "кто-то"
    return user.first_name or user.username or f"id{user.id}"


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

    # Record EVERY message into the session buffer first — including colleagues
    # talking among themselves. This keeps the session alive (resets the gap) and
    # gives the bot the surrounding context when it's eventually addressed.
    who = _display_name(update.effective_user)
    _buffer_append(chat.id, who, msg.text)

    if chat.id == CHAT_ID and not (is_reply_to_bot or mentioned):
        return  # not addressed — captured as ambient context, nothing to answer
    question = msg.text.replace(f"@{me}", "").strip() if me else msg.text.strip()
    log.info("engaging: chat=%s reply=%s mention=%s q=%r",
             chat.id, is_reply_to_bot, mentioned, question[:60])

    if not question:
        return
    if not aihelper.available():
        await msg.reply_text("AI-режим выключен (нет токена). Доступны команды — /help")
        return

    def work(req_id):
        ctx = build_ai_context()
        session = _session_context(chat.id)
        answer = ask_agent(question, ctx, session, req_id=req_id)
        if answer is None:  # agent down/unreachable — fall back to the in-bot toolless path
            answer = aihelper.answer_question(question, ctx)
        if answer:
            _buffer_append(chat.id, "бот", answer, bot=True)
            _episodic_append(chat.id, question, answer)
        return tgformat.render_ai(answer) if answer else "Не смог получить ответ от AI-слоя, попробуй ещё раз или /status"

    await run_with_progress(update, context, work)


async def on_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Non-text messages: always recorded into the ambient buffer (level 1); if the
    bot is addressed and it's a photo, the image is downloaded and the agent looks
    at it via its Read tool (level 2)."""
    msg = update.message
    if msg is None:
        return
    if not await allowed(update, context):
        return

    chat = update.effective_chat
    me = context.bot.username or ""
    placeholder, kind = _describe_media(msg)
    caption = (msg.caption or "").strip()
    who = _display_name(update.effective_user)
    _buffer_append(chat.id, who, placeholder + (f" {caption}" if caption else ""))

    is_reply_to_bot = (
        msg.reply_to_message is not None
        and msg.reply_to_message.from_user is not None
        and msg.reply_to_message.from_user.id == context.bot.id
    )
    mentioned = (f"@{me}".lower() in caption.lower()) if me else False
    if chat.id == CHAT_ID and not (is_reply_to_bot or mentioned):
        return  # ambient only — captured for context, not addressed
    if not aihelper.available():
        return

    images = []
    if kind == "photo":
        p = await _download_photo(context, msg)
        if p:
            images.append(p)
    question = (caption.replace(f"@{me}", "").strip() if me else caption)
    if not question:
        question = "Посмотри вложение и скажи, что на нём и что с этим делать." if images else f"Пользователь прислал {placeholder}."
    if not images and kind != "photo":
        question += f" (приложен {placeholder} — я пока умею смотреть только фото)"
    log.info("engaging(media): chat=%s kind=%s img=%d", chat.id, kind, len(images))

    def work(req_id):
        ctx = build_ai_context()
        session = _session_context(chat.id)
        answer = ask_agent(question, ctx, session, images, req_id=req_id)
        if answer is None:
            answer = aihelper.answer_question(question, ctx)
        if answer:
            _buffer_append(chat.id, "бот", answer, bot=True)
            _episodic_append(chat.id, question, answer)
        return tgformat.render_ai(answer) if answer else "Не смог обработать, попробуй ещё раз или /status"

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
            text += "\n\n🤖 " + tgformat.render_ai(ai_part)
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
            await _send_message_resilient(
                context.bot, CHAT_ID,
                "⚠️ Не смог собрать дневной отчёт, см. логи obs-tgbot", None,
            )
        except Exception:
            pass
    await _consolidate_memory(context)


async def _consolidate_memory(context: ContextTypes.DEFAULT_TYPE):
    """Trigger the agent's daily memory consolidation and post what it learned."""
    try:
        r = await asyncio.to_thread(
            lambda: requests.post(f"{AGENT_URL}/consolidate", timeout=AGENT_TIMEOUT)
        )
        summary = r.json().get("summary")
        if summary:
            await context.bot.send_message(
                CHAT_ID, "🧠 <b>Память за сутки</b>\n" + esc(summary), parse_mode=ParseMode.HTML
            )
    except Exception:
        log.warning("memory consolidation failed")


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
    with open(path, encoding="utf-8", errors="replace") as f:
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
    global _bot_app, _bot_loop
    _bot_app = app
    _bot_loop = asyncio.get_running_loop()
    _start_alert_server()
    log.info("bot started, AI layer: %s", "on" if aihelper.available() else "off")


def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(15)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(10)
        .get_updates_read_timeout(30)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("digest", cmd_digest))
    app.add_handler(CommandHandler("report", cmd_digest))
    app.add_handler(CommandHandler("errors", cmd_errors))
    app.add_handler(CommandHandler("top", cmd_top))
    app.add_handler(CommandHandler("alerts", cmd_alerts))
    app.add_handler(CommandHandler("suppressed", cmd_suppressed))
    app.add_handler(CommandHandler("noise", cmd_suppressed))
    app.add_handler(CommandHandler("disk", cmd_disk))
    app.add_handler(CommandHandler("selfcheck", cmd_selfcheck))
    app.add_handler(CommandHandler("forget", cmd_forget))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    media_filter = (
        filters.PHOTO | filters.VIDEO | filters.VIDEO_NOTE | filters.VOICE
        | filters.AUDIO | filters.Document.ALL | filters.Sticker.ALL
    )
    app.add_handler(MessageHandler(media_filter & ~filters.COMMAND, on_media))
    app.add_error_handler(on_error)

    jq = app.job_queue
    jq.run_daily(job_daily_report, time=REPORT_TIME, name="daily_report")
    jq.run_repeating(job_watchdog, interval=600, first=60, name="watchdog")
    jq.run_repeating(job_events, interval=60, first=30, name="events")

    app.run_polling(allowed_updates=["message"])


if __name__ == "__main__":
    main()
