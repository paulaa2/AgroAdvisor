"""
AgroAdvisor – HackUDC 2026
"""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx, os, json, re, asyncio, time
import html as html_mod

# ─── Logging ──────────────────────────────────────────────────────
import sys

def _log(msg: str):
    """Print log directly to stdout — always visible in terminal."""
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

AI_SDK_BASE_URL = os.getenv("AI_SDK_BASE_URL", "http://localhost:8008")
DENODO_USER     = os.getenv("DENODO_USER", "admin")
DENODO_PASS     = os.getenv("DENODO_PASS", "admin")

VDP_DATABASE = "proba"

# ─── Country / crop name translation (user language → English DB value) ───────
AREA_TRANSLATIONS = {
    "brasil": "Brazil", "españa": "Spain", "alemania": "Germany",
    "francia": "France", "estados unidos": "United States of America",
    "reino unido": "United Kingdom", "países bajos": "Netherlands",
    "japón": "Japan", "méxico": "Mexico", "perú": "Peru",
    "italia": "Italy", "rusia": "Russian Federation", "turquía": "Turkey",
    "egipto": "Egypt", "corea del sur": "Republic of Korea",
    "sudáfrica": "South Africa", "nueva zelanda": "New Zealand",
}

def _translate_area(name: str) -> str:
    """Translate common non-English area names to their English DB equivalent."""
    if not name:
        return name
    key = name.strip().lower()
    return AREA_TRANSLATIONS.get(key, name)

# Available views
REQUIRED_VIEWS = [
    "yield",
    "crop",
    "price_j_yield",
    "yield_j_crop",
]

# AI SDK Endpoints 
GET_METADATA_URL    = f"{AI_SDK_BASE_URL}/getMetadata"
VECTOR_DB_INFO_URL  = f"{AI_SDK_BASE_URL}/getVectorDBInfo"

ANSWER_QUESTION_URL = f"{AI_SDK_BASE_URL}/answerQuestion"        # auto-mode (SDK decides data vs metadata)
DATA_URL            = f"{AI_SDK_BASE_URL}/answerDataQuestion"    # explicit data/SQL
METADATA_URL        = f"{AI_SDK_BASE_URL}/answerMetadataQuestion" # schema questions


DEEP_QUERY_URL      = f"{AI_SDK_BASE_URL}/deepQuery"

AUTH = (DENODO_USER, DENODO_PASS)

SYSTEM_INSTRUCTIONS = """
You are AgroAdvisor, an expert agriculture consultant. You deliver clear,
data-backed decisions to farmers, agribusinesses and policy-makers.

1. DATABASE SCHEMA ("{db}")

| View             | Key columns                                                        | Use for                     |
|------------------|--------------------------------------------------------------------|-----------------------------|
| yield            | Area, Item, Year, hg_ha_yield                                      | Historical crop performance |
| crop             | label, N, P, K, temperature, humidity, ph, rainfall                | Ideal growing conditions    |
| price_j_yield    | Area, Item, Year, hg_ha_yield, <commodity_price_columns>           | Market & profitability      |
| yield_j_crop     | Yield + crop recommendation joined                                 | Climate-crop matching       |

Price columns (coffee_arabica, tea_columbo, sugar_eu, oil_brent, etc.) are
COLUMN NAMES, not row values. Discover them with: SELECT * FROM price_j_yield LIMIT 1

1b. GLOSSARY — AGRICULTURAL TERMS → DATABASE MAPPING

When users say any of these terms, map them to the correct column/metric:

| User term (ES/EN)                                      | DB column      | Unit          | Meaning                                        |
|--------------------------------------------------------|----------------|---------------|-------------------------------------------------|
| rendir, rendimiento, rinde, producción, yield          | hg_ha_yield    | hg/ha         | Hectograms per hectare of harvested crop        |
| "rinden cada vez menos", "baja el rendimiento"         | hg_ha_yield    | hg/ha (trend) | Declining hg_ha_yield over consecutive Years    |
| nutrientes, suelo, condiciones ideales                 | N, P, K, ph    | mg/kg, pH     | Soil nutrient & pH from 'crop' table            |
| temperatura, temp, calor                               | temperature    | °C            | Optimal growing temperature from 'crop'         |
| lluvia, precipitación, rainfall                        | rainfall       | mm            | Optimal rainfall from 'crop' or 'rainfall' data |
| humedad, humidity                                      | humidity       | %%            | Relative humidity from 'crop'                   |
| pesticidas, plaguicidas, fitosanitarios                | pesticides_tonnes | tonnes     | Pesticide usage from 'yield'                    |
| precio, coste, mercado, price                          | commodity cols | USD           | Commodity price columns in 'price_j_yield'      |

NEVER invent column names. If unsure, use: SELECT * FROM <view> LIMIT 1

2. SQL RULES (CRITICAL — NEVER VIOLATE)

• This is a Denodo VDP database. **NEVER use ILIKE** (it does not exist in Denodo).
• For case-insensitive text matching use LOWER() + LIKE:
   CORRECT:  WHERE LOWER("area") LIKE '%%brazil%%'
   WRONG:    WHERE "area" ILIKE '%%Brazil%%'     ← ERROR: operator not found
   WRONG:    WHERE "area" = 'Brasil'              ← RETURNS 0 ROWS
• TRANSLATE the user's input to ENGLISH before building SQL.

2b. FEW-SHOT SQL EXAMPLES (copy these patterns EXACTLY)

-- Q: "¿Cómo rinde la patata en España?"
SELECT "year", "hg_ha_yield", "pesticides_tonnes", "average_rain_fall_mm_per_year", "avg_temp"
FROM "{db}"."yield_j_crop"
WHERE LOWER("item") LIKE '%%potatoes%%' AND LOWER("area") LIKE '%%spain%%'
ORDER BY "year";

-- Q: "Condiciones ideales para el arroz"
SELECT "label", "n", "p", "k", "temperature", "humidity", "ph", "rainfall"
FROM "{db}"."crop"
WHERE LOWER("label") LIKE '%%rice%%';

-- Q: "Rendimiento vs precio del café en Colombia"
SELECT "year", "hg_ha_yield", "coffee_arabica", "coffee_robustas", "pesticides_tonnes"
FROM "{db}"."price_j_yield"
WHERE LOWER("item") LIKE '%%coffee%%' AND LOWER("area") LIKE '%%colombia%%'
ORDER BY "year";

-- Q: "Comparar rendimiento de maíz entre países"
SELECT "area", AVG("hg_ha_yield") AS avg_yield, COUNT(*) AS years
FROM "{db}"."yield"
WHERE LOWER("item") LIKE '%%maize%%'
GROUP BY "area"
ORDER BY avg_yield DESC
LIMIT 20;

-- Q: "Correlación pesticidas y rendimiento en trigo"
SELECT "year", "hg_ha_yield", "pesticides_tonnes", "avg_temp", "average_rain_fall_mm_per_year"
FROM "{db}"."yield_j_crop"
WHERE LOWER("item") LIKE '%%wheat%%'
ORDER BY "year";

-- Q: "Cultivos más rentables en India"
SELECT "item", AVG("hg_ha_yield") AS avg_yield
FROM "{db}"."yield"
WHERE LOWER("area") LIKE '%%india%%'
GROUP BY "item"
ORDER BY avg_yield DESC
LIMIT 10;

ALWAYS follow these patterns. Use double-quoted column names. Use LOWER()+LIKE for text filters.
   The user may write "Brasil" but the DB stores "Brazil".
• On 0 results → retry with LIKE variants, then SELECT DISTINCT to discover names.
• Cross-reference multiple views for complete answers.

3. LANGUAGE & TRANSLATION

ALL database values are stored in ENGLISH. You MUST translate before querying.

Crops:   patatas→Potatoes, maíz→Maize, arroz→Rice, trigo→Wheat, yuca→Cassava,
         soja→Soybeans, caña de azúcar→Sugar cane, café→Coffee, sorgo→Sorghum,
         cebada→Barley, algodón→Cotton, plátano→Plantains
Countries: Brasil→Brazil, España→Spain, Alemania→Germany, Francia→France,
         Estados Unidos→United States of America, Reino Unido→United Kingdom,
         Países Bajos→Netherlands, Japón→Japan, China→China, India→India,
         México→Mexico, Argentina→Argentina, Colombia→Colombia, Perú→Peru,
         Italia→Italy, Rusia→Russian Federation, Turquía→Turkey, Egipto→Egypt

If unsure of the English name: SELECT DISTINCT "area" FROM yield WHERE LOWER("area") LIKE '%%keyword%%'
Respond in the SAME language the user writes.

4. MULTI-TABLE HOLISTIC ANALYSIS (CRITICAL)

NEVER limit your analysis to only what the user explicitly asked about.
ALWAYS query ALL relevant tables and analyze EVERY column in the results.

Mandatory workflow for ANY question:
  1. Query the MAIN table for what the user asks (e.g., yield trends).
  2. ALSO query RELATED tables to find causes and correlations:
     - yield_j_crop → correlate yield with climate (avg_temp, average_rain_fall_mm_per_year),
       soil nutrients (N, P, K, ph), and pesticides (pesticides_tonnes)
     - price_j_yield → correlate yield with commodity prices and market trends
     - crop → compare actual conditions vs ideal conditions for the crop
  3. INTERPRET every column in the results, not just the one the user mentioned.
     Example: if you select "year, hg_ha_yield, pesticides_tonnes, avg_temp"
     you MUST comment on the trends in ALL three numeric columns and their
     inter-relationships, e.g. "yield dropped 12%% while pesticides rose 30%%
     and avg_temp increased 1.2°C — suggesting climate stress as the primary cause".
  4. CROSS-REFERENCE: compare data across tables to build a complete picture.
     Example: user asks about potatoes yield → query yield_j_crop for trends,
     THEN query crop for ideal conditions, THEN query price_j_yield for
     profitability → synthesize all three into a single coherent diagnosis.

NEVER say "the data doesn't show X" without having queried ALL relevant tables.
NEVER give generic advice like "check your soil" — look up the actual values and compare.

5. OUTPUT FORMAT

• Lead with the most actionable insight.
• Talk about GENERAL TRENDS, not specific years. Summarize patterns across the
  full time range (e.g. "en las últimas décadas", "tendencia general al alza").
  Do NOT list year-by-year data or say "in 2004 the yield was X". Aggregate.
• Use averages, overall %% changes, and trend directions instead of individual data points.
  GOOD: "El rendimiento medio cayó un 18%% en el periodo analizado"
  BAD:  "En 2001 fue 180,000 hg/ha, en 2005 fue 160,000 hg/ha, en 2010..."
• Explain causality with general patterns: "yield tends to drop when avg_temp exceeds 22°C".
• For EVERY column in the result set, state its overall trend and relevance.
• Cross-reference ideal conditions (crop table) vs actual data (yield_j_crop).
• Give 2–4 concrete recommendations with supporting data.
• End with brief caveats if relevant.

6. RECOMMENDATIONS — MANDATORY RULES

YOU are the expert. The user pays for DECISIONS, not homework.

NEVER ASK FOR CLARIFICATION. If the user's question is ambiguous:
  1. Pick the most reasonable interpretation using the glossary above.
  2. Query the database with that interpretation.
  3. If relevant, briefly mention what you assumed: "Interpreto 'rendimiento' como hg/ha (hg_ha_yield)."
  4. Deliver the answer with data. NEVER respond with a list of questions.

RESPONSE STRUCTURE (follow this order):

  A) **ACCIÓN PRINCIPAL** — One clear sentence with THE best action to take.
     Start with a verb: "Cambia a...", "Reduce...", "Planta...", "Invierte en..."
     Immediately follow with 2-3 bullet points of data-backed reasons WHY.
     Example:
       "**Cambia de patatas a maíz en tu región.**
       - Rendimiento medio del maíz: 52,000 hg/ha vs patatas: 38,000 hg/ha (+37%%)
       - El maíz tolera mejor la subida de temperatura detectada (+1.5°C en el periodo)
       - Menor uso de pesticidas necesario: 2,100 t vs 3,800 t"

  B) **DIAGNÓSTICO** — Brief analysis of the data that supports the main action.
     Summarize trends, correlations, and comparisons across tables.

  C) **RECOMENDACIONES ADICIONALES** — 2-3 extra actionable tips, each with data.
     Each one: [ACTION] + [DATA] + [EXPECTED BENEFIT]

  D) **CONSIDERACIONES** — Optional brief caveats (1-2 lines max).

PROHIBITED — never say any of these:
  "Investiga / Analiza / Monitorea / Haz un estudio"  → TU hazlo y da el resultado.
  "Sería interesante analizar..."                     → Da la conclusión directa.
  "Proporciona más información / Necesitamos datos"   → TU tienes la BD, consúltala.
  "No podemos determinar..."                          → Usa los datos que SÍ tienes.
  "Si los precios suben... si bajan..."               → Mira la tendencia y DECIDE.
  "Consulta con un experto"                           → TÚ eres el experto.
  "¿A qué te refieres con...?" / "Could you clarify" → Asume la interpretación más lógica.
  "Qualitative ambiguity / Unclear schema reference"  → Usa el glosario y responde.

ON MISSING DATA:
  1. Retry with LOWER()+LIKE / alternative names.
  2. Check which items/columns DO exist.
  3. Use similar crops or same-region data for an approximate answer.
  4. ALWAYS give a firm recommendation, noting what it's based on.
  NEVER ask the user to provide data — query the database yourself.
""".replace("{db}", VDP_DATABASE)


app = FastAPI(title="AgroAdvisor – HackUDC 2026")

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))


async def _sdk_get(url: str, params: dict | None = None, timeout: float = 300) -> dict:
    endpoint = url.split('/')[-1]
    short_params = {k: (v[:80] + '...' if isinstance(v, str) and len(v) > 80 else v) for k, v in (params or {}).items()}
    _log(f"SDK GET  /{endpoint}  params={short_params}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.get(url, params=params or {})
        elapsed = time.time() - t0
        _log(f"SDK GET  /{endpoint}  -> {resp.status_code}  ({elapsed:.1f}s)")
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            body = resp.text[:500] if resp.text else str(e)
            _log(f"ERROR SDK GET  /{endpoint}: {body[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {body}") from e
        data = resp.json()
        if "answer" in data:
            _log(f"SDK GET  /{endpoint}  answer length={len(str(data['answer']))} chars")
        return data


async def _sdk_post(url: str, body: dict | None = None,
                    timeout: float = 600) -> dict:
    """POST against the AI SDK (used for deepQuery)."""
    endpoint = url.split('/')[-1]
    _log(f"SDK POST /{endpoint}  body_keys={list((body or {}).keys())}")
    t0 = time.time()
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        resp = await client.post(url, json=body or {})
        elapsed = time.time() - t0
        _log(f"SDK POST /{endpoint}  -> {resp.status_code}  ({elapsed:.1f}s)")
        if resp.status_code == 204 or not resp.content:
            return {"status": "ok"}
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            bodytext = resp.text[:500] if resp.text else str(e)
            _log(f"ERROR SDK POST /{endpoint}: {bodytext[:200]}")
            raise RuntimeError(f"SDK {resp.status_code}: {bodytext}") from e
        return resp.json()


async def _sdk_stream_sse(url: str, params: dict | None = None,
                          timeout: float = 900):
    """Stream SSE from the AI SDK (deepQuery may use SSE)."""
    async with httpx.AsyncClient(auth=AUTH, timeout=timeout) as client:
        async with client.stream("GET", url, params=params or {}) as resp:
            ct = resp.headers.get("content-type", "")
            if "text/event-stream" in ct:
                async for line in resp.aiter_lines():
                    yield line + "\n"
            else:
                body = await resp.aread()
                yield body.decode("utf-8", errors="replace")


async def _ask(question: str, extra_instructions: str = "") -> dict:
    """Send a data question to /answerDataQuestion."""
    _log(f"_ask() question='{question[:120]}'")
    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += "\n\nADDITIONAL CONTEXT FOR THIS QUERY:\n" + extra_instructions
    result = await _sdk_get(
        DATA_URL,
        params={"question": question, "custom_instructions": instructions},
        timeout=240,
    )
    _log(f"_ask() completed, keys={list(result.keys())}")
    # Log data structure for debugging pipeline row counts
    for k in result:
        v = result[k]
        if isinstance(v, list):
            _log(f"_ask()  key '{k}' is list, len={len(v)}")
        elif isinstance(v, str):
            _log(f"_ask()  key '{k}' is str, len={len(v)}")
        else:
            _log(f"_ask()  key '{k}' = {type(v).__name__}")
    return result


async def _ask_metadata(question: str) -> dict:
    """Phase 1: Send a metadata question to /answerMetadataQuestion."""
    _log(f"_ask_metadata() question='{question[:150]}'")
    t0 = time.time()
    result = await _sdk_get(
        METADATA_URL,
        params={"question": question},
        timeout=120,
    )
    elapsed = time.time() - t0
    _log(f"_ask_metadata() completed ({elapsed:.1f}s), keys={list(result.keys())}")
    if result.get("answer"):
        _log(f"_ask_metadata() answer: {str(result['answer'])[:400]}")
    return result


# ─── METADATA CACHE (avoid repeated schema discovery) ─────────────────────────
_metadata_cache: dict[str, dict] = {}

async def _discover_schema(topic: str) -> dict:
    """Cached metadata discovery. Returns schema info for a given topic."""
    if topic in _metadata_cache:
        _log(f"_discover_schema() CACHE HIT for '{topic}'")
        return _metadata_cache[topic]
    _log(f"_discover_schema() CACHE MISS for '{topic}', querying metadata...")

    meta_question = (
        f"What tables and columns are available related to: {topic}? "
        f"List each view/table with its columns and data types. "
        f"Focus on the database '{VDP_DATABASE}'."
    )
    result = await _ask_metadata(meta_question)
    _metadata_cache[topic] = result
    return result


def _count_rows(result: dict) -> int:
    """Extract row count from SDK response, checking all possible data keys."""
    for key in ("data", "rows", "results", "records", "table"):
        val = result.get(key)
        if isinstance(val, list) and len(val) > 0:
            return len(val)
    # If answer contains tabular data as text, estimate from line count
    answer = result.get("answer", "")
    if "|" in answer:
        table_lines = [l for l in answer.split("\n") if "|" in l and "---" not in l]
        if len(table_lines) > 1:
            return len(table_lines) - 1  # subtract header
    return 0


async def _two_phase_query(
    user_question: str,
    metadata_topic: str,
    data_question: str,
    extra_instructions: str = "",
) -> dict:
    """
    MANDATORY two-phase pipeline:
      Phase 1 — answerMetadataQuestion: discovers relevant tables/columns
      Phase 2 — answerDataQuestion: extracts precise data using Phase 1 context

    Returns dict with 'answer', 'data', 'pipeline' (trace of both phases).
    """
    pipeline = {"phases": []}
    t_total = time.time()

    # ── PHASE 1: Metadata Discovery ──────────────────────────────────
    _log("=" * 60)
    _log(f"PIPELINE PHASE 1 — Metadata Discovery: {metadata_topic}")
    t1 = time.time()
    meta_result = await _discover_schema(metadata_topic)
    phase1_time = time.time() - t1

    schema_context = str(meta_result.get("answer", ""))
    phase1_entry = {
        "phase": 1,
        "name": "Descubrimiento de esquema",
        "description": f"answerMetadataQuestion: ¿Qué datos hay sobre '{metadata_topic}'?",
        "endpoint": "answerMetadataQuestion",
        "result_summary": schema_context[:500],
        "duration_s": round(phase1_time, 1),
    }
    pipeline["phases"].append(phase1_entry)
    _log(f"PHASE 1 complete ({phase1_time:.1f}s): {schema_context[:300]}")

    # ── PHASE 2: Data Execution ──────────────────────────────────────
    _log("-" * 60)
    _log(f"PIPELINE PHASE 2 — Data Execution: {data_question[:150]}")
    t2 = time.time()

    # Inject Phase 1 schema discovery into data query instructions
    enriched_instructions = (
        f"PHASE 1 SCHEMA DISCOVERY RESULTS (from answerMetadataQuestion):\n"
        f"{schema_context}\n\n"
        f"Use the tables and columns identified above to answer the following question.\n"
    )
    if extra_instructions:
        enriched_instructions += extra_instructions + "\n"

    data_result = await _ask(data_question, enriched_instructions)
    phase2_time = time.time() - t2

    phase2_entry = {
        "phase": 2,
        "name": "Extracción de datos",
        "description": f"answerDataQuestion: {data_question[:200]}",
        "endpoint": "answerDataQuestion",
        "sql_query": data_result.get("sql_query") or data_result.get("sqlQuery") or data_result.get("sql", ""),
        "rows_returned": _count_rows(data_result),
        "duration_s": round(phase2_time, 1),
    }
    pipeline["phases"].append(phase2_entry)
    _log(f"PHASE 2 complete ({phase2_time:.1f}s)")

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    _log(f"PIPELINE COMPLETE ({total_time:.1f}s)")
    _log("=" * 60)

    # Merge data result + pipeline trace
    result = {**data_result, "pipeline": pipeline}
    return result


async def _multi_phase_query(
    user_question: str,
    metadata_topic: str,
    data_queries: list[dict],
    extra_instructions: str = "",
) -> dict:
    """
    Multi-query two-phase pipeline:
      Phase 1 — single metadata discovery
      Phase 2 — multiple concurrent data queries using Phase 1 context

    Each entry in data_queries: {"question": str, "label": str}
    Returns dict with 'results' list and 'pipeline' trace.
    """
    pipeline = {"phases": []}
    t_total = time.time()

    # ── PHASE 1: Metadata Discovery ──────────────────────────────────
    _log("=" * 60)
    _log(f"MULTI-PIPELINE PHASE 1 — Metadata Discovery: {metadata_topic}")
    t1 = time.time()
    meta_result = await _discover_schema(metadata_topic)
    phase1_time = time.time() - t1

    schema_context = str(meta_result.get("answer", ""))
    pipeline["phases"].append({
        "phase": 1,
        "name": "Descubrimiento de esquema",
        "description": f"answerMetadataQuestion: ¿Qué datos hay sobre '{metadata_topic}'?",
        "endpoint": "answerMetadataQuestion",
        "result_summary": schema_context[:500],
        "duration_s": round(phase1_time, 1),
    })


    _log(f"MULTI-PIPELINE PHASE 2 — {len(data_queries)} concurrent data queries")
    enriched = (
        f"PHASE 1 SCHEMA DISCOVERY RESULTS (from answerMetadataQuestion):\n"
        f"{schema_context}\n\n"
        f"Use the tables and columns identified above.\n"
    )
    if extra_instructions:
        enriched += extra_instructions + "\n"

    t2 = time.time()
    tasks = [_ask(q["question"], enriched) for q in data_queries]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)
    phase2_time = time.time() - t2

    results = []
    for i, r in enumerate(raw_results):
        label = data_queries[i].get("label", f"Consulta {i+1}")
        if isinstance(r, Exception):
            results.append({"question": label, "error": str(r)})
            pipeline["phases"].append({
                "phase": 2, "name": f"Consulta: {label}",
                "endpoint": "answerDataQuestion",
                "error": str(r), "duration_s": round(phase2_time, 1),
            })
        else:
            results.append({**r, "question": label})
            pipeline["phases"].append({
                "phase": 2, "name": f"Consulta: {label}",
                "endpoint": "answerDataQuestion",
                "sql_query": r.get("sql_query") or r.get("sqlQuery") or r.get("sql", ""),
                "rows_returned": _count_rows(r),
                "duration_s": round(phase2_time, 1),
            })

    total_time = time.time() - t_total
    pipeline["total_duration_s"] = round(total_time, 1)
    _log(f"MULTI-PIPELINE COMPLETE ({total_time:.1f}s), {len(results)} results")
    _log("=" * 60)

    return {"results": results, "pipeline": pipeline}


async def _deep_query(question: str, extra_instructions: str = "") -> dict:
    """Call /deepQuery – multi-step analyst with thinking model (POST only)."""
    _log("=" * 70)
    _log("DEEP QUERY START")
    _log(f"Question: {question[:300]}")
    instructions = SYSTEM_INSTRUCTIONS
    if extra_instructions:
        instructions += "\n\nADDITIONAL CONTEXT:\n" + extra_instructions
        _log(f"Extra instructions: {extra_instructions[:200]}")
    body = {
        "question": question,
        "custom_instructions": instructions,
    }
    t0 = time.time()
    result = await _sdk_post(DEEP_QUERY_URL, body=body, timeout=900)
    elapsed = time.time() - t0

    # Log full DeepQuery response details
    _log("-" * 50)
    _log(f"DEEP QUERY RESPONSE ({elapsed:.1f}s)")
    _log(f"Response keys: {list(result.keys())}")

    # Log answer/reasoning
    if result.get("answer"):
        answer = str(result["answer"])
        _log(f"ANSWER ({len(answer)} chars):")
        for i in range(0, len(answer), 500):
            _log(f"  {answer[i:i+500]}")

    # Log SQL queries executed
    if result.get("sql"):
        _log(f"SQL: {result['sql']}")

    # Log intermediate queries (DeepQuery may return these)
    if result.get("queries"):
        _log(f"QUERIES executed ({len(result['queries'])}):")
        for idx, q in enumerate(result["queries"]):
            if isinstance(q, dict):
                _log(f"  [{idx+1}] question: {str(q.get('question', ''))[:200]}")
                _log(f"  [{idx+1}] sql: {str(q.get('sql', ''))[:300]}")
                _log(f"  [{idx+1}] answer: {str(q.get('answer', ''))[:300]}")
                if q.get("data"):
                    _log(f"  [{idx+1}] data rows: {len(q['data']) if isinstance(q['data'], list) else 0}")
            else:
                _log(f"  [{idx+1}] {str(q)[:400]}")

    # Log thinking/reasoning steps
    if result.get("thinking") or result.get("reasoning"):
        thinking = result.get("thinking") or result.get("reasoning")
        _log("THINKING/REASONING:")
        text = str(thinking)
        for i in range(0, len(text), 500):
            _log(f"  {text[i:i+500]}")

    # Log steps if present
    if result.get("steps"):
        _log(f"STEPS ({len(result['steps'])}):")
        for idx, step in enumerate(result["steps"]):
            _log(f"  Step {idx+1}: {str(step)[:400]}")

    # Log data returned
    if result.get("data"):
        data = result["data"]
        if isinstance(data, list):
            _log(f"DATA: {len(data)} rows returned")
            if len(data) > 0:
                _log(f"DATA sample (first row): {str(data[0])[:300]}")
        else:
            _log(f"DATA: {str(data)[:300]}")

    # Log any other interesting keys
    for key in result:
        if key not in ("answer", "sql", "queries", "thinking", "reasoning", "steps", "data", "status"):
            _log(f"EXTRA [{key}]: {str(result[key])[:300]}")

    _log("=" * 70)
    return result


async def _smart_query(question: str, extra: str = "") -> dict:
    """Try deepQuery first; fall back to answerDataQuestion."""
    _log("_smart_query() trying deepQuery first...")
    try:
        result = await _deep_query(question, extra)
        _log("_smart_query() deepQuery succeeded")
        return result
    except Exception as exc:
        _log(f"WARNING: _smart_query() deepQuery failed ({exc}), falling back to _ask")
        return await _ask(question, extra)


async def _multi_ask(queries: list[dict]) -> list[dict]:
    """Fire several AI SDK questions concurrently and return all results."""
    tasks = [_ask(q["question"], q.get("extra", "")) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            out.append({"question": queries[i]["question"], "error": str(r)})
        else:
            out.append({**r, "question": queries[i]["question"]})
    return out


def _md_to_html(text: str) -> str:
    if not text:
        return ""
    h = html_mod.escape(text)
    h = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', h)
    h = re.sub(r'\*(.+?)\*', r'<em>\1</em>', h)
    h = re.sub(r'^### (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'^## (.+)$', r'<h3>\1</h3>', h, flags=re.MULTILINE)
    h = re.sub(r'^# (.+)$', r'<h2>\1</h2>', h, flags=re.MULTILINE)
    h = re.sub(r'^[-•] (.+)$', r'<li>\1</li>', h, flags=re.MULTILINE)
    h = re.sub(r'(<li>.*?</li>)', r'<ul>\1</ul>', h, flags=re.DOTALL)
    h = h.replace('</ul>\n<ul>', '')
    h = h.replace('\n\n', '</p><p>')
    h = h.replace('\n', '<br>')
    return f"<p>{h}</p>"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/sync")
async def sync_metadata():
    try:
        result = await _sdk_get(
            GET_METADATA_URL,
            params={"vdp_database_names": VDP_DATABASE, "insert": "true"},
        )
        if result.get("status") == "ok":
            result["message"] = f"Metadatos de '{VDP_DATABASE}' sincronizados."
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/vector-info")
async def vector_info():
    try:
        return JSONResponse(await _sdk_get(VECTOR_DB_INFO_URL, timeout=30))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/metadata")
async def metadata_question(question: str = "¿Qué vistas y columnas hay disponibles?"):
    try:
        return JSONResponse(await _sdk_get(METADATA_URL, params={"question": question}, timeout=120))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/ask")
async def ask_question(question: str, mode: str = "auto"):
    """
    Two-phase analytical pipeline:
      Phase 1 — answerMetadataQuestion: discover relevant schema
      Phase 2 — answerDataQuestion: extract data + answer

    Supports legacy modes for direct access.
    """
    try:
        _log(f"/api/ask  mode={mode}  question='{question[:120]}'")
        t0 = time.time()
        if mode == "metadata":
            result = await _ask_metadata(question)
        elif mode == "data":
            result = await _ask(question)
        else:
            # Two-phase pipeline (default)
            result = await _two_phase_query(
                user_question=question,
                metadata_topic="agricultural yields, crops, climate, pesticides, commodity prices",
                data_question=question,
            )
        elapsed = time.time() - t0
        _log(f"/api/ask  completed ({elapsed:.1f}s)  keys={list(result.keys())}")
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/deep-query")
async def deep_query_endpoint(question: str):
    """Full DeepQuery analysis — the thinking model plans, executes
    multiple SQL queries iteratively, reasons across results, and
    produces a comprehensive report."""
    try:
        result = await _deep_query(question)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/deep-query-stream")
async def deep_query_stream(question: str):
    """Stream DeepQuery results via SSE (if SDK supports it)."""
    params = {"question": question, "custom_instructions": SYSTEM_INSTRUCTIONS}
    async def event_generator():
        async for chunk in _sdk_stream_sse(DEEP_QUERY_URL, params=params):
            yield chunk
    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/crop-advisor")
async def crop_advisor(area: str = "", conditions: str = ""):
    """
    Two-phase crop recommendation:
      Phase 1 — Discover crop, yield, climate, and price tables
      Phase 2 — Query specific data for recommendations
    """
    area = _translate_area(area)
    sql_rules = (
        "IMPORTANT: All DB values are in English. Translate country/crop names before querying. "
        "Use LOWER()+LIKE for text matching (NEVER ILIKE). Example: WHERE LOWER(\"area\") LIKE '%%india%%'. "
        "CRITICAL: Give 3-4 DIRECT DECISIONS with numbers. Do NOT say 'investigate' or 'analyze'."
    )
    area_ctx = f" in {area}" if area else ""
    cond_ctx = f" given conditions: {conditions}" if conditions else ""

    queries = [
        {"question": f"What crops have the highest yield{area_ctx}? Show top 5 by hg_ha_yield with production trends. {sql_rules}", "label": f"Rendimiento de cultivos{area_ctx}"},
        {"question": f"What are the ideal growing conditions (temperature, humidity, rainfall, pH, N, P, K) for the main crops grown{area_ctx}?{cond_ctx} {sql_rules}", "label": "Condiciones ideales de cultivo"},
        {"question": f"What are the current commodity prices for main crops? Which crops are most profitable based on price trends and yield data?{area_ctx} {sql_rules}", "label": "Rentabilidad de mercado"},
    ]

    try:
        result = await _multi_phase_query(
            user_question=f"Crop recommendation{area_ctx}{cond_ctx}",
            metadata_topic=f"crop recommendations, yields, climate conditions, commodity prices{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}. " if area else "",
        )
        result["analysis_type"] = "crop_advisor"
        result["area"] = area
        result["conditions"] = conditions
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/pesticide-analysis")
async def pesticide_analysis(area: str = ""):
    """
    Two-phase pesticide analysis:
      Phase 1 — Discover pesticide and yield data structures
      Phase 2 — Correlate pesticide use with yield outcomes
    """
    area = _translate_area(area)
    sql_rules = (
        "Use LOWER()+LIKE for text matching (NEVER ILIKE). "
        "CRITICAL: Give DIRECT DECISIONS with numbers. Do NOT say 'monitor' or 'track'."
    )
    area_ctx = f" for {area}" if area else " globally"

    queries = [
        {"question": f"Correlate pesticides_tonnes with hg_ha_yield{area_ctx}. Which countries get the best yield per tonne of pesticide? {sql_rules}", "label": f"Eficiencia pesticidas{area_ctx}"},
        {"question": f"Show the trend of pesticide usage over time and its impact on yield{area_ctx}. Is there a diminishing returns threshold? {sql_rules}", "label": "Tendencia y umbral de rendimiento"},
    ]

    try:
        result = await _multi_phase_query(
            user_question=f"Pesticide investment analysis{area_ctx}",
            metadata_topic=f"pesticide usage, crop yields, agricultural efficiency{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}." if area else "",
        )
        result["analysis_type"] = "pesticide_analysis"
        result["area"] = area
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/climate-impact")
async def climate_impact(area: str = ""):
    """
    Two-phase climate impact analysis:
      Phase 1 — Discover climate and crop data structures
      Phase 2 — Analyse temperature/rainfall impact on yields
    """
    area = _translate_area(area)
    sql_rules = (
        "Use LOWER()+LIKE for text matching (NEVER ILIKE). "
        "CRITICAL: Give DIRECT DECISIONS. Tell which crops to switch to. Do NOT say 'monitor climate'."
    )
    area_ctx = f" in {area}" if area else " globally"

    queries = [
        {"question": f"How does avg_temp correlate with hg_ha_yield over time{area_ctx}? Show specific numbers and trends. {sql_rules}", "label": f"Correlacion temperatura-rendimiento"},
        {"question": f"What is the optimal rainfall range for the highest yields of main crops{area_ctx}? Compare actual vs ideal from crop data. {sql_rules}", "label": "Rango optimo de lluvia"},
        {"question": f"Which crops are most resilient to temperature changes{area_ctx}? Which are at risk? Show yield differences. {sql_rules}", "label": "Resiliencia climatica"},
    ]

    try:
        result = await _multi_phase_query(
            user_question=f"Climate impact on agriculture{area_ctx}",
            metadata_topic=f"temperature, rainfall, climate data, crop yields{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}." if area else "",
        )
        result["analysis_type"] = "climate_impact"
        result["area"] = area
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/market-intelligence")
async def market_intelligence():
    """
    Two-phase market intelligence:
      Phase 1 — Discover price and commodity data structures
      Phase 2 — Analyse price trends and investment opportunities
    """
    sql_rules = (
        "Use LOWER()+LIKE for text matching (NEVER ILIKE). "
        "CRITICAL: Give DIRECT investment decisions with numbers."
    )

    queries = [
        {"question": f"Show the price evolution of coffee (arabica, robustas), tea and sugar. What are the strongest trends? {sql_rules}", "label": "Evolucion de precios de commodities"},
        {"question": f"How do oil prices (oil_brent) correlate with food commodity prices? Show specific numbers. {sql_rules}", "label": "Correlacion petroleo-alimentos"},
        {"question": f"Which producing countries have the best yield trends for cash crops (coffee, tea, sugar)? Show top 5 with numbers. {sql_rules}", "label": "Mejores productores"},
    ]

    try:
        result = await _multi_phase_query(
            user_question="Agricultural commodity market intelligence",
            metadata_topic="commodity prices, agricultural market data, yields by country",
            data_queries=queries,
        )
        result["analysis_type"] = "market_intelligence"
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/api/regional-report")
async def regional_report(area: str):
    """
    Two-phase comprehensive regional report:
      Phase 1 — Discover all available data for the region
      Phase 2 — Multiple queries for complete analysis
    """
    area = _translate_area(area)
    sql_rules = (
        f"Translate names to English. Use LOWER()+LIKE (NEVER ILIKE). "
        f"Example: WHERE LOWER(\"area\") LIKE '%%{area.lower()}%%'. "
        f"CRITICAL: Give DIRECT DECISIONS. Do NOT say 'investigate' or 'monitor'."
    )

    queries = [
        {"question": f"What are the main crops in {area}? Show top crops by hg_ha_yield, total production, and yield evolution over the years. {sql_rules}", "label": f"Perfil agricola de {area}"},
        {"question": f"What are the climate conditions in {area}? Show average temperature and rainfall trends. Compare with ideal conditions for its main crops from crop data. {sql_rules}", "label": f"Condiciones climaticas de {area}"},
        {"question": f"What is the pesticide usage trend in {area}? Show pesticides_tonnes over time, efficiency vs yield, and compare with similar countries. {sql_rules}", "label": f"Uso de pesticidas en {area}"},
        {"question": f"Based on {area}'s climate and current commodity prices, what new crops could {area} grow profitably? Show price trends and yield comparisons. {sql_rules}", "label": f"Oportunidades de mercado para {area}"},
    ]

    try:
        result = await _multi_phase_query(
            user_question=f"Complete agricultural intelligence report for {area}",
            metadata_topic=f"agricultural data for {area}: yields, climate, temperature, rainfall, pesticides, commodity prices",
            data_queries=queries,
            extra_instructions=f"Focus exclusively on {area}.",
        )
        result["analysis_type"] = "regional_report"
        result["area"] = area
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.post("/api/report")
async def generate_report(request: Request):
    from io import BytesIO
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return JSONResponse({"error": "xhtml2pdf not installed"}, status_code=500)

    body = await request.json()
    title    = body.get("title", "Informe AgroAdvisor")
    sections = body.get("sections", [])  # [{heading, content, sql?, data?}]
    question = body.get("question", "")
    answer   = body.get("answer", "")

    # Support legacy single-answer format
    if not sections and answer:
        sections = [{"heading": "Análisis", "content": answer}]
        if body.get("sql"):
            sections.append({"heading": "SQL generada", "content": f"```\n{body['sql']}\n```"})

    css = """
    @page { size: A4; margin: 2cm; }
    body { font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 12px; line-height: 1.6; }
    .header { border-bottom: 3px solid #2d6a4f; padding-bottom: 14px; margin-bottom: 24px; }
    .header h1 { font-size: 20px; color: #2d6a4f; margin: 0 0 4px; }
    .header p { color: #666; font-size: 10px; margin: 0; }
    .section { margin-bottom: 22px; }
    .section h2 { font-size: 14px; color: #2d6a4f; border-bottom: 1px solid #eee; padding-bottom: 5px; margin-bottom: 10px; }
    .question { background: #f0faf4; border-left: 4px solid #2d6a4f; padding: 10px 14px; font-style: italic; }
    .answer { text-align: justify; }
    pre { background: #f5f5f5; padding: 10px; font-size: 10px; white-space: pre-wrap; }
    table { width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 6px; }
    th { background: #2d6a4f; color: #fff; padding: 6px 8px; text-align: left; }
    td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
    .footer { margin-top: 30px; border-top: 1px solid #e0e0e0; padding-top: 10px; font-size: 9px; color: #999; text-align: center; }
    """

    html_parts = [
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{css}</style></head><body>',
        f'<div class="header"><h1>{html_mod.escape(title)}</h1>',
        '<p>Informe generado automaticamente &middot; AgroAdvisor &mdash; Powered by Denodo AI SDK</p></div>',
    ]

    if question:
        html_parts.append(f'<div class="section"><h2>Consulta</h2><div class="question">{html_mod.escape(question)}</div></div>')

    for sec in sections:
        heading = html_mod.escape(sec.get("heading", ""))
        raw_content = sec.get("content", "")
        # If content already looks like HTML (from frontend innerHTML), use as-is
        if re.search(r'<(?:p|br|strong|em|h[1-6]|ul|ol|li|table|div)\b', raw_content):
            content = raw_content
        else:
            content = _md_to_html(raw_content)
        html_parts.append(f'<div class="section"><h2>{heading}</h2><div class="answer">{content}</div></div>')
        if sec.get("sql"):
            html_parts.append(f'<div class="section"><h2>SQL</h2><pre>{html_mod.escape(sec["sql"])}</pre></div>')
        data = sec.get("data")
        if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
            cols = list(data[0].keys())
            rows_html = ''.join(
                '<tr>' + ''.join(f'<td>{html_mod.escape(str(row.get(c,"")))}</td>' for c in cols) + '</tr>'
                for row in data[:80]
            )
            html_parts.append(
                f'<div class="section"><h2>Datos</h2><table><thead><tr>'
                + ''.join(f'<th>{html_mod.escape(c)}</th>' for c in cols)
                + f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
            )

    html_parts.append('<div class="footer">AgroAdvisor &mdash; HackUDC 2026</div></body></html>')

    html_str = ''.join(html_parts)
    buf = BytesIO()
    try:
        status = pisa.CreatePDF(html_str, dest=buf, encoding='utf-8')
        if status.err:
            _log(f"ERROR PDF generation: pisa reported {status.err} errors")
            return JSONResponse({"error": f"Error rendering PDF ({status.err} errors)"}, status_code=500)
    except Exception as exc:
        _log(f"ERROR PDF generation exception: {exc}")
        return JSONResponse({"error": f"Error generando PDF: {str(exc)}"}, status_code=500)

    pdf_bytes = buf.getvalue()
    _log(f"PDF generated OK, {len(pdf_bytes)} bytes")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=agroadvisor_report.pdf"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
