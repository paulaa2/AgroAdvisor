"""AgroAdvisor - HackUDC 2026
FastAPI application.

Business logic in:
  core/config.py      - constants
  core/prompts.py     - system instructions
  core/utils.py       - pure helpers
  core/sdk_client.py  - Denodo AI SDK client
  core/pipeline.py    - query pipeline
"""

import os
import re
import html as html_mod
from io import BytesIO

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import GET_METADATA_URL, METADATA_URL, VECTOR_DB_INFO_URL, DEEP_QUERY_URL, VDP_DATABASE
from core.prompts import SYSTEM_INSTRUCTIONS
from core.utils import log, translate_area, md_to_html
from core.sdk_client import ask, ask_metadata, sdk_get, sdk_stream_sse
from core.pipeline import two_phase_query, multi_phase_query, deep_query, smart_query

_BASE = os.path.dirname(__file__)

app = FastAPI(title="AgroAdvisor - HackUDC 2026")
app.mount("/static", StaticFiles(directory=os.path.join(_BASE, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(_BASE, "templates"))

_SQL_HINT = "Use LOWER()+LIKE (NEVER ILIKE). Translate names to English. Give DIRECT decisions with numbers."


async def _handle(coro) -> JSONResponse:
    try:
        return JSONResponse(await coro)
    except Exception as exc:
        log(f"API ERROR: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=502)


# ---- Routes ----

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok", "service": "AgroAdvisor"})


@app.get("/api/sync")
async def sync_metadata():
    async def _sync():
        result = await sdk_get(GET_METADATA_URL, params={"vdp_database_names": VDP_DATABASE, "insert": "true"})
        if result.get("status") == "ok":
            result["message"] = f"Metadatos de '{VDP_DATABASE}' sincronizados."
        return result
    return await _handle(_sync())


@app.get("/api/vector-info")
async def vector_info():
    return await _handle(sdk_get(VECTOR_DB_INFO_URL, timeout=30))


@app.get("/api/metadata")
async def metadata_question(question: str = "Que vistas y columnas hay disponibles?"):
    return await _handle(sdk_get(METADATA_URL, params={"question": question}, timeout=120))


@app.get("/api/ask")
async def ask_endpoint(question: str, mode: str = "auto"):
    log(f"/api/ask mode={mode} '{question[:120]}'")
    if mode == "metadata":
        return await _handle(ask_metadata(question))
    if mode == "data":
        return await _handle(ask(question))
    return await _handle(two_phase_query(
        user_question=question,
        metadata_topic="agricultural yields, crops, climate, pesticides, commodity prices",
        data_question=question,
    ))


@app.get("/api/deep-query")
async def deep_query_endpoint(question: str):
    return await _handle(deep_query(question))


@app.get("/api/deep-query-stream")
async def deep_query_stream(question: str):
    params = {"question": question, "custom_instructions": SYSTEM_INSTRUCTIONS}
    async def gen():
        async for chunk in sdk_stream_sse(DEEP_QUERY_URL, params=params):
            yield chunk
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/crop-advisor")
async def crop_advisor(area: str = "", conditions: str = ""):
    area = translate_area(area)
    area_ctx = f" in {area}" if area else ""
    cond_ctx = f" given conditions: {conditions}" if conditions else ""

    if conditions:
        cond_label = (
            f"Condiciones del terreno: '{conditions}'{area_ctx}. "
            f"Usando condiciones ideales de cultivo, identifica los cultivos que mejor se adaptan "
            f"y recomienda cuales plantar."
        )
    else:
        cond_label = f"Condiciones ideales de cultivo{area_ctx}"

    queries = [
        {"question": f"Top crops by hg_ha_yield{area_ctx}. Show top 5 with trends. {_SQL_HINT}",
         "label": f"Rendimiento de cultivos{area_ctx}"},
        {"question": f"Return ALL rows from 'crop' table (label, temperature, humidity, rainfall, ph, n, p, k). {_SQL_HINT}",
         "label": cond_label},
        {"question": f"Current commodity prices. Most profitable crops based on price+yield{area_ctx}. {_SQL_HINT}",
         "label": "Rentabilidad de mercado"},
    ]

    async def _run():
        result = await multi_phase_query(
            user_question=f"Crop recommendation{area_ctx}{cond_ctx}",
            metadata_topic=f"crop recommendations, yields, climate, prices{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}." if area else "",
        )
        result.update(analysis_type="crop_advisor", area=area, conditions=conditions)
        return result
    return await _handle(_run())


@app.get("/api/pesticide-analysis")
async def pesticide_analysis(area: str = ""):
    area = translate_area(area)
    area_ctx = f" for {area}" if area else " globally"
    queries = [
        {"question": f"Correlate pesticides_tonnes with hg_ha_yield{area_ctx}. Best yield per tonne? {_SQL_HINT}",
         "label": f"Eficiencia pesticidas{area_ctx}"},
        {"question": f"Pesticide usage trend over time and impact on yield{area_ctx}. Diminishing returns? {_SQL_HINT}",
         "label": "Tendencia y umbral de rendimiento"},
    ]
    async def _run():
        result = await multi_phase_query(
            user_question=f"Pesticide investment analysis{area_ctx}",
            metadata_topic=f"pesticide usage, crop yields{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}." if area else "",
        )
        result.update(analysis_type="pesticide_analysis", area=area)
        return result
    return await _handle(_run())


@app.get("/api/climate-impact")
async def climate_impact(area: str = ""):
    area = translate_area(area)
    area_ctx = f" in {area}" if area else " globally"
    queries = [
        {"question": f"How does avg_temp correlate with hg_ha_yield over time{area_ctx}? {_SQL_HINT}",
         "label": "Correlacion temperatura-rendimiento"},
        {"question": f"Optimal rainfall range for highest yields{area_ctx}? Compare actual vs ideal. {_SQL_HINT}",
         "label": "Rango optimo de lluvia"},
        {"question": f"Most climate-resilient crops{area_ctx}? Show yield differences. {_SQL_HINT}",
         "label": "Resiliencia climatica"},
    ]
    async def _run():
        result = await multi_phase_query(
            user_question=f"Climate impact on agriculture{area_ctx}",
            metadata_topic=f"temperature, rainfall, climate, yields{area_ctx}",
            data_queries=queries,
            extra_instructions=f"Focus on {area}." if area else "",
        )
        result.update(analysis_type="climate_impact", area=area)
        return result
    return await _handle(_run())


@app.get("/api/market-intelligence")
async def market_intelligence():
    queries = [
        {"question": f"Price evolution of coffee, tea, sugar. Strongest trends? {_SQL_HINT}",
         "label": "Evolucion de precios"},
        {"question": f"How do oil prices correlate with food commodity prices? {_SQL_HINT}",
         "label": "Correlacion petroleo-alimentos"},
    ]
    async def _run():
        result = await multi_phase_query(
            user_question="Agricultural commodity market intelligence",
            metadata_topic="commodity prices, market data, yields",
            data_queries=queries,
        )
        result.update(analysis_type="market_intelligence")
        return result
    return await _handle(_run())


@app.get("/api/regional-report")
async def regional_report(area: str):
    area = translate_area(area)
    hint = f"Translate names to English. Use LOWER()+LIKE. Give DIRECT decisions."
    queries = [
        {"question": f"Main crops in {area}. Top by hg_ha_yield, production trends. {hint}",
         "label": f"Perfil agricola de {area}"},
        {"question": f"Climate conditions in {area}. Temperature/rainfall trends vs ideal. {hint}",
         "label": f"Condiciones climaticas de {area}"},
        {"question": f"Pesticide usage trend in {area}. Efficiency vs yield. {hint}",
         "label": f"Uso de pesticidas en {area}"},
        {"question": f"Based on {area}'s climate and prices, what new crops to grow profitably? {hint}",
         "label": f"Oportunidades para {area}"},
    ]
    async def _run():
        result = await multi_phase_query(
            user_question=f"Complete agricultural report for {area}",
            metadata_topic=f"agricultural data for {area}: yields, climate, pesticides, prices",
            data_queries=queries,
            extra_instructions=f"Focus exclusively on {area}.",
        )
        result.update(analysis_type="regional_report", area=area)
        return result
    return await _handle(_run())


# ---- PDF report ----

_PDF_CSS = """
@page { size: A4; margin: 2cm; }
body { font-family: Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 12px; line-height: 1.6; }
.header { border-bottom: 3px solid #2d6a4f; padding-bottom: 14px; margin-bottom: 24px; }
.header h1 { font-size: 20px; color: #2d6a4f; margin: 0 0 4px; }
.header p { color: #666; font-size: 10px; margin: 0; }
.section { margin-bottom: 22px; }
.section h2 { font-size: 14px; color: #2d6a4f; border-bottom: 1px solid #eee; padding-bottom: 5px; }
.question { background: #f0faf4; border-left: 4px solid #2d6a4f; padding: 10px 14px; font-style: italic; }
.answer { text-align: justify; }
pre { background: #f5f5f5; padding: 10px; font-size: 10px; white-space: pre-wrap; }
table { width: 100%; border-collapse: collapse; font-size: 10px; margin-top: 6px; }
th { background: #2d6a4f; color: #fff; padding: 6px 8px; text-align: left; }
td { padding: 5px 8px; border-bottom: 1px solid #e0e0e0; }
.footer { margin-top: 30px; border-top: 1px solid #e0e0e0; padding-top: 10px; font-size: 9px; color: #999; text-align: center; }
"""


def _build_pdf_html(title: str, question: str, sections: list) -> str:
    parts = [
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_PDF_CSS}</style></head><body>',
        f'<div class="header"><h1>{html_mod.escape(title)}</h1>',
        '<p>Informe generado - AgroAdvisor - Powered by Denodo AI SDK</p></div>',
    ]
    if question:
        parts.append(f'<div class="section"><div class="question">{html_mod.escape(question)}</div></div>')
    for sec in sections:
        heading = html_mod.escape(sec.get("heading", ""))
        raw = sec.get("content", "")
        content = raw if re.search(r'<(?:p|br|strong|em|h[1-6]|ul|ol|li|table|div)\b', raw) else md_to_html(raw)
        parts.append(f'<div class="section"><h2>{heading}</h2><div class="answer">{content}</div></div>')
        if sec.get("sql"):
            parts.append(f'<div class="section"><h2>SQL</h2><pre>{html_mod.escape(sec["sql"])}</pre></div>')
        data = sec.get("data")
        if data and isinstance(data, list) and data and isinstance(data[0], dict):
            cols = list(data[0].keys())
            rows_html = "".join(
                "<tr>" + "".join(f'<td>{html_mod.escape(str(row.get(c, "")))}</td>' for c in cols) + "</tr>"
                for row in data[:80]
            )
            parts.append(
                '<div class="section"><h2>Datos</h2><table><thead><tr>'
                + "".join(f'<th>{html_mod.escape(c)}</th>' for c in cols)
                + f'</tr></thead><tbody>{rows_html}</tbody></table></div>'
            )
    parts.append('<div class="footer">AgroAdvisor - HackUDC 2026</div></body></html>')
    return "".join(parts)


@app.post("/api/report")
async def generate_report(request: Request):
    try:
        from xhtml2pdf import pisa
    except ImportError:
        return JSONResponse({"error": "xhtml2pdf not installed"}, status_code=500)

    body = await request.json()
    title = body.get("title", "Informe AgroAdvisor")
    question = body.get("question", "")
    sections = body.get("sections", [])
    answer = body.get("answer", "")

    if not sections and answer:
        sections = [{"heading": "Analisis", "content": answer}]
        if body.get("sql"):
            sections.append({"heading": "SQL generada", "content": f"`\n{body['sql']}\n`"})

    html_str = _build_pdf_html(title, question, sections)
    buf = BytesIO()
    try:
        status = pisa.CreatePDF(html_str, dest=buf, encoding="utf-8")
        if status.err:
            return JSONResponse({"error": f"PDF error ({status.err})"}, status_code=500)
    except Exception as exc:
        return JSONResponse({"error": f"PDF error: {exc}"}, status_code=500)

    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=agroadvisor_report.pdf"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
