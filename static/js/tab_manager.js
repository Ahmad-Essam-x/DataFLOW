/**
 * TabManager — Multi-Workflow Tab System for Antigravity DataFlow.
 *
 * Provides Alteryx-style simultaneous multi-workflow editing.
 * Each tab is a fully isolated TabContext: independent Canvas, ConfigPanel,
 * ResultsPanel, HistoryManager, run state, dirty tracking, and autosave session.
 * Global elements (theme, UI zoom, menu bar) are shared across all tabs.
 */

// ─────────────────────────────────────────────────────────────
// TabContext — represents one open workflow document
// ─────────────────────────────────────────────────────────────
class TabContext {
  constructor({ id, name, canvas, configPanel, resultsPanel, history, sessionId, hostEl }) {
    this.id = id;
    this.name = name || 'New Workflow';
    this.canvas = canvas;
    this.configPanel = configPanel;
    this.resultsPanel = resultsPanel;
    this.history = history;
    this.sessionId = sessionId;
    this.hostEl = hostEl;           // .tab-canvas-host <div>

    // Per-tab state mirrors
    this.workflowFile = { handle: null, name: null, path: null };
    this.isDirty = false;
    this.isRunning = false;
    this.activeRunId = null;
    this.lastResult = null;
    this.logs = [];
  }
}

// ─────────────────────────────────────────────────────────────
// TabManager — orchestrates all tabs
// ─────────────────────────────────────────────────────────────
class TabManager {
  constructor() {
    this.tabs = [];
    this.activeTabId = null;
    this.maxTabs = 12;
    this._tabIdCounter = 0;

    this._stripEl = null;     // Set after DOM is ready
    this._newTabBtn = null;
  }

  get activeTab() {
    return this.tabs.find(t => t.id === this.activeTabId) || null;
  }

  get activeCanvas() {
    const t = this.activeTab;
    return t ? t.canvas : null;
  }

  // ── Bootstrap ────────────────────────────────────────────────

  /** Called by app.js after DOMContentLoaded to wire up the DOM. */
  init() {
    this._stripEl = document.getElementById('workflow-tab-strip');
    this._newTabBtn = document.getElementById('btn-new-tab');

    if (this._newTabBtn) {
      this._newTabBtn.addEventListener('click', () => this.createTab());
    }
  }

  // ── Tab Creation ─────────────────────────────────────────────

  /**
   * Creates a new tab. Instantiates its own Canvas, ConfigPanel,
   * ResultsPanel, and HistoryManager inside a fresh host div.
   * @param {object|null} workflowData — optional initial workflow to load
   * @param {string} name — display name for the tab
   * @param {string|null} filePath — optional full file path on disk
   * @param {object|null} fileHandle — optional Chromium FileSystemFileHandle
   * @returns {TabContext}
   */
  createTab(workflowData = null, name = 'New Workflow', filePath = null, fileHandle = null) {
    if (this.tabs.length >= this.maxTabs) {
      if (window.showToast) {
        window.showToast('warning', 'Tab Limit Reached', `Maximum of ${this.maxTabs} workflow tabs are open.`);
      }
      return null;
    }

    const id = ++this._tabIdCounter;
    const sessionId = 'tab_' + id + '_sess_' + Math.random().toString(36).substring(2, 9) + Date.now().toString(36);

    const genericNames = ['new workflow', 'untitled_workflow', 'untitled', 'workflow'];
    let resolvedName = name;
    if (workflowData && workflowData.name && !genericNames.includes(String(workflowData.name).trim().toLowerCase())) {
      resolvedName = workflowData.name;
    } else if (filePath) {
      const base = filePath.split('/').pop().split('\\').pop().replace(/\.(json|yxmd|zip|yxzp)$/i, '');
      resolvedName = base.replace(/_/g, ' ');
    } else if (fileHandle && fileHandle.name) {
      const base = fileHandle.name.replace(/\.(json|yxmd|zip|yxzp)$/i, '');
      resolvedName = base.replace(/_/g, ' ');
    }
    resolvedName = (resolvedName && resolvedName.trim()) || 'New Workflow';

    const filename = filePath ? filePath.split('/').pop().split('\\').pop() : (fileHandle ? fileHandle.name : null);

    // 1. Create isolated host div inside #canvas-container
    const canvasContainer = document.getElementById('canvas-container');
    const hostEl = document.createElement('div');
    hostEl.className = 'tab-canvas-host';
    hostEl.dataset.tabId = id;
    hostEl.innerHTML = `
      <div class="canvas-wrapper" id="tab-canvas-wrapper-${id}">
        <svg class="canvas-svg" id="tab-canvas-svg-${id}" viewBox="-50000 -50000 100000 100000">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b"></path>
            </marker>
            <marker id="arrow-selected" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8"></path>
            </marker>
            <marker id="tab-arrow-${id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b"></path>
            </marker>
            <marker id="tab-arrow-selected-${id}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 10 5 L 0 9 z" fill="#38bdf8"></path>
            </marker>
          </defs>
          <g id="tab-wires-group-${id}"></g>
          <path id="tab-temp-wire-${id}" class="wire temp-wire" d=""></path>
        </svg>
        <div id="tab-containers-layer-${id}" class="containers-layer"></div>
        <div id="tab-comments-layer-${id}" class="comments-layer"></div>
        <div id="tab-nodes-layer-${id}" class="nodes-layer"></div>
      </div>
    `;
    // Insert before the shared overlays (dropzone, hint, minimap)
    canvasContainer.insertBefore(hostEl, canvasContainer.firstChild);

    // Resolve tools registry for the new tab canvas
    const toolsData = this._toolsData
      || (window.toolRegistry ? Object.values(window.toolRegistry) : null)
      || (window.toolsData ? window.toolsData : null)
      || (window.appCanvas && Object.values(window.appCanvas.toolRegistry || {}));

    // 2. Instantiate Canvas bound to this host with toolRegistry pre-hydrated
    const tabCanvas = new Canvas(hostEl, {
      tabId: id,
      toolRegistry: toolsData,
      onSelectNode: (node) => {
        if (this.activeTabId !== id) return;
        window.appConfigPanel.render(node);
        window.appResultsPanel.showNodeResults(node);
      },
      onWorkflowChange: () => {
        if (this.activeTabId !== id) return;
        if (window.appCanvas && window.appCanvas.selectedNodeId) {
          const node = window.appCanvas.nodes.find(n => n.id === window.appCanvas.selectedNodeId);
          const isEditingInPanel = document.activeElement &&
            window.appConfigPanel.contentEl &&
            window.appConfigPanel.contentEl.contains(document.activeElement);
          if (!isEditingInPanel) window.appConfigPanel.render(node);
          window.appCanvas.updateNodeValidation(node);
        }
        if (typeof window.markWorkflowDirty === 'function') {
          window.markWorkflowDirty();
        }
      }
    });

    if (toolsData && toolsData.length > 0) {
      tabCanvas.setToolsRegistry(toolsData);
    }

    // 3. Instantiate history for this tab
    const tabHistory = new HistoryManager(tabCanvas);

    // 4. Construct the TabContext
    const ctx = new TabContext({
      id,
      name: resolvedName,
      canvas: tabCanvas,
      configPanel: window.appConfigPanel,  // shared DOM element, re-rendered on switch
      resultsPanel: window.appResultsPanel, // shared DOM element, re-rendered on switch
      history: tabHistory,
      sessionId,
      hostEl
    });

    if (this._sampleDatasets && window.appConfigPanel) {
      window.appConfigPanel.setSampleDatasets(this._sampleDatasets);
    }

    ctx.workflowFile = {
      handle: fileHandle || null,
      name: filename || (workflowData ? `${resolvedName}.json` : null),
      path: filePath || null
    };

    this.tabs.push(ctx);
    this._renderTabPill(ctx);
    this.activateTab(id);

    // 5. Load workflow if provided (now with toolRegistry fully hydrated so authentic glyphs render)
    if (workflowData) {
      tabCanvas.loadWorkflow(workflowData);
      ctx.isDirty = false;
      window._activeTabIsDirty = false;
      this._updateTabPill(id);
      const nameInput = document.getElementById('workflow-name-input');
      if (nameInput) nameInput.value = resolvedName;
      document.title = `${resolvedName} - Antigravity DataFlow`;
      const dirtyBadge = document.getElementById('workflow-dirty-badge');
      if (dirtyBadge) {
        dirtyBadge.textContent = '✓ Saved';
        dirtyBadge.classList.remove('is-dirty');
        dirtyBadge.classList.add('is-clean');
      }
    }

    return ctx;
  }

  // ── Tab Activation ───────────────────────────────────────────

  /**
   * Switches the visible workspace to the given tab.
   * Saves current tab's transient state, then hydrates global singletons
   * from the target tab's context.
   */
  activateTab(tabId) {
    const targetCtx = this.tabs.find(t => t.id === tabId);
    if (!targetCtx) return;

    // Snapshot current tab's name from toolbar (user may have typed)
    if (this.activeTabId !== null && this.activeTabId !== tabId) {
      const prevCtx = this.tabs.find(t => t.id === this.activeTabId);
      if (prevCtx) {
        const nameInput = document.getElementById('workflow-name-input');
        if (nameInput) prevCtx.name = nameInput.value.trim() || prevCtx.name;
        // Snapshot dirty state
        prevCtx.isDirty = !!window._activeTabIsDirty;
        prevCtx.lastResult = window.appLastResult;
      }
    }

    // Hide all canvas hosts
    document.querySelectorAll('.tab-canvas-host').forEach(el => {
      el.classList.remove('active-tab-host');
    });

    // Show target host
    targetCtx.hostEl.classList.add('active-tab-host');

    // Update active tab id
    this.activeTabId = tabId;

    // ── Hydrate global singletons ──
    window.appCanvas = targetCtx.canvas;
    window.appHistory = targetCtx.history;
    window.clientSessionId = targetCtx.sessionId;
    window.activeRunId = targetCtx.activeRunId;
    window._isWorkflowRunning = targetCtx.isRunning;
    window.activeWorkflowFile = targetCtx.workflowFile;
    window.appLastResult = targetCtx.lastResult;

    // Set history canvas reference
    targetCtx.history.setCanvas(targetCtx.canvas);

    // ── Sync toolbar elements ──
    const nameInput = document.getElementById('workflow-name-input');
    if (nameInput) nameInput.value = targetCtx.name;

    // Sync dirty badge
    window._activeTabIsDirty = targetCtx.isDirty;
    if (targetCtx.isDirty) {
      if (typeof window.markWorkflowDirty === 'function') {
        // Call quietly without pushing another history snapshot
        const dirtyBadge = document.getElementById('workflow-dirty-badge');
        if (dirtyBadge) {
          dirtyBadge.textContent = '● Unsaved';
          dirtyBadge.classList.remove('is-clean');
          dirtyBadge.classList.add('is-dirty');
        }
        const wfName = targetCtx.name || 'Workflow';
        document.title = `* ${wfName} - Antigravity DataFlow`;
      }
    } else {
      const dirtyBadge = document.getElementById('workflow-dirty-badge');
      if (dirtyBadge) {
        dirtyBadge.textContent = '✓ Saved';
        dirtyBadge.classList.remove('is-dirty');
        dirtyBadge.classList.add('is-clean');
      }
      const wfName = targetCtx.name || 'Workflow';
      document.title = `${wfName} - Antigravity DataFlow`;
    }

    // Sync Run/Stop button states
    this._syncRunStopButtons(targetCtx);

    // Sync undo/redo buttons
    const canUndo = targetCtx.history.undoStack.length > 0;
    const canRedo = targetCtx.history.redoStack.length > 0;
    const undoBtn = document.getElementById('btn-undo');
    const redoBtn = document.getElementById('btn-redo');
    if (undoBtn) undoBtn.disabled = !canUndo;
    if (redoBtn) redoBtn.disabled = !canRedo;

    // Sync ToolPalette and ConfigPanel with target canvas
    if (window.appPalette && typeof window.appPalette.setCanvas === 'function') {
      window.appPalette.setCanvas(targetCtx.canvas);
    }

    // Re-render config and results panels for the now-active canvas
    if (window.appConfigPanel) {
      if (typeof window.appConfigPanel.setCanvas === 'function') {
        window.appConfigPanel.setCanvas(targetCtx.canvas);
      }
      const selNode = targetCtx.canvas.selectedNodeId
        ? targetCtx.canvas.nodes.find(n => n.id === targetCtx.canvas.selectedNodeId)
        : null;
      // Re-apply sample datasets so input node file-pickers work on any tab
      if (this._sampleDatasets && typeof window.appConfigPanel.setSampleDatasets === 'function') {
        window.appConfigPanel.setSampleDatasets(this._sampleDatasets);
      }
      window.appConfigPanel.render(selNode || null);
    }

    // Hydrate ResultsPanel with target tab's execution logs and results
    if (window.appResultsPanel) {
      window.appResultsPanel.clear();
      if (targetCtx.logs && targetCtx.logs.length > 0) {
        targetCtx.logs.forEach(l => window.appResultsPanel.appendLog(l));
      }
      if (targetCtx.lastResult) {
        window.appResultsPanel.finalizeRun(targetCtx.lastResult);
      }
      const selNode = targetCtx.canvas.selectedNodeId
        ? targetCtx.canvas.nodes.find(n => n.id === targetCtx.canvas.selectedNodeId)
        : null;
      window.appResultsPanel.showNodeResults(selNode || null);
    }

    // Sync canvas transform & grid background for target canvas
    if (targetCtx.canvas) {
      targetCtx.canvas.updateTransform();
    }

    // Update minimap if present
    if (window.appMiniMap) {
      window.appMiniMap.canvas = targetCtx.canvas;
      window.appMiniMap.render();
    }

    // Update tab pills
    this._renderStrip();

    // Notify event bus
    if (window.appEventBus) {
      window.appEventBus.emit('tab:activated', { tabId });
    }
  }

  // ── Tab Closing ──────────────────────────────────────────────

  /**
   * Closes a tab. If only one tab is left, clears its canvas instead.
   * Prompts user if the tab has unsaved changes.
   */
  closeTab(tabId) {
    const ctx = this.tabs.find(t => t.id === tabId);
    if (!ctx) return;

    // If last tab — clear canvas instead of closing
    if (this.tabs.length === 1) {
      if (ctx.isDirty && ctx.canvas.nodes && ctx.canvas.nodes.length > 0) {
        if (!confirm('Clear this workflow? You have unsaved changes.')) return;
      }
      ctx.canvas.loadWorkflow({ nodes: [], connections: [] });
      ctx.canvas.cachedNodeIds && ctx.canvas.cachedNodeIds.clear();
      ctx.isDirty = false;
      ctx.name = 'New Workflow';
      ctx.workflowFile = { handle: null, name: null, path: null };
      ctx.activeRunId = null;
      ctx.lastResult = null;
      if (window.appResultsPanel) window.appResultsPanel.clear();
      if (window.appConfigPanel) window.appConfigPanel.render(null);
      const nameInput = document.getElementById('workflow-name-input');
      if (nameInput) nameInput.value = 'New Workflow';
      if (typeof window.markWorkflowClean === 'function') window.markWorkflowClean();
      if (window.appHistory) window.appHistory.pushSnapshot('New Workflow');
      this._updateTabPill(tabId);
      if (window.showToast) window.showToast('info', 'Canvas Cleared', 'Workflow cleared. Last tab cannot be closed — canvas reset instead.');
      return;
    }

    // Unsaved-changes guard
    if (ctx.isDirty && ctx.canvas.nodes && ctx.canvas.nodes.length > 0) {
      if (!confirm(`Close "${ctx.name}"? You have unsaved changes that will be lost.`)) return;
    }

    // Cancel active background execution if running
    if (ctx.isRunning && ctx.activeRunId) {
      try {
        fetch(`/api/cancel/${encodeURIComponent(ctx.activeRunId)}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: ctx.activeRunId })
        }).catch(() => {});
      } catch (_) {}
    }

    // Find next tab to activate
    const idx = this.tabs.findIndex(t => t.id === tabId);
    const nextIdx = idx > 0 ? idx - 1 : 1;
    const nextTab = this.tabs[nextIdx];

    // Remove host element from DOM
    ctx.hostEl.remove();

    // Remove from array
    this.tabs.splice(idx, 1);

    // Activate neighbor
    if (nextTab) {
      this.activateTab(nextTab.id);
    }
    if (typeof window.syncDirtyStateToServer === 'function') window.syncDirtyStateToServer();
  }

  // ── Tab Navigation ────────────────────────────────────────────

  activateNextTab() {
    if (this.tabs.length < 2) return;
    const idx = this.tabs.findIndex(t => t.id === this.activeTabId);
    const next = this.tabs[(idx + 1) % this.tabs.length];
    this.activateTab(next.id);
  }

  activatePrevTab() {
    if (this.tabs.length < 2) return;
    const idx = this.tabs.findIndex(t => t.id === this.activeTabId);
    const prev = this.tabs[(idx - 1 + this.tabs.length) % this.tabs.length];
    this.activateTab(prev.id);
  }

  // ── Tab Metadata Updates ──────────────────────────────────────

  /** Updates stored name for the active tab from toolbar input */
  syncActiveTabName(newName) {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    if (ctx && newName) {
      ctx.name = newName;
      this._updateTabPill(ctx.id);
    }
  }

  /** Marks the active tab as dirty (unsaved changes) */
  markActiveDirty() {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    if (ctx) {
      ctx.isDirty = true;
      window._activeTabIsDirty = true;
      this._updateTabPill(ctx.id);
      if (typeof window.syncDirtyStateToServer === 'function') window.syncDirtyStateToServer();
    }
  }

  /** Marks the active tab as clean (saved) */
  markActiveClean() {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    if (ctx) {
      ctx.isDirty = false;
      window._activeTabIsDirty = false;
      this._updateTabPill(ctx.id);
      if (typeof window.syncDirtyStateToServer === 'function') window.syncDirtyStateToServer();
    }
  }

  /** Updates active tab's workflowFile reference */
  setActiveWorkflowFile(fileInfo) {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    if (ctx) {
      ctx.workflowFile = fileInfo;
    }
  }

  /** Gets active tab's workflowFile */
  getActiveWorkflowFile() {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    return ctx ? ctx.workflowFile : { handle: null, name: null, path: null };
  }

  /** Updates run state on active tab */
  setActiveRunState(isRunning, runId = null) {
    const ctx = this.tabs.find(t => t.id === this.activeTabId);
    if (ctx) {
      ctx.isRunning = isRunning;
      if (runId !== null) ctx.activeRunId = runId;
      window._isWorkflowRunning = isRunning;
      window.activeRunId = ctx.activeRunId;
    }
  }

  /** Returns the currently active TabContext */
  get activeTab() {
    return this.tabs.find(t => t.id === this.activeTabId) || null;
  }

  // ── DOM Rendering ─────────────────────────────────────────────

  _renderStrip() {
    if (!this._stripEl) return;

    // Remove all existing tab pills (but keep the + button)
    const pills = this._stripEl.querySelectorAll('.workflow-tab');
    pills.forEach(p => p.remove());

    // Re-render all tab pills in order, before the + button
    this.tabs.forEach(ctx => {
      const pill = this._buildTabPill(ctx);
      this._stripEl.insertBefore(pill, this._newTabBtn);
    });
  }

  _renderTabPill(ctx) {
    if (!this._stripEl) return;
    const pill = this._buildTabPill(ctx);
    this._stripEl.insertBefore(pill, this._newTabBtn);
  }

  _updateTabPill(tabId) {
    const ctx = this.tabs.find(t => t.id === tabId);
    if (!ctx || !this._stripEl) return;

    const existing = this._stripEl.querySelector(`.workflow-tab[data-tab-id="${tabId}"]`);
    if (!existing) {
      this._renderStrip();
      return;
    }

    const titleEl = existing.querySelector('.tab-title');
    if (titleEl) titleEl.textContent = ctx.name || 'Untitled';

    existing.classList.toggle('is-dirty', ctx.isDirty);
    existing.classList.toggle('active', ctx.id === this.activeTabId);
  }

  _buildTabPill(ctx) {
    const isActive = ctx.id === this.activeTabId;

    const pill = document.createElement('div');
    pill.className = `workflow-tab${isActive ? ' active' : ''}${ctx.isDirty ? ' is-dirty' : ''}`;
    pill.dataset.tabId = ctx.id;
    pill.role = 'tab';
    pill.tabIndex = 0;
    pill.setAttribute('aria-selected', isActive ? 'true' : 'false');
    pill.title = ctx.name || 'Untitled';

    pill.innerHTML = `
      <span class="tab-dirty-dot" title="Unsaved changes"></span>
      <span class="tab-title">${_escapeHtml(ctx.name || 'Untitled')}</span>
      <button class="tab-close-btn" title="Close tab (Ctrl+W)" aria-label="Close tab">✕</button>
    `;

    pill.addEventListener('click', (e) => {
      if (e.target.closest('.tab-close-btn')) return;
      this.activateTab(ctx.id);
    });

    pill.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.activateTab(ctx.id);
      }
    });

    pill.querySelector('.tab-close-btn').addEventListener('click', (e) => {
      e.stopPropagation();
      this.closeTab(ctx.id);
    });

    // Middle-click to close
    pill.addEventListener('mousedown', (e) => {
      if (e.button === 1) {
        e.preventDefault();
        this.closeTab(ctx.id);
      }
    });

    return pill;
  }

  _syncRunStopButtons(ctx) {
    const runBtn = document.getElementById('btn-run');
    const stopBtn = document.getElementById('btn-stop');
    if (!runBtn || !stopBtn) return;

    if (ctx.isRunning) {
      runBtn.classList.add('loading', 'is-running');
      runBtn.disabled = true;
      runBtn.innerHTML = `
        <span class="spinner-sm" aria-hidden="true"></span>
        <span>Running...</span>
      `;
      stopBtn.disabled = false;
      stopBtn.classList.add('btn-stop-active');
    } else {
      runBtn.classList.remove('loading', 'is-running');
      runBtn.disabled = false;
      runBtn.innerHTML = `
        <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
          <polygon points="5 3 19 12 5 21 5 3"></polygon>
        </svg>
        <span>Run Workflow</span>
        <kbd>Ctrl+Enter</kbd>
      `;
      stopBtn.disabled = true;
      stopBtn.classList.remove('btn-stop-active', 'is-stopping');
      stopBtn.innerHTML = `
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <rect x="5" y="5" width="14" height="14" rx="2"></rect>
        </svg>
        <span>Stop</span>
        <kbd>Esc</kbd>
      `;
    }
  }
}

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────

function _escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Expose globally
window.TabManager = TabManager;
window.TabContext = TabContext;
