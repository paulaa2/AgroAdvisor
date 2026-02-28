"""
AgroAdvisor – Utility helpers
Pure functions with no external dependencies.
"""

import sys
import time
import re
import html as html_mod

from .config import AREA_TRANSLATIONS


# ─── Logging ────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    """Timestamped stdout log — always flushed, always visible."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ─── Area name translation ───────────────────────────────────────────────────

def translate_area(name: str) -> str:
    """Translate a user-provided country/region name to its English DB equivalent."""
    if not name:
        return name
    return AREA_TRANSLATIONS.get(name.strip().lower(), name)


# ─── SQL key extraction ──────────────────────────────────────────────────────

def get_sql(result: dict) -> str:
    """Extract the SQL query string from an SDK response (handles multiple key names)."""
    return (
        result.get("sql_query")
        or result.get("sqlQuery")
        or result.get("sql")
        or ""
    )


# ─── Row count extraction ────────────────────────────────────────────────────

def count_rows(result: dict) -> int:
    """
    Return the number of data rows in an SDK response.
    Checks every key the SDK might use, and falls back to counting
    markdown-table lines in the answer text.
    """
    for key in ("data", "rows", "results", "records", "table"):
        val = result.get(key)
        if isinstance(val, list) and len(val) > 0:
            return len(val)

    # Fallback: answer text contains a markdown table
    answer = result.get("answer", "")
    if "|" in answer:
        table_lines = [
            line for line in answer.split("\n")
            if "|" in line and "---" not in line
        ]
        if len(table_lines) > 1:
            return len(table_lines) - 1  # subtract header row
    return 0


# ─── Minimal Markdown → HTML (PDF renderer only) ────────────────────────────

def md_to_html(text: str) -> str:
    """
    Convert a small subset of Markdown to HTML.
    Only used for PDF generation — the frontend uses marked.js.
    """
    if not text:
        return ""
    h = html_mod.escape(text)
    h = re.sub(r'\*\*(.+?)\*\*',  r'<strong>\1</strong>', h)
    h = re.sub(r'\*(.+?)\*',       r'<em>\1</em>',         h)
    h = re.sub(r'^### (.+)$',      r'<h3>\1</h3>',         h, flags=re.MULTILINE)
    h = re.sub(r'^## (.+)$',       r'<h3>\1</h3>',         h, flags=re.MULTILINE)
    h = re.sub(r'^# (.+)$',        r'<h2>\1</h2>',         h, flags=re.MULTILINE)
    h = re.sub(r'^[-•] (.+)$',     r'<li>\1</li>',         h, flags=re.MULTILINE)
    h = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', h, flags=re.DOTALL)
    h = h.replace('</ul>\n<ul>', '')
    h = h.replace('\n\n', '</p><p>')
    h = h.replace('\n', '<br>')
    return f"<p>{h}</p>"
