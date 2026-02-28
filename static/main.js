/* ═══════════════════════════════════════════════════════════════
   AgroAdvisor — main.js
   ═══════════════════════════════════════════════════════════════ */

const BOT_AVATAR = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`;
const USER_AVATAR = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;

// ─── Panel navigation ───────────────────────────────────────────
function showPanel(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('panel-' + id);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`.nav-item[data-panel="${id}"]`);
  if (btn) btn.classList.add('active');
  document.getElementById('sidebar').classList.remove('open');
}

// ─── Toast ──────────────────────────────────────────────────────
let toastBox;
function toast(msg, type = 'info', ms = 4000) {
  if (!toastBox) {
    toastBox = document.createElement('div');
    toastBox.className = 'toast-container';
    document.body.appendChild(toastBox);
  }
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  toastBox.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, ms);
}

// ─── Loading ────────────────────────────────────────────────────
function showLoading(container, message = 'Analizando datos...') {
  container.innerHTML = `<div class="loading-indicator"><div class="spinner"></div><span>${message}</span></div>`;
}

// ─── Markdown ───────────────────────────────────────────────────
function renderMd(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') return marked.parse(text);
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>').replace(/\n/g, '<br>');
}

// ─── Escape HTML ────────────────────────────────────────────────
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

// ─── Render pipeline trace ──────────────────────────────────────
function renderPipeline(pipeline) {
  if (!pipeline || !pipeline.phases || pipeline.phases.length === 0) return '';
  const phases = pipeline.phases;
  const total = pipeline.total_duration_s || 0;

  let steps = '';
  for (const p of phases) {
    const phaseNum = p.phase || 1;
    const pClass = phaseNum === 1 ? 'phase-1' : 'phase-2';
    const spClass = phaseNum === 1 ? 'sp-1' : 'sp-2';
    const phaseLabel = phaseNum === 1 ? 'Fase 1 — Metadata' : 'Fase 2 — Data';
    const time = p.duration_s ? `${p.duration_s}s` : '';
    const endpoint = p.endpoint || '';

    let detail = '';
    if (p.result_summary) {
      const summary = p.result_summary.length > 250 ? p.result_summary.slice(0, 250) + '...' : p.result_summary;
      detail += `<div class="step-detail">Esquema descubierto: ${esc(summary)}</div>`;
    }
    if (p.rows_returned !== undefined && p.rows_returned > 0) {
      detail += `<div class="step-detail">${p.rows_returned} filas obtenidas</div>`;
    } else if (p.rows_returned === 0 && p.phase === 2) {
      detail += `<div class="step-detail" style="color:var(--n-400)">Datos integrados en la respuesta</div>`;
    }
    if (p.sql_query) {
      detail += `<div class="step-sql">${esc(p.sql_query)}</div>`;
    }
    if (p.error) {
      detail += `<div class="step-detail" style="color:var(--red)">Error: ${esc(p.error)}</div>`;
    }

    steps += `<div class="pipeline-step ${pClass}">
      <div class="step-head">
        <span class="step-phase ${spClass}">${phaseLabel}</span>
        <span class="step-name">${esc(p.name || '')}</span>
        <span class="step-endpoint">${esc(endpoint)}</span>
        <span class="step-time">${time}</span>
      </div>
      ${detail}
    </div>`;
  }

  return `<details class="pipeline-trace" open>
    <summary>
      <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      Pipeline de razonamiento
      <span class="pipeline-label pl-ok">${phases.length} pasos</span>
      <span class="pipeline-label pl-time">${total}s total</span>
    </summary>
    <div class="pipeline-steps">${steps}</div>
  </details>`;
}

// ─── Render single result ───────────────────────────────────────
function renderResult(r, idx) {
  const question = r.question || `Consulta ${idx + 1}`;
  const answer = r.answer || r.error || 'Sin respuesta.';
  const sql = r.sql_query || r.sqlQuery || r.sql || '';
  const data = r.data || [];
  const isError = !!r.error;

  let html = `<div class="result-card">
    <div class="result-card-head" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
      <h4>${esc(question)}</h4>
      <span class="result-badge${isError ? ' error' : ''}">${isError ? 'Error' : 'Completado'}</span>
    </div>
    <div class="result-card-body">${renderMd(answer)}`;

  if (data.length > 0 && typeof data[0] === 'object') {
    const cols = Object.keys(data[0]);
    html += '<table><thead><tr>' + cols.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
    data.slice(0, 50).forEach(row => {
      html += '<tr>' + cols.map(c => `<td>${esc(String(row[c] ?? ''))}</td>`).join('') + '</tr>';
    });
    html += '</tbody></table>';
    if (data.length > 50) html += `<p style="color:var(--n-400);font-size:.78rem">Mostrando 50 de ${data.length} filas</p>`;
  }

  if (sql) {
    html += `<div class="result-sql"><details><summary>Ver SQL generada</summary><pre><code>${esc(sql)}</code></pre></details></div>`;
  }

  html += `<div class="result-actions">
      <button class="btn-sm" onclick='downloadSectionPDF(${JSON.stringify(question)}, this)'>Descargar PDF</button>
    </div></div></div>`;
  return html;
}

// Render all results
function renderResults(container, data) {
  if (data.error) {
    container.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">${esc(data.error)}</div></div>`;
    return;
  }

  let html = '';

  // Render pipeline trace if present
  if (data.pipeline) {
    html += renderPipeline(data.pipeline);
  }

  const results = data.results || [data];
  if (!data.results && data.answer) {
    html += renderResult(data, 0);
  } else {
    html += results.map((r, i) => renderResult(r, i)).join('');
  }

  container.innerHTML = html;

  const btn = document.createElement('button');
  btn.className = 'btn-primary';
  btn.style.marginTop = '12px';
  btn.textContent = 'Descargar informe completo (PDF)';
  btn.onclick = () => downloadFullReport(data);
  container.appendChild(btn);
}

// ─── API calls ──────────────────────────────────────────────────

async function syncMetadata() {
  toast('Sincronizando metadatos...', 'info');
  try {
    const res = await fetch('/api/sync');
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    toast(data.message || 'Metadatos sincronizados', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

// ─── Chat mode ──────────────────────────────────────────────────
let chatMode = 'pipeline';
function setChatMode(mode) {
  chatMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';
  input.style.height = 'auto';

  const msgs = document.getElementById('chat-messages');
  const modeLabel = chatMode === 'deep' ? 'DeepQuery' : 'Pipeline';

  msgs.innerHTML += `<div class="msg user"><div class="avatar av-user">${USER_AVATAR}</div><div class="bubble">${esc(question)}</div></div>`;

  const lid = 'ld-' + Date.now();
  msgs.innerHTML += `<div class="msg bot" id="${lid}"><div class="avatar av-bot">${BOT_AVATAR}</div><div class="bubble"><div class="loading-indicator"><div class="spinner"></div><span>${modeLabel}: Analizando...</span></div></div></div>`;
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const url = chatMode === 'deep'
      ? '/api/deep-query?question=' + encodeURIComponent(question)
      : '/api/ask?question=' + encodeURIComponent(question) + '&mode=auto';
    const res = await fetch(url);
    const data = await res.json();
    const el = document.getElementById(lid);
    if (el) el.remove();

    const answer = data.answer || data.error || 'No se pudo obtener respuesta.';
    let content = '';

    // Pipeline trace (collapsible inside chat bubble)
    if (data.pipeline) content += renderPipeline(data.pipeline);

    content += renderMd(answer);

    if (data.data && data.data.length > 0 && typeof data.data[0] === 'object') {
      const cols = Object.keys(data.data[0]);
      content += '<table><thead><tr>' + cols.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
      data.data.slice(0, 20).forEach(row => {
        content += '<tr>' + cols.map(c => `<td>${esc(String(row[c] ?? ''))}</td>`).join('') + '</tr>';
      });
      content += '</tbody></table>';
    }

    msgs.innerHTML += `<div class="msg bot"><div class="avatar av-bot">${BOT_AVATAR}</div><div class="bubble">${content}</div></div>`;
  } catch (e) {
    const el = document.getElementById(lid);
    if (el) el.remove();
    msgs.innerHTML += `<div class="msg bot"><div class="avatar av-bot">${BOT_AVATAR}</div><div class="bubble" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`;
  }
  msgs.scrollTop = msgs.scrollHeight;
}

// ─── Analysis runners ───────────────────────────────────────────

async function runCropAdvisor() {
  const area = document.getElementById('crop-area').value.trim();
  const conditions = document.getElementById('crop-conditions').value.trim();
  const c = document.getElementById('crop-results');
  showLoading(c, 'Analizando cultivos optimos (1-2 min)...');
  try {
    const p = new URLSearchParams();
    if (area) p.set('area', area);
    if (conditions) p.set('conditions', conditions);
    const res = await fetch('/api/crop-advisor?' + p);
    renderResults(c, await res.json());
  } catch (e) { c.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`; }
}

async function runPesticideAnalysis() {
  const area = document.getElementById('pest-area').value.trim();
  const c = document.getElementById('pesticide-results');
  showLoading(c, 'Analizando inversion en pesticidas...');
  try {
    const p = new URLSearchParams();
    if (area) p.set('area', area);
    const res = await fetch('/api/pesticide-analysis?' + p);
    renderResults(c, await res.json());
  } catch (e) { c.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`; }
}

async function runClimateImpact() {
  const area = document.getElementById('climate-area').value.trim();
  const c = document.getElementById('climate-results');
  showLoading(c, 'Analizando impacto climatico...');
  try {
    const p = new URLSearchParams();
    if (area) p.set('area', area);
    const res = await fetch('/api/climate-impact?' + p);
    renderResults(c, await res.json());
  } catch (e) { c.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`; }
}

async function runMarketIntelligence() {
  const c = document.getElementById('market-results');
  showLoading(c, 'Analizando mercado de commodities...');
  try {
    const res = await fetch('/api/market-intelligence');
    renderResults(c, await res.json());
  } catch (e) { c.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`; }
}

async function runRegionalReport() {
  const area = document.getElementById('region-area').value.trim();
  if (!area) { toast('Indica un pais o region', 'error'); return; }
  const c = document.getElementById('regional-results');
  showLoading(c, `Generando informe de ${area}...`);
  try {
    const res = await fetch('/api/regional-report?area=' + encodeURIComponent(area));
    renderResults(c, await res.json());
  } catch (e) { c.innerHTML = `<div class="result-card"><div class="result-card-body" style="color:var(--red)">Error: ${esc(e.message)}</div></div>`; }
}

// ─── PDF downloads ──────────────────────────────────────────────

async function downloadSectionPDF(question, btnEl) {
  const section = btnEl.closest('.result-card');
  const body = section.querySelector('.result-card-body');
  const answer = body ? body.innerHTML : '';
  toast('Generando PDF...', 'info', 3000);
  try {
    const res = await fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'Informe AgroAdvisor', question, answer }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Error generando PDF');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'agroadvisor_report.pdf'; a.click();
    URL.revokeObjectURL(url);
    toast('PDF descargado', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}

async function downloadFullReport(data) {
  let sections;
  if (data.results && data.results.length > 0) {
    sections = data.results.map(r => ({
      heading: r.question || 'Analisis',
      content: r.answer || r.error || '',
      sql: r.sql_query || r.sqlQuery || '',
      data: r.data || [],
    }));
  } else {
    // Single-response format (deepQuery / answerDataQuestion)
    sections = [{
      heading: data.question || 'Analisis',
      content: data.answer || data.error || '',
      sql: data.sql_query || data.sqlQuery || data.sql || '',
      data: data.data || [],
    }];
  }
  const labels = {
    crop_advisor: 'Asesor de Cultivos', pesticide_analysis: 'Analisis de Pesticidas',
    climate_impact: 'Impacto Climatico', market_intelligence: 'Inteligencia de Mercado',
    regional_report: 'Informe Regional',
  };
  const title = (labels[data.analysis_type] || 'Informe') + (data.area ? ` - ${data.area}` : '');
  try {
    const res = await fetch('/api/report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, sections }),
    });
    if (!res.ok) throw new Error('Error generando PDF');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'agroadvisor_informe.pdf'; a.click();
    URL.revokeObjectURL(url);
    toast('Informe PDF descargado', 'success');
  } catch (e) { toast('Error: ' + e.message, 'error'); }
}
