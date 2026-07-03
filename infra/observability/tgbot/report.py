"""Daily 17:20 MSK report: collects a 24h picture and renders telegram HTML.

collect() returns a dict (also fed to the AI layer as context);
render() turns it into the deterministic part of the message.
"""

import datetime
import html
import json
import os

import datasources as ds

DATA_DIR = os.environ.get("BOT_DATA_DIR", "/data")
MSK = datetime.timezone(datetime.timedelta(hours=3))


def esc(s):
    """Escape dynamic strings — commit subjects, alert summaries etc. can contain
    <...> that would otherwise break Telegram HTML parsing of the whole message."""
    return html.escape(str(s), quote=False)


def _read_events(hours=24):
    """Deploy/drift events written by the host-side drift checker."""
    path = os.path.join(DATA_DIR, "events.jsonl")
    cutoff = datetime.datetime.now(tz=MSK).timestamp() - hours * 3600
    events = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("ts", 0) >= cutoff:
                        events.append(e)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return events


def read_drift():
    path = os.path.join(DATA_DIR, "drift.json")
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def collect():
    return {
        "generated_at": datetime.datetime.now(tz=MSK).strftime("%d.%m.%Y %H:%M МСК"),
        "services_24h": ds.service_snapshot(hours=24),
        "logins_24h": ds.login_snapshot(hours=24),
        "host": ds.host_snapshot(),
        "active_alerts": ds.grafana_active_alerts(),
        "alert_history_24h": ds.grafana_alert_history(hours=24),
        "targets_down": ds.scrape_targets_down(),
        "events_24h": _read_events(hours=24),
        "drift": read_drift(),
    }


def _fmt_p95(v):
    return f"{v:.2f}s" if v is not None else "–"


def render(data):
    lines = [f"📊 <b>Дневной отчёт Russ360</b> · {data['generated_at']}", ""]

    # services
    lines.append("<b>Сервисы (prod, за 24ч)</b>")
    for svc, m in data["services_24h"].items():
        req = int(m["requests"])
        e5 = int(m["errors_5xx"])
        exc = int(m["exceptions"])
        flags = []
        if e5:
            flags.append(f"5xx: {e5}")
        if exc:
            flags.append(f"exc: {exc}")
        flag_s = (" ⚠️ " + ", ".join(flags)) if flags else ""
        lines.append(f"• {esc(svc)}: {req} req, p95 {_fmt_p95(m['p95'])}{flag_s}")
    lines.append("")

    # logins
    lg = data["logins_24h"]
    total_ok = int(lg["password_ok"] + lg["otp_ok"])
    total_fail = int(lg["password_fail"] + lg["otp_fail"])
    lines.append("<b>Входы (за 24ч)</b>")
    lines.append(
        f"• успешных: {total_ok} (пароль {int(lg['password_ok'])}, OTP {int(lg['otp_ok'])}), "
        f"неудачных: {total_fail}"
    )
    lines.append(
        f"• токенов выдано: {int(lg['tokens_issued'])}"
        + (f", отказов token: {int(lg['token_fail'])}" if lg["token_fail"] else "")
        + (f", регистраций: {int(lg['registrations'])}" if lg["registrations"] else "")
    )
    lines.append("")

    # alerts
    alerts = data["active_alerts"]
    hist = data["alert_history_24h"]
    if alerts:
        lines.append(f"<b>Активные алерты: {len(alerts)}</b> 🔥")
        for a in alerts[:6]:
            tgt = "/".join(x for x in (a["service"], a["env"]) if x)
            lines.append(f"• {esc(a['name'])}{f' ({esc(tgt)})' if tgt else ''}")
    elif alerts is not None:
        lines.append("<b>Алерты:</b> активных нет ✅")
    else:
        lines.append("<b>Алерты:</b> Grafana недоступна ⚠️")
    if hist:
        lines.append(f"• срабатываний за сутки: {len(hist)}")
    lines.append("")

    # deploys / drift
    deploys = [e for e in data["events_24h"] if e.get("type") == "deploy"]
    if deploys:
        lines.append("<b>Деплои за сутки</b> 🚀")
        for e in deploys[:8]:
            lines.append(f"• {esc(e.get('repo', '?'))}: {esc(e.get('detail', ''))}")
        lines.append("")
    drift = data["drift"] or {}
    drifted = [r for r in drift.get("repos", []) if r.get("status") not in ("clean", "no-fetch")]
    if drifted:
        lines.append("<b>Дрейф репозиториев</b> ⚠️")
        for r in drifted[:6]:
            lines.append(f"• {esc(r['name'])}: {esc(r['status'])}")
        lines.append("")

    # host
    h = data["host"]
    disk = h["disk_used_pct"]
    mem = h["mem_used_pct"]
    sessions = h["active_sessions"]
    host_bits = []
    if disk is not None:
        host_bits.append(f"диск {disk:.0f}%")
    if mem is not None:
        host_bits.append(f"RAM {mem:.0f}%")
    if h["load15"] is not None:
        host_bits.append(f"load15 {h['load15']:.1f}")
    if sessions is not None:
        host_bits.append(f"онлайн ~{int(sessions)}")
    lines.append("<b>Хост:</b> " + ", ".join(host_bits))

    down = data["targets_down"]
    if down:
        lines.append("⚠️ <b>Не скрейпятся:</b> " + ", ".join(f"{esc(j)}/{esc(e)}" for j, e in down))

    return "\n".join(lines)
