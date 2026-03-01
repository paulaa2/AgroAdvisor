/* ═══════════════════════════════════════════════════════════════
   AgroAdvisor — api.js
   API call helpers: analysis runners, sync, and PDF downloads.
   Depends on: render.js (renderResults, esc), main.js (toast, showLoading)
   ═══════════════════════════════════════════════════════════════ */

/* ─── Sync ─────────────────────────────────────────────────────────────────── */

async function syncMetadata() {
  toast('Sincronizando metadatos…', 'info');
  try {
    const res  = await fetch('/api/sync');
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    toast(data.message || 'Metadatos sincronizados', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

/* ─── Generic analysis runner ─────────────────────────────────────────────── */

/**
 * Generic helper for all analysis panels.
 * Fetches a URL, shows a loading state, and renders the result.
 *
 * @param {string}      containerId  ID of the results container element
 * @param {string}      url          Endpoint URL (already built with params)
 * @param {string}      loadingMsg   Message shown while loading
 */
async function runAnalysis(containerId, url, loadingMsg) {
  const container = document.getElementById(containerId);
  if (!container) return;
  showLoading(container, loadingMsg);
  try {
    const res  = await fetch(url);
    const data = await res.json();
    renderResults(container, data);
  } catch (e) {
    container.innerHTML =
      `<div class="result-card">
        <div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div>
      </div>`;
  }
}

/* ─── Analysis panel runners ──────────────────────────────────────────────── */

function runCropAdvisor() {
  const area       = document.getElementById('crop-area')?.value.trim()       ?? '';
  const conditions = document.getElementById('crop-conditions')?.value.trim() ?? '';
  const p = new URLSearchParams();
  if (area)       p.set('area', area);
  if (conditions) p.set('conditions', conditions);
  runAnalysis('crop-results', `/api/crop-advisor?${p}`, 'Analizando cultivos óptimos (1-2 min)…');
}

function runPesticideAnalysis() {
  const area = document.getElementById('pest-area')?.value.trim() ?? '';
  const p = new URLSearchParams();
  if (area) p.set('area', area);
  runAnalysis('pesticide-results', `/api/pesticide-analysis?${p}`, 'Analizando inversión en pesticidas…');
}

function runClimateImpact() {
  const area = document.getElementById('climate-area')?.value.trim() ?? '';
  const p = new URLSearchParams();
  if (area) p.set('area', area);
  runAnalysis('climate-results', `/api/climate-impact?${p}`, 'Analizando impacto climático…');
}

function runMarketIntelligence() {
  runAnalysis('market-results', '/api/market-intelligence', 'Analizando mercado de commodities…');
}

function runRegionalReport() {
  const area = document.getElementById('region-area')?.value.trim() ?? '';
  if (!area) { toast('Indica un país o región', 'error'); return; }
  runAnalysis(
    'regional-results',
    `/api/regional-report?area=${encodeURIComponent(area)}`,
    `Generando informe de ${area}…`
  );
}

/* ─── PDF downloads ────────────────────────────────────────────────────────── */

/**
 * Download a single result card as PDF.
 * @param {string}      question  The question / section heading
 * @param {HTMLElement} btnEl     The button that triggered the download
 */
async function downloadSectionPDF(question, btnEl) {
  const section = btnEl.closest('.result-card');
  const answer  = section?.dataset.answer || '';
  const sql     = section?.dataset.sql    || '';
  toast('Generando PDF…', 'info', 3000);
  try {
    const res = await fetch('/api/report', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title: 'Informe AgroAdvisor', question, sections: [{ heading: question, content: answer, sql }] }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Error generando PDF');
    }
    _triggerDownload(await res.blob(), 'agroadvisor_report.pdf');
    toast('PDF descargado', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

/**
 * Download the full analysis as a multi-section PDF report.
 * @param {object} data  Full API response object
 */
async function downloadFullReport(data) {
  let sections;
  if (data.results?.length) {
    sections = data.results.map(r => ({
      heading: r.question || 'Análisis',
      content: r.answer   || r.error || '',
      sql:     r.sql_query || r.sqlQuery || '',
      data:    r.data || [],
    }));
  } else {
    sections = [{
      heading: data.question || 'Análisis',
      content: data.answer   || data.error || '',
      sql:     data.sql_query || data.sqlQuery || data.sql || '',
      data:    data.data || [],
    }];
  }

  const LABELS = {
    crop_advisor:        'Asesor de Cultivos',
    pesticide_analysis:  'Análisis de Pesticidas',
    climate_impact:      'Impacto Climático',
    market_intelligence: 'Inteligencia de Mercado',
    regional_report:     'Informe Regional',
  };
  const title = (LABELS[data.analysis_type] || 'Informe') + (data.area ? ` - ${data.area}` : '');

  try {
    const res = await fetch('/api/report', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ title, sections }),
    });
    if (!res.ok) throw new Error('Error generando PDF');
    _triggerDownload(await res.blob(), 'agroadvisor_informe.pdf');
    toast('Informe PDF descargado', 'success');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

/* ─── Internal helpers ─────────────────────────────────────────────────────── */

function _triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a   = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
