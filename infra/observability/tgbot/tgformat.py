"""Markdown -> Telegram-HTML converter for AI free-text output.

The AI layer emits Markdown (headings, **bold**, tables, arrows, em-dashes,
~~strike~~). Telegram's HTML parse mode understands none of that: `**` shows
literally, tables wrap into garbage, box-drawing/arrow glyphs read as AI tells.

This module renders AI text into the small HTML subset Telegram supports
(<b> <i> <s> <u> <code> <pre> <a>), turns tables into aligned monospace blocks
that scroll instead of breaking, and normalizes typography. It is applied ONLY
to AI output — the bot's own deterministic strings are already valid HTML.
"""

import html
import re

# ---- typography (run on raw text, before HTML-escaping) --------------------

def _typography(t):
    # long dashes -> plain hyphen (the classic AI tell). Arrow glyphs (→ ← etc.)
    # are left as-is: Telegram renders them fine, and converting to -> reads as
    # a plain dash and is misleading.
    for d in ("—", "–", "―", "‒"):
        t = t.replace(d, "-")
    # non-breaking / thin spaces -> regular
    t = t.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return t


# ---- table rendering -------------------------------------------------------

def _looks_tabular(line):
    s = line.strip()
    if not s:
        return False
    if s.startswith("|"):
        return True
    if re.match(r"^:?-{2,}:?(\s*\|\s*:?-{2,}:?)+$", s):
        return True
    return False


def _is_sep_cells(cells):
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c or "") for c in cells)


def _render_table(rows):
    """rows: list of raw (already HTML-escaped) markdown table lines.
    Returns an aligned <pre> block (monospace -> Telegram scrolls it, no wrap-break)."""
    parsed = []
    for r in rows:
        s = r.strip().strip("|")
        cells = [c.strip() for c in s.split("|")]
        if _is_sep_cells(cells):
            continue
        parsed.append(cells)
    if not parsed:
        return ""
    ncols = max(len(c) for c in parsed)
    widths = [0] * ncols
    for cells in parsed:
        for j in range(ncols):
            cell = cells[j] if j < len(cells) else ""
            widths[j] = max(widths[j], len(cell))
    out = []
    for cells in parsed:
        padded = [(cells[j] if j < len(cells) else "").ljust(widths[j]) for j in range(ncols)]
        out.append(" │ ".join(padded).rstrip())
    return "<pre>" + "\n".join(out) + "</pre>"


# ---- block-level line rendering (on already-escaped text) ------------------

def _render_block_line(line):
    s = line.rstrip()
    # horizontal rule -> drop
    if re.fullmatch(r"\s*([-*_])\1{2,}\s*", s):
        return ""
    # headings ###... -> bold line
    m = re.match(r"^\s*#{1,6}\s+(.*)$", s)
    if m:
        return "<b>" + m.group(1).strip() + "</b>"
    # blockquote (> escaped to &gt;) -> » prefix
    m = re.match(r"^\s*&gt;\s?(.*)$", s)
    if m:
        return "» " + m.group(1)
    # bullet list -> • (preserve indent)
    m = re.match(r"^(\s*)[-*+]\s+(.*)$", s)
    if m:
        return m.group(1) + "• " + m.group(2)
    return line


# ---- inline formatting -----------------------------------------------------

def _inline(text):
    # links first so their [text](url) isn't mangled by emphasis
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', text)
    # strike, bold, italic  (bold before italic so ** wins over *)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text, flags=re.S)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.S)
    text = re.sub(r"(?<!\*)\*(?!\*)(\S(?:.*?\S)?)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w`])_(?!_)(\S(?:.*?\S)?)_(?![\w`])", r"<i>\1</i>", text)
    # drop any stray leftover emphasis markers
    text = text.replace("**", "")
    return text


# ---- entry point -----------------------------------------------------------

def render_ai(text):
    """Convert AI Markdown output into Telegram-safe HTML."""
    if not text:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    fences, codes, tables = [], [], []

    # stash fenced code blocks (raw; escaped on restore)
    def _stash_fence(m):
        fences.append(m.group(1))
        return f"\x00F{len(fences) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _stash_fence, text, flags=re.S)
    text = re.sub(r"```(.+?)```", _stash_fence, text, flags=re.S)

    # stash inline code (raw; escaped on restore)
    def _stash_code(m):
        codes.append(m.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", _stash_code, text)

    text = _typography(text)
    text = html.escape(text, quote=False)

    # block structure: collect tables, render the rest line-by-line
    out_lines = []
    buf = []

    def _flush():
        if not buf:
            return
        if len(buf) >= 2:
            tables.append(_render_table(buf))
            out_lines.append(f"\x00T{len(tables) - 1}\x00")
        else:
            for ln in buf:
                out_lines.append(_render_block_line(ln))
        buf.clear()

    for line in text.split("\n"):
        if _looks_tabular(line):
            buf.append(line)
            continue
        _flush()
        out_lines.append(_render_block_line(line))
    _flush()
    text = "\n".join(out_lines)

    text = _inline(text)

    # collapse 3+ blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    # restore placeholders
    for i, c in enumerate(codes):
        text = text.replace(f"\x00C{i}\x00", "<code>" + html.escape(c, quote=False) + "</code>")
    for i, f in enumerate(fences):
        text = text.replace(f"\x00F{i}\x00", "<pre>" + html.escape(f.strip("\n"), quote=False) + "</pre>")
    for i, tb in enumerate(tables):
        text = text.replace(f"\x00T{i}\x00", tb)
    return text
