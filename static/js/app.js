/**
 * Outlook Fusion - Enterprise Dashboard Controller & State Engine
 */

const App = (function () {
  'use strict';

  // ----------------------------------------------------
  // 1. 全局状态仓库 (Single Source of Truth)
  // ----------------------------------------------------
  const state = {
    currentView: 'accounts', // 'accounts' | 'emails' | 'settings'
    isRefreshing: false,
    
    // 账户数据
    accounts: [],
    health: { total: 0, active: 0, expired: 0, needs_reauth: 0 },
    selectedEmails: new Set(),

    // 邮件工作台
    email: {
      activeEmail: '',
      folder: 'inbox',
      page: 1,
      pageSize: 30,
      searchQuery: '',
      emails: [],
      totalEmails: 0,
      selectedMessageId: null,
      currentDetail: null,
      detailTab: 'html', // 'html' | 'plain'
      detectedOtp: null
    },

    // 系统安全
    security: {
      apiKeyConfigured: false,
      lockThreshold: 5,
      lockDuration: 300,
      lockedIps: []
    }
  };

  // ----------------------------------------------------
  // 2. 视图切换路由
  // ----------------------------------------------------
  function switchView(viewName) {
    state.currentView = viewName;

    // 切换 Header Tabs
    ['accounts', 'emails', 'settings'].forEach(v => {
      const tab = $('tab-' + v);
      const panel = $('panel-' + v);
      if (tab) tab.classList.toggle('active', v === viewName);
      if (panel) panel.classList.toggle('active', v === viewName);
    });

    if (viewName === 'settings') {
      loadSecurityData();
    } else if (viewName === 'emails') {
      populateEmailAccountDropdown();
      if (state.email.activeEmail && !state.email.emails.length) {
        loadEmails(false);
      }
    }
  }

  // ----------------------------------------------------
  // 3. 账户管理模块
  // ----------------------------------------------------
  async function loadAccounts() {
    try {
      const [listRes, healthRes] = await Promise.all([
        api('/api/accounts'),
        api('/api/accounts/_health')
      ]);

      state.accounts = listRes.accounts || [];
      if (healthRes) {
        state.health = {
          total: healthRes.total || 0,
          active: healthRes.active || 0,
          expired: healthRes.expired || 0,
          needs_reauth: healthRes.needs_reauth || 0
        };
      }

      renderHealthCards();
      renderAccountsTable();
      populateEmailAccountDropdown();
    } catch (err) {
      toast('加载账户列表失败: ' + err.message, 'error');
      $('accountsTableBody').innerHTML = `
        <tr><td colspan="7" style="text-align:center;padding:30px;color:var(--c-error);">
          加载失败: ${esc(err.message)}
        </td></tr>
      `;
    }
  }

  function renderHealthCards() {
    $('statTotal').textContent = state.health.total;
    $('statActive').textContent = state.health.active;
    $('statNeedsAuth').textContent = state.health.needs_reauth;
    $('statExpired').textContent = state.health.expired;
    $('headerAccountCount').textContent = state.accounts.length;
  }

  function getFilteredAccounts() {
    const q = ($('accountSearchInput')?.value || '').trim().toLowerCase();
    const st = $('accountStatusFilter')?.value || 'all';
    const pt = $('accountProtocolFilter')?.value || 'all';

    return state.accounts.filter(a => {
      if (q) {
        const matchEmail = a.email.toLowerCase().includes(q);
        const matchTags = (a.tags || []).some(t => t.toLowerCase().includes(q));
        const matchNote = (a.note || '').toLowerCase().includes(q);
        if (!matchEmail && !matchTags && !matchNote) return false;
      }
      if (st !== 'all' && a.status !== st) return false;
      if (pt !== 'all' && (a.email_protocol || 'auto') !== pt) return false;
      return true;
    });
  }

  function onAccountFilterChange() {
    renderAccountsTable();
  }

  function renderAccountsTable() {
    const tbody = $('accountsTableBody');
    if (!tbody) return;

    const list = getFilteredAccounts();
    updateBatchBar(list);

    if (!list.length) {
      tbody.innerHTML = `
        <tr><td colspan="7" style="text-align:center;padding:40px;color:var(--c-text-muted);">
          未找到符合条件的账户
        </td></tr>
      `;
      return;
    }

    tbody.innerHTML = list.map(a => {
      const isSelected = state.selectedEmails.has(a.email);
      const tagsHtml = (a.tags && a.tags.length)
        ? a.tags.map(t => `<span class="badge badge-neutral" style="margin-right:4px;">${esc(t)}</span>`).join('')
        : (a.note ? `<span style="color:var(--c-text-muted);font-size:12px;">${esc(a.note)}</span>` : '<span style="color:var(--c-text-subtle);font-size:12px;">-</span>');
      
      const lastRefresh = a.last_refreshed_at ? new Date(a.last_refreshed_at).toLocaleString() : '-';

      return `
        <tr class="${isSelected ? 'selected' : ''}">
          <td>
            <input type="checkbox" ${isSelected ? 'checked' : ''} onchange="App.toggleAccountSelect('${esc(a.email)}')">
          </td>
          <td>
            <div class="email-col">
              <span style="font-weight:600;">${esc(a.email)}</span>
              <button class="copy-btn" onclick="copyText('${esc(a.email)}', '邮箱已复制')" title="复制邮箱">📋</button>
            </div>
          </td>
          <td>
            <span class="badge badge-${esc(a.status)}">
              <span class="dot"></span>${esc(a.status)}
            </span>
          </td>
          <td><span class="badge badge-neutral">${esc(a.email_protocol || 'auto')}</span></td>
          <td style="color:var(--c-text-muted);font-size:12px;">${lastRefresh}</td>
          <td>${tagsHtml}</td>
          <td style="text-align:right;">
            <div style="display:inline-flex;gap:4px;">
              <button class="btn btn-sm" onclick="App.jumpToEmails('${esc(a.email)}')">📬 查看邮件</button>
              <button class="btn btn-secondary btn-sm" onclick="App.refreshOneToken('${esc(a.email)}')">🔄 刷新</button>
              <button class="btn btn-secondary btn-sm" onclick="App.markStatusOne('${esc(a.email)}', 'expired')" title="手动标记失效">⛔</button>
              <button class="btn btn-danger btn-sm" onclick="App.deleteAccountOne('${esc(a.email)}')">🗑️</button>
            </div>
          </td>
        </tr>
      `;
    }).join('');
  }

  function toggleAccountSelect(email) {
    if (state.selectedEmails.has(email)) {
      state.selectedEmails.delete(email);
    } else {
      state.selectedEmails.add(email);
    }
    renderAccountsTable();
  }

  function toggleSelectAllAccounts(checked) {
    const list = getFilteredAccounts();
    if (checked) {
      list.forEach(a => state.selectedEmails.add(a.email));
    } else {
      list.forEach(a => state.selectedEmails.delete(a.email));
    }
    renderAccountsTable();
  }

  function clearAccountSelection() {
    state.selectedEmails.clear();
    renderAccountsTable();
  }

  function updateBatchBar(filteredList) {
    const count = state.selectedEmails.size;
    const batchBar = $('batchBar');
    const selectAll = $('selectAllAccounts');
    
    if (batchBar) batchBar.classList.toggle('active', count > 0);
    if ($('selectedAccountCount')) $('selectedAccountCount').textContent = count;
    
    if (selectAll) {
      selectAll.checked = filteredList.length > 0 && filteredList.every(a => state.selectedEmails.has(a.email));
    }
  }

  function copySelectedEmails() {
    const list = Array.from(state.selectedEmails);
    if (!list.length) return;
    copyText(list.join('\n'), `已复制 ${list.length} 个邮箱地址`);
  }

  async function batchRefreshSelected() {
    const list = Array.from(state.selectedEmails);
    if (!list.length) return;
    toast(`开始批量刷新 ${list.length} 个账户...`, 'info');
    let ok = 0, fail = 0;
    for (const email of list) {
      try {
        await api('/api/tokens/' + encodeURIComponent(email) + '/refresh', { method: 'POST' });
        ok++;
      } catch { fail++; }
    }
    toast(`批量刷新完成: 成功 ${ok}, 失败 ${fail}`, ok >= fail ? 'success' : 'warning');
    loadAccounts();
  }

  async function batchMarkExpiredSelected() {
    const list = Array.from(state.selectedEmails);
    if (!list.length) return;
    if (!await confirmDialog(`确定将选中的 ${list.length} 个账户标记为已失效？`)) return;
    for (const email of list) {
      try {
        await api('/api/accounts/' + encodeURIComponent(email) + '/status', {
          method: 'PUT',
          body: JSON.stringify({ status: 'expired' })
        });
      } catch {}
    }
    toast(`已将 ${list.length} 个账户标记为失效`, 'success');
    loadAccounts();
  }

  async function batchDeleteSelected() {
    const list = Array.from(state.selectedEmails);
    if (!list.length) return;
    if (!await confirmDialog(`确定永久删除选中的 ${list.length} 个账户？此操作不可撤销！`)) return;
    for (const email of list) {
      try {
        await api('/api/accounts/' + encodeURIComponent(email), { method: 'DELETE' });
      } catch {}
    }
    toast(`已成功删除 ${list.length} 个账户`, 'success');
    state.selectedEmails.clear();
    loadAccounts();
  }

  async function refreshOneToken(email) {
    try {
      toast(`正在刷新 ${email} Token...`, 'info');
      await api('/api/tokens/' + encodeURIComponent(email) + '/refresh', { method: 'POST' });
      toast(`Token 刷新成功: ${email}`, 'success');
      loadAccounts();
    } catch (err) {
      toast(`刷新失败: ${err.message}`, 'error');
    }
  }

  async function markStatusOne(email, status) {
    try {
      await api('/api/accounts/' + encodeURIComponent(email) + '/status', {
        method: 'PUT',
        body: JSON.stringify({ status })
      });
      toast(`已将 ${email} 标记为 ${status}`, 'success');
      loadAccounts();
    } catch (err) {
      toast(`更新失败: ${err.message}`, 'error');
    }
  }

  async function deleteAccountOne(email) {
    if (!await confirmDialog(`确定删除账户 ${email}？`)) return;
    try {
      await api('/api/accounts/' + encodeURIComponent(email), { method: 'DELETE' });
      toast('账户已删除', 'success');
      state.selectedEmails.delete(email);
      loadAccounts();
    } catch (err) {
      toast(`删除失败: ${err.message}`, 'error');
    }
  }

  async function refreshAllTokens() {
    if (!await confirmDialog('确定全量刷新所有未失效账户的 Token？')) return;
    toast('全量刷新任务已提交执行...', 'info');
    try {
      const res = await api('/api/tokens/refresh-all', { method: 'POST' });
      toast(res.message || '全量刷新已完成', 'success');
      loadAccounts();
    } catch (err) {
      toast('全量刷新失败: ' + err.message, 'error');
    }
  }

  // 批量导入
  function toggleImportBox(open) {
    const box = $('importBox');
    if (!box) return;
    if (open === undefined) {
      box.classList.toggle('open');
    } else {
      box.classList.toggle('open', !!open);
    }
  }

  async function submitBatchImport() {
    const text = ($('importText')?.value || '').trim();
    if (!text) {
      toast('请输入批量导入内容', 'warning');
      return;
    }
    const btn = $('btnDoImport');
    const statusEl = $('importStatus');
    btn.disabled = true;
    btn.textContent = '导入中...';
    statusEl.innerHTML = '';

    try {
      const res = await api('/api/accounts/batch', {
        method: 'POST',
        body: JSON.stringify({ text })
      });
      statusEl.innerHTML = `
        <span style="color:var(--c-success);">成功: ${res.success}</span>，
        <span style="color:var(--c-error);">失败: ${res.failed}</span>
      `;
      toast(`导入完成：成功 ${res.success}，失败 ${res.failed}`, res.failed > 0 ? 'warning' : 'success');
      $('importText').value = '';
      loadAccounts();
    } catch (err) {
      statusEl.innerHTML = `<span style="color:var(--c-error);">${esc(err.message)}</span>`;
      toast('批量导入失败: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '开始导入';
    }
  }

  // 添加单账户模态框
  function openAddAccountModal() {
    $('newAccEmail').value = '';
    $('newAccClientId').value = '';
    $('newAccRefreshToken').value = '';
    $('newAccTags').value = '';
    $('newAccNote').value = '';
    openModal('modalAddAccount');
  }

  async function submitAddSingleAccount() {
    const email = $('newAccEmail').value.trim();
    const clientId = $('newAccClientId').value.trim();
    const refreshToken = $('newAccRefreshToken').value.trim();
    const tagsStr = $('newAccTags').value.trim();
    const note = $('newAccNote').value.trim();

    if (!email || !clientId || !refreshToken) {
      toast('请完整填写邮箱、Client ID 和 Refresh Token', 'warning');
      return;
    }

    const btn = $('btnSubmitAddAcc');
    btn.disabled = true;
    btn.textContent = '添加中...';

    try {
      const tags = tagsStr ? tagsStr.split(/[,， ]+/).filter(Boolean) : [];
      await api('/api/accounts', {
        method: 'POST',
        body: JSON.stringify({
          email,
          client_id: clientId,
          refresh_token: refreshToken,
          tags,
          note
        })
      });
      toast('账户添加成功', 'success');
      closeModal('modalAddAccount');
      loadAccounts();
    } catch (err) {
      toast('添加失败: ' + err.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = '确认添加';
    }
  }

  // ----------------------------------------------------
  // 4. 邮件工作台模块 (Email Workspace)
  // ----------------------------------------------------
  function populateEmailAccountDropdown() {
    const sel = $('emailAccountSelector');
    if (!sel) return;
    const current = state.email.activeEmail;
    
    let html = '<option value="">-- 选择查看账户 --</option>';
    state.accounts.forEach(a => {
      const isSel = a.email === current ? 'selected' : '';
      html += `<option value="${esc(a.email)}" ${isSel}>${esc(a.email)} (${esc(a.status)})</option>`;
    });
    sel.innerHTML = html;
  }

  function jumpToEmails(email) {
    state.email.activeEmail = email;
    switchView('emails');
    const sel = $('emailAccountSelector');
    if (sel) sel.value = email;
    state.email.page = 1;
    loadEmails(false);
  }

  function onEmailAccountChange(email) {
    state.email.activeEmail = email;
    state.email.page = 1;
    loadEmails(false);
  }

  function switchEmailFolder(folder) {
    state.email.folder = folder;
    state.email.page = 1;
    ['inbox', 'junk', 'all'].forEach(f => {
      $('folder-' + f)?.classList.toggle('active', f === folder);
    });
    loadEmails(false);
  }

  function changeEmailPage(delta) {
    const newPage = state.email.page + delta;
    if (newPage < 1) return;
    state.email.page = newPage;
    loadEmails(false);
  }

  function exportCsvCurrent() {
    if (!state.email.activeEmail) {
      toast('请先选择账户', 'warning');
      return;
    }
    window.location.href = `/api/emails/${encodeURIComponent(state.email.activeEmail)}/export.csv?folder=${state.email.folder}&page_size=500`;
  }

  async function loadEmails(forceRefresh = false) {
    const email = state.email.activeEmail;
    const listContainer = $('emailListScroll');
    if (!email) {
      state.email.emails = [];
      state.email.currentDetail = null;
      state.email.selectedMessageId = null;
      listContainer.innerHTML = '<div class="email-detail-empty"><span>📬 请先在上方选择要查看的账户</span></div>';
      renderEmailDetail();
      return;
    }

    listContainer.innerHTML = `
      <div style="padding:40px;text-align:center;color:var(--c-text-muted);">
        <div class="spinner"></div>
        <div style="margin-top:8px;font-size:12px;">正在加载邮件...</div>
      </div>
    `;

    try {
      const q = ($('emailSearchInput')?.value || '').trim();
      let data;
      if (q) {
        data = await api(`/api/emails/${encodeURIComponent(email)}/search?q=${encodeURIComponent(q)}&folder=${state.email.folder}&limit=50`);
      } else {
        data = await api(`/api/emails/${encodeURIComponent(email)}?folder=${state.email.folder}&page=${state.email.page}&page_size=${state.email.pageSize}&refresh=${forceRefresh}`);
      }

      state.email.emails = data.emails || [];
      state.email.totalEmails = data.total_emails || 0;

      renderEmailList();

      if (state.email.emails.length > 0) {
        if (!state.email.selectedMessageId || !state.email.emails.some(m => m.message_id === state.email.selectedMessageId)) {
          selectEmail(state.email.emails[0].message_id);
        }
      } else {
        state.email.selectedMessageId = null;
        state.email.currentDetail = null;
        renderEmailDetail();
      }
    } catch (err) {
      toast('加载邮件失败: ' + err.message, 'error');
      listContainer.innerHTML = `
        <div class="email-detail-empty">
          <span style="color:var(--c-error);">加载失败: ${esc(err.message)}</span>
        </div>
      `;
    }
  }

  function renderEmailList() {
    const listContainer = $('emailListScroll');
    if (!listContainer) return;

    $('emailPageInfo').textContent = `第 ${state.email.page} 页 / 共 ${state.email.totalEmails} 封`;
    $('btnPrevPage').disabled = state.email.page <= 1;
    $('btnNextPage').disabled = state.email.emails.length < state.email.pageSize;

    if (!state.email.emails.length) {
      listContainer.innerHTML = `
        <div class="email-detail-empty">
          <div style="font-size:28px;">📭</div>
          <div style="font-size:13px;">该文件夹暂无邮件</div>
        </div>
      `;
      return;
    }

    listContainer.innerHTML = state.email.emails.map(m => {
      const isSel = m.message_id === state.email.selectedMessageId;
      const otpCode = extractOtpCode(m.subject || '', '');
      const otpBtn = otpCode ? `
        <button class="code-pill" onclick="event.stopPropagation(); copyText('${esc(otpCode)}', '验证码已复制')">
          🔑 ${esc(otpCode)} 复制
        </button>
      ` : '';

      return `
        <div class="email-card ${isSel ? 'active' : ''}" onclick="App.selectEmail('${esc(m.message_id)}')">
          <div class="email-card-top">
            <div class="email-sender" title="${esc(m.from_email)}">${esc(m.from_email || '未知发件人')}</div>
            <div class="email-date">${esc(m.date || '')}</div>
          </div>
          <div class="email-subject" title="${esc(m.subject)}">${esc(m.subject || '(无主题)')}</div>
          <div class="email-card-bottom">
            <span class="email-badge-folder">${esc(m.folder || state.email.folder)}</span>
            ${otpBtn}
          </div>
        </div>
      `;
    }).join('');
  }

  async function selectEmail(messageId) {
    state.email.selectedMessageId = messageId;
    renderEmailList();

    const pane = $('emailDetailPane');
    pane.innerHTML = `
      <div style="display:flex;flex:1;align-items:center;justify-content:center;color:var(--c-text-muted);">
        <div class="spinner"></div>
        <span style="margin-left:8px;font-size:13px;">正在解析邮件正文...</span>
      </div>
    `;

    try {
      const d = await api(`/api/emails/${encodeURIComponent(state.email.activeEmail)}/${encodeURIComponent(messageId)}`);
      state.email.currentDetail = d;
      state.email.detectedOtp = extractOtpCode(d.subject || '', d.body_plain || d.body_html || '');
      renderEmailDetail();
    } catch (err) {
      toast('加载正文失败: ' + err.message, 'error');
      pane.innerHTML = `
        <div class="email-detail-empty">
          <span style="color:var(--c-error);">正文解析错误: ${esc(err.message)}</span>
        </div>
      `;
    }
  }

  function renderEmailDetail() {
    const pane = $('emailDetailPane');
    if (!pane) return;

    const d = state.email.currentDetail;
    if (!d || !state.email.selectedMessageId) {
      pane.innerHTML = `
        <div class="email-detail-empty">
          <div style="font-size:48px;">📨</div>
          <div style="font-weight:600;font-size:15px;">未选择邮件</div>
          <div style="font-size:12px;">从左侧列表中点击邮件以快速预览正文与提取验证码</div>
        </div>
      `;
      return;
    }

    const otpBanner = state.email.detectedOtp ? `
      <div class="otp-highlight-banner">
        <div class="otp-text-group">
          <span style="font-size:20px;">🔑</span>
          <div>
            <div style="font-size:11px;color:#1e40af;font-weight:600;">智能检测到验证码</div>
            <div class="otp-big-code">${esc(state.email.detectedOtp)}</div>
          </div>
        </div>
        <button class="btn btn-sm" onclick="copyText('${esc(state.email.detectedOtp)}', '验证码已复制')">一键复制验证码</button>
      </div>
    ` : '';

    pane.innerHTML = `
      <div style="display:flex;flex:1;flex-direction:column;overflow:hidden;">
        <div class="email-detail-header">
          <div class="detail-subject-row">
            <div class="detail-subject">${esc(d.subject || '(无主题)')}</div>
            <button class="btn btn-ghost btn-xs" onclick="App.copyCurrentPlainBody()" title="复制邮件纯文本">📋 复制正文</button>
          </div>
          <div class="detail-meta-grid">
            <span class="detail-meta-label">发件人:</span> <span>${esc(d.from_email || '-')}</span>
            <span class="detail-meta-label">收件人:</span> <span>${esc(d.to_email || '-')}</span>
            <span class="detail-meta-label">时间:</span> <span>${esc(d.date || '-')}</span>
          </div>
        </div>

        ${otpBanner}

        <div class="detail-body-container">
          <div class="detail-view-tabs">
            <button class="btn btn-sm ${state.email.detailTab === 'html' ? 'btn-secondary' : 'btn-ghost'}" onclick="App.switchDetailTab('html')">🎨 富文本视图</button>
            <button class="btn btn-sm ${state.email.detailTab === 'plain' ? 'btn-secondary' : 'btn-ghost'}" onclick="App.switchDetailTab('plain')">📄 纯文本视图</button>
          </div>
          
          <div id="detailIframeBox" class="detail-iframe-box" style="display:${state.email.detailTab === 'html' ? 'block' : 'none'};">
            <iframe id="detailIframe" sandbox="allow-popups allow-same-origin"></iframe>
          </div>
          
          <div id="detailPlainBox" class="detail-plain-box" style="display:${state.email.detailTab === 'plain' ? 'block' : 'none'};">
            ${esc(d.body_plain || d.body_html || '(无纯文本正文)')}
          </div>
        </div>
      </div>
    `;

    if (state.email.detailTab === 'html') {
      renderDetailIframe();
    }
  }

  function switchDetailTab(tab) {
    state.email.detailTab = tab;
    const iframeBox = $('detailIframeBox');
    const plainBox = $('detailPlainBox');
    if (iframeBox) iframeBox.style.display = tab === 'html' ? 'block' : 'none';
    if (plainBox) plainBox.style.display = tab === 'plain' ? 'block' : 'none';
    if (tab === 'html') renderDetailIframe();
  }

  function renderDetailIframe() {
    const iframe = $('detailIframe');
    const d = state.email.currentDetail;
    if (!iframe || !d) return;

    const htmlBody = d.body_html || (d.body_plain ? `<pre style="white-space:pre-wrap;font-family:inherit;line-height:1.6;">${esc(d.body_plain)}</pre>` : '<div style="color:#94a3b8;padding:20px;">(无正文)</div>');
    const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src https: http: data: cid: blob:; style-src 'unsafe-inline'; font-src https: data:; base-uri 'none';">`;
    const baseTarget = `<base target="_blank">`;
    const resetStyle = `<style>
      body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b; margin: 18px; word-break: break-word; background: #fff; }
      img { max-width: 100%; height: auto; }
      table { max-width: 100% !important; }
      a { color: #2563eb; }
    </style>`;

    iframe.srcdoc = `<!DOCTYPE html><html><head><meta charset="UTF-8">${csp}${baseTarget}${resetStyle}</head><body>${htmlBody}</body></html>`;
  }

  function copyCurrentPlainBody() {
    const d = state.email.currentDetail;
    if (d) copyText(d.body_plain || d.body_html || '', '邮件正文已复制');
  }

  // ----------------------------------------------------
  // 5. 系统与安全模块
  // ----------------------------------------------------
  async function loadSecurityData() {
    try {
      const sec = await api('/api/admin/security/status');
      state.security.apiKeyConfigured = !!sec.api_key_configured;
      state.security.lockThreshold = sec.lock_threshold || 5;
      state.security.lockDuration = sec.lock_duration_seconds || 300;
      state.security.lockedIps = sec.locked_ips || [];

      // Render API Key Badge
      const badge = $('apiKeyBadge');
      const btnDel = $('btnDeleteApiKey');
      if (state.security.apiKeyConfigured) {
        badge.className = 'badge badge-active';
        badge.textContent = '🟢 已配置生效中';
        if (btnDel) btnDel.style.display = 'inline-flex';
      } else {
        badge.className = 'badge badge-expired';
        badge.textContent = '⚪ 未配置';
        if (btnDel) btnDel.style.display = 'none';
      }

      // Render IP lock
      $('secLockThreshold').textContent = state.security.lockThreshold + ' 次';
      $('secLockDuration').textContent = state.security.lockDuration + ' 秒';
      const ipBox = $('secLockedIpsContainer');
      if (state.security.lockedIps && state.security.lockedIps.length) {
        ipBox.innerHTML = state.security.lockedIps.map(ip => `<div style="color:var(--c-error);">🚫 ${esc(ip)}</div>`).join('');
      } else {
        ipBox.innerHTML = '<span style="color:var(--c-success);">🛡️ 暂无被封禁的 IP，系统运行正常</span>';
      }
    } catch (err) {
      toast('获取安全状态失败: ' + err.message, 'error');
    }
  }

  async function rotateApiKeyAction() {
    if (!await confirmDialog('确定轮换或生成新的 API Key？原有的 API Key 将立即失效！')) return;
    try {
      const res = await api('/api/admin/api-key/rotate', { method: 'POST' });
      $('newApiKeyText').textContent = res.api_key;
      openModal('modalApiKey');
      loadSecurityData();
    } catch (err) {
      toast('轮换 API Key 失败: ' + err.message, 'error');
    }
  }

  async function deleteApiKeyAction() {
    if (!await confirmDialog('确定删除当前的 API Key？删除后所有基于 API Key 的请求将无法通过认证！')) return;
    try {
      await api('/api/admin/api-key', { method: 'DELETE' });
      toast('API Key 已删除', 'success');
      loadSecurityData();
    } catch (err) {
      toast('删除失败: ' + err.message, 'error');
    }
  }

  async function triggerSchedulerNow() {
    toast('正在触发后台调度器...', 'info');
    try {
      const res = await api('/api/tokens/trigger-scheduler', { method: 'POST' });
      toast(res.message || '调度器已触发并在后台运行', 'success');
    } catch (err) {
      toast('触发失败: ' + err.message, 'error');
    }
  }

  // ----------------------------------------------------
  // 6. 全局刷新与快捷键
  // ----------------------------------------------------
  async function doGlobalRefresh() {
    const btn = $('btnRefreshHdr');
    if (btn) btn.classList.add('loading');
    try {
      await loadAccounts();
      if (state.currentView === 'emails' && state.email.activeEmail) {
        await loadEmails(true);
      } else if (state.currentView === 'settings') {
        await loadSecurityData();
      }
      toast('数据已刷新', 'success');
    } catch (err) {
      toast('刷新失败: ' + err.message, 'error');
    } finally {
      if (btn) btn.classList.remove('loading');
    }
  }

  async function doLogout() {
    try { await fetch('/api/auth/logout', { method: 'POST' }); } catch {}
    window.location.href = '/login';
  }

  // ----------------------------------------------------
  // 7. 初始化启动
  // ----------------------------------------------------
  function init() {
    loadAccounts();

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeModal('modalAddAccount');
        closeModal('modalApiKey');
        toggleImportBox(false);
      }
      if (e.key === '/' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        if (state.currentView === 'accounts') {
          $('accountSearchInput')?.focus();
        } else if (state.currentView === 'emails') {
          $('emailSearchInput')?.focus();
        }
      }
      if (e.key === 'r' && document.activeElement.tagName !== 'INPUT' && document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        doGlobalRefresh();
      }
    });
  }

  // DOM 就绪后立即自启
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 导出公共 API
  return {
    state,
    switchView,
    loadAccounts,
    onAccountFilterChange,
    toggleAccountSelect,
    toggleSelectAllAccounts,
    clearAccountSelection,
    copySelectedEmails,
    batchRefreshSelected,
    batchMarkExpiredSelected,
    batchDeleteSelected,
    refreshOneToken,
    markStatusOne,
    deleteAccountOne,
    refreshAllTokens,
    toggleImportBox,
    submitBatchImport,
    openAddAccountModal,
    submitAddSingleAccount,
    jumpToEmails,
    onEmailAccountChange,
    switchEmailFolder,
    changeEmailPage,
    exportCsvCurrent,
    loadEmails,
    selectEmail,
    switchDetailTab,
    copyCurrentPlainBody,
    loadSecurityData,
    rotateApiKeyAction,
    deleteApiKeyAction,
    triggerSchedulerNow,
    doGlobalRefresh,
    doLogout
  };
})();
