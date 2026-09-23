/**
 * Template Library — Browse, preview, and load pre-built workflow templates.
 * Usage: window.templateLibrary = new TemplateLibrary(); templateLibrary.show();
 */
class TemplateLibrary {
  constructor() {
    this._templates = [];       // All templates from API
    this._filtered = [];        // Currently visible templates
    this._activeCat = 'all';    // Active category filter
    this._searchQuery = '';     // Current search query
    this._searchTimer = null;   // Debounce timer
    this._initialized = false;

    // Category display config
    this._categories = [
      { id: 'all',          label: 'All' },
      { id: 'ai_llm',       label: '🧠 AI / LLM' },
      { id: 'sales',        label: '📊 Sales' },
      { id: 'marketing',    label: '📣 Marketing' },
      { id: 'data_quality', label: '🔍 Data Quality' },
      { id: 'operations',   label: '⚙️ Operations' },
      { id: 'finance',      label: '💰 Finance' },
      { id: 'user',         label: '📁 My Templates' },
    ];

    this._catLabels = {
      ai_llm:       '🧠 AI / LLM',
      sales:        '📊 Sales',
      marketing:    '📣 Marketing',
      data_quality: '🔍 Data Quality',
      operations:   '⚙️ Operations',
      finance:      '💰 Finance',
      general:      '📦 General',
    };

    this._modalEl = null;
    this._gridEl = null;
  }

  // ─── Public API ────────────────────────────────────────────
  show() {
    if (!this._modalEl) this._buildModal();
    this._modalEl.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    this._load();
    // Auto-focus search
    const si = document.getElementById('tpl-search-input');
    if (si) setTimeout(() => si.focus(), 80);
  }

  hide() {
    if (this._modalEl) this._modalEl.style.display = 'none';
    document.body.style.overflow = '';
  }

  // ─── Build Modal DOM ───────────────────────────────────────
  _buildModal() {
    const modal = document.createElement('div');
    modal.id = 'template-library-modal';
    modal.className = 'app-modal';
    modal.style.display = 'none';
    modal.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="modal-dialog modal-dialog-xl" style="display:flex;flex-direction:column;max-height:90vh;">
        <div class="modal-header" style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--border-subtle);">
          <div class="modal-title-wrap" style="display:flex;align-items:center;gap:10px;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2">
              <rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect>
              <rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect>
            </svg>
            <span style="font-size:15px;font-weight:700;color:var(--text-primary);">Workflow Templates</span>
            <span id="tpl-count-label" class="tpl-count-label"></span>
          </div>
          <button id="tpl-close-btn" class="modal-close-btn" style="background:none;border:none;cursor:pointer;color:var(--text-muted);padding:4px;" aria-label="Close">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>

        <div class="modal-body" style="padding:16px 20px;flex:1;display:flex;flex-direction:column;overflow:hidden;gap:0;">

          <!-- Search toolbar -->
          <div class="tpl-toolbar">
            <div class="tpl-search-wrap">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
              <input id="tpl-search-input" class="tpl-search-input" placeholder="Search templates by name, description or tag…" autocomplete="off" />
            </div>
          </div>

          <!-- Category tabs -->
          <div class="tpl-cat-tabs" id="tpl-cat-tabs"></div>

          <!-- Template grid -->
          <div class="tpl-grid" id="tpl-grid">
            <div class="tpl-empty-state">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
              <span>Loading templates…</span>
            </div>
          </div>
        </div>

        <!-- Footer: Save as template -->
        <div class="modal-footer" style="padding:12px 20px;border-top:1px solid var(--border-subtle);">
          <div class="tpl-save-section">
            <span class="tpl-save-hint">💾 Save the current canvas workflow as a reusable template</span>
            <button id="tpl-btn-save-as" class="btn btn-secondary btn-sm">Save as Template</button>
          </div>
          <div id="tpl-save-form">
            <div class="tpl-save-row">
              <label>Name</label>
              <input id="tpl-save-name" type="text" placeholder="My Custom Template" maxlength="100" />
            </div>
            <div class="tpl-save-row">
              <label>Description</label>
              <input id="tpl-save-desc" type="text" placeholder="What does this workflow do?" maxlength="500" />
            </div>
            <div class="tpl-save-row">
              <label>Category</label>
              <select id="tpl-save-cat">
                <option value="general">General</option>
                <option value="ai_llm">AI / LLM</option>
                <option value="sales">Sales</option>
                <option value="marketing">Marketing</option>
                <option value="data_quality">Data Quality</option>
                <option value="operations">Operations</option>
                <option value="finance">Finance</option>
              </select>
            </div>
            <div class="tpl-save-actions">
              <button id="tpl-btn-save-cancel" class="btn btn-secondary btn-sm">Cancel</button>
              <button id="tpl-btn-save-confirm" class="btn btn-primary btn-sm">Save Template</button>
            </div>
          </div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    this._modalEl = modal;
    this._gridEl = document.getElementById('tpl-grid');

    this._buildCatTabs();
    this._bindEvents();
  }

  _buildCatTabs() {
    const container = document.getElementById('tpl-cat-tabs');
    this._categories.forEach(cat => {
      const btn = document.createElement('button');
      btn.className = 'tpl-cat-btn' + (cat.id === 'all' ? ' active' : '');
      btn.dataset.cat = cat.id;
      btn.textContent = cat.label;
      btn.addEventListener('click', () => this._setCat(cat.id));
      container.appendChild(btn);
    });
  }

  _bindEvents() {
    // Close on backdrop / button
    this._modalEl.querySelector('#tpl-close-btn').addEventListener('click', () => this.hide());
    this._modalEl.querySelector('.modal-backdrop').addEventListener('click', () => this.hide());

    // Keyboard Escape
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._modalEl && this._modalEl.style.display !== 'none') this.hide();
    });

    // Search input
    const searchInput = document.getElementById('tpl-search-input');
    searchInput.addEventListener('input', () => {
      clearTimeout(this._searchTimer);
      this._searchTimer = setTimeout(() => {
        this._searchQuery = searchInput.value.toLowerCase().trim();
        this._applyFilters();
      }, 180);
    });

    // Save as template
    const btnSaveAs = document.getElementById('tpl-btn-save-as');
    const saveForm = document.getElementById('tpl-save-form');
    const btnCancel = document.getElementById('tpl-btn-save-cancel');
    const btnConfirm = document.getElementById('tpl-btn-save-confirm');

    btnSaveAs.addEventListener('click', () => {
      saveForm.classList.toggle('visible');
      btnSaveAs.textContent = saveForm.classList.contains('visible') ? 'Cancel' : 'Save as Template';
      // Pre-fill name from canvas
      const nameInput = document.getElementById('workflow-name-input');
      if (nameInput && nameInput.value && nameInput.value !== 'New Workflow') {
        document.getElementById('tpl-save-name').value = nameInput.value;
      }
    });

    btnCancel.addEventListener('click', () => {
      saveForm.classList.remove('visible');
      btnSaveAs.textContent = 'Save as Template';
    });

    btnConfirm.addEventListener('click', () => this._doSaveTemplate());
  }

  // ─── Load Templates from API ───────────────────────────────
  async _load() {
    try {
      const res = await fetch('/api/templates');
      const data = await res.json();
      this._templates = data.templates || [];
      this._applyFilters();
    } catch (err) {
      this._showError('Failed to load templates. Is the server running?');
    }
  }

  // ─── Filter Logic ──────────────────────────────────────────
  _setCat(catId) {
    this._activeCat = catId;
    document.querySelectorAll('.tpl-cat-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.cat === catId);
    });
    this._applyFilters();
  }

  _applyFilters() {
    let list = this._templates;

    // Category filter
    if (this._activeCat === 'user') {
      list = list.filter(t => t.is_user);
    } else if (this._activeCat !== 'all') {
      list = list.filter(t => t.category === this._activeCat);
    }

    // Search filter
    if (this._searchQuery) {
      const q = this._searchQuery;
      list = list.filter(t =>
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.tags || []).some(tag => tag.toLowerCase().includes(q))
      );
    }

    this._filtered = list;
    this._render();
  }

  // ─── Render Grid ───────────────────────────────────────────
  _render() {
    const grid = this._gridEl;
    grid.innerHTML = '';

    // Update count label
    const countLabel = document.getElementById('tpl-count-label');
    if (countLabel) {
      const total = this._templates.length;
      const shown = this._filtered.length;
      countLabel.textContent = shown === total ? `${total} templates` : `${shown} of ${total}`;
    }

    if (this._filtered.length === 0) {
      grid.innerHTML = `
        <div class="tpl-empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <span>No templates match your search.</span>
        </div>`;
      return;
    }

    // Curated first, then user
    const curated = this._filtered.filter(t => !t.is_user);
    const user = this._filtered.filter(t => t.is_user);

    if (curated.length > 0) curated.forEach(t => grid.appendChild(this._buildCard(t)));

    if (user.length > 0) {
      const divider = document.createElement('div');
      divider.style.cssText = 'grid-column:1/-1;font-size:11px;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.08em;padding-top:8px;border-top:1px solid var(--border-subtle);margin-top:4px;';
      divider.textContent = '📁 My Templates';
      grid.appendChild(divider);
      user.forEach(t => grid.appendChild(this._buildCard(t)));
    }
  }

  _buildCard(tpl) {
    const catLabel = this._catLabels[tpl.category] || tpl.category;
    const diffClass = `tpl-difficulty-${tpl.difficulty || 'beginner'}`;
    const diffLabel = (tpl.difficulty || 'beginner').charAt(0).toUpperCase() + (tpl.difficulty || 'beginner').slice(1);
    const nodeChips = (tpl.nodes_preview || [])
      .map(n => `<span class="tpl-node-chip">${this._esc(n)}</span>`).join('');

    const card = document.createElement('div');
    card.className = 'tpl-card';
    card.dataset.cat = tpl.category || 'general';
    card.dataset.user = tpl.is_user ? 'true' : 'false';
    card.dataset.file = tpl.file;
    card.innerHTML = `
      <div class="tpl-card-header">
        <div class="tpl-card-title">${this._esc(tpl.name)}</div>
        <span class="tpl-card-badge tpl-badge-${tpl.category || 'general'}">${catLabel}</span>
      </div>
      <div class="tpl-card-desc">${this._esc(tpl.description || '')}</div>
      ${nodeChips ? `<div class="tpl-nodes-strip">${nodeChips}</div>` : ''}
      <div class="tpl-card-footer">
        <div class="tpl-card-meta">
          <span>
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
            ${tpl.node_count} nodes
          </span>
          <span class="tpl-difficulty ${diffClass}">${diffLabel}</span>
        </div>
        <div style="display:flex;gap:5px;align-items:center;">
          <button class="btn-delete-template" data-file="${this._esc(tpl.file)}" title="Delete this template" aria-label="Delete">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6l-1 14H6L5 6"></path></svg>
            Delete
          </button>
          <button class="btn-use-template" data-file="${this._esc(tpl.file)}" data-name="${this._esc(tpl.name)}">Use this ▸</button>
        </div>
      </div>
    `;

    // Bind "Use this" button
    card.querySelector('.btn-use-template').addEventListener('click', (e) => {
      e.stopPropagation();
      this._loadTemplate(tpl.file, tpl.name);
    });

    // Bind delete button
    const delBtn = card.querySelector('.btn-delete-template');
    if (delBtn) {
      delBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._deleteTemplate(tpl.file, tpl.name, card);
      });
    }

    // Card click also loads (click anywhere)
    card.addEventListener('click', (e) => {
      if (e.target.closest('.btn-use-template') || e.target.closest('.btn-delete-template')) return;
      this._loadTemplate(tpl.file, tpl.name);
    });

    return card;
  }

  // ─── Load Template onto Canvas ─────────────────────────────
  async _loadTemplate(filename, templateName) {
    try {
      const res = await fetch(`/api/templates/${encodeURIComponent(filename)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      // Use the app's existing workflow loader
      if (typeof handleWorkflowLoaded === 'function') {
        handleWorkflowLoaded(data, templateName || data.name || filename);
      } else if (window.appCanvas) {
        window.appCanvas.loadWorkflow(data);
        const nameInput = document.getElementById('workflow-name-input');
        if (nameInput) nameInput.value = templateName || data.name || 'Workflow';
      }

      this.hide();

      if (typeof showToast === 'function') {
        showToast('success', 'Template Loaded', `"${templateName}" is ready on the canvas.`);
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast('error', 'Load Failed', err.message || 'Could not load template.');
      } else {
        alert('Failed to load template: ' + err.message);
      }
    }
  }

  // ─── Delete User Template ──────────────────────────────────
  async _deleteTemplate(filename, name, cardEl) {
    if (!confirm(`Delete the template "${name}"? This cannot be undone.`)) return;
    try {
      const res = await fetch(`/api/templates/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Delete failed');

      // Remove from local list and re-render
      this._templates = this._templates.filter(t => t.file !== filename);
      cardEl.style.transition = 'opacity 0.2s, transform 0.2s';
      cardEl.style.opacity = '0';
      cardEl.style.transform = 'scale(0.95)';
      setTimeout(() => this._applyFilters(), 220);

      if (typeof showToast === 'function') {
        showToast('info', 'Template Deleted', `"${name}" has been removed.`);
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast('error', 'Delete Failed', err.message);
      }
    }
  }

  // ─── Save Current Workflow as Template ────────────────────
  async _doSaveTemplate() {
    const name = document.getElementById('tpl-save-name').value.trim();
    const desc = document.getElementById('tpl-save-desc').value.trim();
    const cat  = document.getElementById('tpl-save-cat').value;

    if (!name) {
      document.getElementById('tpl-save-name').focus();
      return;
    }

    // Get current canvas workflow data
    let workflow = {};
    if (window.appCanvas && typeof window.appCanvas.getWorkflowData === 'function') {
      workflow = window.appCanvas.getWorkflowData();
    }

    if (!workflow.nodes || workflow.nodes.length === 0) {
      if (typeof showToast === 'function') {
        showToast('warning', 'Empty Canvas', 'Add at least one tool to the canvas before saving as a template.');
      }
      return;
    }

    const btn = document.getElementById('tpl-btn-save-confirm');
    btn.disabled = true;
    btn.textContent = 'Saving…';

    try {
      const res = await fetch('/api/templates/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: desc, category: cat, tags: [], workflow })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Save failed');

      // Clear form & hide
      document.getElementById('tpl-save-name').value = '';
      document.getElementById('tpl-save-desc').value = '';
      document.getElementById('tpl-save-form').classList.remove('visible');
      document.getElementById('tpl-btn-save-as').textContent = 'Save as Template';

      // Reload templates and switch to My Templates tab
      await this._load();
      this._setCat('user');

      if (typeof showToast === 'function') {
        showToast('success', 'Template Saved', `"${name}" has been added to My Templates.`);
      }
    } catch (err) {
      if (typeof showToast === 'function') {
        showToast('error', 'Save Failed', err.message);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save Template';
    }
  }

  // ─── Error state ───────────────────────────────────────────
  _showError(msg) {
    if (this._gridEl) {
      this._gridEl.innerHTML = `
        <div class="tpl-empty-state">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="1.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <span style="color:var(--text-secondary)">${this._esc(msg)}</span>
        </div>`;
    }
  }

  _esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
}
