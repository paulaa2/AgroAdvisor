"""AgroAdvisor - Denodo AI SDK HTTP Client."""

import asyncio
import time
import httpx

from .config import (
    AUTH, DATA_URL, METADATA_URL, VDP_DATABASE,
    TIMEOUT_DATA, TIMEOUT_METADATA, TIMEOUT_VECTOR,
    THINKING_MODEL, OLLAMA_BASE_URL,
)
from .prompts import SYSTEM_INSTRUCTIONS
from .utils import log, count_rows

_metadata_cache: dict[str, dict] = {}
_vector_cache: dict[str, str] = {}

# Short SQL-only instructions for /answerDataQuestion.
# SYSTEM_INSTRUCTIONS is too large and causes the SDK to skip SQL generation.
_SQL_INSTRUCTIONS = f"""You are a SQL agent for a Denodo VDP database "{VDP_DATABASE}".
Your ONLY job is to generate and execute SQL. NEVER answer from general knowledge.

VIEWS (database "{VDP_DATABASE}"):
  yield          - area, item, year, hg_ha_yield, average_rain_fall_mm_per_year, pesticides_tonnes, avg_temp
  crop           - label, n, p, k, temperature, humidity, ph, rainfall
  yield_j_crop   - area, item, year, hg_ha_yield, pesticides_tonnes, average_rain_fall_mm_per_year, avg_temp, n, p, k, ph, humidity
  price_j_yield  - area, item, year, hg_ha_yield, coffee_arabica, coffee_robustas, tea_columbo, sugar_eu, sugar_world, oil_brent

SQL RULES:
  - Double-quote all identifiers: "area", "hg_ha_yield", "yield"
  - NEVER use ILIKE. Use LOWER() + LIKE: WHERE LOWER("area") LIKE '%brazil%'
  - NEVER use PostgreSQL functions (this is Denodo VDP)
  - NEVER use LIMIT 1. Return at least 20 rows; for trends no LIMIT
  - ALL filter values in ENGLISH: arroz->Rice, Espana->Spain, etc.
  - Return results as a Markdown table

TRANSLATIONS: arroz->Rice, trigo->Wheat, maiz->Maize, patatas->Potatoes,
  soja->Soybeans, cafe->Coffee, Espana->Spain, Brasil->Brazil,
  Francia->France, Alemania->Germany, Mexico->Mexico
"""


async def sdk_get(url: str, params: dict | None = None, timeout: float = 300) -> dict:
    endpoint = url.split("/")[-1]
    log(f"SDK GET /{endpoint}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.get(url, params=params or {})
        log(f"SDK GET /{endpoint} -> {resp.status_code} ({time.time()-t0:.1f}s)")
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = resp.text[:500] if resp.text else str(exc)
            log(f"ERROR SDK /{endpoint}: {body[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {body}") from exc
        data = resp.json()
        if "answer" in data:
            log(f"SDK /{endpoint} answer={len(str(data['answer']))} chars")
        return data


async def sdk_post(url: str, body: dict | None = None, timeout: float = 600) -> dict:
    endpoint = url.split("/")[-1]
    log(f"SDK POST /{endpoint}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.post(url, json=body or {})
        log(f"SDK POST /{endpoint} -> {resp.status_code} ({time.time()-t0:.1f}s)")
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body_text = resp.text[:500] if resp.text else str(exc)
            log(f"ERROR SDK /{endpoint}: {body_text[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {body_text}") from exc
        return resp.json()


async def sdk_stream_sse(url: str, params: dict | None = None, timeout: float = 900):
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        async with client.stream("GET", url, params=params or {}) as resp:
            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                async for line in resp.aiter_lines():
                    yield line + "\n"
            else:
                body = await resp.aread()
                yield body.decode("utf-8", errors="replace")


async def ask(question: str, extra_instructions: str = "", _retry: bool = True) -> dict:
    """Send a data question to /answerDataQuestion. Auto-retries on 0 rows."""
    log(f"ask() '{question[:120]}'")

    instructions = _SQL_INSTRUCTIONS
    if extra_instructions:
        instructions = f"CONTEXT:\n{extra_instructions}\n\n{instructions}"

    sql_question = f"EXECUTE SQL: {question}"
    result = await sdk_get(
        DATA_URL,
        params={"question": sql_question, "custom_instructions": instructions},
        timeout=TIMEOUT_DATA,
    )

    sql_ret = result.get("sql_query", "")
    answer = result.get("answer", "")
    log(f"ask() sql_len={len(sql_ret)} answer_len={len(str(answer))}")
    if sql_ret:
        log(f"ask() SQL: {sql_ret[:300]}")

    if _retry and count_rows(result) == 0 and len(str(answer)) < 1500:
        log("ask() 0 rows - retrying with schema discovery")
        try:
            schema = await discover_schema(
                f"tables, columns, item/area names for: {question[:200]}"
            )
            hint = str(schema.get("answer", ""))[:800]
            retry_ctx = (
                f"PREVIOUS ATTEMPT returned 0 rows. Schema:\n{hint}\n\n"
                f"Use EXACT column/view names above. Try LOWER()+LIKE with partial matches.\n"
            )
            if extra_instructions:
                retry_ctx = f"{extra_instructions}\n\n{retry_ctx}"
            result = await ask(question, retry_ctx, _retry=False)
        except Exception as exc:
            log(f"ask() retry failed: {exc}")

    return result


async def think_interpret(question: str, raw_data: str, sql: str = "", schema_context: str = "") -> str:
    """Phase 3 - Deep reasoning via Ollama thinking model."""
    log(f"think_interpret() model={THINKING_MODEL} data={len(raw_data)} chars")
    t0 = time.time()

    context_parts = []
    if sql:
        context_parts.append(f"SQL EXECUTED:\n`sql\n{sql}\n`")
    if schema_context:
        context_parts.append(f"SCHEMA CONTEXT:\n{schema_context[:800]}")
    context_parts.append(f"QUERY RESULTS:\n{raw_data}")

    user_prompt = (
        "You are AgroAdvisor, an expert agricultural consultant. "
        "N, P, K are nitrogen, phosphorus, potassium - essential soil nutrients.\n\n"
        f"USER QUESTION:\n{question}\n\n"
        + "\n\n".join(context_parts) + "\n\n"
        "INSTRUCTIONS:\n"
        "1. LEAD WITH 2-3 SPECIFIC ACTIONS backed by numbers from the data.\n"
        "   Example: 'Plant rice: yields 45,200 hg/ha vs wheat at 28,100 (+61%)'\n"
        "2. THEN EXPLAIN WHY - walk through trends, correlations, % changes.\n"
        "   Every claim must cite a number from the data.\n"
        "3. STYLE: flowing prose, no section headers, no raw tables.\n"
        "   Never mention DB table names. Write in the user's language.\n"
        "   Minimum 200 words of analysis.\n"
    )

    payload = {
        "model": THINKING_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            result_text = resp.json().get("message", {}).get("content", raw_data)
        log(f"think_interpret() done ({time.time()-t0:.1f}s) {len(result_text)} chars")
        return result_text
    except Exception as exc:
        log(f"think_interpret() FAILED: {exc}")
        return raw_data


async def ask_metadata(question: str) -> dict:
    log(f"ask_metadata() '{question[:150]}'")
    t0 = time.time()
    result = await sdk_get(METADATA_URL, params={"question": question}, timeout=TIMEOUT_METADATA)
    log(f"ask_metadata() done ({time.time()-t0:.1f}s)")
    return result


async def discover_schema(topic: str) -> dict:
    if topic in _metadata_cache:
        return _metadata_cache[topic]
    try:
        result = await ask_metadata(
            f"What tables and columns relate to: {topic}? "
            f"List views with columns. Database: '{VDP_DATABASE}'."
        )
        _metadata_cache[topic] = result
        return result
    except Exception as exc:
        log(f"discover_schema() failed: {exc}")
        return {}


async def vector_search(question: str) -> str:
    cache_key = question[:150]
    if cache_key in _vector_cache:
        return _vector_cache[cache_key]

    log(f"vector_search() '{question[:100]}'")
    t0 = time.time()

    queries = [
        f"What columns and data types relate to: {question}",
        f"Show sample values for items and areas in '{VDP_DATABASE}'",
        f"Exact column names for yield, climate, pesticides, prices in '{VDP_DATABASE}'",
    ]
    tasks = [sdk_get(METADATA_URL, params={"question": q}, timeout=TIMEOUT_VECTOR) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    fragments = []
    for r in results:
        if isinstance(r, dict) and r.get("answer"):
            fragments.append(str(r["answer"]))

    combined = "\n---\n".join(fragments)
    log(f"vector_search() done ({time.time()-t0:.1f}s) {len(fragments)} fragments")
    _vector_cache[cache_key] = combined
    return combined


async def multi_ask(queries: list[dict]) -> list[dict]:
    tasks = [ask(q["question"], q.get("extra", "")) for q in queries]
    raw = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        {"question": queries[i].get("label", queries[i]["question"]), "error": str(r)}
        if isinstance(r, Exception)
        else {**r, "question": queries[i].get("label", queries[i]["question"])}
        for i, r in enumerate(raw)
    ]
