"""
AgroAdvisor – Query Pipeline
Three-phase reasoning pipeline:
  Phase 0 — VectorDB semantic search + local TABLE_CATALOGUE keyword ranking
  Phase 1 — Focused schema discovery for top-ranked tables; explicit table selection
  Phase 2 — Data extraction against the selected table(s) only
"""

import asyncio
import time
from typing import Any

from .config import DEEP_QUERY_URL, TABLE_CATALOGUE, TIMEOUT_DEEP
from .prompts import SYSTEM_INSTRUCTIONS
from .sdk_client import ask, ask_metadata, discover_schema, sdk_post, vector_search, think_interpret
from .utils import count_rows, extract_chart_data, get_sql, log


# ─────────────────────────────────────────────────────────────────────────────
# Phase entry builders
# ─────────────────────────────────────────────────────────────────────────────

def _phase0_entry(
    vector_context: str,
    ranked_tables: list[dict],
    duration_s: float,
) -> dict:
    """Phase 0: VectorDB search + local table ranking."""
    top_names = [t["name"] for t in ranked_tables[:3] if t["score"] > 0]
    return {
        "phase": 0,
        "name": "Busqueda semantica + Ranking de tablas",
        "description": (
            "VectorDB embeddings (ChromaDB + gemini-embedding-001) "
            "+ scoring local sobre catalogo de tablas"
        ),
        "endpoint": "answerMetadataQuestion (embeddings)",
        "ranked_tables": ranked_tables,
        "result_summary": (
            f"Tablas mas relevantes: {', '.join(top_names)}\n"
            + (vector_context[:300] if vector_context else "Sin resultados VectorDB")
        ),
        "duration_s": round(duration_s, 1),
    }


def _phase1_entry(
    selected_tables: list[str],
    schema_context: str,
    duration_s: float,
) -> dict:
    """Phase 1: Focused schema discovery + explicit table selection."""
    return {
        "phase": 1,
        "name": "Seleccion de tabla",
        "description": (
            f"Esquema descubierto para: {', '.join(selected_tables) or 'ninguna'}. "
            "Solo se consultan las tablas necesarias."
        ),
        "endpoint": "answerMetadataQuestion (focused)",
        "selected_tables": selected_tables,
        "result_summary": schema_context[:600] if schema_context else "Esquema local (sin Data Catalog)",
        "duration_s": round(duration_s, 1),
    }


def _phase2_entry(label: str, result: dict, duration_s: float) -> dict:
    return {
        "phase": 2,
        "name": f"Consulta: {label}",
        "endpoint": "answerDataQuestion",
        "sql_query": get_sql(result),
        "rows_returned": count_rows(result),
        "duration_s": round(duration_s, 1),
    }


def _phase2_error_entry(label: str, error: str, duration_s: float) -> dict:
    return {
        "phase": 2,
        "name": f"Consulta: {label}",
        "endpoint": "answerDataQuestion",
        "error": error,
        "duration_s": round(duration_s, 1),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Local table scoring (Phase 0 — no network call needed)
# ─────────────────────────────────────────────────────────────────────────────

def _score_tables(question: str) -> list[dict]:
    """
    Score every entry in TABLE_CATALOGUE against the user question using
    keyword overlap, column-name hits and description word overlap.
    Returns a sorted list of {name, score, description, denodo} dicts.
    """
    q = question.lower()
    results: list[dict] = []

    for name, info in TABLE_CATALOGUE.items():
        score = 0.0

        # Keyword hits (strongest signal)
        for kw in info.get("keywords", []):
            if kw.lower() in q:
                score += 1.0

        # Column-name hits (medium signal)
        for col in info.get("columns", "").lower().split(", "):
            col = col.strip()
            if col and col in q:
                score += 0.5

        # Description word overlap (weak signal)
        desc_words = [w for w in info.get("description", "").lower().split() if len(w) > 4]
        for w in desc_words:
            if w in q:
                score += 0.2

        # Denodo-queryable tables get a small boost (prefer directly queryable)
        if info.get("denodo"):
            score += 0.1

        results.append({
            "name": name,
            "score": round(score, 2),
            "description": info["description"],
            "denodo": info.get("denodo", False),
            "join_keys": info.get("join_keys", ""),
            "use_for": info.get("use_for", ""),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _build_table_context(selected_tables: list[str]) -> str:
    """
    Build a concise schema context string from TABLE_CATALOGUE
    for the selected tables, used as extra instructions in Phase 2.
    """
    parts: list[str] = []
    for name in selected_tables:
        info = TABLE_CATALOGUE.get(name)
        if not info:
            continue
        parts.append(
            f"TABLE: {name}\n"
            f"  Description: {info['description']}\n"
            f"  Columns:     {info['columns']}\n"
            f"  Join keys:   {info['join_keys']}\n"
            f"  Use for:     {info['use_for']}\n"
            f"  Queryable via Denodo: {'YES' if info.get('denodo') else 'NO (local CSV)'}"
        )
    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Core phase runner
# ─────────────────────────────────────────────────────────────────────────────

async def _run_phases(
    user_question: str,
    metadata_topic: str,
) -> tuple[str, str, list[str], dict, dict]:
    """
    Execute Phase 0 (VectorDB + local ranking) and Phase 1 (focused schema
    for selected tables) in sequence.

    Returns:
      (vector_context, schema_context, selected_tables, phase0_entry, phase1_entry)

    Both phases are non-blocking — failures degrade gracefully.
    """
    # ── Phase 0: VectorDB + local ranking ─────────────────────────────────────
    log(f"PIPELINE PHASE 0 — VectorDB + table ranking: {user_question[:100]}")
    t0 = time.time()

    vector_context = ""
    try:
        vector_context = await vector_search(user_question)
    except Exception as exc:
        log(f"PHASE 0 VectorDB failed (non-blocking): {exc}")

    ranked = _score_tables(user_question)
    ranked_tables = ranked  # full list for the phase entry

    phase0_time = time.time() - t0
    p0 = _phase0_entry(vector_context, ranked_tables, phase0_time)
    log(
        f"PHASE 0 complete ({phase0_time:.1f}s) | "
        f"top tables: {[t['name'] for t in ranked[:3]]}"
    )

    # ── Phase 1: Focused schema for top-ranked Denodo tables ──────────────────
    # Pick Denodo-queryable tables with score > 0 first, then any table
    denodo_candidates = [t for t in ranked if t["denodo"] and t["score"] > 0]
    any_candidates = [t for t in ranked if t["score"] > 0]

    # Prefer Denodo tables; for edge cases fall back to the top-scored table
    if denodo_candidates:
        top_for_schema = [t["name"] for t in denodo_candidates[:2]]
    elif any_candidates:
        top_for_schema = [t["name"] for t in any_candidates[:2]]
    else:
        top_for_schema = [ranked[0]["name"]] if ranked else []

    log(f"PIPELINE PHASE 1 — Focused schema for: {top_for_schema}")
    t1 = time.time()
    schema_context = ""
    selected_tables: list[str] = []

    try:
        focused_topic = (
            f"Exact schema (views, columns, data types) for: {', '.join(top_for_schema)}. "
            f"Context: {metadata_topic}"
        )
        meta = await discover_schema(focused_topic)
        schema_context = str(meta.get("answer", ""))
        selected_tables = top_for_schema
    except Exception as exc:
        log(f"PHASE 1 schema discovery failed (non-blocking): {exc}")
        selected_tables = top_for_schema  # still pass the selection even if schema fails

    # Enrich schema_context with local TABLE_CATALOGUE info
    local_ctx = _build_table_context(selected_tables)
    if local_ctx:
        schema_context = local_ctx + (
            ("\n\nDATA CATALOG SCHEMA:\n" + schema_context) if schema_context else ""
        )

    phase1_time = time.time() - t1
    p1 = _phase1_entry(selected_tables, schema_context, phase1_time)
    log(
        f"PHASE 1 complete ({phase1_time:.1f}s) | "
        f"selected: {selected_tables} | schema_chars={len(schema_context)}"
    )

    return vector_context, schema_context, selected_tables, p0, p1


# ─────────────────────────────────────────────────────────────────────────────
# Enriched instructions builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_enriched_instructions(
    vector_context: str,
    schema_context: str,
    selected_tables: list[str],
    extra: str = "",
) -> str:
    """
    Combine Phase 0/1 context into a single instruction block for Phase 2.
    Emphasises which table(s) to query and guards against common Denodo pitfalls.
    """
    parts: list[str] = []

    if vector_context:
        parts.append(
            "PHASE 0 — VECTORDB SEMANTIC CONTEXT:\n" + vector_context[:1200]
        )

    if schema_context:
        parts.append(
            "PHASE 1 — SELECTED TABLE SCHEMA:\n" + schema_context
        )

    if selected_tables:
        denodo_sel = [t for t in selected_tables if TABLE_CATALOGUE.get(t, {}).get("denodo")]
        if denodo_sel:
            parts.append(
                f"FOCUS: query the following Denodo view(s): {', '.join(denodo_sel)}. "
                "Do NOT query other views unless strictly necessary."
            )

    parts.append(
        'OVERRIDE: The yield column is ALWAYS "hg_ha_yield". '
        "Do NOT use CAST on hg_ha_yield — it is already numeric."
    )

    if extra:
        parts.append(extra)

    return "\n\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Public pipeline functions
# ─────────────────────────────────────────────────────────────────────────────

async def two_phase_query(
    user_question: str,
    metadata_topic: str,
    data_question: str,
    extra_instructions: str = "",
) -> dict:
    """
    Three-phase pipeline for a single data question.
    Returns: {**data_result, "pipeline": {phases, total_duration_s}}
    """
    pipeline: dict[str, Any] = {"phases": []}
    t_total = time.time()

    log("=" * 60)
    log(f"TWO-PHASE PIPELINE: {user_question[:100]}")

    vector_context, schema_context, selected_tables, p0, p1 = await _run_phases(
        user_question, metadata_topic
    )
    pipeline["phases"].extend([p0, p1])

    log(f"PIPELINE PHASE 2 — Data query / SQL (tables: {selected_tables}): {data_question[:120]}")
    enriched = _build_enriched_instructions(
        vector_context, schema_context, selected_tables, extra_instructions
    )
    # Tell the LLM to focus on accurate SQL + clean data return; interpretation is Phase 3
    enriched += (
        "\n\nPHASE 2 ROLE: Your ONLY job is to generate the correct SQL query and execute it. "
        "CRITICAL RULES FOR DATA RETURN:\n"
        "- NEVER use LIMIT 1. Always return at least 5-10 rows for comparison/trends.\n"
        "- Use GROUP BY + ORDER BY to show rankings, trends over years, or multi-crop/country comparisons.\n"
        "- If the user asks 'which is best,' show the TOP 5 so we can compare, not just the winner.\n"
        "- If the user asks about a single crop/area, show its trend over multiple years.\n"
        "- ALWAYS format the results as a Markdown table with headers, separator row, and data rows.\n"
        "Example format:\n"
        "| area | year | hg_ha_yield |\n"
        "| --- | --- | --- |\n"
        "| Brazil | 2018 | 11000 |\n"
        "| Brazil | 2019 | 11500 |\n"
        "| Brazil | 2020 | 12345 |\n\n"
        "Do NOT provide analysis, recommendations or narrative — just the table."
    )
    t2 = time.time()
    data_result = await ask(data_question, enriched)
    phase2_time = time.time() - t2
    pipeline["phases"].append(_phase2_entry(data_question[:60], data_result, phase2_time))

    # ── Extract structured data BEFORE Phase 3 overwrites the answer ──────────
    chart_rows = extract_chart_data(data_result)
    log(f"CHART DATA extracted: {len(chart_rows)} rows")
    if chart_rows:
        log(f"CHART DATA keys: {list(chart_rows[0].keys())}")
        log(f"CHART DATA row 0: {chart_rows[0]}")

    # ── Phase 3: Thinking LLM deep interpretation ──────────────────────────────
    log("PIPELINE PHASE 3 — Thinking LLM interpretation")
    t3 = time.time()
    raw_answer = str(data_result.get("answer", ""))

    # Append structured JSON for deeper reasoning
    structured_data = ""
    if chart_rows:
        import json
        structured_data = "\nSTRUCTURED SQL RESULTS:\n"
        structured_data += json.dumps(chart_rows[:30], indent=2, ensure_ascii=False)

    sql_used = str(data_result.get("sql_query") or data_result.get("sqlQuery") or data_result.get("sql") or "")
    final_answer = await think_interpret(
        question=user_question,
        raw_data=raw_answer + structured_data,
        sql=sql_used,
        schema_context=schema_context,
    )
    phase3_time = time.time() - t3

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    log(f"TWO-PHASE PIPELINE COMPLETE ({total_time:.1f}s)")
    log("=" * 60)

    # Build clean response — put chart rows in 'data' so frontend gets them directly
    resp = {
        "answer": final_answer,
        "sql_query": sql_used,
        "data": chart_rows,
        "pipeline": pipeline,
    }
    return resp


async def multi_phase_query(
    user_question: str,
    metadata_topic: str,
    data_queries: list[dict],
    extra_instructions: str = "",
) -> dict:
    """
    Three-phase pipeline for multiple concurrent data questions.
    Each entry in data_queries: {"question": str, "label": str}
    Returns: {"results": [...], "pipeline": {...}}
    """
    pipeline: dict[str, Any] = {"phases": []}
    t_total = time.time()

    log("=" * 60)
    log(f"MULTI-PHASE PIPELINE: {user_question[:100]}")

    vector_context, schema_context, selected_tables, p0, p1 = await _run_phases(
        user_question, metadata_topic
    )
    pipeline["phases"].extend([p0, p1])

    log(
        f"PIPELINE PHASE 2 — {len(data_queries)} concurrent queries "
        f"(tables: {selected_tables})"
    )
    enriched = _build_enriched_instructions(
        vector_context, schema_context, selected_tables, extra_instructions
    )
    # Phase 2 role: SQL generation + data retrieval only
    enriched += (
        "\n\nPHASE 2 ROLE: Your ONLY job is to generate the correct SQL query and execute it. "
        "CRITICAL RULES FOR DATA RETURN:\n"
        "- NEVER use LIMIT 1. Always return at least 5-10 rows for comparison/trends.\n"
        "- Use GROUP BY + ORDER BY to show rankings, trends over years, or multi-crop/country comparisons.\n"
        "- If the user asks 'which is best,' show the TOP 5 so we can compare, not just the winner.\n"
        "- ALWAYS format the results as a Markdown table with headers, separator row, and data rows.\n"
        "Example format:\n"
        "| area | year | hg_ha_yield |\n"
        "| --- | --- | --- |\n"
        "| Brazil | 2018 | 11000 |\n"
        "| Brazil | 2019 | 11500 |\n\n"
        "Do NOT provide analysis or narrative — just the table."
    )

    t2 = time.time()
    tasks = [ask(q["question"], enriched) for q in data_queries]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    phase2_time = time.time() - t2

    results: list[dict] = []
    for i, r in enumerate(raw_results):
        label = data_queries[i].get("label", f"Consulta {i + 1}")
        if isinstance(r, Exception):
            results.append({"question": label, "error": str(r)})
            pipeline["phases"].append(_phase2_error_entry(label, str(r), phase2_time))
        else:
            results.append({**r, "question": label})
            pipeline["phases"].append(_phase2_entry(label, r, phase2_time))

    # ── Extract chart data BEFORE Phase 3 overwrites the answers ──────────────
    for r in results:
        if "error" not in r:
            r["data"] = extract_chart_data(r)
            log(f"CHART DATA for '{r.get('question','')[:40]}': {len(r['data'])} rows")
            if r["data"]:
                log(f"  keys: {list(r['data'][0].keys())}")
            # Remove execution_result to keep JSON response small
            r.pop("execution_result", None)

    # ── Phase 3: Thinking LLM interpretation for each result ──────────────────
    log(f"PIPELINE PHASE 3 — Thinking LLM interpretation ({len(results)} results)")
    t3 = time.time()
    async def _noop(text: str) -> str:
        return text

    interp_tasks = []
    for r in results:
        if "error" not in r:
            raw_answer = str(r.get("answer", ""))
            structured_data = ""
            if r.get("data"):
                import json
                structured_data = "\nSTRUCTURED SQL RESULTS:\n"
                structured_data += json.dumps(r["data"][:30], indent=2, ensure_ascii=False)
            interp_tasks.append(think_interpret(
                question=r.get("question", user_question),
                raw_data=raw_answer + structured_data,
                sql=str(r.get("sql_query") or r.get("sqlQuery") or r.get("sql") or ""),
                schema_context=schema_context,
            ))
        else:
            interp_tasks.append(_noop(r.get("error", "")))

    interpreted = await asyncio.gather(*interp_tasks, return_exceptions=True)
    phase3_time = time.time() - t3

    for i, r in enumerate(results):
        if "error" not in r and not isinstance(interpreted[i], Exception):
            r["answer"] = interpreted[i]

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    log(f"MULTI-PHASE PIPELINE COMPLETE ({total_time:.1f}s), {len(results)} results")
    log("=" * 60)

    return {"results": results, "pipeline": pipeline}


# ─────────────────────────────────────────────────────────────────────────────
# DeepQuery
# ─────────────────────────────────────────────────────────────────────────────

async def deep_query(question: str, extra_instructions: str = "") -> dict:
    """
    Call /deepQuery — the thinking model plans, executes multiple SQL queries
    iteratively, reasons across results, and produces a comprehensive report.
    """
    log("=" * 70)
    log("DEEP QUERY START")
    log(f"Question: {question[:300]}")

    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += "\n\nADDITIONAL CONTEXT:\n" + extra_instructions

    t0 = time.time()
    result = await sdk_post(
        DEEP_QUERY_URL,
        body={"question": question, "custom_instructions": instructions},
        timeout=TIMEOUT_DEEP,
    )
    elapsed = time.time() - t0

    log(f"DEEP QUERY RESPONSE ({elapsed:.1f}s) keys={list(result.keys())}")
    _log_deep_response(result)
    log("=" * 70)

    chart_data = extract_chart_data(result)
    result.pop("execution_result", None)  # keep response small
    return {**result, "data": chart_data}


def _log_deep_response(result: dict) -> None:
    if result.get("answer"):
        answer = str(result["answer"])
        log(f"ANSWER ({len(answer)} chars): {answer[:500]}")
    if result.get("sql"):
        log(f"SQL: {result['sql']}")
    if result.get("queries"):
        qs = result["queries"]
        log(f"QUERIES executed ({len(qs)}):")
        for idx, q in enumerate(qs):
            if isinstance(q, dict):
                log(f"  [{idx+1}] {str(q.get('question',''))[:120]}")
                log(f"  [{idx+1}] sql: {str(q.get('sql',''))[:200]}")
    if result.get("data") and isinstance(result["data"], list):
        log(f"DATA: {len(result['data'])} rows")


async def smart_query(question: str, extra: str = "") -> dict:
    """Try deepQuery first; fall back to a standard data question on failure."""
    log("smart_query() trying deepQuery first...")
    try:
        result = await deep_query(question, extra)
        log("smart_query() deepQuery succeeded")
        return result
    except Exception as exc:
        log(f"smart_query() deepQuery failed ({exc}), falling back to ask()")
        return await ask(question, extra)