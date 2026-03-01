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
    Checks execution_result, direct array keys, and falls back to counting
    markdown-table lines in the answer text.
    """
    # 1. SDK execution_result (most reliable)
    er = result.get("execution_result")
    if isinstance(er, dict) and er:
        return len(er)

    # 2. Direct array keys
    for key in ("data", "rows", "results", "records", "table"):
        val = result.get(key)
        if isinstance(val, list) and len(val) > 0:
            return len(val)

    # 3. Fallback: answer text contains a markdown table
    answer = result.get("answer", "")
    if "|" in answer:
        table_lines = [
            line for line in answer.split("\n")
            if "|" in line and "---" not in line
        ]
        if len(table_lines) > 1:
            return len(table_lines) - 1  # subtract header row
    return 0


# ─── Chart data extraction ─────────────────────────────────────────────────

def _parse_md_table(text: str) -> list[dict]:
    """
    Parse ALL Markdown tables in text into a single flat list of row-dicts.
    Header cells become keys (lowercased, spaces→underscores).
    Numeric strings are auto-converted to float.
    """
    if not text or "|" not in text:
        return []

    rows: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        # Detect separator row  |---|---|  or  | :--- | ---: |
        if i > 0 and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i]) and "-" in lines[i]:
            header_line = lines[i - 1]
            # Strip markdown bold/italic from cells (preserve underscores for SQL column names)
            clean = lambda s: re.sub(r"[*`]", "", s).strip()
            headers = [
                clean(h).lower().replace(" ", "_").replace("(", "").replace(")", "")
                         .replace("/", "_").replace("%", "").replace("°", "")
                for h in header_line.strip().strip("|").split("|")
            ]
            if not any(headers):
                i += 1
                continue
            j = i + 1
            while j < len(lines):
                row_line = lines[j].strip()
                if not row_line or "|" not in row_line:
                    break
                # Another separator row means a new table is starting
                if re.match(r"^\|?[\s:|-]+\|[\s:|-]*$", row_line) and "-" in row_line:
                    break
                cells = [clean(c) for c in row_line.strip().strip("|").split("|")]
                obj: dict = {}
                for h, raw in zip(headers, cells):
                    if not h:
                        continue
                    try:
                        obj[h] = float(raw.replace(",", "").replace(" ", "")) if raw else None
                    except ValueError:
                        obj[h] = raw
                if obj:
                    rows.append(obj)
                j += 1
            i = j
        else:
            i += 1
    return rows


def _parse_execution_result(execution_result: dict) -> list[dict]:
    """
    Parse the SDK's execution_result format into a flat list of row-dicts.
    SDK format: {"Row 1": [{"columnName": "x", "value": "y"}, ...], "Row 2": ...}
    Returns: [{"x": y, ...}, {"x": y, ...}, ...]
    """
    if not execution_result or not isinstance(execution_result, dict):
        return []
    rows: list[dict] = []
    # Sort by row number to maintain order
    sorted_keys = sorted(execution_result.keys(), key=lambda k: int(k.split()[-1]) if k.split()[-1].isdigit() else 0)
    for key in sorted_keys:
        cells = execution_result[key]
        if not isinstance(cells, list):
            continue
        obj: dict = {}
        for cell in cells:
            if isinstance(cell, dict) and "columnName" in cell and "value" in cell:
                col = cell["columnName"]
                raw = cell["value"]
                # Try numeric conversion
                if raw is not None and str(raw).strip():
                    try:
                        obj[col] = float(str(raw).replace(",", ""))
                    except (ValueError, TypeError):
                        obj[col] = raw
                else:
                    obj[col] = raw
        if obj:
            rows.append(obj)
    return rows


def extract_chart_data(result: dict) -> list[dict]:
    """
    Return structured row-dicts suitable for charting from ANY SDK response.
    Priority order:
      1. Direct data arrays (data / rows / records / table keys)
      2. DeepQuery sub-query data arrays
      3. Markdown table(s) parsed from the answer text
    Returns [] when nothing chartable is found.
    """
    # 1. SDK execution_result (most reliable — actual SQL output)
    er = result.get("execution_result")
    if isinstance(er, dict) and er:
        parsed = _parse_execution_result(er)
        if len(parsed) >= 2:
            return parsed

    # 2. Direct array keys
    for key in ("data", "rows", "records", "table"):
        val = result.get(key)
        if isinstance(val, list) and len(val) >= 2 and isinstance(val[0], dict):
            return val

    # 3. DeepQuery sub-queries
    queries = result.get("queries") or []
    for q in queries:
        if isinstance(q, dict):
            for key in ("data", "rows", "records"):
                val = q.get(key)
                if isinstance(val, list) and len(val) >= 2 and isinstance(val[0], dict):
                    return val

    # 4. Parse markdown table from answer text
    answer = result.get("answer", "")
    if answer and "|" in answer:
        rows = _parse_md_table(answer)
        if len(rows) >= 2:
            return rows

    return []


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
