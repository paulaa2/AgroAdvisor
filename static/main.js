/* =================================================================
   AgroAdvisor -- main.js
   UI shell: shared avatars, panel navigation, toast, loading.
   Business logic is split across:
     render.js  -- rendering helpers (pipeline, results, markdown)
     api.js     -- fetch helpers (analysis runners, PDF downloads)
     chat.js    -- chat panel (mode toggle, sendChat)
   ================================================================= */

/* --- Shared SVG avatars (used by chat.js) ---------------------- */
const BOT_AVATAR  = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>`;
const USER_AVATAR = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;

/* --- Panel navigation ------------------------------------------ */
function showPanel(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('panel-' + id);
  if (panel) panel.classList.add('active');
  const btn = document.querySelector(`.nav-item[data-panel="${id}"]`);
  if (btn) btn.classList.add('active');
  document.getElementById('sidebar').classList.remove('open');
}

/* --- Toast ----------------------------------------------------- */
let _toastBox;
function toast(msg, type = 'info', ms = 4000) {
  if (!_toastBox) {
    _toastBox = document.createElement('div');
    _toastBox.className = 'toast-container';
    document.body.appendChild(_toastBox);
  }
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.textContent = msg;
  _toastBox.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, ms);
}

/* --- Loading spinner ------------------------------------------- */
function showLoading(container, message = 'Analizando datos...') {
  container.innerHTML =
    `<div class="loading-indicator"><div class="spinner"></div><span>${message}</span></div>`;
}

/* --- Init ------------------------------------------------------ */
document.addEventListener('DOMContentLoaded', () => {
  showPanel('consult');

  // Auto-resize chat textarea
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
    });
  }
});
