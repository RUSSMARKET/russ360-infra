"""Read-only clients for the observability stack (Prometheus, Loki, Grafana).

Everything returns plain python data; formatting lives in bot.py/report.py.
All calls are best-effort: a dead datasource yields None/[] so one broken
component never takes down the whole bot.
"""

import logging
import os
import time

import requests

log = logging.getLogger(__name__)

PROM_URL = os.environ.get("PROM_URL", "http://obs-prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://obs-loki:3100")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://obs-grafana:3000")
AGENT_URL = os.environ.get("AGENT_URL", "http://obs-agent:8080")
ALERT_PORT = os.environ.get("ALERT_PORT", "8090")
GRAFANA_USER = os.environ.get("GF_SECURITY_ADMIN_USER", "admin")
GRAFANA_PASSWORD = os.environ.get("GF_SECURITY_ADMIN_PASSWORD", "admin")

SERVICES = ["rusaifin", "rusaicore", "rusaiauth", "rusaisklad"]
TIMEOUT = 15


def prom_query(query, default=None):
    try:
        r = requests.get(
            f"{PROM_URL}/api/v1/query", params={"query": query}, timeout=TIMEOUT
        )
        r.raise_for_status()
        return r.json()["data"]["result"]
    except Exception as e:
        log.warning("prom_query failed: %s (%s)", query[:80], e)
        return default if default is not None else []


def prom_scalar(query):
    """First sample value as float, or None."""
    res = prom_query(query)
    if res:
        try:
            v = float(res[0]["value"][1])
            return None if v != v else v  # NaN -> None
        except (KeyError, ValueError, IndexError):
            return None
    return None


def prom_by_label(query, label):
    """{label_value: float} for a grouped instant query (NaN dropped)."""
    out = {}
    for r in prom_query(query):
        try:
            v = float(r["value"][1])
            if v == v:
                out[r["metric"].get(label, "?")] = v
        except (KeyError, ValueError):
            continue
    return out


def loki_query(logql, minutes=60, limit=50):
    """Log lines (newest first) as [(unix_ts, line)]."""
    end = int(time.time())
    try:
        r = requests.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": logql,
                "start": (end - minutes * 60) * 10**9,
                "end": end * 10**9,
                "limit": limit,
                "direction": "backward",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        lines = []
        for stream in r.json()["data"]["result"]:
            for ts, line in stream["values"]:
                lines.append((int(ts) // 10**9, line))
        lines.sort(reverse=True)
        return lines[:limit]
    except Exception as e:
        log.warning("loki_query failed: %s (%s)", logql[:80], e)
        return []


def grafana_active_alerts():
    """Firing alert instances from the embedded alertmanager, or None on error."""
    try:
        r = requests.get(
            f"{GRAFANA_URL}/api/alertmanager/grafana/api/v2/alerts",
            params={"active": "true", "silenced": "false", "inhibited": "false"},
            auth=(GRAFANA_USER, GRAFANA_PASSWORD),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        alerts = []
        for a in r.json():
            labels = a.get("labels", {})
            if labels.get("alertname") in (None, "DatasourceError", "DatasourceNoData"):
                continue
            alerts.append(
                {
                    "name": labels.get("alertname", "?"),
                    "service": labels.get("service") or labels.get("job") or "",
                    "env": labels.get("env", ""),
                    "severity": labels.get("severity", ""),
                    "summary": a.get("annotations", {}).get("summary", ""),
                    "since": a.get("startsAt", ""),
                }
            )
        return alerts
    except Exception as e:
        log.warning("grafana alerts failed: %s", e)
        return None


def grafana_alert_history(hours=24):
    """Alert state-change annotations for the report period."""
    now_ms = int(time.time() * 1000)
    try:
        r = requests.get(
            f"{GRAFANA_URL}/api/annotations",
            params={"type": "alert", "from": now_ms - hours * 3600 * 1000, "to": now_ms, "limit": 100},
            auth=(GRAFANA_USER, GRAFANA_PASSWORD),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        events = []
        for a in r.json():
            new_state = (a.get("newState") or "").lower()
            if "alerting" in new_state or "firing" in new_state:
                events.append(
                    {"ts": a["time"] // 1000, "text": a.get("text", ""), "state": "firing"}
                )
        return events
    except Exception as e:
        log.warning("grafana history failed: %s", e)
        return []


def health():
    """Component reachability for /selfcheck and the watchdog. Includes the triage
    path (obs-agent + the bot's own alert webhook) — both went on the critical alert
    path, so a state change here is proactively reported by the watchdog."""
    checks = {}
    for name, url in [
        ("prometheus", f"{PROM_URL}/-/ready"),
        ("loki", f"{LOKI_URL}/ready"),
        ("grafana", f"{GRAFANA_URL}/api/health"),
        ("agent (триаж)", f"{AGENT_URL}/health"),
        ("webhook алертов", f"http://127.0.0.1:{ALERT_PORT}/health"),
    ]:
        try:
            r = requests.get(url, timeout=10)
            checks[name] = r.status_code == 200
        except Exception:
            checks[name] = False
    return checks


def scrape_targets_down():
    """[(job, env)] currently failing scrape."""
    return [
        (r["metric"].get("job", "?"), r["metric"].get("env", "?"))
        for r in prom_query("up == 0")
    ]


# ---- snapshot builders -------------------------------------------------

def service_snapshot(hours=1):
    """Per-service RED numbers over the window: req/min, 5xx, p95, exceptions."""
    w = f"{hours}h"
    reqs = prom_by_label(
        f'sum by (service) (increase(russ360_http_requests_total{{env="prod"}}[{w}]))',
        "service",
    )
    err5 = prom_by_label(
        f'sum by (service) (increase(russ360_http_requests_total{{env="prod",status=~"5.."}}[{w}]))',
        "service",
    )
    p95 = prom_by_label(
        f"histogram_quantile(0.95, sum by (le,service) "
        f'(rate(russ360_http_request_duration_seconds_bucket{{env="prod"}}[{w}])))',
        "service",
    )
    exc = prom_by_label(
        f'sum by (service) (increase(russ360_exceptions_total{{env="prod"}}[{w}]))',
        "service",
    )
    out = {}
    for s in SERVICES:
        out[s] = {
            "requests": reqs.get(s, 0.0),
            "errors_5xx": err5.get(s, 0.0),
            "p95": p95.get(s),
            "exceptions": exc.get(s, 0.0),
        }
    return out


def login_snapshot(hours=24):
    """Auth funnel from rusaiauth route counters."""
    w = f"{hours}h"

    def cnt(route_re, status_re):
        return (
            prom_scalar(
                f'sum(increase(russ360_http_requests_total{{env="prod",service="rusaiauth",'
                f'route=~"{route_re}",status=~"{status_re}"}}[{w}]))'
            )
            or 0.0
        )

    return {
        "password_ok": cnt("api/v1/login/password", "2.."),
        "password_fail": cnt("api/v1/login/password", "4..|5.."),
        "otp_ok": cnt("api/v1/login/otp/verify", "2.."),
        "otp_fail": cnt("api/v1/login/otp/verify", "4..|5.."),
        "tokens_issued": cnt("oauth/token", "2.."),
        "token_fail": cnt("oauth/token", "4..|5.."),
        "registrations": cnt("api/v1/registration", "2.."),
    }


def host_snapshot():
    return {
        "disk_used_pct": prom_scalar(
            '100 * (1 - node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"}'
            ' / node_filesystem_size_bytes{mountpoint="/",fstype!~"tmpfs|overlay"})'
        ),
        "load15": prom_scalar("node_load15"),
        "mem_used_pct": prom_scalar(
            "100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)"
        ),
        "active_sessions": prom_scalar(
            'max(russ360_active_sessions{env="prod",service="rusaifin"})'
        ),
    }


def top_routes(minutes=60, limit=7):
    """Slowest routes by avg duration (rusaifin prod), with request counts."""
    w = f"{minutes}m"
    avg = prom_by_label(
        f"(sum by (route) "
        f'(rate(russ360_http_request_duration_seconds_sum{{env="prod",service="rusaifin"}}[{w}]))'
        f" / clamp_min(sum by (route) "
        f'(rate(russ360_http_request_duration_seconds_count{{env="prod",service="rusaifin"}}[{w}])), 1e-9))'
        f" and (sum by (route) "
        f'(increase(russ360_http_request_duration_seconds_count{{env="prod",service="rusaifin"}}[{w}])) > 5)',
        "route",
    )
    counts = prom_by_label(
        f'sum by (route) (increase(russ360_http_requests_total{{env="prod",service="rusaifin"}}[{w}]))',
        "route",
    )
    out = [
        {"route": route, "avg_s": v, "count": counts.get(route, 0.0)}
        for route, v in avg.items()
    ]
    out.sort(key=lambda x: x["avg_s"], reverse=True)
    return out[:limit]


def recent_errors(service, minutes=60, limit=15):
    sel = f'{{service="{service}",env="prod"}}'
    return loki_query(
        f'{sel} |~ `(?i)"level_name":"(error|critical)"|\\[error\\]|\\bERROR\\b|\\bCRITICAL\\b`',
        minutes=minutes,
        limit=limit,
    )
