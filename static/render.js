/* ═══════════════════════════════════════════════════════════════
   AgroAdvisor — render.js
   Pure rendering helpers: markdown, pipeline trace, results.
   No side-effects, no fetch calls.
   ═══════════════════════════════════════════════════════════════ */

/* ─── Markdown & escaping ──────────────────────────────────────────────────── */

/**
 * Escape a string for safe HTML insertion.
 * @param {string} str
 * @returns {string}
 */
function esc(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

/**
 * Render Markdown to HTML using marked.js if available, or a minimal fallback.
 * @param {string} text
 * @returns {string}
 */
function renderMd(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') return marked.parse(text);
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,     '<em>$1</em>')
    .replace(/\n/g,            '<br>');
}

/* ─── Pipeline trace ───────────────────────────────────────────────────────── */

const _PHASE_CLASSES = {
  0: { step: 'phase-0', badge: 'sp-0', label: 'Fase 0 — Ranking' },
  1: { step: 'phase-1', badge: 'sp-1', label: 'Fase 1 — Selección' },
  2: { step: 'phase-2', badge: 'sp-2', label: 'Fase 2 — Datos' },
};

/**
 * Build the HTML for a single pipeline step.
 * @param {object} p  Phase entry from the backend pipeline object
 * @returns {string}
 */
/**
 * Render a row of table-name chips (for ranked_tables or selected_tables).
 * @param {Array} tables
 * @param {string} chipClass  CSS class for the chip
 */
function _renderTableChips(tables, chipClass) {
  if (!tables?.length) return '';
  const chips = tables.map(t => {
    const name  = typeof t === 'string' ? t : t.name;
    const score = typeof t === 'object' && t.score != null ? ` · ${t.score}` : '';
    const tip   = typeof t === 'object' && t.description ? t.description : '';
    const color = typeof t === 'object' && t.denodo === false ? ' chip-local' : '';
    return `<span class="table-chip ${chipClass}${color}" title="${esc(tip)}">${esc(name)}${esc(score)}</span>`;
  }).join('');
  return `<div class="step-chips">${chips}</div>`;
}

/**
 * Build the HTML for a single pipeline step.
 * @param {object} p  Phase entry from the backend pipeline object
 * @returns {string}
 */
function _renderPhaseStep(p) {
  const phaseNum = p.phase ?? 1;
  const cls      = _PHASE_CLASSES[phaseNum] ?? _PHASE_CLASSES[2];
  const time     = p.duration_s ? `${p.duration_s}s` : '';

  let detail = '';

  // Phase 0: ranked table list
  if (p.ranked_tables?.length) {
    const visible = p.ranked_tables.filter(t => t.score > 0).slice(0, 6);
    if (visible.length) {
      detail += `<div class="step-detail step-detail-label">Tablas candidatas (score > 0):</div>`;
      detail += _renderTableChips(visible, 'chip-ranked');
    }
  }

  // Phase 1: selected tables
  if (p.selected_tables?.length) {
    detail += `<div class="step-detail step-detail-label">Tablas seleccionadas:</div>`;
    detail += _renderTableChips(p.selected_tables, 'chip-selected');
  }

  // result_summary — show full text in a collapsible if long
  if (p.result_summary) {
    const full = p.result_summary;
    const short = full.length > 160 ? full.slice(0, 160) + '…' : full;
    const id = 'ps-' + Math.random().toString(36).slice(2, 8);
    if (full.length > 160) {
      detail += `<div class="step-detail">
        <span id="${id}-s">${esc(short)}
          <a href="#" class="step-expand" onclick="
            document.getElementById('${id}-s').style.display='none';
            document.getElementById('${id}-f').style.display='block';
            return false;">ver más</a>
        </span>
        <span id="${id}-f" style="display:none">${esc(full)}
          <a href="#" class="step-expand" onclick="
            document.getElementById('${id}-s').style.display='block';
            document.getElementById('${id}-f').style.display='none';
            return false;">ver menos</a>
        </span>
      </div>`;
    } else {
      detail += `<div class="step-detail">${esc(short)}</div>`;
    }
  }

  // rows / data feedback
  if (p.rows_returned > 0) {
    detail += `<div class="step-detail step-ok">${p.rows_returned} filas obtenidas</div>`;
  } else if (p.rows_returned === 0 && phaseNum === 2) {
    detail += `<div class="step-detail" style="color:var(--n-400)">Datos integrados en la respuesta</div>`;
  }

  // SQL
  if (p.sql_query) {
    detail += `<div class="step-sql">${esc(p.sql_query)}</div>`;
  }

  // Errors
  if (p.error) {
    detail += `<div class="step-detail" style="color:var(--red)">Error: ${esc(p.error)}</div>`;
  }

  return `<div class="pipeline-step ${cls.step}">
    <div class="step-head">
      <span class="step-phase ${cls.badge}">${cls.label}</span>
      <span class="step-name">${esc(p.name || '')}</span>
      <span class="step-endpoint">${esc(p.endpoint || '')}</span>
      <span class="step-time">${time}</span>
    </div>
    ${detail}
  </div>`;
}

/**
 * Render the collapsible pipeline trace block.
 * @param {object|null} pipeline  The `pipeline` key from an API response
 * @returns {string}  HTML string (empty if no pipeline data)
 */
/**
 * Render the full pipeline trace as a collapsible block.
 * Starts collapsed to save space; user can expand to see all steps.
 * @param {object|null} pipeline
 * @param {boolean} [startOpen=false]
 * @returns {string}
 */
function renderPipeline(pipeline, startOpen = false) {
  if (!pipeline?.phases?.length) return '';
  const total      = pipeline.total_duration_s ?? 0;
  const steps      = pipeline.phases.map(_renderPhaseStep).join('');
  const phase2n    = pipeline.phases.filter(p => p.phase === 2).length;
  const openAttr   = startOpen ? ' open' : '';

  // Build a one-line summary of selected tables (from Phase 1 entry)
  const p1 = pipeline.phases.find(p => p.phase === 1);
  const selNames = p1?.selected_tables?.join(', ') || '';
  const selBadge = selNames
    ? `<span class="pipeline-label pl-table">${esc(selNames)}</span>`
    : '';

  return `<details class="pipeline-trace"${openAttr}>
    <summary>
      <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      Pipeline de razonamiento
      ${selBadge}
      <span class="pipeline-label pl-ok">${pipeline.phases.length} pasos · ${phase2n} consulta${phase2n !== 1 ? 's' : ''}</span>
      <span class="pipeline-label pl-time">${total}s total</span>
    </summary>
    <div class="pipeline-steps">${steps}</div>
  </details>`;
}

/* ─── Data table ────────────────────────────────────────────────────────────── */

/**
 * Render a list of row-objects as an HTML table (capped at 50 rows).
 * @param {Array<object>} data
 * @returns {string}
 */
function renderDataTable(data) {
  if (!data?.length || typeof data[0] !== 'object') return '';
  const cols = Object.keys(data[0]);
  const bodyRows = data.slice(0, 50).map(row =>
    '<tr>' + cols.map(c => `<td>${esc(String(row[c] ?? ''))}</td>`).join('') + '</tr>'
  ).join('');
  const footer = data.length > 50
    ? `<p style="color:var(--n-400);font-size:.78rem">Mostrando 50 de ${data.length} filas</p>`
    : '';
  return (
    '<table><thead><tr>' + cols.map(c => `<th>${esc(c)}</th>`).join('') + '</tr></thead>'
    + `<tbody>${bodyRows}</tbody></table>` + footer
  );
}

/* ─── Result card ────────────────────────────────────────────────────────────── */

/**
 * Render a single analysis result as a collapsible card.
 * @param {object} r    Result object from API
 * @param {number} idx  Index for fallback label
 * @returns {string}
 */
function renderResult(r, idx) {
  const question = r.question || `Consulta ${idx + 1}`;
  const answer   = r.answer || r.error || 'Sin respuesta.';
  const sql      = r.sql_query || r.sqlQuery || r.sql || '';
  const isError  = !!r.error;

  let body = renderMd(answer);
  body += renderDataTable(r.data || []);
  if (sql) {
    body += `<div class="result-sql">
      <details><summary>Ver SQL generada</summary>
        <pre><code>${esc(sql)}</code></pre>
      </details></div>`;
  }

  const _encAttr = s => s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/\n/g,'&#10;').replace(/\r/g,'');
  return `<div class="result-card"
    data-answer="${_encAttr(answer)}"
    data-sql="${_encAttr(sql)}">
    <div class="result-card-head"
         onclick="this.nextElementSibling.style.display=
                  this.nextElementSibling.style.display==='none'?'block':'none'">
      <h4>${esc(question)}</h4>
      <span class="result-badge${isError ? ' error' : ''}">${isError ? 'Error' : 'Completado'}</span>
    </div>
    <div class="result-card-body">
      ${body}
      <div class="result-actions">
        <button class="btn-sm"
                onclick='downloadSectionPDF(${JSON.stringify(question)}, this)'>
          Descargar PDF
        </button>
      </div>
    </div>
  </div>`;
}

/* ─── Results pane ───────────────────────────────────────────────────────────── */

/**
 * Populate a results container with pipeline trace + result cards + PDF button.
 * @param {HTMLElement} container
 * @param {object}      data       Full API response object
 */
function renderResults(container, data) {
  if (data.error) {
    container.innerHTML =
      `<div class="result-card">
        <div class="result-card-body" style="color:var(--red)">${esc(data.error)}</div>
      </div>`;
    return;
  }

  let html = '';
  if (data.pipeline) html += renderPipeline(data.pipeline, true);

  const results = data.results?.length ? data.results : (data.answer ? [data] : []);
  results.forEach((r, i) => { html += renderResult(r, i); });

  container.innerHTML = html;

  // Inject charts into each result card after HTML is in the DOM
  if (typeof renderCharts === 'function' && typeof extractChartData === 'function') {
    results.forEach((r, i) => {
      const rowData = r.chart_data?.length >= 2 ? r.chart_data : extractChartData(r);
      if (rowData.length < 2) return;
      // Find the result card body at position i
      const cards = container.querySelectorAll('.result-card-body');
      const cardBody = cards[i];
      if (!cardBody) return;
      const chartSection = document.createElement('div');
      chartSection.className = 'chart-section';
      cardBody.appendChild(chartSection);
      renderCharts(rowData, chartSection);
    });
  }

  const btn = document.createElement('button');
  btn.className = 'btn-primary';
  btn.style.marginTop = '12px';
  btn.textContent = 'Descargar informe completo (PDF)';
  btn.onclick = () => downloadFullReport(data);
  container.appendChild(btn);
}
