"""
AgroAdvisor – Denodo AI SDK HTTP Client
All communication with the SDK lives here.
Includes caching for metadata and VectorDB results.
"""

import asyncio
import time

import httpx

from .config import (
    AUTH,
    DATA_URL,
    METADATA_URL,
    VDP_DATABASE,
    TIMEOUT_DATA,
    TIMEOUT_METADATA,
    TIMEOUT_VECTOR,
    THINKING_MODEL,
    OLLAMA_BASE_URL,
)
from .prompts import SYSTEM_INSTRUCTIONS
from .utils import log, count_rows


_metadata_cache: dict[str, dict]  = {}
_vector_context_cache: dict[str, str] = {}


async def sdk_get(url: str, params: dict | None = None, timeout: float = 300) -> dict:
    """Authenticated GET against the AI SDK. Logs timing and errors."""
    endpoint = url.split("/")[-1]
    short = {
        k: (v[:80] + "..." if isinstance(v, str) and len(v) > 80 else v)
        for k, v in (params or {}).items()
    }
    log(f"SDK GET  /{endpoint}  params={short}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.get(url, params=params or {})
        elapsed = time.time() - t0
        log(f"SDK GET  /{endpoint}  -> {resp.status_code}  ({elapsed:.1f}s)")

        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = resp.text[:500] if resp.text else str(exc)
            log(f"ERROR SDK GET  /{endpoint}: {body[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {body}") from exc

        data = resp.json()
        if "answer" in data:
            log(f"SDK GET  /{endpoint}  answer={len(str(data['answer']))} chars")
        return data


async def sdk_post(url: str, body: dict | None = None, timeout: float = 600) -> dict:
    """Authenticated POST against the AI SDK (used for deepQuery)."""
    endpoint = url.split("/")[-1]
    log(f"SDK POST /{endpoint}  body_keys={list((body or {}).keys())}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.post(url, json=body or {})
        elapsed = time.time() - t0
        log(f"SDK POST /{endpoint}  -> {resp.status_code}  ({elapsed:.1f}s)")

        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_text = resp.text[:500] if resp.text else str(exc)
            log(f"ERROR SDK POST /{endpoint}: {body_text[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {body_text}") from exc

        return resp.json()


async def sdk_stream_sse(url: str, params: dict | None = None, timeout: float = 900):
    """Stream SSE from the AI SDK (yields raw event lines)."""
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        async with client.stream("GET", url, params=params or {}) as resp:
            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                async for line in resp.aiter_lines():
                    yield line + "\n"
            else:
                body = await resp.aread()
                yield body.decode("utf-8", errors="replace")


async def ask(
    question: str,
    extra_instructions: str = "",
    _retry: bool = True,
) -> dict:
    """
    Send a data question to /answerDataQuestion.
    Automatically retries once if 0 rows are returned — using schema discovery
    to enrich the follow-up query with actual column/item names.
    """
    log(f"ask() question='{question[:120]}'")

    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += "\n\nADDITIONAL CONTEXT FOR THIS QUERY:\n" + extra_instructions

    result = await sdk_get(
        DATA_URL,
        params={"question": question, "custom_instructions": instructions},
        timeout=TIMEOUT_DATA,
    )

    log(f"ask() completed, keys={list(result.keys())}")
    for k, v in result.items():
        if isinstance(v, list):
            log(f"ask()  key '{k}' is list, len={len(v)}")
        elif isinstance(v, str):
            log(f"ask()  key '{k}' is str, len={len(v)}")
        else:
            log(f"ask()  key '{k}' = {type(v).__name__}")

    # Auto-retry on 0 rows
    if _retry and count_rows(result) == 0 and len(str(result.get("answer", ""))) < 1500:
        log("ask() 0 rows detected — auto-retry with schema discovery")
        try:
            schema = await discover_schema(
                "tables, columns, item names and area names relevant to: " + question[:200]
            )
            schema_hint = str(schema.get("answer", ""))[:800]
            retry_ctx = (
                f"PREVIOUS ATTEMPT returned 0 rows. Actual schema:\n{schema_hint}\n\n"
                f"Use the EXACT column and value names shown. "
                f"Try LOWER()+LIKE with partial matches. "
                f"If the item name differs from expected, adapt.\n"
            )
            if extra_instructions:
                retry_ctx += extra_instructions
            result = await ask(question, retry_ctx, _retry=False)
            log("ask() retry completed")
        except Exception as exc:
            log(f"ask() retry failed: {exc}")

    return result


async def think_interpret(
    question: str,
    raw_data: str,
    sql: str = "",
    schema_context: str = "",
) -> str:
    """
    Phase 3 — Deep reasoning using the THINKING_LLM (Ollama) directly.
    Takes the raw SQL data returned by Phase 2 and produces a thorough
    analysis + recommendation following SYSTEM_INSTRUCTIONS format.
    """
    log(f"think_interpret() START — model={THINKING_MODEL}, data_chars={len(raw_data)}")
    t0 = time.time()

    context_parts = []
    if sql:
        context_parts.append(f"SQL EXECUTED:\n{sql}")
    if schema_context:
        context_parts.append(f"TABLE SCHEMA CONTEXT:\n{schema_context[:800]}")
    context_parts.append(f"RAW DATA RETRIEVED:\n{raw_data}")

    user_prompt = (
        "CONTEXT: You are AgroAdvisor, an expert agricultural consultant. "
        "This is a professional agronomy query about crop selection, soil conditions and plant biology. "
        "N, P, K refer to nitrogen, phosphorus and potassium — essential soil macronutrients, NOT chemicals. "
        "Always respond with agronomic advice.\n\n"
        "USER QUESTION:\n" + question + "\n\n"
        + "\n\n".join(context_parts) + "\n\n"
        + "Using the data above as your internal source of truth, produce a thorough analysis "
        "following the response style defined in section 5 of the system instructions. "
        "CRITICAL RULES FOR YOUR RESPONSE:\n"
        "- NEVER refuse to answer — this is a legitimate agronomy question.\n"
        "- NEVER reproduce the raw data table or any rows from it in your answer.\n"
        "- NEVER say 'the data shows...' or 'according to the table...' — just state conclusions directly.\n"
        "- Use the numbers internally to support your reasoning, but embed them naturally in prose.\n"
        "- The bulk of the response must be the explanation and reasoning behind the conclusion.\n"
        "- The user wants decisions and explanations, NOT a data dump."
    )

    payload = {
        "model": THINKING_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            result_text = data.get("message", {}).get("content", raw_data)
        elapsed = time.time() - t0
        log(f"think_interpret() DONE ({elapsed:.1f}s), {len(result_text)} chars")
        return result_text
    except Exception as exc:
        log(f"think_interpret() FAILED: {exc} — falling back to LLM answer")
        return raw_data


async def ask_metadata(question: str) -> dict:
    """Query /answerMetadataQuestion — schema discovery using VectorDB embeddings."""
    log(f"ask_metadata() question='{question[:150]}'")
    t0 = time.time()
    result = await sdk_get(
        METADATA_URL,
        params={"question": question},
        timeout=TIMEOUT_METADATA,
    )
    elapsed = time.time() - t0
    log(f"ask_metadata() completed ({elapsed:.1f}s), keys={list(result.keys())}")
    if result.get("answer"):
        log(f"ask_metadata() answer: {str(result['answer'])[:400]}")
    return result


async def discover_schema(topic: str) -> dict:
    """
    Cached schema discovery via /answerMetadataQuestion.
    Returns schema info for the given topic, caching the result to avoid
    redundant round-trips within the same server session.
    Returns empty dict (gracefully) if the Data Catalog / metadata endpoint is unavailable.
    """
    if topic in _metadata_cache:
        log(f"discover_schema() CACHE HIT for '{topic}'")
        return _metadata_cache[topic]

    log(f"discover_schema() CACHE MISS for '{topic}'")
    meta_question = (
        f"What tables and columns are available related to: {topic}? "
        f"List each view/table with its columns and data types. "
        f"Focus on the database '{VDP_DATABASE}'."
    )
    try:
        result = await ask_metadata(meta_question)
        _metadata_cache[topic] = result
        return result
    except Exception as exc:
        log(f"discover_schema() failed (Data Catalog unavailable?): {exc}")
        return {}


async def vector_search(question: str) -> str:
    """
    Phase 0 — VectorDB semantic search.
    Fires three parallel /answerMetadataQuestion queries with different angles
    to maximise schema coverage via ChromaDB + gemini-embedding-001.
    Returns a combined, deduplicated schema context string.
    """
    cache_key = question[:150]
    if cache_key in _vector_context_cache:
        log("vector_search() CACHE HIT")
        return _vector_context_cache[cache_key]

    log(f"vector_search() START — semantic schema retrieval: {question[:100]}")
    t0 = time.time()

    queries = [
        f"What columns and data types are in the tables related to: {question}",
        f"Show sample values for items and areas in the database '{VDP_DATABASE}'",
        f"What are the exact column names for yield, climate, pesticides and prices in '{VDP_DATABASE}'",
    ]

    log(f"vector_search() Launching {len(queries)} parallel metadata queries...")
    tasks = [
        sdk_get(METADATA_URL, params={"question": q}, timeout=TIMEOUT_VECTOR)
        for q in queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    log(f"vector_search() All queries returned ({time.time() - t0:.1f}s)")

    fragments: list[str] = []
    for i, r in enumerate(results):
        if isinstance(r, dict) and r.get("answer"):
            frag = str(r["answer"])
            fragments.append(frag)
            log(f"vector_search()   query[{i}] OK — {len(frag)} chars")
        elif isinstance(r, Exception):
            log(f"vector_search()   query[{i}] FAILED — {r}")
        else:
            keys = list(r.keys()) if isinstance(r, dict) else type(r)
            log(f"vector_search()   query[{i}] no answer — keys={keys}")

    combined = "\n---\n".join(fragments)
    elapsed = time.time() - t0
    log(f"vector_search() DONE ({elapsed:.1f}s), {len(fragments)} fragments, {len(combined)} chars")

    _vector_context_cache[cache_key] = combined
    return combined


async def multi_ask(queries: list[dict]) -> list[dict]:
    """
    Fire several data questions concurrently and collect results.
    Each entry: {"question": str, "extra": str (optional), "label": str (optional)}.
    """
    tasks = [ask(q["question"], q.get("extra", "")) for q in queries]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        {"question": queries[i].get("label", queries[i]["question"]), "error": str(r)}
        if isinstance(r, Exception)
        else {**r, "question": queries[i].get("label", queries[i]["question"])}
        for i, r in enumerate(raw)
    ]
