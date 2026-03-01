# AgroAdvisor — AI-Powered Agricultural Intelligence Platform

> **Ask a question. Get a decision. Backed by live data, driven by AI.**

---

## Inspiration

Agriculture is one of the most data-rich industries on the planet, yet most farmers and agribusinesses still make decisions based on intuition rather than evidence. Datasets on crop yields, climate conditions, pesticide usage and commodity prices exist — but they are fragmented, hard to query and incomprehensible without specialist knowledge.

The core inequality we wanted to address is simple: a large agribusiness can afford data scientists and analysts. A smallholder farmer in Spain or Colombia cannot. We wanted to close that gap.

The Denodo AI SDK challenge gave us the perfect vehicle: a live virtual database federating heterogeneous agricultural data, combined with LLM-driven SQL generation that anyone can drive with plain language. The question *"¿Vale la pena plantar trigo en España este año?"* should produce a concrete, number-backed answer — not a dashboard that requires a data analyst to interpret.

---

## What We Built

AgroAdvisor is a single-page web application with six specialised analysis modules, all powered by the same underlying reasoning pipeline:

| Module | What it answers |
|---|---|
| **Consulta Libre** | Any free-form agricultural question, answered with data + charts |
| **Asesor de Cultivos** | Which crops to plant given a region and soil/climate conditions |
| **Análisis de Pesticidas** | Pesticide efficiency vs. yield; diminishing-returns thresholds |
| **Impacto Climático** | How temperature and rainfall trends affect yield over time |
| **Inteligencia de Mercado** | Commodity price evolution and investment signals |
| **Informe Regional** | Complete agricultural dossier for any country |

Every response ships with **automatically generated charts** (line, bar, or radar) rendered on the backend as PNG images, and can be exported as a **formatted PDF report**.

---

## How We Built It

### Data Layer — Denodo VDP

All data is federated through four virtual views in a Denodo Virtual DataPort database:

- **`yield`** — historical crop output, temperature, rainfall and pesticide data by country and year  
- **`crop`** — ideal growing conditions per crop type (N, P, K, pH, temperature, humidity, rainfall)  
- **`yield_j_crop`** — joined view for climate–soil–yield correlation  
- **`price_j_yield`** — joined view for market profitability analysis

The virtual layer means we can query heterogeneous CSV sources with full SQL without managing a physical database — critical for a 24-hour hackathon.

### The 3-Phase Reasoning Pipeline

The core of AgroAdvisor is a custom pipeline we built on top of the Denodo AI SDK. Each user query goes through four sequential phases:

**Phase 0 — Semantic Retrieval**  
ChromaDB vector search (using `gemini-embedding-001` embeddings) ranks all available database tables by semantic similarity to the question, combined with a local keyword-scoring function over our table catalogue.

**Phase 1 — Schema Discovery**  
A focused `answerMetadataQuestion` call retrieves exact column names and data types for the top-ranked tables, so the SQL-generation model always operates with accurate schema context.

**Phase 2 — Data Extraction**  
An enriched instruction block — containing the schema, vector context and strict SQL rules — is sent to `answerDataQuestion`. The model generates SQL, executes it against VDP, and returns the results.

**Phase 3 — Interpretation**  
A thinking LLM (Gemini 2.5 Flash via `deepQuery`) receives the raw SQL results and synthesises a final agronomist-style recommendation.

The total latency for a multi-query endpoint (e.g. Crop Advisor, which runs 3 parallel Phase-2 queries) can be expressed as:

$$T_{\text{total}} = T_0 + T_1 + \max_{i}(T_{2,i}) + \max_{i}(T_{3,i})$$

where $T_0, T_1$ are sequential (schema discovery depends on ranking), and Phase-2 and Phase-3 tasks are fanned out with `asyncio.gather` for concurrency.

### Backend Chart Generation

After each SQL response, the backend analyses the result structure and picks the appropriate chart type:

- Year column detected → **line chart** (one per numeric metric, max 4)
- Category column, many rows → **horizontal bar chart** (max 3 metrics)  
- Category column, $n \leq 10$ rows with $k \geq 4$ numeric metrics → **radar chart**

Numeric metrics are normalised to $[0, 100]$ for the radar chart using:

$$\hat{v}_{i,c} = \frac{v_{i,c}}{\max_j v_{j,c}} \times 100$$

Charts are rendered with `matplotlib` (non-interactive `Agg` backend), saved as PNGs in `static/charts/` and returned as URL paths — no client-side rendering required.

### Prompt Engineering

The `SYSTEM_INSTRUCTIONS` string is a self-contained agricultural knowledge base:

- A **glossary** mapping Spanish agricultural terms to exact database column names (`rendir → hg_ha_yield`, `pesticidas → pesticides_tonnes`, …)
- A **translation table** for crop and country names (Spanish → stored English values)
- **Few-shot SQL examples** covering the most common query patterns
- A **mandatory multi-table workflow**: the model is required to cross-reference `yield_j_crop`, `crop` and `price_j_yield` on every query, not just the most obvious table
- An **expert decision rule**: the system never asks for clarification — it chooses the most reasonable interpretation, queries the database and delivers a firm recommendation

---

## Challenges We Faced

### 1. Denodo SQL Dialect

Denodo VDP does not support `ILIKE`, PostgreSQL-specific window functions, or implicit numeric casts. The LLM consistently generated PostgreSQL-flavoured SQL in early iterations. We solved this by injecting explicit rules at the top of every Phase-2 prompt:

```sql
-- CORRECT (Denodo compatible)
WHERE LOWER("area") LIKE '%brazil%'

-- WRONG (breaks in Denodo)
WHERE "area" ILIKE '%Brazil%'
```

### 2. The LIMIT 1 Problem

The model frequently returned only one row — making chart generation impossible, since a chart requires at minimum two data points. We introduced a hard `_NO_LIMIT_RULE` constant prepended to all Phase-2 instructions before any schema context:

> ⚠️ ABSOLUTE SQL RULE — CHARTS REQUIRE MULTIPLE ROWS:
> - NEVER write `LIMIT 1` or any limit < 10.
> - For trends, return ALL available years (no LIMIT at all).
> - A query returning only 1 row means NO chart can be drawn — **critical failure**.

Positioning this rule *before* any other context dramatically increased compliance.

### 3. Chart Data Extraction from Markdown Tables

SQL results arrive embedded in markdown tables inside the model's answer text rather than as structured JSON. We wrote a custom markdown table parser in `utils.py` that:

- Handles multi-table answers, extracting all tables into a flat row list
- Strips markdown formatting from cell values (`**bold**`, backticks)
- Auto-converts numeric strings (handling commas and spaces as thousands separators)
- Falls back to direct `execution_result` parsing when the SDK returns the raw row format

### 4. Column Name Hallucination

The model occasionally invented column names absent from the schema (e.g. `hgha_yield_0` instead of `hg_ha_yield`). The 3-phase pipeline with focused schema injection in Phase 1 largely eliminated this, and a hard override rule was added:

> `OVERRIDE: The yield column is ALWAYS "hg_ha_yield". DO NOT use CAST on hg_ha_yield — it is already numeric.`

### 5. Concurrency and Latency

The multi-query endpoints (Crop Advisor, Regional Report) issue 3–4 independent SQL queries. Running them sequentially would be unacceptably slow. We restructured Phase 2 as a concurrent fan-out:

```python
tasks = [ask(q["question"], enriched) for q in data_queries]
raw_results = await asyncio.gather(*tasks, return_exceptions=True)
```

Phase-3 interpretation tasks are similarly fanned out, reducing total wall-clock time by roughly $1 - \frac{1}{n}$ for $n$ independent queries.

---

## What We Learned

- **Prompt position matters.** Prepending a critical rule vs. appending it has a measurable effect on LLM compliance — the model pays more attention to instructions it reads first.

- **Virtual data federation is underrated for hackathons.** Denodo VDP let us join heterogeneous CSV datasets, expose them over a single authenticated SQL endpoint, and query them from the AI SDK without managing indices, migrations or schemas. We went from raw CSVs to queryable views in under an hour.

- **Backend chart generation is more reliable than client-side.** Column type detection, normalisation and chart-type selection are far easier to implement and debug in Python than in JavaScript, especially when the incoming data structure varies across queries.

- **Mandatory cross-table analysis produces better answers.** Early versions of the system prompt allowed the model to answer from a single table. Adding an explicit multi-table workflow (query all relevant views, cross-reference findings) produced dramatically richer, more accurate recommendations.

- **Strict SQL rules are not enough — you also need examples.** Few-shot SQL examples in the system prompt were more effective at teaching Denodo-compatible patterns than rule descriptions alone. The model learns from examples far better than from prohibitions.

---

## What's Next for AgroAdvisor

- **Real-time data feeds** — connect satellite crop-monitoring APIs and weather services as additional Denodo virtual data sources, so yield forecasts can incorporate live conditions.
- **Field-level analysis** — integrate GPS coordinates so farmers can query yield and climate data for their exact geographic region, not just country averages.
- **Alert system** — scheduled queries that notify users when commodity prices cross user-defined thresholds or climate forecasts deviate from crop ideal ranges.
- **Expanded language support** — extend translation tables beyond Spanish ↔ English to cover Portuguese, French and Arabic agricultural vocabularies.
- **Mobile app** — a lightweight wrapper around the existing API targeting smallholder farmers who access the internet primarily via mobile.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · httpx · asyncio |
| Charts | matplotlib — backend PNG generation |
| Frontend | Vanilla JS · marked.js |
| LLM Routing | Denodo AI SDK |
| SQL Engine | Denodo Virtual DataPort (VDP) |
| Vector Search | ChromaDB + `gemini-embedding-001` |
| LLM (SQL) | Groq — LLaMA 3.3 70B Versatile |
| LLM (Thinking) | Google AI Studio — Gemini 2.5 Flash |
| PDF Export | xhtml2pdf |
| Containers | Docker Compose |

---

*Built at **HackUDC 2026** — Universidade da Coruña*  
*Team: Paula Esteve Sabater · Sergi Flores · Weihao Lin*
