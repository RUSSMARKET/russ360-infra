"""db MCP server — read-only SQL query tool for obs-agent.

Connects as SELECT-only DB users (the read-only guarantee is enforced by the
GRANTs, not by this code). A soft guard additionally rejects anything that is not
a single read statement, and pg sessions are opened read-only. Talks only to
local prod DBs (mysql socket + pg over the app networks), never the internet.

rusaiauth_prod is intentionally NOT reachable here (password hashes / oauth
secrets) — auth questions go through SMS analytics + Loki instead.
"""

import os

import psycopg2
import pymysql
from mcp.server.fastmcp import FastMCP

PW = os.environ.get("DB_RO_PASSWORD", "")
MYSQL_SOCK = os.environ.get("DB_MYSQL_SOCKET", "/run/mysqld/mysqld.sock")
DB_USER = os.environ.get("DB_RO_USER", "botro")
MAX_ROWS = 200

SOURCES = {
    "fintech_base": {"engine": "mysql", "db": "fintech_base"},
    "rusaicore_prod": {"engine": "pg", "host": "rusaicore_back_prod-pgsql-1", "db": "rusaicore_prod"},
    "rusaisklad_prod_db": {"engine": "pg", "host": "rusaisklad_back_prod-pgsql-1", "db": "rusaisklad_prod_db"},
}
ALIASES = {
    "mysql": "fintech_base", "fin": "fintech_base", "rusaifin": "fintech_base",
    "core": "rusaicore_prod", "rusaicore": "rusaicore_prod",
    "sklad": "rusaisklad_prod_db", "rusaisklad": "rusaisklad_prod_db",
}
READ_PREFIXES = ("select", "with", "explain", "show", "table")

mcp = FastMCP("db")


def _is_read(sql):
    body = sql.strip().rstrip(";")
    if ";" in body:  # single statement only — no stacked queries
        return False
    return body.lstrip("(").lower().startswith(READ_PREFIXES)


def _format(cols, rows):
    if not cols:
        return "OK (запрос без результата)."
    out = [" | ".join(cols)]
    for r in rows:
        out.append(" | ".join("" if v is None else str(v)[:200] for v in r))
    if len(rows) >= MAX_ROWS:
        out.append(f"… обрезано на {MAX_ROWS} строках (добавь LIMIT/агрегацию)")
    return "\n".join(out)


@mcp.tool()
def query(datasource: str, sql: str) -> str:
    """Выполнить SELECT к прод-БД (read-only, до 200 строк).

    datasource:
      fintech_base — MySQL rusaifin: промоутеры/пользователи, смены, карты, оформление, проекты.
      rusaicore_prod — PG Core: employees, projects, project_memberships, operational_locations, assignments.
      rusaisklad_prod_db — PG склад: остатки, перемещения, инвентаризации, SKU, документы.
    Разрешён ОДИН SELECT/WITH/EXPLAIN/SHOW. Пиши LIMIT сам. В БД есть PII (ФИО/телефоны) — это ок.
    Схему таблиц можно узнать через information_schema (например: SELECT table_name FROM information_schema.tables WHERE table_schema='public').
    """
    ds = ALIASES.get(datasource.strip().lower(), datasource.strip())
    if ds not in SOURCES:
        return f"Неизвестный datasource. Есть: {', '.join(SOURCES)}"
    if not _is_read(sql):
        return "Разрешён только один read-запрос (SELECT/WITH/EXPLAIN/SHOW), без ';'."
    cfg = SOURCES[ds]
    conn = None
    try:
        if cfg["engine"] == "mysql":
            conn = pymysql.connect(
                unix_socket=MYSQL_SOCK, user=DB_USER, password=PW, database=cfg["db"],
                connect_timeout=8, read_timeout=15,
            )
            cur = conn.cursor()
            cur.execute("SET SESSION MAX_EXECUTION_TIME=10000")
            cur.execute(sql)
        else:
            conn = psycopg2.connect(
                host=cfg["host"], port=5432, user=DB_USER, password=PW, dbname=cfg["db"],
                connect_timeout=8,
            )
            conn.set_session(readonly=True, autocommit=True)
            cur = conn.cursor()
            cur.execute("SET statement_timeout=10000")
            cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS) if cols else []
        return _format(cols, rows)
    except Exception as e:
        return f"Ошибка запроса: {e}"
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    mcp.run()
