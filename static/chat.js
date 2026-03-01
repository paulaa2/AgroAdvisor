/* AgroAdvisor - chat.js */

let chatMode = 'pipeline';

function setChatMode(mode) {
  chatMode = mode;
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === mode);
  });
}

async function sendChat() {
  const input = document.getElementById('chat-input');
  const question = input.value.trim();
  if (!question) return;
  input.value = '';
  input.style.height = 'auto';

  const msgs = document.getElementById('chat-messages');
  const modeLabel = chatMode === 'deep' ? 'DeepQuery' : 'Pipeline';

  _appendMsg(msgs, 'user',
    '<div class="avatar av-user">' + USER_AVATAR + '</div>' +
    '<div class="bubble">' + esc(question) + '</div>');

  const loadId = 'ld-' + Date.now();
  _appendMsg(msgs, 'bot',
    '<div class="avatar av-bot" id="' + loadId + '-av">' + BOT_AVATAR + '</div>' +
    '<div class="bubble" id="' + loadId + '">' +
      '<div class="loading-indicator"><div class="spinner"></div><span>' + modeLabel + ': Analizando...</span></div>' +
    '</div>', loadId + '-wrap');
  msgs.scrollTop = msgs.scrollHeight;

  try {
    const url = chatMode === 'deep'
      ? '/api/deep-query?question=' + encodeURIComponent(question)
      : '/api/ask?question=' + encodeURIComponent(question) + '&mode=auto';
    const res = await fetch(url);
    const data = await res.json();

    document.getElementById(loadId + '-wrap')?.remove();

    if (data.pipeline) {
      const pipeDiv = document.createElement('div');
      pipeDiv.className = 'msg bot pipeline-msg';
      pipeDiv.innerHTML = '<div class="avatar av-bot">' + BOT_AVATAR + '</div>' +
        '<div class="pipeline-outer">' + renderPipeline(data.pipeline, true) + '</div>';
      msgs.appendChild(pipeDiv);
    }

    const answer = data.answer || data.error || 'No se pudo obtener respuesta.';
    let content = renderMd(answer);
    content += renderDataTable((data.data || []).slice(0, 20));

    const msgId = 'msg-' + Date.now();
    _appendMsg(msgs, 'bot',
      '<div class="avatar av-bot">' + BOT_AVATAR + '</div>' +
      '<div class="bubble" id="' + msgId + '">' + content + '</div>');

    // Client-side charts
    let chartData = Array.isArray(data.data) && data.data.length >= 2 ? data.data : [];
    if (chartData.length < 2 && typeof extractChartData === 'function') {
      chartData = extractChartData(data);
    }
    if (chartData.length >= 2) {
      const bubble = document.getElementById(msgId);
      if (bubble) {
        const section = document.createElement('div');
        section.className = 'chart-section';
        bubble.appendChild(section);
        if (typeof renderCharts === 'function') renderCharts(chartData, section);
      }
    }
  } catch (e) {
    document.getElementById(loadId + '-wrap')?.remove();
    _appendMsg(msgs, 'bot',
      '<div class="avatar av-bot">' + BOT_AVATAR + '</div>' +
      '<div class="bubble" style="color:var(--red)">Error: ' + esc(e.message) + '</div>');
  }
  msgs.scrollTop = msgs.scrollHeight;
}

function _appendMsg(container, role, innerHTML, id) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  if (id) div.id = id;
  div.innerHTML = innerHTML;
  container.appendChild(div);
}
