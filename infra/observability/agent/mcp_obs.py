"""obs MCP server — read-only Prometheus/Loki query tools for obs-agent.

Spawned by the claude subprocess over stdio (see mcp.json). Talks ONLY to the
internal obs stack; `trust_env=False` makes it ignore the Anthropic proxy env it
inherits from claude, so internal queries never leave the box. Everything is
read-only by nature (PromQL/LogQL queries), so there is nothing to mutate.
"""

import os
import time

import requests
from mcp.server.fastmcp import FastMCP

PROM_URL = os.environ.get("PROM_URL", "http://obs-prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://obs-loki:3100")
SERVICES = ["rusaifin", "rusaicore", "rusaiauth", "rusaisklad"]
TIMEOUT = 15

_sess = requests.Session()
_sess.trust_env = False  # never route internal calls through the Anthropic proxy

mcp = FastMCP("obs")


@mcp.tool()
def metrics(promql: str) -> str:
    """Выполнить мгновенный PromQL-запрос к Prometheus (read-only) и вернуть результат.

    Ключевые метрики (label env="prod"|"dev", service ∈ {rusaifin,rusaicore,rusaiauth,rusaisklad}):
      russ360_http_requests_total{service,status,route} — counter запросов
      russ360_http_request_duration_seconds_{bucket,sum,count}{service,route,le} — гистограмма латенси
      russ360_exceptions_total{service} — исключения
      russ360_active_sessions{service} — активные сессии
      up — 0/1 состояние скрейпа таргета
      node_load15, node_memory_MemAvailable_bytes, node_filesystem_avail_bytes{mountpoint} — хост
      container_last_seen{name} — живость контейнеров (cadvisor)
    Для окон используй increase(...[1h]) / rate(...[5m]); для перцентилей histogram_quantile.
    Пример: histogram_quantile(0.95, sum by (le,service) (rate(russ360_http_request_duration_seconds_bucket{env="prod"}[1h])))
    """
    try:
        r = _sess.get(f"{PROM_URL}/api/v1/query", params={"query": promql}, timeout=TIMEOUT)
        r.raise_for_status()
        res = r.json()["data"]["result"]
    except Exception as e:
        return f"Ошибка запроса: {e}"
    if not res:
        return "Пусто (нет данных под этот запрос)."
    lines = []
    for item in res[:30]:
        metric = item.get("metric", {})
        name = metric.get("__name__", "")
        labels = {k: v for k, v in metric.items() if k != "__name__"}
        lbl = ("{" + ", ".join(f'{k}="{v}"' for k, v in labels.items()) + "}") if labels else ""
        val = item.get("value", ["", "?"])[1]
        lines.append(f"{name}{lbl} = {val}")
    if len(res) > 30:
        lines.append(f"… ещё {len(res) - 30} серий (уточни запрос)")
    return "\n".join(lines)


@mcp.tool()
def logs(service: str, filter: str = "", minutes: int = 60, limit: int = 30) -> str:
    """Последние строки логов сервиса из Loki (read-only, новые сверху).

    service ∈ {rusaifin,rusaicore,rusaiauth,rusaisklad}.
    filter — regex-подстрока (LogQL |~), пусто = все строки.
    minutes — окно назад (макс 1440). limit — сколько строк (макс 100).
    Пример: logs("rusaifin", "(?i)error|exception", 120)
    """
    if service not in SERVICES:
        return f"Неизвестный сервис. Есть: {', '.join(SERVICES)}"
    minutes = min(max(int(minutes), 1), 1440)
    limit = min(max(int(limit), 1), 100)
    sel = f'{{service="{service}",env="prod"}}'
    logql = f'{sel} |~ `{filter.replace("`", "")}`' if filter else sel
    end = int(time.time())
    try:
        r = _sess.get(
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
        streams = r.json()["data"]["result"]
    except Exception as e:
        return f"Ошибка Loki: {e}"
    rows = []
    for stream in streams:
        for ts, line in stream["values"]:
            rows.append((int(ts), line))
    rows.sort(reverse=True)
    if not rows:
        suffix = f" по фильтру /{filter}/" if filter else ""
        return f"{service}: строк не найдено за {minutes} мин{suffix}"
    return "\n".join(line[:500] for _, line in rows[:limit])


@mcp.tool()
def list_metrics(prefix: str = "russ360") -> str:
    """Список имён метрик Prometheus, содержащих подстроку (для поиска нужной метрики)."""
    try:
        r = _sess.get(f"{PROM_URL}/api/v1/label/__name__/values", timeout=TIMEOUT)
        r.raise_for_status()
        names = sorted(n for n in r.json()["data"] if prefix.lower() in n.lower())
    except Exception as e:
        return f"Ошибка: {e}"
    if not names:
        return "ничего не найдено"
    return "\n".join(names[:100]) + (f"\n… ещё {len(names) - 100}" if len(names) > 100 else "")


if __name__ == "__main__":
    mcp.run()
