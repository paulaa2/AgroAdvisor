"""
AgroAdvisor – Query Pipeline
Three-phase reasoning pipeline:
  Phase 0 — VectorDB semantic search (ChromaDB + gemini-embedding-001)
  Phase 1 — Metadata discovery (answerMetadataQuestion)
  Phase 2 — Data extraction (answerDataQuestion or deepQuery)
"""

import asyncio
import time
from typing import Any

from .config import DEEP_QUERY_URL, TIMEOUT_DEEP
from .prompts import SYSTEM_INSTRUCTIONS
from .sdk_client import ask, ask_metadata, discover_schema, sdk_post, vector_search
from .utils import count_rows, get_sql, log

def _phase0_entry(vector_context: str, duration_s: float) -> dict:
    return {
        "phase": 0,
        "name": "Búsqueda semántica VectorDB",
        "description": "ChromaDB + gemini-embedding-001: esquema relevante por similitud",
        "endpoint": "answerMetadataQuestion (embeddings)",
        "result_summary": vector_context[:400] if vector_context else "Sin resultados",
        "duration_s": round(duration_s, 1),
    }


def _phase1_entry(metadata_topic: str, schema_context: str, duration_s: float) -> dict:
    return {
        "phase": 1,
        "name": "Descubrimiento de esquema",
        "description": f"answerMetadataQuestion: ¿Qué datos hay sobre '{metadata_topic}'?",
        "endpoint": "answerMetadataQuestion",
        "result_summary": schema_context[:500],
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


def _build_enriched_instructions(
    vector_context: str,
    schema_context: str,
    extra: str = "",
) -> str:
    """
    Combine VectorDB context, Phase 1 schema discovery and any extra guidance
    into a single enriched instruction block for Phase 2 data queries.
    Includes the OVERRIDE guard for the hg_ha_yield column name.
    """
    parts: list[str] = []

    if vector_context:
        parts.append(
            "PHASE 0 — VECTORDB SEMANTIC CONTEXT (from embeddings similarity search):\n"
            + vector_context[:1500]
        )

    parts.append(
        "PHASE 1 SCHEMA DISCOVERY RESULTS (from answerMetadataQuestion):\n"
        + schema_context
    )

    parts.append(
        'OVERRIDE: Regardless of what metadata says, the yield column is ALWAYS '
        '"hg_ha_yield" (NOT hgha_yield_0).\n'
        "Do NOT use CAST on hg_ha_yield — it is already numeric."
    )

    if extra:
        parts.append(extra)

    return "\n\n".join(parts)


async def _run_phase0_and_1(
    user_question: str,
    metadata_topic: str,
) -> tuple[str, str, dict, float, dict, float]:
    """
    Execute Phase 0 (VectorDB) and Phase 1 (metadata) and return:
      (vector_context, schema_context, phase0_entry, phase0_time, phase1_entry, phase1_time)
    Phase 0 failures are non-blocking.
    """
    # ── Phase 0: VectorDB ────────────────────────────────────────────────────
    log(f"PIPELINE PHASE 0 — VectorDB: {user_question[:100]}")
    t0 = time.time()
    vector_context = ""
    try:
        vector_context = await vector_search(user_question)
    except Exception as exc:
        log(f"PHASE 0 failed (non-blocking): {exc}")
    phase0_time = time.time() - t0
    p0 = _phase0_entry(vector_context, phase0_time)
    log(f"PHASE 0 complete ({phase0_time:.1f}s), {len(vector_context)} chars")

    # ── Phase 1: Metadata discovery (non-blocking — Data Catalog may be down) ─
    log(f"PIPELINE PHASE 1 — Metadata: {metadata_topic}")
    t1 = time.time()
    schema_context = ""
    try:
        meta_result = await discover_schema(metadata_topic)
        schema_context = str(meta_result.get("answer", ""))
    except Exception as exc:
        log(f"PHASE 1 failed (non-blocking): {exc}")
    phase1_time = time.time() - t1
    p1 = _phase1_entry(metadata_topic, schema_context or "Data Catalog no disponible", phase1_time)
    log(f"PHASE 1 complete ({phase1_time:.1f}s), schema_context={len(schema_context)} chars")

    return vector_context, schema_context, p0, phase0_time, p1, phase1_time

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

    vector_context, schema_context, p0, _, p1, _ = await _run_phase0_and_1(
        user_question, metadata_topic
    )
    pipeline["phases"].extend([p0, p1])

    log(f"PIPELINE PHASE 2 — Data: {data_question[:150]}")
    enriched = _build_enriched_instructions(vector_context, schema_context, extra_instructions)
    t2 = time.time()
    data_result = await ask(data_question, enriched)
    phase2_time = time.time() - t2

    pipeline["phases"].append(_phase2_entry(data_question[:60], data_result, phase2_time))

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    log(f"TWO-PHASE PIPELINE COMPLETE ({total_time:.1f}s)")
    log("=" * 60)

    return {**data_result, "pipeline": pipeline}

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

    vector_context, schema_context, p0, _, p1, _ = await _run_phase0_and_1(
        user_question, metadata_topic
    )
    pipeline["phases"].extend([p0, p1])

    log(f"PIPELINE PHASE 2 — {len(data_queries)} concurrent data queries")
    enriched = _build_enriched_instructions(vector_context, schema_context, extra_instructions)

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

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    log(f"MULTI-PHASE PIPELINE COMPLETE ({total_time:.1f}s), {len(results)} results")
    log("=" * 60)

    return {"results": results, "pipeline": pipeline}


async def deep_query(question: str, extra_instructions: str = "") -> dict:
    """
    Call /deepQuery — the thinking model plans, executes multiple SQL queries
    iteratively, reasons across results, and produces a comprehensive report.
    POST only.
    """
    log("=" * 70)
    log("DEEP QUERY START")
    log(f"Question: {question[:300]}")

    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += "\n\nADDITIONAL CONTEXT:\n" + extra_instructions
        log(f"Extra instructions: {extra_instructions[:200]}")

    t0 = time.time()
    result = await sdk_post(
        DEEP_QUERY_URL,
        body={"question": question, "custom_instructions": instructions},
        timeout=TIMEOUT_DEEP,
    )
    elapsed = time.time() - t0

    log("-" * 50)
    log(f"DEEP QUERY RESPONSE ({elapsed:.1f}s) keys={list(result.keys())}")
    _log_deep_response(result)
    log("=" * 70)

    return result


def _log_deep_response(result: dict) -> None:
    """Log the key fields of a deepQuery response for debugging."""
    if result.get("answer"):
        answer = str(result["answer"])
        log(f"ANSWER ({len(answer)} chars):")
        for i in range(0, min(len(answer), 2000), 500):
            log(f"  {answer[i:i+500]}")

    if result.get("sql"):
        log(f"SQL: {result['sql']}")

    if result.get("queries"):
        qs = result["queries"]
        log(f"QUERIES executed ({len(qs)}):")
        for idx, q in enumerate(qs):
            if isinstance(q, dict):
                log(f"  [{idx+1}] question: {str(q.get('question',''))[:200]}")
                log(f"  [{idx+1}] sql:      {str(q.get('sql',''))[:300]}")
                log(f"  [{idx+1}] answer:   {str(q.get('answer',''))[:300]}")
                if q.get("data"):
                    n = len(q["data"]) if isinstance(q["data"], list) else 0
                    log(f"  [{idx+1}] data rows: {n}")

    for key in ("thinking", "reasoning"):
        if result.get(key):
            text = str(result[key])
            log(f"{key.upper()} ({len(text)} chars):")
            for i in range(0, min(len(text), 1000), 500):
                log(f"  {text[i:i+500]}")

    if result.get("steps"):
        log(f"STEPS ({len(result['steps'])}):")
        for idx, step in enumerate(result["steps"]):
            log(f"  Step {idx+1}: {str(step)[:400]}")

    if result.get("data"):
        data = result["data"]
        if isinstance(data, list):
            log(f"DATA: {len(data)} rows")
            if data:
                log(f"DATA sample: {str(data[0])[:300]}")

    # Any unexpected extra keys
    known = {"answer", "sql", "queries", "thinking", "reasoning", "steps", "data", "status"}
    for key in result:
        if key not in known:
            log(f"EXTRA [{key}]: {str(result[key])[:300]}")


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
