/**
 * Interactive Column-Level Lineage & Downstream Impact Side Drawer with Canvas X-Ray.
 * Displays upstream provenance and downstream impact analysis with live canvas path glow.
 */
class LineagePanel {
  constructor() {
    this._drawerEl = null;
    this._isOpen = false;
    this._currentNodeId = null;
    this._currentNodeName = null;
    this._workflow = null;
    this._direction = 'upstream'; // 'upstream' | 'downstream'
    this._activeFilter = 'all'; // 'all' | 'calculated' | 'renamed' | 'joined' | 'passthrough'
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
          <span class="lineage-icon">🔗</span>
          <span class="lineage-title">Column Lineage & Impact</span>
          <span class="lineage-node-tag" id="lineage-node-tag"></span>
        </div>
        <button class="lineage-close-btn" id="btn-close-lineage" title="Close Panel (Esc)">✕</button>
      </div>

      <div class="lineage-mode-tabs">
        <button class="lineage-mode-tab active" id="tab-mode-upstream" data-mode="upstream">
          ⬅ Upstream Provenance
        </button>
        <button class="lineage-mode-tab" id="tab-mode-downstream" data-mode="downstream">
          ➡ Downstream Impact
        </button>
      </div>

      <div class="lineage-toolbar">
        <div class="lineage-search-box">
          <span class="lineage-search-icon">🔍</span>
          <input type="text" class="lineage-search-input" id="lineage-search-input" placeholder="Search columns in this tool..." autocomplete="off">
          <button class="lineage-search-clear" id="lineage-search-clear" style="display:none;" title="Clear search">✕</button>
        </div>

        <div class="lineage-filter-pills" id="lineage-filter-pills">
          <button class="lineage-pill active" data-filter="all">All <span id="cnt-pill-all">(0)</span></button>
          <button class="lineage-pill" data-filter="calculated">✨ Calculated <span id="cnt-pill-calc">(0)</span></button>
          <button class="lineage-pill" data-filter="renamed">🏷️ Renamed <span id="cnt-pill-rename">(0)</span></button>
          <button class="lineage-pill" data-filter="joined">🔀 Joined <span id="cnt-pill-join">(0)</span></button>
          <button class="lineage-pill" data-filter="passthrough">➡️ Passthrough <span id="cnt-pill-pass">(0)</span></button>
        </div>
      </div>

      <div class="lineage-meta-hint" id="lineage-meta-hint">
        <span>Hover or click a column to light up its path on the canvas</span>
        <span><kbd>Esc</kbd> to close</span>
      </div>

      <div class="lineage-body" id="lineage-body">
        <div class="lineage-placeholder">Select a tool and click "Show Column Lineage" to trace dependencies.</div>
      </div>
    `;

    document.body.appendChild(drawer);
    this._drawerEl = drawer;

    // Close button
    drawer.querySelector('#btn-close-lineage')?.addEventListener('click', () => this.hide());

    // Mode tabs
    drawer.querySelector('#tab-mode-upstream')?.addEventListener('click', () => this._switchMode('upstream'));
    drawer.querySelector('#tab-mode-downstream')?.addEventListener('click', () => this._switchMode('downstream'));

    // Search input
    const searchInput = drawer.querySelector('#lineage-search-input');
    const searchClear = drawer.querySelector('#lineage-search-clear');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this._searchQuery = (e.target.value || '').trim().toLowerCase();
        if (searchClear) searchClear.style.display = this._searchQuery ? 'block' : 'none';
        this._renderCurrentView();
      });
    }
    if (searchClear) {
      searchClear.addEventListener('click', () => {
        if (searchInput) searchInput.value = '';
        this._searchQuery = '';
        searchClear.style.display = 'none';
        this._renderCurrentView();
      });
    }

    // Filter pills
    drawer.querySelectorAll('.lineage-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        drawer.querySelectorAll('.lineage-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        this._activeFilter = pill.getAttribute('data-filter') || 'all';
        this._renderCurrentView();
      });
    });

    // Close on Escape key
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && this._isOpen) {
        this.hide();
      }
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
    if (nodeTag) {
      nodeTag.textContent = this._currentNodeName;
      nodeTag.title = `Node ID: ${nodeId}`;
    }

    await this._loadData();
  }

  hide() {
    this._isOpen = false;
    this._lockedHighlightCol = null;
    if (this._drawerEl) {
      this._drawerEl.classList.add('hidden');
    }
    if (window.appCanvas && typeof window.appCanvas.clearLineageHighlight === 'function') {
      window.appCanvas.clearLineageHighlight();
    }
  }

  _switchMode(mode) {
    if (this._direction === mode) return;
    this._direction = mode;
    this._lockedHighlightCol = null;
    if (window.appCanvas) window.appCanvas.clearLineageHighlight();

    this._drawerEl.querySelectorAll('.lineage-mode-tab').forEach(t => {
      t.classList.toggle('active', t.getAttribute('data-mode') === mode);
    });

    // Hide category pills in downstream mode (since they apply to incoming classifications)
    const pillsRow = this._drawerEl.querySelector('#lineage-filter-pills');
    if (pillsRow) {
      pillsRow.style.display = mode === 'upstream' ? 'flex' : 'none';
    }

    const hintEl = this._drawerEl.querySelector('#lineage-meta-hint');
    if (hintEl) {
      hintEl.querySelector('span:first-child').textContent = mode === 'upstream'
        ? 'Hover or click a column to light up its upstream path on canvas'
        : 'Hover or click a column to light up downstream consumers on canvas';
    }

    this._loadData();
  }

  async _loadData() {
    const bodyEl = document.getElementById('lineage-body');
    if (this._dataCache[this._direction]) {
      this._renderCurrentView();
      return;
    }

    if (bodyEl) {
      bodyEl.innerHTML = `
        <div class="lineage-loading">
          <div style="width: 22px; height: 22px; border: 2.5px solid var(--border-subtle); border-top-color: var(--accent-primary); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: 10px;"></div>
          <span>${this._direction === 'upstream' ? 'Tracing upstream column origins across DAG...' : 'Analyzing downstream impact across workflow...'}</span>
        </div>
      `;
    }

    try {
      const resp = await fetch('/api/workflow/lineage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow: this._workflow,
          node_id: this._currentNodeId,
          direction: this._direction
        })
      });

      const data = await resp.json();
      if (!data.success) {
        throw new Error(data.error || 'Failed to analyze lineage');
      }

      this._dataCache[this._direction] = data;
      this._updateFilterPillCounts(data);
      this._renderCurrentView();
    } catch (err) {
      if (bodyEl) {
        bodyEl.innerHTML = `
          <div class="lineage-error" style="padding: 24px 16px; color: var(--color-error, #f87171); text-align: center;">
            <div style="font-size: 20px; margin-bottom: 6px;">⚠</div>
            <div style="font-weight: 600;">Error analyzing column lineage</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">${this._escape(err.message)}</div>
          </div>
        `;
      }
    }
  }

  _updateFilterPillCounts(data) {
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

    const setTxt = (id, txt) => {
      const el = document.getElementById(id);
      if (el) el.textContent = txt;
    };
    setTxt('cnt-pill-all', `(${cols.length})`);
    setTxt('cnt-pill-calc', `(${calc})`);
    setTxt('cnt-pill-rename', `(${ren})`);
    setTxt('cnt-pill-join', `(${join})`);
    setTxt('cnt-pill-pass', `(${pass})`);
  }

  _renderCurrentView() {
    const data = this._dataCache[this._direction];
    if (!data) return;

    if (this._direction === 'upstream') {
      this._renderUpstream(data);
    } else {
      this._renderDownstream(data);
    }
  }

  _renderUpstream(data) {
    const bodyEl = document.getElementById('lineage-body');
    if (!bodyEl) return;

    const rich = data.rich_lineage || {};
    let cols = Object.keys(rich);

    // Apply category filter
    if (this._activeFilter !== 'all') {
      cols = cols.filter(c => {
        const cat = (rich[c].category || 'passthrough').toLowerCase();
        if (this._activeFilter === 'calculated') return cat === 'calculated';
        if (this._activeFilter === 'renamed') return cat === 'renamed';
        if (this._activeFilter === 'joined') return cat === 'joined';
        if (this._activeFilter === 'passthrough') return cat === 'passthrough' || cat === 'origin';
        return true;
      });
    }

    // Apply text search
    if (this._searchQuery) {
      cols = cols.filter(c => c.toLowerCase().includes(this._searchQuery));
    }

    if (cols.length === 0) {
      bodyEl.innerHTML = `
        <div class="lineage-empty">
          <div style="font-size: 26px; margin-bottom: 8px;">🔍</div>
          <div style="font-weight: 500;">No columns match filter</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">Try searching for another field or clearing filters.</div>
        </div>
      `;
      return;
    }

    let html = '';
    cols.forEach(col => {
      const info = rich[col] || {};
      const cat = info.category || 'passthrough';
      const hops = info.hops || [];
      const ancestors = info.ancestor_node_ids || [];

      let originText = 'Unknown Origin';
      if (hops.length > 0) {
        const rootHop = hops[0];
        originText = `${rootHop.node_name}: ${rootHop.column || col}`;
      }

      const catBadgeClass = `lineage-cat-${cat}`;
      const catLabel = cat.charAt(0).toUpperCase() + cat.slice(1);

      const isInitialMatch = this._searchQuery && col.toLowerCase() === this._searchQuery;
      const isAutoExpanded = isInitialMatch || cols.length === 1;

      html += `
        <div class="lineage-card ${isAutoExpanded ? 'expanded highlighted' : ''}" data-col="${this._escape(col)}" data-ancestors='${JSON.stringify(ancestors)}'>
          <div class="lineage-card-header">
            <div class="lineage-card-left">
              <span class="lineage-category-tag ${catBadgeClass}">${catLabel}</span>
              <span class="lineage-col-name" title="${this._escape(col)}">${this._escape(col)}</span>
            </div>
            <div class="lineage-card-right">
              <span class="lineage-origin-summary" title="${this._escape(originText)}">← ${this._escape(originText)}</span>
              <span class="lineage-card-chevron">▼</span>
            </div>
          </div>

          <div class="lineage-card-steps">
            <div class="lineage-step-list">
              ${hops.map((hop, hIdx) => {
                const isFirst = hIdx === 0;
                const isLast = hIdx === hops.length - 1;
                let stepClass = 'lineage-step-pass';
                if (isFirst) stepClass = 'lineage-step-origin';
                else if (hop.action && hop.action.toLowerCase().includes('calculat')) stepClass = 'lineage-step-calc';
                else if (hop.action && hop.action.toLowerCase().includes('rename')) stepClass = 'lineage-step-rename';

                return `
                  <div class="lineage-step-item ${stepClass}">
                    <div class="lineage-step-dot"></div>
                    <div class="lineage-step-header">
                      <span class="lineage-step-tool">${isFirst ? '🌱 ' : (isLast ? '🎯 ' : '⚙️ ')}${this._escape(hop.node_name || hop.node_id)}</span>
                      <span class="lineage-step-action">${this._escape(hop.action || 'Hop')}</span>
                    </div>
                    <div class="lineage-step-detail">${this._escape(hop.detail || hop.column || '')}</div>
                  </div>
                `;
              }).join('')}
            </div>
          </div>
        </div>
      `;
    });

    bodyEl.innerHTML = html;
    this._bindCardInteractions(bodyEl);

    if (cols.length === 1 || (this._searchQuery && cols.some(c => c.toLowerCase() === this._searchQuery))) {
      const matchCard = bodyEl.querySelector('.lineage-card.highlighted') || bodyEl.querySelector('.lineage-card');
      if (matchCard && window.appCanvas) {
        const colName = matchCard.getAttribute('data-col');
        try {
          const nodeIds = JSON.parse(matchCard.getAttribute('data-ancestors') || '[]');
          if (this._currentNodeId && !nodeIds.includes(this._currentNodeId)) nodeIds.push(this._currentNodeId);
          this._lockedHighlightCol = colName;
          window.appCanvas.highlightLineagePath(nodeIds);
        } catch (e) {}
      }
    }
  }

  _renderDownstream(data) {
    const bodyEl = document.getElementById('lineage-body');
    if (!bodyEl) return;

    const columnsMap = data.columns || {};
    let cols = Object.keys(columnsMap);

    if (this._searchQuery) {
      cols = cols.filter(c => c.toLowerCase().includes(this._searchQuery));
    }

    if (cols.length === 0) {
      bodyEl.innerHTML = `
        <div class="lineage-empty">
          <div style="font-size: 26px; margin-bottom: 8px;">🌱</div>
          <div style="font-weight: 500;">No downstream dependents</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
            This tool is an endpoint or downstream nodes do not reference its columns.
          </div>
        </div>
      `;
      return;
    }

    let html = '';
    cols.forEach(col => {
      const usages = columnsMap[col] || [];
      const targetNodeIds = usages.map(u => u.node_id);
      const isInitialMatch = this._searchQuery && col.toLowerCase() === this._searchQuery;
      const isAutoExpanded = isInitialMatch || cols.length === 1;

      html += `
        <div class="lineage-card ${isAutoExpanded ? 'expanded highlighted' : ''}" data-col="${this._escape(col)}" data-ancestors='${JSON.stringify(targetNodeIds)}'>
          <div class="lineage-card-header">
            <div class="lineage-card-left">
              <span class="lineage-col-name">${this._escape(col)}</span>
            </div>
            <div class="lineage-card-right">
              <span class="lineage-origin-summary">${usages.length} dependent tool(s)</span>
              <span class="lineage-card-chevron">▼</span>
            </div>
          </div>

          <div class="lineage-card-steps">
            ${usages.length === 0 ? `
              <div style="font-size: 11px; color: var(--text-muted); padding: 4px 0;">No active downstream filters or formulas depend on this column.</div>
            ` : `
              <div style="display:flex; flex-direction:column; gap:6px; margin-top:4px;">
                ${usages.map(u => `
                  <div class="lineage-impact-card" data-nid="${this._escape(u.node_id)}">
                    <div class="lineage-impact-header">
                      <span class="lineage-impact-target">⚡ ${this._escape(u.node_name)}</span>
                      <span class="lineage-impact-badge">${this._escape(u.usage)}</span>
                    </div>
                    <div class="lineage-impact-detail">${this._escape(u.detail)}</div>
                  </div>
                `).join('')}
              </div>
            `}
          </div>
        </div>
      `;
    });

    bodyEl.innerHTML = html;
    this._bindCardInteractions(bodyEl);

    if (cols.length === 1 || (this._searchQuery && cols.some(c => c.toLowerCase() === this._searchQuery))) {
      const matchCard = bodyEl.querySelector('.lineage-card.highlighted') || bodyEl.querySelector('.lineage-card');
      if (matchCard && window.appCanvas) {
        const colName = matchCard.getAttribute('data-col');
        try {
          const nodeIds = JSON.parse(matchCard.getAttribute('data-ancestors') || '[]');
          if (this._currentNodeId && !nodeIds.includes(this._currentNodeId)) nodeIds.push(this._currentNodeId);
          this._lockedHighlightCol = colName;
          window.appCanvas.highlightLineagePath(nodeIds);
        } catch (e) {}
      }
    }
  }

  _bindCardInteractions(container) {
    const cards = container.querySelectorAll('.lineage-card');
    cards.forEach(card => {
      const colName = card.getAttribute('data-col');
      let nodeIds = [];
      try {
        nodeIds = JSON.parse(card.getAttribute('data-ancestors') || '[]');
      } catch (e) {
        nodeIds = [];
      }

      // Always include current node in the highlight set
      if (this._currentNodeId && !nodeIds.includes(this._currentNodeId)) {
        nodeIds.push(this._currentNodeId);
      }

      // Hover: Light up path on canvas (X-Ray glow)
      card.addEventListener('mouseenter', () => {
        if (!this._lockedHighlightCol && window.appCanvas) {
          window.appCanvas.highlightLineagePath(nodeIds);
        }
      });

      card.addEventListener('mouseleave', () => {
        if (!this._lockedHighlightCol && window.appCanvas) {
          window.appCanvas.clearLineageHighlight();
        }
      });

      // Click: Toggle accordion step details and lock highlight
      card.addEventListener('click', (e) => {
        const isCurrentlyExpanded = card.classList.contains('expanded');

        // Close other cards for clean accordion feel
        cards.forEach(c => c.classList.remove('expanded', 'highlighted'));

        if (!isCurrentlyExpanded) {
          card.classList.add('expanded', 'highlighted');
          this._lockedHighlightCol = colName;
          if (window.appCanvas) {
            window.appCanvas.highlightLineagePath(nodeIds);
          }
        } else {
          this._lockedHighlightCol = null;
          if (window.appCanvas) {
            window.appCanvas.clearLineageHighlight();
          }
        }
      });
    });
  }

  _escape(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}

window.appLineagePanel = new LineagePanel();
