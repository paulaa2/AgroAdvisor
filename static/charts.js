/* ═══════════════════════════════════════════════════════════════
   AgroAdvisor — charts.js
   Smart chart generation from API data arrays.
   Detects series type and renders Chart.js visuals automatically.
   Requires Chart.js loaded before this script.
   ═══════════════════════════════════════════════════════════════ */

/* ─── Markdown table parser ───────────────────────────────────── */

/**
 * Parse the first Markdown table found in `text` into an array of
 * plain objects (header row becomes keys, body rows become values).
 * Returns [] if no table is found.
 */
function parseMdTable(text) {
  if (!text || typeof text !== 'string') return [];

  const lines = text.split('\n');
  let headerIdx = -1;

  // Find the separator row (---|---|---)
  for (let i = 1; i < lines.length; i++) {
    if (/^\s*\|?[\s:|-]+\|/.test(lines[i]) && lines[i].includes('-')) {
      headerIdx = i - 1;
      break;
    }
  }
  if (headerIdx < 0) return [];

  const parseRow = line =>
    line.replace(/^\s*\|/, '').replace(/\|\s*$/, '')
        .split('|').map(cell => cell.trim().replace(/\*\*/g, ''));

  const headers = parseRow(lines[headerIdx])
    .map(h => h.toLowerCase().replace(/\s+/g, '_').replace(/[()°%\/]/g, ''));
  if (!headers.length) return [];

  const rows = [];
  for (let i = headerIdx + 2; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || !line.includes('|')) continue;
    // Stop if we hit another table separator or a heading
    if (/^[\s|:-]+$/.test(line) || /^#+\s/.test(line)) break;
    const cells = parseRow(lines[i]);
    const obj = {};
    headers.forEach((h, idx) => {
      const raw = cells[idx] ?? '';
      const num = parseFloat(raw.replace(/,/g, ''));
      obj[h] = !isNaN(num) && raw.trim() !== '' ? num : raw;
    });
    rows.push(obj);
  }
  return rows;
}

/**
 * Given a full API response object, return the best data array for charting.
 * Tries: response.data → response.rows → response.records →
 *        parse markdown table from response.answer →
 *        sub-query data from deepQuery response.queries[]
 */
function extractChartData(response) {
  if (!response || typeof response !== 'object') return [];

  // Direct data array keys
  for (const key of ['data', 'rows', 'records', 'table']) {
    if (Array.isArray(response[key]) && response[key].length >= 2) {
      return response[key];
    }
  }

  // DeepQuery: aggregate data from sub-queries
  if (Array.isArray(response.queries)) {
    for (const q of response.queries) {
      if (Array.isArray(q?.data) && q.data.length >= 2) return q.data;
    }
  }

  // Parse markdown table embedded in answer text
  const answer = response.answer || response.error || '';
  if (answer && answer.includes('|') && answer.includes('-')) {
    const parsed = parseMdTable(answer);
    if (parsed.length >= 2) return parsed;
  }

  return [];
}

const _CHART_PALETTE = [
  '#10b981', '#3b82f6', '#f59e0b', '#ef4444',
  '#8b5cf6', '#14b8a6', '#f97316', '#ec4899',
  '#06b6d4', '#84cc16',
];

/* ─── Column classification helpers ──────────────────────────── */

const _YEAR_KEYS   = new Set(['year', 'año', 'anio']);
const _CAT_KEYS    = new Set(['item', 'label', 'area', 'crop', 'cultivo', 'pais', 'country']);
const _EXCLUDE_NUM = new Set(['id', 'year', 'año', 'anio']);

function _isYear(k)     { return _YEAR_KEYS.has(k.toLowerCase()); }
function _isCategory(k) { return _CAT_KEYS.has(k.toLowerCase()); }

/** Return columns whose values look numeric, excluding _EXCLUDE_NUM keys. */
function _numericCols(row, extraExclude = []) {
  const exc = new Set([...Array.from(_EXCLUDE_NUM), ...extraExclude.map(k => k.toLowerCase())]);
  return Object.keys(row).filter(k => {
    if (exc.has(k.toLowerCase())) return false;
    const v = row[k];
    if (typeof v === 'number') return true;
    if (typeof v === 'string' && v.trim() !== '') return !isNaN(parseFloat(v));
    return false;
  });
}

function _toNum(v) {
  const n = parseFloat(v);
  return isNaN(n) ? null : n;
}

/* ─── Human-readable column labels ───────────────────────────── */

const _COL_LABELS = {
  hg_ha_yield:                    'Rendimiento (hg/ha)',
  avg_yield:                      'Rendimiento medio (hg/ha)',
  pesticides_tonnes:              'Pesticidas (t)',
  avg_pest:                       'Pesticidas medios (t)',
  avg_temp:                       'Temperatura media (°C)',
  temperature:                    'Temperatura (°C)',
  average_rain_fall_mm_per_year:  'Precipitación (mm/año)',
  avg_rain:                       'Precipitación media (mm)',
  rainfall:                       'Precipitación (mm)',
  humidity:                       'Humedad (%)',
  ph:                             'pH del suelo',
  n:                              'Nitrógeno (N)',
  p:                              'Fósforo (P)',
  k:                              'Potasio (K)',
  coffee_arabica:                 'Café Arábica (USD)',
  tea_columbo:                    'Té Colombo (USD)',
  sugar_eu:                       'Azúcar EU (USD)',
  sugar_world:                    'Azúcar mundial (USD)',
  oil_brent:                      'Petróleo Brent (USD)',
};

function _colLabel(col) {
  return _COL_LABELS[col] ?? col.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

/* ─── Chart.js shared option builders ────────────────────────── */

function _lineOpts(yLabel) {
  return {
    responsive: true,
    maintainAspectRatio: true,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { labels: { font: { size: 11 }, padding: 12 } },
      tooltip: { bodyFont: { size: 11 } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxTicksLimit: 12 }, grid: { color: '#f0f0f0' } },
      y: {
        ticks: { font: { size: 10 } },
        grid: { color: '#f0f0f0' },
        title: { display: !!yLabel, text: yLabel, font: { size: 10 } },
      },
    },
  };
}

function _barOpts(yLabel, horizontal = false) {
  const base = {
    responsive: true,
    maintainAspectRatio: true,
    plugins: {
      legend: { display: false },
      tooltip: { bodyFont: { size: 11 } },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 45 }, grid: { color: '#f0f0f0' } },
      y: {
        ticks: { font: { size: 10 } },
        grid: { color: '#f0f0f0' },
        title: { display: !!yLabel, text: yLabel, font: { size: 10 } },
      },
    },
  };
  if (horizontal) base.indexAxis = 'y';
  return base;
}

/* ─── DOM helpers ─────────────────────────────────────────────── */

function _createChartWrap(title) {
  const div = document.createElement('div');
  div.className = 'chart-wrap';
  const titleEl = document.createElement('div');
  titleEl.className = 'chart-title';
  titleEl.textContent = title;
  const canvas = document.createElement('canvas');
  div.appendChild(titleEl);
  div.appendChild(canvas);
  return div;
}

/* ─── Chart renderers ─────────────────────────────────────────── */

/**
 * Time-series line chart. Groups by category column when present.
 * Renders one chart per numeric metric (max 4).
 */
function _renderTimeSeries(data, yearCol, catCol, parentEl) {
  const numCols = _numericCols(data[0], catCol ? [yearCol, catCol] : [yearCol]).slice(0, 4);
  if (!numCols.length) return;

  // Build { category → { year → row } }
  const series = {};
  data.forEach(row => {
    const cat = catCol ? String(row[catCol] ?? 'Global') : 'Global';
    if (!series[cat]) series[cat] = {};
    series[cat][row[yearCol]] = row;
  });

  const years = [...new Set(data.map(r => r[yearCol]))].sort();
  const cats  = Object.keys(series).slice(0, 8);

  numCols.forEach(col => {
    const wrap   = _createChartWrap(_colLabel(col));
    const canvas = wrap.querySelector('canvas');
    parentEl.appendChild(wrap);

    const datasets = cats.map((cat, i) => ({
      label:           cat === 'Global' && cats.length === 1 ? _colLabel(col) : cat,
      data:            years.map(y => _toNum(series[cat]?.[y]?.[col])),
      borderColor:     _CHART_PALETTE[i % _CHART_PALETTE.length],
      backgroundColor: _CHART_PALETTE[i % _CHART_PALETTE.length] + '18',
      tension:         0.35,
      fill:            cats.length === 1,
      pointRadius:     years.length > 25 ? 2 : 4,
      spanGaps:        true,
    }));

    new Chart(canvas, {
      type: 'line',
      data: { labels: years, datasets },
      options: _lineOpts(cats.length === 1 ? _colLabel(col) : ''),
    });
  });
}

/**
 * Horizontal bar chart for category comparisons (no time axis).
 * Renders one chart per numeric metric (max 3).
 */
function _renderCategoryBars(data, catCol, parentEl) {
  const rows    = data.slice(0, 25);
  const numCols = _numericCols(rows[0], [catCol]).slice(0, 3);
  if (!numCols.length) return;

  const labels = rows.map(r => String(r[catCol] ?? ''));
  const horizontal = labels.length > 8;

  numCols.forEach(col => {
    const wrap   = _createChartWrap(_colLabel(col));
    const canvas = wrap.querySelector('canvas');
    parentEl.appendChild(wrap);

    const values = rows.map(r => _toNum(r[col]) ?? 0);

    new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label:           _colLabel(col),
          data:            values,
          backgroundColor: labels.map((_, i) => _CHART_PALETTE[i % _CHART_PALETTE.length] + 'cc'),
          borderColor:     labels.map((_, i) => _CHART_PALETTE[i % _CHART_PALETTE.length]),
          borderWidth:     1,
          borderRadius:    4,
        }],
      },
      options: _barOpts(_colLabel(col), horizontal),
    });
  });
}

/**
 * Radar chart for multi-metric crop condition profiles (normalised 0–100).
 */
function _renderRadar(data, catCol, parentEl) {
  const numCols = _numericCols(data[0], catCol ? [catCol] : []).slice(0, 8);
  if (numCols.length < 3) return;

  // Normalise each axis to 0–100
  const colMax = {};
  numCols.forEach(c => {
    colMax[c] = Math.max(...data.map(r => _toNum(r[c]) ?? 0)) || 1;
  });

  const wrap   = _createChartWrap('Perfil comparativo (normalizado)');
  const canvas = wrap.querySelector('canvas');
  parentEl.appendChild(wrap);

  const datasets = data.slice(0, 6).map((row, i) => ({
    label:            catCol ? String(row[catCol]) : `Fila ${i + 1}`,
    data:             numCols.map(c => Math.round((_toNum(row[c]) ?? 0) / colMax[c] * 100)),
    borderColor:      _CHART_PALETTE[i % _CHART_PALETTE.length],
    backgroundColor:  _CHART_PALETTE[i % _CHART_PALETTE.length] + '22',
    pointBackgroundColor: _CHART_PALETTE[i % _CHART_PALETTE.length],
  }));

  new Chart(canvas, {
    type: 'radar',
    data: { labels: numCols.map(_colLabel), datasets },
    options: {
      responsive: true,
      plugins: { legend: { labels: { font: { size: 11 } } } },
      scales: {
        r: {
          min: 0, max: 100,
          ticks: { stepSize: 25, font: { size: 9 } },
          grid:  { color: '#e5e5e5' },
          pointLabels: { font: { size: 10 } },
        },
      },
    },
  });
}

/* ─── Main public function ────────────────────────────────────── */

/**
 * Analyse `data` and append the appropriate charts to `parentEl`.
 * @param {Array<object>} data      Row array from the API
 * @param {HTMLElement}   parentEl  DOM element to append charts into
 */
function renderCharts(data, parentEl) {
  if (!data?.length || typeof Chart === 'undefined') return;
  // Need at least 2 rows to make a meaningful chart
  if (data.length < 2) return;

  const sample  = data[0];
  const keys    = Object.keys(sample);
  const yearCol = keys.find(_isYear);
  const catCol  = keys.find(_isCategory);
  const numCols = _numericCols(sample, yearCol ? [yearCol] : []);

  if (!numCols.length) return;

  try {
    if (yearCol) {
      // Time series — most important case (yield/pesticide/price trends)
      _renderTimeSeries(data, yearCol, catCol ?? null, parentEl);
    } else if (catCol) {
      const uniqueCats = new Set(data.map(r => r[catCol]));
      if (uniqueCats.size >= 2) {
        // Multi-metric radar for crop conditions (few rows, many dimensions)
        if (data.length <= 10 && numCols.length >= 4) {
          _renderRadar(data, catCol, parentEl);
        } else {
          _renderCategoryBars(data, catCol, parentEl);
        }
      }
    }
  } catch (e) {
    console.warn('AgroAdvisor charts: rendering error', e);
  }
}
