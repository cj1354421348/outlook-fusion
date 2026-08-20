/**
 * Outlook Fusion - Core Utility Functions
 */

const $ = (id) => document.getElementById(id);

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#39;'
}[c]));

/**
 * 跨浏览器/剪贴板 API 文本复制
 */
async function copyText(text, successMsg = '已复制到剪贴板') {
  if (!text) return;
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      document.execCommand('copy');
      ta.remove();
    }
    toast(successMsg, 'success');
  } catch (err) {
    toast('复制失败: ' + err.message, 'error');
  }
}

/**
 * Toast 提示通知系统
 */
function toast(msg, type = 'info', duration = 3000) {
  const container = $('toastContainer');
  if (!container) return;
  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
  const el = document.createElement('div');
  el.className = 'toast toast-' + type;
  el.innerHTML = `
    <span class="toast-icon">${icons[type] || 'ℹ️'}</span>
    <span class="toast-msg">${esc(msg)}</span>
    <span class="toast-close" onclick="this.parentElement.classList.add('removing');setTimeout(()=>this.parentElement.remove(),200)">&times;</span>
  `;
  container.appendChild(el);
  setTimeout(() => {
    if (el.parentElement) {
      el.classList.add('removing');
      setTimeout(() => el.remove(), 200);
    }
  }, duration);
}

/**
 * 统一确认对话框 Promise 封装
 */
function confirmDialog(msg, title = '确认操作') {
  return new Promise((resolve) => {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay open';
    overlay.innerHTML = `
      <div class="modal-card" style="max-width:380px;">
        <div class="modal-head"><h4>${esc(title)}</h4></div>
        <div class="modal-body"><p style="font-size:13px;line-height:1.5;color:var(--c-text);">${esc(msg)}</p></div>
        <div class="modal-foot">
          <button class="btn btn-secondary btn-sm" id="_confirmNo">取消</button>
          <button class="btn btn-danger btn-sm" id="_confirmYes">确定</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector('#_confirmNo').onclick = () => { overlay.remove(); resolve(false); };
    overlay.querySelector('#_confirmYes').onclick = () => { overlay.remove(); resolve(true); };
  });
}

/**
 * 统一 Fetch API 客户端封装（带 401 会话失效拦截）
 */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('未登录');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
  return data;
}

/**
 * 模态框打开与关闭控制
 */
function openModal(id) { $(id)?.classList.add('open'); }
function closeModal(id) { $(id)?.classList.remove('open'); }

/**
 * 智能验证码正则匹配引擎 (支持 4~8 位数字/大写英文/PIN)
 */
function extractOtpCode(subject = '', bodyText = '') {
  const fullText = (subject + ' ' + (bodyText || ''));
  const codePatterns = [
    /(?:code|verification|token|passcode|pin|验证码|校验码|动态码)[^\w\d]{1,12}([A-Za-z0-9]{4,8})\b/i,
    /\b([0-9]{6})\b/,
    /\b([0-9]{4})\b/,
    /\b([0-9]{8})\b/,
  ];
  for (const pattern of codePatterns) {
    const match = fullText.match(pattern);
    if (match && match[1]) {
      const candidate = match[1].trim();
      // 过滤年份 (如 1999, 2024, 2026)
      if (!/^(19|20)\d\d$/.test(candidate)) return candidate;
    }
  }
  return null;
}
