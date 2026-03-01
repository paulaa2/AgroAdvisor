"""AgroAdvisor - Query Pipeline.

Three-phase reasoning:
  Phase 0 - VectorDB semantic search + local table ranking
  Phase 1 - Focused schema discovery for top tables
  Phase 2 - SQL data extraction
  Phase 3 - Thinking LLM interpretation (recommend action, then justify with data)
"""

import asyncio
import json
import time
from typing import Any

from .config import DEEP_QUERY_URL, TABLE_CATALOGUE, TIMEOUT_DEEP
from .prompts import SYSTEM_INSTRUCTIONS
from .sdk_client import ask, discover_schema, sdk_post, vector_search, think_interpret
from .utils import count_rows, extract_data, get_sql, log


# ---- Phase entry builders ----

def _phase_entry(phase: int, name: str, endpoint: str, duration: float, **extra) -> dict:
    entry = {"phase": phase, "name": name, "endpoint": endpoint, "duration_s": round(duration, 1)}
    entry.update(extra)
    return entry


# ---- Table scoring (Phase 0) ----

def _score_tables(question: str) -> list[dict]:
    q = question.lower()
    results = []
    for name, info in TABLE_CATALOGUE.items():
        score = sum(1.0 for kw in info.get("keywords", []) if kw.lower() in q)
        score += sum(0.5 for col in info.get("columns", "").lower().split(", ") if col.strip() and col.strip() in q)
        desc_words = [w for w in info.get("description", "").lower().split() if len(w) > 4]
        score += sum(0.2 for w in desc_words if w in q)
        if info.get("denodo"):
            score += 0.1
        results.append({
            "name": name, "score": round(score, 2),
            "description": info["description"],
            "denodo": info.get("denodo", False),
            "join_keys": info.get("join_keys", ""),
            "use_for": info.get("use_for", ""),
        })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


def _build_table_context(tables: list[str]) -> str:
    parts = []
    for name in tables:
        info = TABLE_CATALOGUE.get(name)
        if not info:
            continue
        queryable = "YES" if info.get("denodo") else "NO (local CSV)"
        parts.append(
            f"TABLE: {name}\n"
            f"  Columns: {info['columns']}\n"
            f"  Use for: {info['use_for']}\n"
            f"  Queryable: {queryable}"
        )
    return "\n\n".join(parts)


# ---- Core phases ----

async def _run_phases(user_question: str, metadata_topic: str):
    """Run Phase 0 + Phase 1. Returns (vector_ctx, schema_ctx, selected_tables, p0, p1)."""

    # Phase 0: VectorDB + table ranking
    log(f"PHASE 0 - VectorDB + ranking: {user_question[:100]}")
    t0 = time.time()
    vector_context = ""
    try:
        vector_context = await vector_search(user_question)
    except Exception as exc:
        log(f"PHASE 0 VectorDB failed: {exc}")

    ranked = _score_tables(user_question)
    top_names = [t["name"] for t in ranked[:3] if t["score"] > 0]
    p0 = _phase_entry(0, "Busqueda semantica + Ranking", "answerMetadataQuestion",
                       time.time() - t0, ranked_tables=ranked,
                       result_summary=f"Top: {', '.join(top_names)}")

    # Phase 1: Schema discovery
    denodo_top = [t for t in ranked if t["denodo"] and t["score"] > 0]
    any_top = [t for t in ranked if t["score"] > 0]
    selected = [t["name"] for t in (denodo_top or any_top)[:2]] or ([ranked[0]["name"]] if ranked else [])

    log(f"PHASE 1 - Schema for: {selected}")
    t1 = time.time()
    schema_context = ""
    try:
        meta = await discover_schema(f"Schema for: {', '.join(selected)}. Context: {metadata_topic}")
        schema_context = str(meta.get("answer", ""))
    except Exception as exc:
        log(f"PHASE 1 failed: {exc}")

    local_ctx = _build_table_context(selected)
    if local_ctx:
        schema_context = local_ctx + ("\n\n" + schema_context if schema_context else "")

    p1 = _phase_entry(1, "Seleccion de tabla", "answerMetadataQuestion",
                       time.time() - t1, selected_tables=selected,
                       result_summary=schema_context[:600] if schema_context else "Local schema only")

    log(f"PHASE 0+1 done | selected={selected} | schema={len(schema_context)} chars")
    return vector_context, schema_context, selected, p0, p1


def _build_instructions(vector_ctx: str, schema_ctx: str, tables: list[str], extra: str = "") -> str:
    """Build Phase 2 instruction block from prior phases."""
    parts = []
    if vector_ctx:
        parts.append(f"VECTORDB CONTEXT:\n{vector_ctx[:1200]}")
    if schema_ctx:
        parts.append(f"TABLE SCHEMA:\n{schema_ctx}")
    denodo_tables = [t for t in tables if TABLE_CATALOGUE.get(t, {}).get("denodo")]
    if denodo_tables:
        parts.append(f"FOCUS: query {', '.join(denodo_tables)}. Do NOT query other views unless necessary.")
    parts.append('The yield column is "hg_ha_yield" (numeric, no CAST needed).')
    parts.append(
        "PHASE 2 ROLE: Generate correct SQL and execute it.\n"
        "- NEVER use LIMIT 1. At least 10-20 rows for comparisons, ALL years for trends.\n"
        "- Use GROUP BY + ORDER BY for rankings/trends.\n"
        "- Format results as Markdown table. No analysis - just data."
    )
    if extra:
        parts.append(extra)
    return "\n\n".join(parts)


# ---- Public pipelines ----

async def two_phase_query(
    user_question: str,
    metadata_topic: str,
    data_question: str,
    extra_instructions: str = "",
) -> dict:
    """Single-question pipeline: Phase 0+1+2+3."""
    pipeline: dict[str, Any] = {"phases": []}
    t_total = time.time()
    log(f"{'='*60}\nPIPELINE: {user_question[:100]}")

    vector_ctx, schema_ctx, tables, p0, p1 = await _run_phases(user_question, metadata_topic)
    pipeline["phases"].extend([p0, p1])

    # Phase 2: SQL query
    log(f"PHASE 2 - SQL query: {data_question[:120]}")
    instructions = _build_instructions(vector_ctx, schema_ctx, tables, extra_instructions)
    t2 = time.time()
    data_result = await ask(data_question, instructions)
    phase2_time = time.time() - t2
    pipeline["phases"].append(_phase_entry(
        2, data_question[:60], "answerDataQuestion", phase2_time,
        sql_query=get_sql(data_result), rows_returned=count_rows(data_result),
    ))

    # Extract structured data before Phase 3 overwrites the answer
    rows = extract_data(data_result)
    log(f"Extracted {len(rows)} data rows")

    # Phase 3: Thinking LLM interpretation
    log("PHASE 3 - Thinking LLM")
    t3 = time.time()
    raw_answer = str(data_result.get("answer", ""))
    structured = ""
    if rows:
        structured = f"\nSTRUCTURED DATA:\n{json.dumps(rows[:30], indent=2, ensure_ascii=False)}"

    final_answer = await think_interpret(
        question=user_question,
        raw_data=raw_answer + structured,
        sql=get_sql(data_result),
        schema_context=schema_ctx,
    )

    total = time.time() - t_total
    pipeline["total_duration_s"] = round(total, 1)
    log(f"PIPELINE COMPLETE ({total:.1f}s)\n{'='*60}")

    return {
        "answer": final_answer,
        "sql_query": get_sql(data_result),
        "data": rows,
        "pipeline": pipeline,
    }


async def multi_phase_query(
    user_question: str,
    metadata_topic: str,
    data_queries: list[dict],
    extra_instructions: str = "",
) -> dict:
    """Multi-question pipeline: shared Phase 0+1, concurrent Phase 2, parallel Phase 3."""
    pipeline: dict[str, Any] = {"phases": []}
    t_total = time.time()
    log(f"{'='*60}\nMULTI-PIPELINE: {user_question[:100]}")

    vector_ctx, schema_ctx, tables, p0, p1 = await _run_phases(user_question, metadata_topic)
    pipeline["phases"].extend([p0, p1])

    # Phase 2: Concurrent SQL queries
    instructions = _build_instructions(vector_ctx, schema_ctx, tables, extra_instructions)
    log(f"PHASE 2 - {len(data_queries)} concurrent queries")
    t2 = time.time()
    tasks = [ask(q["question"], instructions) for q in data_queries]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    phase2_time = time.time() - t2

    results = []
    for i, r in enumerate(raw_results):
        label = data_queries[i].get("label", f"Consulta {i+1}")
        if isinstance(r, Exception):
            results.append({"question": label, "error": str(r)})
            pipeline["phases"].append(_phase_entry(2, label, "answerDataQuestion", phase2_time, error=str(r)))
        else:
            results.append({**r, "question": label})
            pipeline["phases"].append(_phase_entry(
                2, label, "answerDataQuestion", phase2_time,
                sql_query=get_sql(r), rows_returned=count_rows(r),
            ))

    # Extract data from each result
    for r in results:
        if "error" not in r:
            r["data"] = extract_data(r)
            r.pop("execution_result", None)

    # Phase 3: Parallel thinking LLM interpretation
    log(f"PHASE 3 - Interpreting {len(results)} results")
    t3 = time.time()

    async def _noop(text):
        return text

    interp_tasks = []
    for r in results:
        if "error" not in r:
            raw = str(r.get("answer", ""))
            structured = ""
            if r.get("data"):
                structured = f"\nSTRUCTURED DATA:\n{json.dumps(r['data'][:30], indent=2, ensure_ascii=False)}"
            interp_tasks.append(think_interpret(
                question=r.get("question", user_question),
                raw_data=raw + structured,
                sql=get_sql(r),
                schema_context=schema_ctx,
            ))
        else:
            interp_tasks.append(_noop(r.get("error", "")))

    interpreted = await asyncio.gather(*interp_tasks, return_exceptions=True)
    for i, r in enumerate(results):
        if "error" not in r and not isinstance(interpreted[i], Exception):
            r["answer"] = interpreted[i]

    total = time.time() - t_total
    pipeline["total_duration_s"] = round(total, 1)
    log(f"MULTI-PIPELINE COMPLETE ({total:.1f}s) {len(results)} results\n{'='*60}")

    return {"results": results, "pipeline": pipeline}


# ---- DeepQuery ----

async def deep_query(question: str, extra_instructions: str = "") -> dict:
    log(f"DEEP QUERY: {question[:300]}")
    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += f"\n\nADDITIONAL CONTEXT:\n{extra_instructions}"

    t0 = time.time()
    result = await sdk_post(
        DEEP_QUERY_URL,
        body={"question": question, "custom_instructions": instructions},
        timeout=TIMEOUT_DEEP,
    )
    log(f"DEEP QUERY done ({time.time()-t0:.1f}s)")

    data = extract_data(result)
    result.pop("execution_result", None)
    return {**result, "data": data}


async def smart_query(question: str, extra: str = "") -> dict:
    try:
        result = await deep_query(question, extra)
        log("smart_query() deepQuery succeeded")
        return result
    except Exception as exc:
        log(f"smart_query() deepQuery failed ({exc}), fallback to ask()")
        return await ask(question, extra)
