"""AgroAdvisor - Utility helpers."""

import re
import time
import html as html_mod

from .config import AREA_TRANSLATIONS, CROP_TRANSLATIONS


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def translate_area(name: str) -> str:
    if not name:
        return name
    return AREA_TRANSLATIONS.get(name.strip().lower(), name)


def translate_crop(name: str) -> str:
    if not name:
        return name
    return CROP_TRANSLATIONS.get(name.strip().lower(), name)


def get_sql(result: dict) -> str:
    return result.get("sql_query") or result.get("sqlQuery") or result.get("sql") or ""


def count_rows(result: dict) -> int:
    er = result.get("execution_result")
    if isinstance(er, dict) and er:
        return len(er)
    for key in ("data", "rows", "results", "records"):
        val = result.get(key)
        if isinstance(val, list) and val:
            return len(val)
    answer = result.get("answer", "")
    if "|" in answer:
        lines = [l for l in answer.split("\n") if "|" in l and "---" not in l]
        if len(lines) > 1:
            return len(lines) - 1
    return 0


def _parse_md_table(text: str) -> list[dict]:
    if not text or "|" not in text:
        return []
    rows: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if i > 0 and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i]) and "-" in lines[i]:
            header_line = lines[i - 1]
            clean = lambda s: re.sub(r"[*`]", "", s).strip()
            headers = [
                clean(h).lower().replace(" ", "_").replace("(", "").replace(")", "")
                         .replace("/", "_").replace("%", "").replace("\u00b0", "")
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
                if re.match(r"^\|?[\s:|-]+\|[\s:|-]*$", row_line) and "-" in row_line:
                    break
                cells = [clean(c) for c in row_line.strip().strip("|").split("|")]
                obj = {}
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
    if not execution_result or not isinstance(execution_result, dict):
        return []
    rows: list[dict] = []
    sorted_keys = sorted(
        execution_result.keys(),
        key=lambda k: int(k.split()[-1]) if k.split()[-1].isdigit() else 0,
    )
    for key in sorted_keys:
        cells = execution_result[key]
        if not isinstance(cells, list):
            continue
        obj = {}
        for cell in cells:
            if isinstance(cell, dict) and "columnName" in cell and "value" in cell:
                col, raw = cell["columnName"], cell["value"]
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


def extract_data(result: dict) -> list[dict]:
    er = result.get("execution_result")
    if isinstance(er, dict) and er:
        parsed = _parse_execution_result(er)
        if len(parsed) >= 2:
            return parsed
    for key in ("data", "rows", "records"):
        val = result.get(key)
        if isinstance(val, list) and len(val) >= 2 and isinstance(val[0], dict):
            return val
    queries = result.get("queries") or []
    for q in queries:
        if isinstance(q, dict):
            for key in ("data", "rows", "records"):
                val = q.get(key)
                if isinstance(val, list) and len(val) >= 2 and isinstance(val[0], dict):
                    return val
    answer = result.get("answer", "")
    if answer and "|" in answer:
        rows = _parse_md_table(answer)
        if len(rows) >= 2:
            return rows
    return []


def md_to_html(text: str) -> str:
    if not text:
        return ""
    h = html_mod.escape(text)
    h = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', h)
    h = re.sub(r'\*(.+?)\*', r'<em>\1</em>', h)
    h = re.sub(r'^### (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'^## (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'^# (.+)$', r'<h2>\1</h2>', h, flags=re.MULTILINE)
    h = re.sub(r'^[-\u2022] (.+)$', r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', h, flags=re.DOTALL)
    h = h.replace('</ul>\n<ul>', '')
    h = h.replace('\n\n', '</p><p>')
    h = h.replace('\n', '<br>')
    return f"<p>{h}</p>"
