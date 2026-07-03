"""memory MCP server — durable notes the agent can write and recall.

Backed by /memory/notes.jsonl on a writable volume. This is the ONLY place the
agent can persist anything across questions; it has no general Write tool, so
memory writes go exclusively through remember() here.
"""

import datetime
import json
import os
import time

from mcp.server.fastmcp import FastMCP

MEM_DIR = os.environ.get("MEM_DIR", "/memory")
NOTES = os.path.join(MEM_DIR, "notes.jsonl")

mcp = FastMCP("memory")


def _load():
    notes = []
    try:
        with open(NOTES) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    notes.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return notes


@mcp.tool()
def remember(text: str, tags: str = "") -> str:
    """Сохранить durable-факт в долгую память (переживает между вопросами и перезапусками).

    Используй для устойчивых, переиспользуемых выводов: причины повторяющихся паттернов,
    объяснения аномалий, разбор инцидентов, договорённости с командой. НЕ для сиюминутных
    чисел (их всегда можно перезапросить). tags — через запятую (например: latency,magnit).
    """
    text = (text or "").strip()
    if not text:
        return "Пустая заметка не сохранена."
    os.makedirs(MEM_DIR, exist_ok=True)
    note = {
        "ts": int(time.time()),
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
        "text": text[:1000],
    }
    with open(NOTES, "a") as f:
        f.write(json.dumps(note, ensure_ascii=False) + "\n")
    return "Запомнил."


@mcp.tool()
def recall(query: str = "", limit: int = 20) -> str:
    """Найти заметки в долгой памяти по подстроке или тегу (пусто = последние).

    Возвращает до limit заметок, новые сверху. Полезно, когда дайджест памяти в контексте
    не покрыл нужное — можно поискать глубже по ключевому слову.
    """
    notes = _load()
    if query:
        q = query.lower()
        notes = [
            n for n in notes
            if q in n.get("text", "").lower() or any(q in t.lower() for t in n.get("tags", []))
        ]
    notes = notes[-max(1, min(int(limit), 100)):][::-1]
    if not notes:
        return "В памяти ничего не найдено."
    lines = []
    for n in notes:
        try:
            d = datetime.datetime.fromtimestamp(n["ts"]).strftime("%d.%m %H:%M")
        except Exception:
            d = "?"
        tg = (" [" + ",".join(n["tags"]) + "]") if n.get("tags") else ""
        lines.append(f"{d}{tg}: {n.get('text', '')}")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
