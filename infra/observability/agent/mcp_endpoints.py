"""endpoints MCP server — whitelisted read-only rusaiauth endpoints for obs-agent.

Currently exposes ONLY the SMS analytics GET endpoints (masked phones, aggregates,
no OTP codes). The client_credentials token carries `identity.password.write`
(the coarse scope those routes share with set-password/provision), but this server
exposes NO write tool and no arbitrary-path tool — the only reachable endpoints
are the two hardcoded GETs below, so the surface stays strictly read-only.

trust_env=False → token mint + calls go to rusaiauth over the internal network,
never through the Anthropic proxy.
"""

import json
import os
import time

import requests
from mcp.server.fastmcp import FastMCP

AUTH_URL = os.environ.get("RUSAIAUTH_INTERNAL_URL", "http://rusaiauth_back_prod-nginx")
CID = os.environ.get("OBS_AGENT_CLIENT_ID", "")
CSECRET = os.environ.get("OBS_AGENT_CLIENT_SECRET", "")
SCOPE = "identity.password.write"
TIMEOUT = 20

_sess = requests.Session()
_sess.trust_env = False  # internal calls, never via the Anthropic proxy
_token = {"val": None, "exp": 0.0}

mcp = FastMCP("auth")


def _get_token():
    now = time.time()
    if _token["val"] and now < _token["exp"] - 30:
        return _token["val"]
    if not (CID and CSECRET):
        raise RuntimeError("OAuth-клиент не сконфигурирован (нет CLIENT_ID/SECRET)")
    r = _sess.post(
        f"{AUTH_URL}/oauth/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CID,
            "client_secret": CSECRET,
            "scope": SCOPE,
        },
        headers={"Accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    j = r.json()
    _token["val"] = j["access_token"]
    _token["exp"] = now + int(j.get("expires_in", 3600))
    return _token["val"]


def _get(path, params):
    tok = _get_token()
    r = _sess.get(
        f"{AUTH_URL}{path}",
        params=params,
        headers={"Authorization": f"Bearer {tok}", "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


@mcp.tool()
def sms_stats(date_from: str, date_to: str) -> str:
    """Агрегаты доставки OTP-SMS (rusaiauth) за период. Даты в формате YYYY-MM-DD.

    Возвращает total_sms, unique_phones, consumed/expired/active, разбивку by_purpose
    (registration/login/recovery) и посуточную статистику. Это про доставку OTP —
    тема недоставки MTS. Данные агрегированы, без телефонов и кодов.
    """
    try:
        j = _get("/internal/v1/sms/stats", {"date_from": date_from, "date_to": date_to})
    except Exception as e:
        return f"Ошибка: {e}"
    return json.dumps(j.get("data", j), ensure_ascii=False)


@mcp.tool()
def sms_events(date_from: str, date_to: str, page: int = 1, per_page: int = 25, phone_suffix: str = "") -> str:
    """Пагинированные события отправки OTP-SMS (rusaiauth). Даты YYYY-MM-DD.

    Телефоны маскированы, самого OTP-кода в ответе нет — только purpose/статус/attempts/время.
    phone_suffix — необязательный фильтр по последним цифрам номера.
    """
    params = {"date_from": date_from, "date_to": date_to, "page": int(page), "per_page": min(int(per_page), 100)}
    if phone_suffix:
        params["phone_suffix"] = phone_suffix
    try:
        j = _get("/internal/v1/sms/events", params)
    except Exception as e:
        return f"Ошибка: {e}"
    return json.dumps(j.get("data", j), ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
