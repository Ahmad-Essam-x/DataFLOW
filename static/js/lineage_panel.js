/**
 * Column-Level Lineage Side Drawer with Canvas X-Ray.
 * Simplified: flat column list → expand for step chain. No subtabs, no origins card.
 */
class LineagePanel {
  constructor() {
    this._drawerEl = null;
    this._isOpen = false;
    this._currentNodeId = null;
    this._currentNodeName = null;
    this._workflow = null;
    this._direction = 'upstream';
    this._activeFilter = 'all';
    this._searchQuery = '';
    this._lockedHighlightCol = null;
    this._dataCache = { upstream: null, downstream: null };
    this._initDOM();
  }

  _initDOM() {
    if (document.getElementById('lineage-drawer')) {
      this._drawerEl = document.getElementById('lineage-drawer');
      return;
    }
    const drawer = document.createElement('div');
    drawer.id = 'lineage-drawer';
    drawer.className = 'lineage-drawer hidden';
    drawer.innerHTML = `
      <div class="lineage-drawer-header">
        <div class="lineage-title-row">
          <span class="lineage-title">Column Lineage</span>
          <span class="lineage-node-tag" id="lineage-node-tag"></span>
        </div>
        <button class="lineage-close-btn" id="btn-close-lineage" title="Close (Esc)">✕</button>
      </div>

      <div class="lineage-mode-tabs">
        <button class="lineage-mode-tab active" id="tab-mode-upstream" data-mode="upstream">↑ Upstream</button>
        <button class="lineage-mode-tab" id="tab-mode-downstream" data-mode="downstream">↓ Downstream</button>
      </div>

      <div class="lineage-toolbar">
        <div class="lineage-search-box">
          <span class="lineage-search-icon">🔍</span>
          <input type="text" class="lineage-search-input" id="lineage-search-input" placeholder="Filter columns…" autocomplete="off">
          <button class="lineage-search-clear" id="lineage-search-clear" style="display:none;" title="Clear">✕</button>
        </div>
        <div class="lineage-filter-pills" id="lineage-filter-pills">
          <button class="lineage-pill active" data-filter="all">All <span id="cnt-pill-all"></span></button>
          <button class="lineage-pill" data-filter="calculated">Calc <span id="cnt-pill-calc"></span></button>
          <button class="lineage-pill" data-filter="renamed">Renamed <span id="cnt-pill-rename"></span></button>
          <button class="lineage-pill" data-filter="joined">Joined <span id="cnt-pill-join"></span></button>
          <button class="lineage-pill" data-filter="passthrough">Pass <span id="cnt-pill-pass"></span></button>
        </div>
      </div>

      <div class="lineage-body" id="lineage-body">
        <div class="lineage-placeholder">Select a tool and open Column Lineage to trace dependencies.</div>
      </div>
    `;
    document.body.appendChild(drawer);
    this._drawerEl = drawer;

    drawer.querySelector('#btn-close-lineage')?.addEventListener('click', () => this.hide());
    drawer.querySelector('#tab-mode-upstream')?.addEventListener('click', () => this._switchMode('upstream'));
    drawer.querySelector('#tab-mode-downstream')?.addEventListener('click', () => this._switchMode('downstream'));

    const searchInput = drawer.querySelector('#lineage-search-input');
    const searchClear = drawer.querySelector('#lineage-search-clear');
    searchInput?.addEventListener('input', (e) => {
      this._searchQuery = (e.target.value || '').trim().toLowerCase();
      if (searchClear) searchClear.style.display = this._searchQuery ? 'block' : 'none';
      this._renderCurrentView();
    });
    searchClear?.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      this._searchQuery = '';
      searchClear.style.display = 'none';
      this._renderCurrentView();
    });

    drawer.querySelectorAll('.lineage-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        drawer.querySelectorAll('.lineage-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        this._activeFilter = pill.getAttribute('data-filter') || 'all';
        this._renderCurrentView();
      });
    });

    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._isOpen) this.hide();
    });
  }

  async showForNode(nodeId, nodeName, workflow, initialColumn = null) {
    if (!this._drawerEl) this._initDOM();
    this._isOpen = true;
    this._currentNodeId = nodeId;
    this._currentNodeName = nodeName || nodeId;
    this._workflow = workflow || (window.appCanvas ? window.appCanvas.getWorkflowData() : { nodes: [], connections: [] });
    this._dataCache = { upstream: null, downstream: null };
    this._lockedHighlightCol = null;

    if (initialColumn) {
      this._searchQuery = initialColumn.trim().toLowerCase();
      const sInput = this._drawerEl.querySelector('#lineage-search-input');
      const sClear = this._drawerEl.querySelector('#lineage-search-clear');
      if (sInput) sInput.value = initialColumn;
      if (sClear) sClear.style.display = 'block';
    }

    this._drawerEl.classList.remove('hidden');
    const nodeTag = document.getElementById('lineage-node-tag');
    if (nodeTag) { nodeTag.textContent = this._currentNodeName; nodeTag.title = `Node ID: ${nodeId}`; }
    await this._loadData();
  }

  hide() {
    this._isOpen = false;
    this._lockedHighlightCol = null;
    this._drawerEl?.classList.add('hidden');
    window.appCanvas?.clearLineageHighlight?.();
  }

  _switchMode(mode) {
    if (this._direction === mode) return;
    this._direction = mode;
    this._lockedHighlightCol = null;
    window.appCanvas?.clearLineageHighlight?.();
    this._drawerEl.querySelectorAll('.lineage-mode-tab').forEach(t =>
      t.classList.toggle('active', t.getAttribute('data-mode') === mode)
    );
    const pillsRow = this._drawerEl.querySelector('#lineage-filter-pills');
    if (pillsRow) pillsRow.style.display = mode === 'upstream' ? 'flex' : 'none';
    this._loadData();
  }

  async _loadData() {
    const bodyEl = document.getElementById('lineage-body');
    if (this._dataCache[this._direction]) { this._renderCurrentView(); return; }
    if (bodyEl) bodyEl.innerHTML = `<div class="lineage-loading"><div class="lineage-spinner"></div><span>Analyzing…</span></div>`;
    try {
      const resp = await fetch('/api/workflow/lineage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow: this._workflow, node_id: this._currentNodeId, direction: this._direction })
      });
      const data = await resp.json();
      if (!data.success) throw new Error(data.error || 'Failed to analyze lineage');
      this._dataCache[this._direction] = data;
      this._updatePillCounts(data);
      this._renderCurrentView();
    } catch (err) {
      if (bodyEl) bodyEl.innerHTML = `<div class="lineage-error">⚠ ${this._esc(err.message)}</div>`;
    }
  }

  _updatePillCounts(data) {
    if (this._direction !== 'upstream') return;
    const rich = data.rich_lineage || {};
    const cols = Object.keys(rich);
    let calc = 0, ren = 0, join = 0, pass = 0;
    cols.forEach(c => {
      const cat = (rich[c].category || 'passthrough').toLowerCase();
      if (cat === 'calculated') calc++;
      else if (cat === 'renamed') ren++;
      else if (cat === 'joined') join++;
      else pass++;
    });
    const s = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v ? `(${v})` : ''; };
    s('cnt-pill-all', cols.length); s('cnt-pill-calc', calc);
    s('cnt-pill-rename', ren); s('cnt-pill-join', join); s('cnt-pill-pass', pass);
  }

  _renderCurrentView() {
    const data = this._dataCache[this._direction];
    if (!data) return;
    this._direction === 'upstream' ? this._renderUpstream(data) : this._renderDownstream(data);
  }

  // ── Category icon helpers ──────────────────────────────────────────────────
  _catIcon(cat) {
    return { calculated: '✦', renamed: '↩', joined: '⊕', origin: '●', passthrough: '→' }[cat] || '→';
  }
  _actionIcon(action) {
    const a = (action || '').toLowerCase();
    if (a.includes('origin')) return '●';
    if (a.includes('calculat') || a.includes('formula')) return '✦';
    if (a.includes('aggregate') || a.includes('sum') || a.includes('avg') || a.includes('count')) return '∑';
    if (a.includes('renam')) return '↩';
    if (a.includes('join')) return '⊕';
    return '→';
  }

  // ── Upstream ───────────────────────────────────────────────────────────────
  _renderUpstream(data) {
    const bodyEl = document.getElementById('lineage-body');
    if (!bodyEl) return;
    const rich = data.rich_lineage || {};
    let cols = Object.keys(rich);

    if (this._activeFilter !== 'all') {
      cols = cols.filter(c => {
        const cat = (rich[c].category || 'passthrough').toLowerCase();
        if (this._activeFilter === 'passthrough') return cat === 'passthrough' || cat === 'origin';
        return cat === this._activeFilter;
      });
    }
    if (this._searchQuery) cols = cols.filter(c => c.toLowerCase().includes(this._searchQuery));

    if (cols.length === 0) {
      bodyEl.innerHTML = `<div class="lineage-empty">No columns match.</div>`;
      return;
    }

    let html = '';
    cols.forEach(col => {
      const info = rich[col] || {};
      const cat = info.category || 'passthrough';
      const hops = info.hops || [];
      const ancestors = info.ancestor_node_ids || [];
      const rootOrigins = info.root_origins || [];

      // Build a concise origin label for the collapsed row
      let originLabel = '';
      if (cat === 'origin') {
        originLabel = 'Raw source';
      } else if (rootOrigins.length === 1) {
        const ro = rootOrigins[0];
        const srcCol = (ro.columns || [])[0] || '';
        originLabel = srcCol ? `${ro.node_name} · ${srcCol}` : ro.node_name;
      } else if (rootOrigins.length > 1) {
        originLabel = `${rootOrigins.length} sources`;
      } else if (hops.length > 0) {
        originLabel = hops[0].node_name || '';
      }

      const isAutoExpanded = (cols.length === 1) || (this._searchQuery && col.toLowerCase() === this._searchQuery);

      // Step chain — inline, no subtabs
      const stepsHtml = hops.map(hop => {
        const icon = this._actionIcon(hop.action);
        const detail = hop.detail && hop.detail !== col
          ? `<span class="ls-detail">${this._fmtExpr(hop.detail)}</span>`
          : '';
        return `<div class="ls-step">
          <span class="ls-step-icon">${icon}</span>
          <span class="ls-step-tool">${this._esc(hop.node_name || hop.node_id)}</span>
          <span class="ls-step-action">${this._esc(hop.action || '')}</span>
          ${detail}
        </div>`;
      }).join('');

      html += `
        <div class="lineage-card${isAutoExpanded ? ' expanded' : ''}"
             data-col="${this._esc(col)}"
             data-ancestors='${JSON.stringify(ancestors)}'>
          <div class="lineage-card-header">
            <span class="lc-cat lc-cat-${cat}" title="${cat}">${this._catIcon(cat)}</span>
            <span class="lc-col" title="${this._esc(col)}">${this._esc(col)}</span>
            ${originLabel ? `<span class="lc-origin">← ${this._esc(originLabel)}</span>` : ''}
            <span class="lc-chevron">${isAutoExpanded ? '▾' : '▸'}</span>
          </div>
          <div class="lineage-steps">${stepsHtml || '<span class="ls-empty">No path data.</span>'}</div>
        </div>`;
    });

    bodyEl.innerHTML = html;
    this._bindCards(bodyEl);
    this._autoHighlight(bodyEl, cols);
  }

  // ── Downstream ─────────────────────────────────────────────────────────────
  _renderDownstream(data) {
    const bodyEl = document.getElementById('lineage-body');
    if (!bodyEl) return;
    const columnsMap = data.columns || {};
    let cols = Object.keys(columnsMap);
    if (this._searchQuery) cols = cols.filter(c => c.toLowerCase().includes(this._searchQuery));

    if (cols.length === 0) {
      bodyEl.innerHTML = `<div class="lineage-empty">No downstream dependents.</div>`;
      return;
    }

    let html = '';
    cols.forEach(col => {
      const usages = columnsMap[col] || [];
      const targetNodeIds = usages.map(u => u.node_id);
      const isAutoExpanded = (cols.length === 1) || (this._searchQuery && col.toLowerCase() === this._searchQuery);
      const summary = usages.length ? `${usages.length} tool${usages.length > 1 ? 's' : ''}` : 'unused';

      const usageHtml = usages.map(u =>
        `<div class="ls-step">
          <span class="ls-step-icon">⊕</span>
          <span class="ls-step-tool">${this._esc(u.node_name)}</span>
          <span class="ls-step-action">${this._esc(u.usage)}</span>
          ${u.detail ? `<span class="ls-detail">${this._fmtExpr(u.detail)}</span>` : ''}
        </div>`
      ).join('') || '<span class="ls-empty">No active downstream usage.</span>';

      html += `
        <div class="lineage-card${isAutoExpanded ? ' expanded' : ''}"
             data-col="${this._esc(col)}"
             data-ancestors='${JSON.stringify(targetNodeIds)}'>
          <div class="lineage-card-header">
            <span class="lc-cat lc-cat-passthrough">→</span>
            <span class="lc-col">${this._esc(col)}</span>
            <span class="lc-origin">${summary}</span>
            <span class="lc-chevron">${isAutoExpanded ? '▾' : '▸'}</span>
          </div>
          <div class="lineage-steps">${usageHtml}</div>
        </div>`;
    });

    bodyEl.innerHTML = html;
    this._bindCards(bodyEl);
    this._autoHighlight(bodyEl, cols);
  }

  // ── Shared helpers ─────────────────────────────────────────────────────────
  _bindCards(container) {
    container.querySelectorAll('.lineage-card').forEach(card => {
      const colName = card.getAttribute('data-col');
      let nodeIds = [];
      try { nodeIds = JSON.parse(card.getAttribute('data-ancestors') || '[]'); } catch (e) {}
      if (this._currentNodeId && !nodeIds.includes(this._currentNodeId)) nodeIds.push(this._currentNodeId);

      card.addEventListener('mouseenter', () => {
        if (!this._lockedHighlightCol) window.appCanvas?.highlightLineagePath?.(nodeIds);
      });
      card.addEventListener('mouseleave', () => {
        if (!this._lockedHighlightCol) window.appCanvas?.clearLineageHighlight?.();
      });

      const header = card.querySelector('.lineage-card-header');
      header?.addEventListener('click', () => {
        const opening = !card.classList.contains('expanded');
        container.querySelectorAll('.lineage-card').forEach(c => {
          c.classList.remove('expanded');
          const chev = c.querySelector('.lc-chevron');
          if (chev) chev.textContent = '▸';
        });
        if (opening) {
          card.classList.add('expanded');
          const chev = card.querySelector('.lc-chevron');
          if (chev) chev.textContent = '▾';
          this._lockedHighlightCol = colName;
          window.appCanvas?.highlightLineagePath?.(nodeIds);
        } else {
          this._lockedHighlightCol = null;
          window.appCanvas?.clearLineageHighlight?.();
        }
      });
    });
  }

  _autoHighlight(container, cols) {
    const matchCard = container.querySelector('.lineage-card.expanded') || container.querySelector('.lineage-card');
    if (matchCard && window.appCanvas && (cols.length === 1 || this._searchQuery)) {
      try {
        const nodeIds = JSON.parse(matchCard.getAttribute('data-ancestors') || '[]');
        if (this._currentNodeId && !nodeIds.includes(this._currentNodeId)) nodeIds.push(this._currentNodeId);
        this._lockedHighlightCol = matchCard.getAttribute('data-col');
        window.appCanvas.highlightLineagePath(nodeIds);
      } catch (e) {}
    }
  }

  _fmtExpr(text) {
    if (!text) return '';
    return this._esc(text).replace(/\[([^\]]+)\]/g, (_, c) =>
      `<span class="lineage-token-col">[${c}]</span>`
    );
  }

  _esc(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}

window.appLineagePanel = new LineagePanel();
