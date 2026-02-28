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
  0: { step: 'phase-0', badge: 'sp-0', label: 'Fase 0 — VectorDB' },
  1: { step: 'phase-1', badge: 'sp-1', label: 'Fase 1 — Metadata' },
  2: { step: 'phase-2', badge: 'sp-2', label: 'Fase 2 — Data'     },
};

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
  if (p.result_summary) {
    const summary = p.result_summary.length > 250
      ? p.result_summary.slice(0, 250) + '…'
      : p.result_summary;
    detail += `<div class="step-detail">Esquema descubierto: ${esc(summary)}</div>`;
  }
  if (p.rows_returned > 0) {
    detail += `<div class="step-detail">${p.rows_returned} filas obtenidas</div>`;
  } else if (p.rows_returned === 0 && phaseNum === 2) {
    detail += `<div class="step-detail" style="color:var(--n-400)">Datos integrados en la respuesta</div>`;
  }
  if (p.sql_query) {
    detail += `<div class="step-sql">${esc(p.sql_query)}</div>`;
  }
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
function renderPipeline(pipeline) {
  if (!pipeline?.phases?.length) return '';
  const total = pipeline.total_duration_s ?? 0;
  const steps = pipeline.phases.map(_renderPhaseStep).join('');

  return `<details class="pipeline-trace" open>
    <summary>
      <svg class="chevron" width="14" height="14" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
      Pipeline de razonamiento
      <span class="pipeline-label pl-ok">${pipeline.phases.length} pasos</span>
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

  return `<div class="result-card">
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
  if (data.pipeline) html += renderPipeline(data.pipeline);

  if (data.results?.length) {
    html += data.results.map((r, i) => renderResult(r, i)).join('');
  } else if (data.answer) {
    html += renderResult(data, 0);
  }

  container.innerHTML = html;

  const btn = document.createElement('button');
  btn.className = 'btn-primary';
  btn.style.marginTop = '12px';
  btn.textContent = 'Descargar informe completo (PDF)';
  btn.onclick = () => downloadFullReport(data);
  container.appendChild(btn);
}
