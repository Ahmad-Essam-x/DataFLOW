/**
 * Main Application Coordinator.
 * Initializes canvas, palette, configuration, results panels, history manager,
 * theme switching, and real-time SSE execution streaming.
 */

import { ConfigPanel } from './config_panel.js';
import { runWorkflow, stopWorkflow } from './workflow_runner.js';
import { registerKeyboardShortcuts } from './keyboard_shortcuts.js';
import {
  markWorkflowDirty, markWorkflowClean, triggerAutosave,
  scheduleDebouncedAutosave, syncDirtyStateToServer,
  checkAutoSaveRecovery, showExitConfirmationDialog, doCleanExit,
  initAutosaveManager
} from './autosave_manager.js';
import {
  saveWorkflow, saveWorkflowAs, openWorkflowData, openWorkflowFileDialog,
  exportWorkflowJson, exportWorkflowPackage, importWorkflowPackage,
  handleWorkflowLoaded, loadWorkflowFromServer, initWorkflowIO
} from './workflow_io.js';
import { ConnectionManagerUI } from './connection_manager_ui.js';

document.addEventListener('DOMContentLoaded', async () => {
  // Database Connections Manager
  const connUI = window.connectionManagerUI || new ConnectionManagerUI();
  window.connectionManagerUI = connUI;
  window.openDatabaseConnectionsModal = (connId = null) => {
    connUI.openModal(connId);
  };

  // ── TabManager: Multi-Workflow Tab System ────────────────────────────────────
  // Instantiate TabManager early; it will adopt the static canvas as Tab 1.
  const tabManager = new TabManager();
  window.appTabManager = tabManager;

  // Session tracking for execution isolation
  let clientSessionId = localStorage.getItem('dataflow_session_id');
  if (!clientSessionId) {
    clientSessionId = 'sess_' + Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
    localStorage.setItem('dataflow_session_id', clientSessionId);
  }
  window.clientSessionId = clientSessionId;
  window.activeRunId = null;

  // 1. Instantiate Core Components
  const resultsPanel = new ResultsPanel();
  window.appResultsPanel = resultsPanel;

  const canvas = new Canvas('canvas-container', {
    tabId: 1,
    onSelectNode: (node) => {
      configPanel.render(node);
      resultsPanel.showNodeResults(node);
    },
    onWorkflowChange: () => {
      if (canvas.selectedNodeId) {
        const node = canvas.nodes.find(n => n.id === canvas.selectedNodeId);
        const isEditingInPanel = document.activeElement && configPanel.contentEl && configPanel.contentEl.contains(document.activeElement);
        if (!isEditingInPanel) {
          configPanel.render(node);
        }
        // Update validation badge when config changes
        canvas.updateNodeValidation(node);
      }
      if (typeof markWorkflowDirty === 'function') {
        markWorkflowDirty();
      }
    }
  });
  window.appCanvas = canvas;

  if (window.appHistory) {
    window.appHistory.setCanvas(canvas);
  }

  const configPanel = new ConfigPanel(canvas);
  window.appConfigPanel = configPanel;

  const palette = new ToolPalette(canvas);
  window.appPalette = palette;

  if (window.CanvasMiniMap) {
    window.appMiniMap = new CanvasMiniMap(canvas);
  }

  // ── Register initial canvas as Tab 1 with TabManager ───────────────────────
  {
    const staticHostEl = document.getElementById('tab-canvas-host-static');
    const tab1History = window.appHistory || new HistoryManager(canvas);
    window.appHistory = tab1History;

    // Build the first TabContext from the already-constructed singletons
    const tab1Ctx = new TabContext({
      id: 1,
      name: (document.getElementById('workflow-name-input') || {}).value || 'New Workflow',
      canvas: canvas,
      configPanel: configPanel,
      resultsPanel: resultsPanel,
      history: tab1History,
      sessionId: clientSessionId,
      hostEl: staticHostEl
    });
    tab1Ctx.workflowFile = { handle: null, name: null, path: null };
    window.activeWorkflowFile = tab1Ctx.workflowFile;

    tabManager.tabs.push(tab1Ctx);
    tabManager.activeTabId = 1;
    tabManager._tabIdCounter = 1;

    // Initialise the strip DOM (button bindings etc.)
    tabManager.init();

    // Render the first tab pill
    tabManager._renderStrip();

    // Expose workflow file via TabManager
    Object.defineProperty(window, 'activeWorkflowFile', {
      get: () => tabManager.getActiveWorkflowFile(),
      set: (v) => tabManager.setActiveWorkflowFile(v),
      configurable: true
    });
  }

  // Active canvas helper — ensures all features operate on the active tab's canvas
  function getActiveCanvas() {
    return (window.appTabManager && window.appTabManager.activeCanvas) || window.appCanvas || canvas;
  }
  window.getActiveCanvas = getActiveCanvas;

  // 1b. Setup UI Scale & Display Zoom
  const UI_ZOOM_LEVELS = [0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0];
  let currentUIScale = 1.0;
  try {
    const savedScale = window.userSettings 
      ? window.userSettings.get('ui_zoom', 1.0) 
      : parseFloat(localStorage.getItem('dataflow_ui_zoom') || '1.0');
    if (!isNaN(savedScale) && savedScale >= 0.5 && savedScale <= 2.5) {
      currentUIScale = savedScale;
    }
  } catch (_) {}

  function applyUIScale(scale, notify = false) {
    scale = Math.min(2.0, Math.max(0.6, Math.round(scale * 100) / 100));
    currentUIScale = scale;

    // Use transform:scale on the app wrapper instead of css `zoom` on documentElement.
    // CSS zoom causes getBoundingClientRect() to return layout-px in older Chromium (pre-128)
    // while mouse clientX/Y are always in viewport-px — producing a marquee offset.
    // transform:scale is handled uniformly by all browsers: BoundingClientRect returns
    // viewport-space coords that match clientX/Y. It also properly contains position:fixed
    // elements so overlays/dropdowns scale with the UI instead of being clipped.
    document.documentElement.style.zoom = '';  // clear any legacy value
    const wrapper = document.getElementById('app-scale-wrapper');
    if (wrapper) {
      if (scale === 1.0) {
        wrapper.style.transform = '';
        wrapper.style.width = '';
        wrapper.style.height = '';
      } else {
        wrapper.style.transform = `scale(${scale})`;
        wrapper.style.transformOrigin = '0 0';
        wrapper.style.width = `${(100 / scale).toFixed(4)}%`;
        wrapper.style.height = `${(100 / scale).toFixed(4)}%`;
      }
    } else {
      // Fallback for any context without the wrapper
      document.documentElement.style.zoom = `${scale}`;
    }
    localStorage.setItem('dataflow_ui_zoom', String(scale));
    if (window.userSettings) {
      window.userSettings.set('ui_zoom', scale);
    }
    if (notify && window.showToast) {
      window.showToast('info', 'UI Display Scale', `Interface zoom: ${Math.round(scale * 100)}%`, 1200);
    }
  }

  function zoomUIIn() {
    let next = UI_ZOOM_LEVELS.find(lvl => lvl > currentUIScale + 0.01);
    if (!next) next = Math.min(2.0, Math.round((currentUIScale + 0.1) * 100) / 100);
    applyUIScale(next, true);
  }

  function zoomUIOut() {
    let prev = [...UI_ZOOM_LEVELS].reverse().find(lvl => lvl < currentUIScale - 0.01);
    if (!prev) prev = Math.max(0.6, Math.round((currentUIScale - 0.1) * 100) / 100);
    applyUIScale(prev, true);
  }

  function resetUIZoom() {
    applyUIScale(1.0, true);
  }

  window.appUIScale = {
    apply: applyUIScale,
    zoomIn: zoomUIIn,
    zoomOut: zoomUIOut,
    reset: resetUIZoom,
    get: () => currentUIScale
  };

  // Apply saved scale immediately
  if (currentUIScale !== 1.0) {
    applyUIScale(currentUIScale, false);
  }

  // 2. Setup Theme Switching (Modern Dark vs Alteryx Classic Light vs High Contrast)
  function setupTheme() {
    // Apply theme from settings (userSettings seeded from localStorage already in constructor)
    if (window.userSettings) {
      window.userSettings._applyTheme();
    } else {
      const savedTheme = localStorage.getItem('alteryx_theme') || 'theme-dark';
      document.documentElement.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
      document.documentElement.classList.add(savedTheme);
      document.body.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
      document.body.classList.add(savedTheme);
    }

    const toggleBtn = document.getElementById('btn-theme-toggle');
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    const label = document.getElementById('theme-toggle-label');

    function updateIcons(theme) {
      if (theme === 'theme-light') {
        if (sunIcon) sunIcon.style.display = 'none';
        if (moonIcon) moonIcon.style.display = 'block';
        if (label) label.textContent = 'Light Mode';
      } else if (theme === 'theme-high-contrast') {
        if (sunIcon) sunIcon.style.display = 'block';
        if (moonIcon) moonIcon.style.display = 'none';
        if (label) label.textContent = 'Contrast';
      } else {
        if (sunIcon) sunIcon.style.display = 'none';
        if (moonIcon) moonIcon.style.display = 'block';
        if (label) label.textContent = 'Dark Mode';
      }
      if (toggleBtn) {
        toggleBtn.title = `Current: ${label ? label.textContent : theme} (Click to toggle theme)`;
        toggleBtn.setAttribute('aria-pressed', theme !== 'theme-light' ? 'true' : 'false');
      }
    }

    const currentTheme = document.body.className.includes('theme-light') ? 'theme-light' :
                         document.body.className.includes('theme-high-contrast') ? 'theme-high-contrast' : 'theme-dark';
    updateIcons(currentTheme);

    if (toggleBtn) {
      toggleBtn.addEventListener('click', () => {
        const isLight = document.body.classList.contains('theme-light');
        const nextTheme = isLight ? 'theme-dark' : 'theme-light';
        document.documentElement.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
        document.documentElement.classList.add(nextTheme);
        document.body.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
        document.body.classList.add(nextTheme);

        // Persist via userSettings (also writes to localStorage + server)
        const shortKey = nextTheme === 'theme-light' ? 'light' : nextTheme === 'theme-high-contrast' ? 'high-contrast' : 'dark';
        if (window.userSettings) window.userSettings.set('theme', shortKey);
        else localStorage.setItem('alteryx_theme', nextTheme);

        updateIcons(nextTheme);
        if (window.appMenuBar && typeof window.appMenuBar.syncMenuStates === 'function') {
          window.appMenuBar.syncMenuStates();
        }
        if (window.showToast) {
          window.showToast('info', 'Theme Changed', `Switched to ${nextTheme === 'theme-light' ? 'Light Mode' : 'Dark Mode'}.`);
        }
      });
    }
  }
  setupTheme();

  // Load server-persisted settings (overrides localStorage, re-applies all settings to DOM/app).
  // This is async but non-blocking — the page is already usable with localStorage values.
  if (window.userSettings) {
    window.userSettings.applyAll();
    window.userSettings.load().catch(err => console.warn('[App] userSettings.load() failed:', err));
  }

  // 3. Setup Undo / Redo Toolbar Controls
  const undoBtn = document.getElementById('btn-undo');
  const redoBtn = document.getElementById('btn-redo');

  if (undoBtn) {
    undoBtn.addEventListener('click', () => {
      if (window.appHistory) window.appHistory.undo();
    });
  }

  if (redoBtn) {
    redoBtn.addEventListener('click', () => {
      if (window.appHistory) window.appHistory.redo();
    });
  }

  if (window.appEventBus) {
    window.appEventBus.on('history:changed', ({ canUndo, canRedo }) => {
      if (undoBtn) undoBtn.disabled = !canUndo;
      if (redoBtn) redoBtn.disabled = !canRedo;
    });
  }

  // 4. Global Toast System
  window.showToast = function(type, title, message, durationMs = 4500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    let iconSvg = '';
    if (type === 'success') {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22c55e" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === 'error') {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else if (type === 'warning') {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
    } else {
      iconSvg = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#0072ce" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;
    }

    toast.innerHTML = `
      <div class="toast-icon">${iconSvg}</div>
      <div class="toast-content">
        <div class="toast-title">${title}</div>
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close">&times;</button>
    `;

    const closeBtn = toast.querySelector('.toast-close');
    const removeToast = () => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 250);
    };
    closeBtn.addEventListener('click', removeToast);

    container.appendChild(toast);

    if (durationMs > 0) {
      setTimeout(removeToast, durationMs);
    }
  };

  // 5. Workflow Execution Engine
  const runBtn = document.getElementById('btn-run');
  const stopBtn = document.getElementById('btn-stop');

  // getToolDisplayName, stopWorkflow, runWorkflow, handleStreamEventForTab, finalizeRun,
  // runWorkflowFallback — imported from ./workflow_runner.js
  // Manages btn-stop-active and is-stopping UI classes during execution; Escape key cancels run

  if (runBtn) {
    runBtn.addEventListener('click', runWorkflow);
  }
  if (stopBtn) {
    stopBtn.addEventListener('click', () => {
      stopWorkflow();
      if (window.appEventBus) window.appEventBus.emit('workflow:stop');
    });
  }



  initAutosaveManager();
  window.activeWorkflowFile = { handle: null, name: null, path: null };

  initWorkflowIO();
  // Modal Dialog Controllers: Dependencies, Revisions & Properties
  async function openWorkflowDependenciesModal() {
    const modal = document.getElementById('modal-workflow-deps');
    if (!modal) return;
    const activeCanvas = getActiveCanvas();
    const wfData = activeCanvas.getWorkflowData();
    const tbody = document.getElementById('deps-table-body');
    const banner = document.getElementById('deps-summary-banner');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="padding: 16px; text-align: center; color: var(--text-muted);">Inspecting workflow assets...</td></tr>`;

    modal.style.display = 'flex';

    try {
      const res = await fetch('/api/workflow/dependencies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(wfData)
      });
      const data = await res.json();
      if (!data.success) throw new Error(data.error || 'Failed to inspect dependencies');

      if (banner) {
        if (data.missing_count === 0) {
          banner.className = 'deps-summary-banner banner-ok';
          banner.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 16px; color: #16a34a;">✓</span>
              <div>
                <strong style="color: #16a34a;">All ${data.total_dependencies} External Assets Found</strong>
                <div style="font-size: 10.5px; color: var(--text-muted);">All referenced files resolve to existing files on disk.</div>
              </div>
            </div>
            <span class="deps-status-pill status-found">${data.total_dependencies} Valid</span>
          `;
        } else {
          banner.className = 'deps-summary-banner banner-warning';
          banner.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 16px; color: #f59e0b;">⚠</span>
              <div>
                <strong style="color: #f59e0b;">${data.missing_count} of ${data.total_dependencies} Assets Missing</strong>
                <div style="font-size: 10.5px; color: var(--text-muted);">Some input/output files do not exist at the specified locations.</div>
              </div>
            </div>
            <span class="deps-status-pill status-missing">${data.missing_count} Missing</span>
          `;
        }
      }

      if (tbody) {
        if (!data.dependencies || data.dependencies.length === 0) {
          tbody.innerHTML = `<tr><td colspan="6" style="padding: 24px; text-align: center; color: var(--text-muted);">No external file dependencies in this workflow.</td></tr>`;
          return;
        }

        tbody.innerHTML = '';
        data.dependencies.forEach(dep => {
          const tr = document.createElement('tr');
          tr.style.borderBottom = '1px solid var(--border-subtle)';
          const statusHtml = dep.exists
            ? `<span class="deps-status-pill status-found">✓ Exists</span>`
            : `<span class="deps-status-pill status-missing">⚠ Missing</span>`;
          const sizeHtml = dep.exists && dep.size_bytes !== null
            ? `${(dep.size_bytes / 1024).toFixed(1)} KB`
            : '-';
          
          tr.innerHTML = `
            <td style="padding: 8px 12px; font-weight: 500;">
              <span class="node-badge" style="background: rgba(0, 114, 206, 0.12); color: var(--color-primary); padding: 2px 6px; border-radius: 3px; font-size: 10px;">${dep.node_type}</span>
              <span style="margin-left: 6px;">#${dep.node_id}</span>
            </td>
            <td style="padding: 8px 12px; text-transform: capitalize; color: var(--text-muted);">${dep.role}</td>
            <td style="padding: 8px 12px; font-family: monospace; font-size: 10.5px; word-break: break-all;" title="${dep.path}">${dep.path}</td>
            <td style="padding: 8px 12px; color: var(--text-secondary);">${sizeHtml}</td>
            <td style="padding: 8px 12px;">${statusHtml}</td>
            <td style="padding: 8px 12px; text-align: right;">
              <button class="btn btn-secondary btn-sm" data-select-node="${dep.node_id}" style="padding: 2px 8px; font-size: 10.5px;">Select Tool</button>
            </td>
          `;

          const selBtn = tr.querySelector(`[data-select-node="${dep.node_id}"]`);
          if (selBtn) {
            selBtn.addEventListener('click', () => {
              modal.style.display = 'none';
              getActiveCanvas().selectNode(dep.node_id);
            });
          }
          tbody.appendChild(tr);
        });
      }
    } catch (err) {
      if (tbody) {
        tbody.innerHTML = `<tr><td colspan="6" style="padding: 16px; color: var(--color-danger); text-align: center;">Error inspecting assets: ${err.message}</td></tr>`;
      }
    }
  }
  window.openWorkflowDependenciesModal = openWorkflowDependenciesModal;

  async function openVersionHistoryModal() {
    const modal = document.getElementById('modal-workflow-revisions');
    if (!modal) return;
    const listContainer = document.getElementById('revisions-list-container');
    const diffContainer = document.getElementById('revision-diff-container');
    const nameInput = document.getElementById('workflow-name-input');
    const wfName = (nameInput ? nameInput.value.trim() : '') || 'workflow';
    const filename = `${wfName.replace(/[\s\W]+/g, '_').toLowerCase()}.json`;

    if (diffContainer) {
      diffContainer.style.display = 'none';
      diffContainer.innerHTML = '';
    }

    if (listContainer) {
      listContainer.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted);">Loading version history...</div>`;
    }
    modal.style.display = 'flex';

    // Wire up Checkpoint Commit Button
    const saveCheckpointBtn = document.getElementById('btn-save-checkpoint');
    const msgInput = document.getElementById('input-checkpoint-msg');
    const tagInput = document.getElementById('input-checkpoint-tag');
    if (saveCheckpointBtn) {
      saveCheckpointBtn.onclick = async () => {
        const msg = (msgInput ? msgInput.value.trim() : '') || 'Manual Checkpoint';
        const tag = (tagInput ? tagInput.value.trim() : '');
        const activeCanvas = getActiveCanvas();
        if (!activeCanvas) return;
        const curWf = activeCanvas.getWorkflowData();
        curWf.name = wfName;

        try {
          saveCheckpointBtn.disabled = true;
          const res = await fetch(`/api/workflow/${encodeURIComponent(filename)}/commit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workflow: curWf,
              message: msg,
              author: 'User',
              tag: tag || null
            })
          });
          const resJson = await res.json();
          if (!resJson.success) throw new Error(resJson.error || 'Failed to save checkpoint');

          if (msgInput) msgInput.value = '';
          if (tagInput) tagInput.value = '';
          if (window.showToast) window.showToast('success', 'Checkpoint Saved', `Created version '${msg}' (${resJson.saved_at}).`);
          await loadRevisionsList();
        } catch (err) {
          if (window.showToast) window.showToast('error', 'Checkpoint Error', err.message);
        } finally {
          saveCheckpointBtn.disabled = false;
        }
      };
    }

    async function loadRevisionsList() {
      try {
        const res = await fetch(`/api/workflow/${encodeURIComponent(filename)}/revisions`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Failed to load revisions');

        if (!listContainer) return;

        if (!data.revisions || data.revisions.length === 0) {
          listContainer.innerHTML = `
            <div style="padding: 30px 16px; text-align: center; color: var(--text-muted);">
              <div style="font-size: 24px; margin-bottom: 8px;">📂</div>
              <div style="font-weight: 500;">No revision history yet</div>
              <div style="font-size: 11px; margin-top: 4px;">Backups are automatically saved on workflow save, and you can create manual checkpoints anytime above.</div>
            </div>
          `;
          return;
        }

        listContainer.innerHTML = '';
        data.revisions.forEach(rev => {
          const card = document.createElement('div');
          card.className = 'revision-card';
          card.style.padding = '10px 14px';
          card.style.borderRadius = '6px';
          card.style.border = '1px solid var(--border-subtle)';
          card.style.background = 'var(--bg-hover)';
          card.style.display = 'flex';
          card.style.justifyContent = 'space-between';
          card.style.alignItems = 'center';
          card.style.gap = '12px';

          const sizeKb = (rev.size_bytes / 1024).toFixed(1);
          const tagBadge = rev.tag ? `<span style="font-size: 9px; padding: 1px 5px; border-radius: 4px; background: rgba(168, 85, 247, 0.2); color: #c084fc; font-weight: 600;">${rev.tag}</span>` : '';
          const msgDisplay = rev.commit_message ? `<div style="font-size: 11.5px; font-weight: 500; color: var(--text-primary); margin-top: 2px;">💬 ${rev.commit_message}</div>` : '';

          card.innerHTML = `
            <div style="flex: 1; overflow: hidden;">
              <div style="font-weight: 600; font-size: 12px; display: flex; align-items: center; gap: 6px;">
                <span>🕒 ${rev.timestamp}</span>
                ${tagBadge}
                <span style="font-weight: normal; color: var(--text-muted); font-size: 10.5px;">(${sizeKb} KB • ${rev.node_count || 0} tools)</span>
              </div>
              ${msgDisplay}
              <div style="font-size: 10px; color: var(--text-muted); margin-top: 3px;">
                File: <code>${rev.backup_file}</code>
              </div>
            </div>
            <div style="display: flex; gap: 6px; align-items: center;">
              <button class="btn btn-secondary btn-sm btn-inspect-diff" style="padding: 4px 8px; font-size: 10.5px;" title="View visual diff comparing to current workflow">
                Inspect Diff
              </button>
              <button class="btn btn-secondary btn-sm btn-restore-copy" style="padding: 4px 8px; font-size: 10.5px;" title="Open this revision in a new separate tab without modifying current workflow">
                Open as Copy
              </button>
              <button class="btn btn-primary btn-sm btn-restore-ver" style="padding: 4px 10px; font-size: 10.5px;" title="Revert current workflow to this revision">
                Restore
              </button>
            </div>
          `;

          // 1. Inspect Diff
          const diffBtn = card.querySelector('.btn-inspect-diff');
          diffBtn.addEventListener('click', async () => {
            if (!diffContainer) return;
            diffContainer.style.display = 'block';
            diffContainer.innerHTML = `<div style="font-size: 11px; color: var(--text-muted); text-align: center; padding: 12px;">Computing DAG diff...</div>`;
            try {
              const activeC = getActiveCanvas();
              const baseWf = activeC ? activeC.getWorkflowData() : {};
              const dRes = await fetch('/api/workflow/diff', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  base_workflow: baseWf,
                  backup_file: rev.backup_file
                })
              });
              const dJson = await dRes.json();
              if (!dJson.success) throw new Error(dJson.error || 'Failed to compute diff');

              const diff = dJson.diff;
              const s = diff.summary || {};
              let diffHtml = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 11px; font-weight: 600;">
                  <span>Diff: Current Canvas vs. Snapshot (${rev.timestamp})</span>
                  <button class="btn btn-secondary btn-sm" id="btn-close-diff" style="padding: 2px 6px; font-size: 10px;">✕ Close Diff</button>
                </div>
                <div style="display: flex; gap: 10px; margin-bottom: 8px; font-size: 11px;">
                  <span style="color: #22c55e;">+${s.added_nodes_count} Added</span>
                  <span style="color: #ef4444;">-${s.removed_nodes_count} Removed</span>
                  <span style="color: #f59e0b;">~${s.modified_nodes_count} Modified</span>
                  <span style="color: var(--text-muted);">${s.added_connections_count} wires added, ${s.removed_connections_count} wires removed</span>
                </div>
              `;

              if (s.is_identical) {
                diffHtml += `<div style="color: #22c55e; font-size: 11px; padding: 6px 0;">✓ This snapshot is identical to your current canvas.</div>`;
              } else {
                diffHtml += `<div style="display: flex; flex-direction: column; gap: 4px; font-size: 11px;">`;
                (diff.added_nodes || []).forEach(n => {
                  diffHtml += `<div style="color: #22c55e;">+ Added tool: <strong>${n.name}</strong> (${n.type})</div>`;
                });
                (diff.removed_nodes || []).forEach(n => {
                  diffHtml += `<div style="color: #ef4444;">- Removed tool: <strong>${n.name}</strong> (${n.type})</div>`;
                });
                (diff.modified_nodes || []).forEach(n => {
                  diffHtml += `<div style="color: #f59e0b;">~ Modified tool: <strong>${n.name}</strong>: ${n.changes.join('; ')}</div>`;
                });
                diffHtml += `</div>`;
              }

              diffContainer.innerHTML = diffHtml;
              const closeDiffBtn = diffContainer.querySelector('#btn-close-diff');
              if (closeDiffBtn) closeDiffBtn.onclick = () => { diffContainer.style.display = 'none'; };
            } catch (err) {
              diffContainer.innerHTML = `<div style="color: var(--color-danger); font-size: 11px; padding: 8px;">Error generating diff: ${err.message}</div>`;
            }
          });

          // 2. Open as Copy (New Tab)
          const copyBtn = card.querySelector('.btn-restore-copy');
          copyBtn.addEventListener('click', async () => {
            try {
              const revRes = await fetch(`/api/workflow/revision/${encodeURIComponent(rev.backup_file)}`);
              const revJson = await revRes.json();
              if (!revJson.success) throw new Error(revJson.error || 'Failed to fetch revision');

              const branchName = `${wfName} (Rev ${rev.timestamp.replace(/[: ]/g, '-')})`;
              if (window.appTabManager) {
                window.appTabManager.createTab(revJson.workflow, branchName);
              } else {
                handleWorkflowLoaded(revJson.workflow, branchName);
              }
              modal.style.display = 'none';
              if (window.showToast) window.showToast('success', 'Revision Opened', `Opened revision as a new workflow tab.`);
            } catch (err) {
              if (window.showToast) window.showToast('error', 'Open Failed', err.message);
            }
          });

          // 3. Restore This Version
          const restoreBtn = card.querySelector('.btn-restore-ver');
          restoreBtn.addEventListener('click', async () => {
            if (!confirm(`Revert to revision from ${rev.timestamp}?\n\nA safety snapshot of your current state will be created automatically before reverting.`)) {
              return;
            }
            try {
              const revRes = await fetch(`/api/workflow/${encodeURIComponent(filename)}/revert`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ backup_file: rev.backup_file })
              });
              const revJson = await revRes.json();
              if (!revJson.success) throw new Error(revJson.error || 'Failed to restore revision');

              handleWorkflowLoaded(revJson.workflow, wfName);
              modal.style.display = 'none';
              window.showToast('success', 'Revision Restored', `Workflow reverted to snapshot from ${rev.timestamp}.`);
            } catch (e) {
              window.showToast('error', 'Restore Failed', e.message);
            }
          });

          listContainer.appendChild(card);
        });
      } catch (err) {
        if (listContainer) {
          listContainer.innerHTML = `<div style="padding: 16px; color: var(--color-danger); text-align: center;">Failed to load revisions: ${err.message}</div>`;
        }
      }
    }

    await loadRevisionsList();
  }
  window.openVersionHistoryModal = openVersionHistoryModal;

  function openWorkflowPropertiesModal() {
    const modal = document.getElementById('modal-workflow-props');
    if (!modal) return;
    const activeCanvas = getActiveCanvas();
    const wfData = activeCanvas ? activeCanvas.getWorkflowData() : { nodes: [], connections: [] };
    const metadata = wfData.metadata || {};

    const nameInput = document.getElementById('prop-wf-name');
    const authorInput = document.getElementById('prop-wf-author');
    const versionInput = document.getElementById('prop-wf-version');
    const descInput = document.getElementById('prop-wf-desc');
    const statNodes = document.getElementById('stat-node-count');
    const statConns = document.getElementById('stat-conn-count');
    const statZoom = document.getElementById('stat-viewport-zoom');

    const topNameInput = document.getElementById('workflow-name-input');
    if (nameInput) nameInput.value = (topNameInput ? topNameInput.value.trim() : '') || wfData.name || 'Workflow';
    if (authorInput) authorInput.value = metadata.author || '';
    if (versionInput) versionInput.value = metadata.version || '2.1.0';
    if (descInput) descInput.value = metadata.description || wfData.description || '';

    if (statNodes) statNodes.textContent = (wfData.nodes || []).length;
    if (statConns) statConns.textContent = (wfData.connections || []).length;
    if (statZoom) statZoom.textContent = `${Math.round(((activeCanvas && activeCanvas.zoom) || 1.0) * 100)}%`;

    modal.style.display = 'flex';
  }
  window.openWorkflowPropertiesModal = openWorkflowPropertiesModal;

  const btnSaveProps = document.getElementById('btn-save-workflow-props');
  if (btnSaveProps) {
    btnSaveProps.addEventListener('click', () => {
      const modal = document.getElementById('modal-workflow-props');
      const nameInput = document.getElementById('prop-wf-name');
      const authorInput = document.getElementById('prop-wf-author');
      const versionInput = document.getElementById('prop-wf-version');
      const descInput = document.getElementById('prop-wf-desc');

      const newName = nameInput ? nameInput.value.trim() : '';
      if (newName) {
        const topNameInput = document.getElementById('workflow-name-input');
        if (topNameInput) topNameInput.value = newName;
      }

      const activeCanvas = getActiveCanvas();
      if (activeCanvas) {
        if (!activeCanvas.workflowMetadata) activeCanvas.workflowMetadata = {};
        activeCanvas.workflowMetadata.author = authorInput ? authorInput.value.trim() : '';
        activeCanvas.workflowMetadata.version = versionInput ? versionInput.value.trim() : '2.1.0';
        activeCanvas.workflowMetadata.description = descInput ? descInput.value.trim() : '';
      }

      markWorkflowDirty();
      if (modal) modal.style.display = 'none';
      window.showToast('info', 'Properties Updated', 'Workflow properties updated.');
    });
  }

  // --------------------------------------------------------------------
  // Workflow-to-SQL Pushdown Modal Controller
  // --------------------------------------------------------------------
  const activeSqlState = {
    sql: '',
    dialect: 'ansi',
    tableMappings: {},
    includeComments: true
  };

  function highlightSql(rawSql) {
    if (!rawSql) return '';
    let s = rawSql
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // 1. Comments
    s = s.replace(/(--[^\n]*)/g, '<span class="sql-comment">$1</span>');

    // 2. Strings
    s = s.replace(/('([^'\\]|\\.)*')/g, '<span class="sql-str">$1</span>');

    // 3. CTE Identifiers before AS (
    s = s.replace(/\b(cte_[a-zA-Z0-9_]+)\s+AS\s+\(/gi, '<span class="sql-cte">$1</span> <span class="sql-kw">AS</span> (');

    // 4. SQL Keywords
    const keywords = [
      'WITH', 'SELECT', 'FROM', 'WHERE', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN',
      'FULL JOIN', 'CROSS JOIN', 'JOIN', 'ON', 'GROUP BY', 'ORDER BY', 'ASC', 'DESC',
      'UNION ALL', 'UNION', 'LIMIT', 'OFFSET', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
      'AND', 'OR', 'NOT', 'IS NULL', 'IS NOT NULL', 'AS', 'IN', 'BETWEEN', 'LIKE', 'ILIKE',
      'PARTITION BY', 'OVER'
    ];
    keywords.forEach(kw => {
      const regex = new RegExp(`\\b(${kw})\\b`, 'gi');
      s = s.replace(regex, (match) => `<span class="sql-kw">${match.toUpperCase()}</span>`);
    });

    // 5. Functions
    const functions = [
      'COUNT', 'SUM', 'AVG', 'MIN', 'MAX', 'ROW_NUMBER', 'CAST', 'TRY_CAST',
      'COALESCE', 'TRIM', 'UPPER', 'LOWER', 'SUBSTR', 'SUBSTRING', 'LEFT', 'RIGHT',
      'ROUND', 'ABS', 'CEIL', 'FLOOR', 'CONCAT', 'EXTRACT', 'STRFTIME',
      'CURRENT_TIMESTAMP', 'CURRENT_DATE', 'READ_CSV_AUTO', 'REPLACE'
    ];
    functions.forEach(fn => {
      const regex = new RegExp(`\\b(${fn})\\s*\\(`, 'gi');
      s = s.replace(regex, (match, p1) => `<span class="sql-fn">${p1.toUpperCase()}</span>(`);
    });

    return s;
  }

  function switchSqlTab(tabName) {
    const btnScript = document.getElementById('tab-btn-sql-script');
    const btnTables = document.getElementById('tab-btn-sql-tables');
    const paneScript = document.getElementById('tab-pane-sql-script');
    const paneTables = document.getElementById('tab-pane-sql-tables');

    if (tabName === 'tables') {
      if (btnTables) btnTables.classList.add('active');
      if (btnScript) btnScript.classList.remove('active');
      if (paneTables) paneTables.style.display = 'block';
      if (paneScript) paneScript.style.display = 'none';
    } else {
      if (btnScript) btnScript.classList.add('active');
      if (btnTables) btnTables.classList.remove('active');
      if (paneScript) paneScript.style.display = 'flex';
      if (paneTables) paneTables.style.display = 'none';
    }
  }

  function renderSqlTableMappings() {
    const container = document.getElementById('sql-table-mappings-list');
    if (!container) return;

    const inputNodes = [];
    const activeCanvas = getActiveCanvas();
    if (activeCanvas && activeCanvas.nodes) {
      activeCanvas.nodes.forEach(node => {
        if (node.type === 'input_data') {
          inputNodes.push(node);
        }
      });
    }

    if (inputNodes.length === 0) {
      container.innerHTML = `
        <div style="padding: 20px; text-align: center; color: var(--text-muted); background: var(--bg-hover); border-radius: 6px;">
          No <strong>Input Data</strong> nodes present in this workflow.
        </div>
      `;
      return;
    }

    let html = `
      <table style="width: 100%; border-collapse: collapse; font-size: 11.5px;">
        <thead>
          <tr style="border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); text-align: left;">
            <th style="padding: 6px 10px;">Tool</th>
            <th style="padding: 6px 10px;">Local Filepath / Name</th>
            <th style="padding: 6px 10px;">Database Table / View Mapping</th>
          </tr>
        </thead>
        <tbody>
    `;

    inputNodes.forEach(n => {
      const toolName = n.name || 'Input Data';
      const fp = (n.config && (n.config.filepath || n.config.file_name)) || 'Unnamed input file';
      const currentMap = activeSqlState.tableMappings[n.id] || '';
      const basePart = fp.split(/[\/\\]/).pop() || 'table_name';
      const placeholder = basePart.replace(/\.[^/.]+$/, '');

      html += `
        <tr style="border-bottom: 1px solid var(--border-subtle);">
          <td style="padding: 8px 10px; font-weight: 600; color: var(--color-primary);">${toolName}</td>
          <td style="padding: 8px 10px; color: var(--text-secondary);"><code style="font-size: 11px;">${fp}</code></td>
          <td style="padding: 8px 10px;">
            <input type="text" class="form-control form-control-sm sql-mapping-input" 
              data-node-id="${n.id}" 
              value="${currentMap}" 
              placeholder='e.g. "PROD_DB"."ANALYTICS"."${placeholder.toUpperCase()}"' 
              style="width: 100%; font-family: 'JetBrains Mono', monospace; font-size: 11px;">
          </td>
        </tr>
      `;
    });

    html += `</tbody></table>`;
    container.innerHTML = html;

    container.querySelectorAll('.sql-mapping-input').forEach(inp => {
      inp.addEventListener('input', (e) => {
        const nid = e.target.dataset.nodeId;
        const val = e.target.value.trim();
        if (val) {
          activeSqlState.tableMappings[nid] = val;
        } else {
          delete activeSqlState.tableMappings[nid];
        }
      });
      inp.addEventListener('change', () => {
        refreshSqlPreview();
      });
    });
  }

  async function refreshSqlPreview() {
    const codeEl = document.getElementById('export-sql-code');
    const statsSummary = document.getElementById('sql-stats-summary');
    const statsTerminal = document.getElementById('sql-stats-terminal');
    const dialectSelect = document.getElementById('sql-dialect-select');
    const commentsCheck = document.getElementById('sql-opt-comments');

    if (codeEl) codeEl.textContent = '-- Compiling visual workflow into SQL...';

    const dialect = dialectSelect ? dialectSelect.value : 'ansi';
    const includeComments = commentsCheck ? commentsCheck.checked : true;
    activeSqlState.dialect = dialect;
    activeSqlState.includeComments = includeComments;

    const nameInput = document.getElementById('workflow-name-input');
    const wfName = (nameInput ? nameInput.value.trim() : '') || 'Workflow';
    const activeCanvas = getActiveCanvas();
    const wfData = activeCanvas ? activeCanvas.getWorkflowData() : { nodes: [], connections: [] };
    wfData.name = wfName;

    try {
      const res = await fetch('/api/workflow/to-sql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workflow: wfData,
          dialect: dialect,
          options: {
            table_mappings: activeSqlState.tableMappings,
            include_comments: includeComments
          }
        })
      });

      const data = await res.json();
      if (!data.success) {
        throw new Error(data.error || 'Compilation error');
      }

      activeSqlState.sql = data.sql;
      if (codeEl) {
        codeEl.innerHTML = highlightSql(data.sql);
      }
      if (statsSummary) {
        statsSummary.innerHTML = `<strong style="color: var(--color-primary);">CTEs:</strong> ${data.ctes_generated} generated &bull; <strong>Dialect:</strong> ${data.dialect.toUpperCase()}`;
      }
      if (statsTerminal) {
        statsTerminal.innerHTML = `<strong>Terminal Output:</strong> <code>${data.terminal_cte || 'N/A'}</code>`;
      }
    } catch (err) {
      if (codeEl) {
        codeEl.textContent = `-- Error compiling SQL: ${err.message}`;
      }
      if (statsSummary) statsSummary.textContent = 'Compilation Failed';
    }
  }

  async function openExportSqlModal() {
    const modal = document.getElementById('modal-export-sql');
    if (!modal) return;

    modal.style.display = 'flex';
    switchSqlTab('script');
    renderSqlTableMappings();
    await refreshSqlPreview();
  }
  window.openExportSqlModal = openExportSqlModal;

  // SQL Modal Wireup
  const tabBtnScript = document.getElementById('tab-btn-sql-script');
  if (tabBtnScript) tabBtnScript.addEventListener('click', () => switchSqlTab('script'));
  const tabBtnTables = document.getElementById('tab-btn-sql-tables');
  if (tabBtnTables) tabBtnTables.addEventListener('click', () => switchSqlTab('tables'));

  const dialectSelect = document.getElementById('sql-dialect-select');
  if (dialectSelect) dialectSelect.addEventListener('change', refreshSqlPreview);
  const commentsCheck = document.getElementById('sql-opt-comments');
  if (commentsCheck) commentsCheck.addEventListener('change', refreshSqlPreview);

  const topExportSqlBtn = document.getElementById('btn-top-export-sql');
  if (topExportSqlBtn) topExportSqlBtn.addEventListener('click', openExportSqlModal);

  const copySqlBtn = document.getElementById('btn-copy-sql');
  if (copySqlBtn) {
    copySqlBtn.addEventListener('click', async () => {
      if (!activeSqlState.sql) return;
      try {
        await navigator.clipboard.writeText(activeSqlState.sql);
        const txt = document.getElementById('copy-sql-text');
        if (txt) txt.textContent = '✓ Copied!';
        if (window.showToast) window.showToast('success', 'SQL Copied', 'SQL script copied to clipboard.');
        setTimeout(() => {
          if (txt) txt.textContent = 'Copy SQL';
        }, 2000);
      } catch (err) {
        if (window.showToast) window.showToast('error', 'Copy Failed', err.message);
      }
    });
  }

  const downloadSqlBtn = document.getElementById('btn-download-sql');
  if (downloadSqlBtn) {
    downloadSqlBtn.addEventListener('click', async () => {
      if (!activeSqlState.sql) await refreshSqlPreview();
      const nameInput = document.getElementById('workflow-name-input');
      const wfName = (nameInput ? nameInput.value.trim() : '') || 'workflow';
      const filename = `${wfName.replace(/[\s\W]+/g, '_').toLowerCase()}.sql`;

      try {
        const blob = new Blob([activeSqlState.sql], { type: 'application/sql' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        if (window.showToast) window.showToast('success', 'SQL Downloaded', `Saved as '${filename}'.`);
      } catch (err) {
        if (window.showToast) window.showToast('error', 'Download Failed', err.message);
      }
    });
  }

  const saveBtn = document.getElementById('btn-save');
  if (saveBtn) {
    saveBtn.addEventListener('click', saveWorkflow);
  }

  // Template Library
  window.templateLibrary = new TemplateLibrary();
  const btnTemplates = document.getElementById('btn-templates');
  if (btnTemplates) {
    btnTemplates.addEventListener('click', () => window.templateLibrary.show());
  }

  // Open Button & Dropdown Wireup
  const openDirectBtn = document.getElementById('btn-open-direct');
  if (openDirectBtn) {
    openDirectBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openWorkflowFileDialog();
    });
  }

  const openBtn = document.getElementById('btn-open-menu');
  const openMenu = document.getElementById('open-menu');

  if (openBtn && openMenu) {
    openBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      openMenu.classList.toggle('show');
    });

    window.addEventListener('click', () => {
      openMenu.classList.remove('show');
    });
  }

  async function refreshSavedWorkflows() {
    const savedList = document.getElementById('saved-workflows-list');
    if (!savedList) return;

    try {
      const res = await fetch('/api/samples');
      const data = await res.json();
      const workflows = data.workflows || [];

      if (workflows.length === 0) {
        savedList.innerHTML = `<div style="padding: 8px 12px; font-size: 11px; color: var(--text-muted);">No saved workflows yet</div>`;
        return;
      }

      savedList.innerHTML = '';
      workflows.forEach(wf => {
        const item = document.createElement('button');
        item.className = 'dropdown-item';
        const dateStr = wf.modified ? ` &bull; ${typeof wf.modified === 'number' ? new Date(wf.modified * 1000).toLocaleDateString() : wf.modified}` : '';
        item.innerHTML = `
          <span class="dropdown-item-title">${wf.name}</span>
          <span class="dropdown-item-sub">${wf.node_count || 0} tools${dateStr}</span>
        `;
        item.addEventListener('click', () => {
          loadWorkflowFromServer(wf.file);
          if (openMenu) openMenu.classList.remove('show');
        });
        savedList.appendChild(item);
      });
    } catch (err) {
      console.warn('Failed to refresh saved workflows:', err);
    }
  }
  window.refreshSavedWorkflows = refreshSavedWorkflows;

  // btn-load-file click → delegates to openWorkflowFileDialog (registered by initWorkflowIO)
  const loadFileBtn = document.getElementById('btn-load-file');
  if (loadFileBtn) {
    loadFileBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (openMenu) openMenu.classList.remove('show');
      openWorkflowFileDialog();
    });
  }

  // fileInput.change is handled by initWorkflowIO() in workflow_io.js

  // Package Input (.zip / .yxzp)
  const packageFileInput = document.getElementById('input-package-file');
  const loadPackageBtn = document.getElementById('btn-load-package');
  if (loadPackageBtn && packageFileInput) {
    loadPackageBtn.addEventListener('click', () => {
      packageFileInput.click();
      if (openMenu) openMenu.classList.remove('show');
    });
  }

  if (packageFileInput) {
    packageFileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        importWorkflowPackage(file);
      }
      packageFileInput.value = '';
    });
  }

  const depsExportBtn = document.getElementById('btn-deps-export-package');
  if (depsExportBtn) {
    depsExportBtn.addEventListener('click', () => {
      exportWorkflowPackage();
    });
  }

  // ====================================================================
  // Centralized Application Command Registry
  // ====================================================================
  const app = {
    async executeCommand(commandId) {
      if (!commandId || typeof commandId !== 'string') return;
      const cmd = commandId.trim().toLowerCase();
      const normCmd = cmd.replace(/_/g, '-');

      switch (normCmd) {
        // --- FILE ---
        case 'file:new':
          // Opens a new blank tab (Ctrl+N)
          if (window.appTabManager) {
            window.appTabManager.createTab(null, 'New Workflow');
          } else if (!isWorkflowDirty || confirm('Create a new blank workflow? Any unsaved changes will be cleared.')) {
            const curC = getActiveCanvas();
            if (curC) {
              curC.loadWorkflow({ nodes: [], connections: [] });
              if (curC.cachedNodeIds) curC.cachedNodeIds.clear();
            }
            resultsPanel.clear();
            configPanel.render(null);
            const nameInput = document.getElementById('workflow-name-input');
            if (nameInput) nameInput.value = 'New Workflow';
            markWorkflowClean();
            if (window.appHistory) window.appHistory.pushSnapshot('New Workflow');
            if (window.showToast) window.showToast('info', 'New Workflow', 'Created blank canvas.');
          }
          break;

        // --- TABS ---
        case 'tab:new':
          if (window.appTabManager) {
            window.appTabManager.createTab(null, 'New Workflow');
          }
          break;

        case 'tab:close':
          if (window.appTabManager) {
            window.appTabManager.closeTab(window.appTabManager.activeTabId);
          }
          break;

        case 'tab:next':
          if (window.appTabManager) window.appTabManager.activateNextTab();
          break;

        case 'tab:prev':
          if (window.appTabManager) window.appTabManager.activatePrevTab();
          break;

        case 'file:open':
          openWorkflowFileDialog();
          break;

        case 'file:templates':
        case 'help:templates':
          if (window.templateLibrary) {
            window.templateLibrary.show();
          }
          break;

        case 'file:save':
          saveWorkflow();
          break;
          saveWorkflow();
          break;

        case 'file:save-as':
          saveWorkflowAs();
          break;

        case 'file:export-json':
          exportWorkflowJson();
          break;

        case 'file:export-package':
          exportWorkflowPackage();
          break;

        case 'file:export-sql':
        case 'workflow:export-sql':
          openExportSqlModal();
          break;

        case 'file:import-package': {
          const pkgInput = document.getElementById('input-package-file');
          if (pkgInput) pkgInput.click();
          break;
        }

        case 'file:revisions':
          openVersionHistoryModal();
          break;

        case 'file:properties':
          openWorkflowPropertiesModal();
          break;

        case 'file:clear': {
          const clearBtn = document.getElementById('btn-clear');
          if (clearBtn) clearBtn.click();
          break;
        }

        case 'file:exit':
        case 'app:exit':
          showExitConfirmationDialog();
          break;

        // --- EDIT ---
        case 'edit:undo':
          if (window.appHistory) window.appHistory.undo();
          break;

        case 'edit:redo':
          if (window.appHistory) window.appHistory.redo();
          break;

        case 'edit:cut':
          getActiveCanvas()?.cutSelection();
          break;

        case 'edit:copy':
          getActiveCanvas()?.copySelection();
          break;

        case 'edit:paste':
          getActiveCanvas()?.pasteClipboard();
          break;

        case 'edit:duplicate':
          getActiveCanvas()?.duplicateSelected();
          break;

        case 'edit:delete':
          getActiveCanvas()?.deleteSelected();
          break;

        case 'edit:select-all':
          getActiveCanvas()?.selectAll();
          break;

        case 'edit:find':
          getActiveCanvas()?.openSpotlight();
          break;

        // --- VIEW ---
        case 'view:toggle-palette': {
          const paletteEl = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
          if (paletteEl) {
            const isHidden = paletteEl.style.display === 'none';
            const willShow = isHidden;
            paletteEl.style.display = willShow ? 'flex' : 'none';
            if (window.userSettings) window.userSettings.set('palette_visible', willShow);
            localStorage.setItem('dataflow_palette_visible', willShow ? 'true' : 'false');
            if (window.appMenuBar) window.appMenuBar.syncMenuStates();
            if (window.showToast) {
              window.showToast('info', 'Tool Palette', `Tool Palette ${willShow ? 'Shown' : 'Hidden'}.`);
            }
          }
          break;
        }

        case 'view:toggle-config': {
          const configEl = document.getElementById('config-panel') || document.getElementById('config-sidebar');
          if (configEl) {
            const isHidden = configEl.style.display === 'none';
            const willShow = isHidden;
            configEl.style.display = willShow ? 'flex' : 'none';
            if (window.userSettings) window.userSettings.set('config_visible', willShow);
            localStorage.setItem('dataflow_config_visible', willShow ? 'true' : 'false');
            if (window.appMenuBar) window.appMenuBar.syncMenuStates();
            if (window.showToast) {
              window.showToast('info', 'Configuration Panel', `Configuration Panel ${willShow ? 'Shown' : 'Hidden'}.`);
            }
          }
          break;
        }

        case 'view:toggle-results': {
          const resultsEl = document.getElementById('results-panel');
          if (resultsEl) {
            const isCollapsed = resultsEl.classList.toggle('collapsed');
            const willShow = !isCollapsed;
            if (window.userSettings) window.userSettings.set('results_visible', willShow);
            localStorage.setItem('dataflow_results_visible', willShow ? 'true' : 'false');
            if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          }
          break;
        }

        case 'view:toggle-histograms': {
          const histBtn = document.getElementById('btn-toggle-histograms');
          if (histBtn) {
            histBtn.click();
          } else if (resultsPanel) {
            resultsPanel.showHistograms = !resultsPanel.showHistograms;
            resultsPanel.renderGrid();
          }
          if (resultsPanel) {
            if (window.userSettings) window.userSettings.set('show_histograms', resultsPanel.showHistograms);
            localStorage.setItem('dataflow_show_histograms', resultsPanel.showHistograms ? 'true' : 'false');
          }
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          break;
        }

        case 'view:zoom-in':
        case 'view:ui-zoom-in':
          // Keyboard: Ctrl+NumpadAdd / Ctrl+Equal (see keyboard_shortcuts.js)
          zoomUIIn();
          break;

        case 'view:zoom-out':
        case 'view:ui-zoom-out':
          // Keyboard: Ctrl+NumpadSubtract / Ctrl+Minus (see keyboard_shortcuts.js)
          zoomUIOut();
          break;

        case 'view:zoom-reset':
        case 'view:ui-zoom-reset':
          // Keyboard: Ctrl+Numpad0 / Ctrl+Digit0 (see keyboard_shortcuts.js)
          resetUIZoom();
          break;

        case 'view:canvas-zoom-in':
          getActiveCanvas()?.zoomIn();
          break;

        case 'view:canvas-zoom-out':
          getActiveCanvas()?.zoomOut();
          break;

        case 'view:canvas-zoom-reset':
          getActiveCanvas()?.resetZoom();
          break;

        case 'view:canvas-zoom-fit':
        case 'view:zoom-fit':
          getActiveCanvas()?.zoomToFit();
          break;

        case 'view:autolayout': {
          const curC = getActiveCanvas();
          if (curC && curC.selectedNodeIds && curC.selectedNodeIds.size > 1) {
            curC.alignSelectedNodes();
          } else {
            curC?.autoLayout();
            if (window.showToast) window.showToast('info', 'Flow Aligned', 'Arranged workflow nodes in clean layers.');
          }
          break;
        }

        case 'canvas:align-selected':
        case 'view:align-selected': {
          const curC = getActiveCanvas();
          if (curC) {
            curC.alignSelectedNodes();
          }
          break;
        }

        case 'view:toggle-overview':
        case 'view:toggle_overview':
          if (window.appMiniMap) {
            window.appMiniMap.toggle();
          }
          break;

        case 'view:reset-panels': {
          localStorage.removeItem('dataflow_panel_dimensions');
          if (window.userSettings) {
            window.userSettings.set('panel_dimensions', {});
            window.userSettings.set('palette_visible', true);
            window.userSettings.set('config_visible', true);
            window.userSettings.set('results_visible', true);
            window.userSettings.set('minimap_visible', true);
          }
          const paletteEl = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
          if (paletteEl) {
            paletteEl.style.display = 'flex';
            paletteEl.style.height = '';
          }
          const configEl = document.getElementById('config-panel') || document.getElementById('config-sidebar');
          if (configEl) {
            configEl.style.display = 'flex';
            configEl.style.width = '';
          }
          const resultsEl = document.getElementById('results-panel');
          if (resultsEl) {
            resultsEl.classList.remove('collapsed');
            resultsEl.style.height = '';
          }
          if (window.appMiniMap) {
            window.appMiniMap.toggle(true);
            window.appMiniMap.render();
          }
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          if (window.showToast) window.showToast('info', 'Panels Reset', 'Restored default panels layout and dimensions.');
          break;
        }

        case 'view:toggle-wire-probes':
        case 'view:toggle_probes':
        case 'options:toggle-wire-probes': {
          const curC = getActiveCanvas();
          if (curC) curC.setWireProbesEnabled(!curC.wireProbesEnabled);
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          break;
        }

        case 'view:toggle-node-tooltips': {
          const curC = getActiveCanvas();
          if (curC) {
            curC.setNodeTooltipsEnabled(!curC.nodeTooltipsEnabled);
            if (window.showToast) {
              window.showToast('info', 'Node Tooltips', `Node tooltips are now ${curC.nodeTooltipsEnabled ? 'Enabled' : 'Disabled'}.`);
            }
          }
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          break;
        }

        case 'view:toggle-wireless-tooltips': {
          const curC = getActiveCanvas();
          if (curC) {
            curC.setWirelessTooltipsEnabled(!curC.wirelessTooltipsEnabled);
            if (window.showToast) {
              window.showToast('info', 'Wireless Tooltips', `Wireless connection tooltips are now ${curC.wirelessTooltipsEnabled ? 'Enabled' : 'Disabled'}.`);
            }
          }
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          break;
        }

        case 'view:badge-duration:3000':
        case 'view:badge-duration:5000':
        case 'view:badge-duration:10000':
        case 'view:badge-duration:always':
        case 'view:badge-duration:off': {
          const durationVal = commandId.replace('view:badge-duration:', '');
          getActiveCanvas()?.setNodeBadgeDuration(durationVal);
          if (window.appMenuBar) window.appMenuBar.syncMenuStates();
          const labelMap = {
            '3000': '3 seconds auto-hide',
            '5000': '5 seconds auto-hide',
            '10000': '10 seconds auto-hide',
            'always': 'always visible',
            'off': 'hidden'
          };
          if (window.showToast) window.showToast('info', 'Execution Badges', `Execution status badge set to ${labelMap[durationVal] || durationVal}.`);
          break;
        }

        // --- OPTIONS ---
        case 'options:dependencies':
          openWorkflowDependenciesModal();
          break;

        case 'options:database-connections':
        case 'options:connections':
          if (window.openDatabaseConnectionsModal) {
            window.openDatabaseConnectionsModal();
          }
          break;

        case 'options:user-settings':
          if (window.appMenuBar) window.appMenuBar.openUserSettingsModal();
          break;

        case 'options:purge-cache': {
          try {
            const res = await fetch('/api/cache/purge', { method: 'POST' });
            const data = await res.json();
            if (data.success) {
              if (resultsPanel) resultsPanel.clear();
              if (window.showToast) {
                const memNote = data.process_memory_mb ? ` (Process RAM: ${data.process_memory_mb} MB)` : '';
                window.showToast('success', 'Cache Purged', `${data.message}${memNote}`);
              }
            } else {
              if (window.showToast) window.showToast('error', 'Purge Failed', data.message || 'Error purging cache.');
            }
          } catch (err) {
            if (window.showToast) window.showToast('error', 'Purge Error', err.message);
          }
          break;
        }

        // --- HELP ---
        case 'help:shortcuts':
          if (window.appMenuBar) window.appMenuBar.openModal('modal-shortcuts');
          break;

        case 'help:about':
          fetch('/api/app-info').then(r => r.json()).then(info => {
            const el = document.getElementById('about-version-number');
            if (el && info.version) el.textContent = info.version;
          }).catch(() => {});
          if (window.appMenuBar) window.appMenuBar.openModal('modal-about');
          break;

        case 'help:check-updates':
          // New versions are published on the Releases page; the server opens the fixed URL in the default browser.
          fetch('/api/open-releases', { method: 'POST' }).then(r => r.json()).then(res => {
            if (res && res.success) window.showToast('info', 'Check for Updates', 'The releases page opened in your browser. Install the newest version if it is higher than the one in Help > About.');
            else window.showToast('warning', 'Check for Updates', `Open ${(res && res.url) || 'the Releases page on GitHub'} in your browser.`);
          }).catch(() => window.showToast('warning', 'Check for Updates', 'Could not open the browser. Open the Releases page on GitHub manually.'));
          break;

        case 'help:export-diagnostics':
          // Logs + version + redacted settings only; never workflows, data or keys.
          if (window.safeDownloadFile) window.safeDownloadFile('/api/diagnostics/export', 'dataflow_support_bundle.zip');
          break;

        // --- WORKFLOW EXECUTION ---
        case 'workflow:run':
          runWorkflow();
          break;

        case 'workflow:cancel':
        case 'workflow:stop':
          if (window._isWorkflowRunning) {
            stopWorkflow();
          }
          break;

        default:
          console.warn('Unknown application command:', commandId);
      }
    }
  };
  window.app = app;
  registerKeyboardShortcuts();

  // Auto-Layout Flow
  const autoLayoutBtn = document.getElementById('btn-autolayout');
  if (autoLayoutBtn) {
    autoLayoutBtn.addEventListener('click', () => {
      const curC = getActiveCanvas();
      if (!curC) return;
      if (curC.selectedNodeIds && curC.selectedNodeIds.size > 1) {
        curC.alignSelectedNodes();
      } else {
        curC.autoLayout();
        window.showToast('info', 'Flow Aligned', 'Arranged workflow nodes in clean left-to-right execution layers.');
      }
    });
  }


  // Clear Canvas
  const clearBtn = document.getElementById('btn-clear');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (confirm('Clear entire workflow canvas?')) {
        const curC = getActiveCanvas();
        if (curC) {
          curC.loadWorkflow({ nodes: [], connections: [] });
          if (curC.cachedNodeIds) curC.cachedNodeIds.clear();
        }
        resultsPanel.clear();
        configPanel.render(null);
        if (window.appHistory) {
          window.appHistory.pushSnapshot('Clear Canvas');
        }
        window.showToast('info', 'Canvas Cleared', 'All tools and wires have been removed.');
      }
    });
  }

  // Zoom controls
  const zoomInBtn = document.getElementById('btn-zoom-in');
  const zoomOutBtn = document.getElementById('btn-zoom-out');
  const zoomResetBtn = document.getElementById('btn-zoom-reset');
  const zoomText = document.getElementById('zoom-level-text');
  if (zoomInBtn) zoomInBtn.addEventListener('click', () => getActiveCanvas()?.zoomIn());
  if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => getActiveCanvas()?.zoomOut());
  if (zoomResetBtn) zoomResetBtn.addEventListener('click', () => getActiveCanvas()?.resetZoom());
  if (zoomText) {
    zoomText.style.cursor = 'pointer';
    zoomText.title = 'Click to reset (100%), double-click to fit workflow in view';
    zoomText.addEventListener('click', () => getActiveCanvas()?.resetZoom());
    zoomText.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      getActiveCanvas()?.zoomToFit();
    });
  }

  // 7. Split Pane Resizers
  setupResizers();

  // 8. Sample Workflows & Datasets Loader
  async function loadSampleWorkflow(filename) {
    try {
      const res = await fetch(`/api/sample-workflow/${filename}`);
      const data = await res.json();
      const filePath = data._path || `workflows/${filename}`;
      const name = data._filename || filename;
      openWorkflowData(data, name, filePath, null);
      runWorkflow();
    } catch (err) {
      console.error('Failed to load sample workflow:', err);
    }
  }

  // 9. Fetch Tools & Samples Metadata
  try {
    const [toolsRes, samplesRes] = await Promise.all([
      fetch('/api/tools'),
      fetch('/api/samples')
    ]);

    const toolsData = await toolsRes.json();
    const samplesData = await samplesRes.json();

    palette.setTools(toolsData.tools);
    canvas.setToolsRegistry(toolsData.tools);
    configPanel.setSampleDatasets(samplesData.datasets || []);

    // Global toolRegistry cache for instant lookup across all tabs and components
    window.toolRegistry = {};
    (toolsData.tools || []).forEach(t => {
      window.toolRegistry[t.type] = t;
    });
    window.toolsData = toolsData.tools;

    // Store tools + datasets on TabManager so new tabs inherit them
    if (window.appTabManager) {
      window.appTabManager._toolsData = toolsData.tools;
      window.appTabManager._sampleDatasets = samplesData.datasets || [];
    }

    await refreshSavedWorkflows();
    
    // 10. Check if a specific initial workflow was specified via CLI (--open) or query param (?open=...)
    let initialLoaded = false;
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const openParam = urlParams.get('open');
      const url = openParam ? `/api/initial-workflow?open=${encodeURIComponent(openParam)}` : '/api/initial-workflow';
      const initRes = await fetch(url);
      if (initRes.ok) {
        const initData = await initRes.json();
        if (initData.workflow) {
          openWorkflowData(initData.workflow, initData.name || 'Workflow', initData.path, null);
          initialLoaded = true;
          runWorkflow();
        }
      }
    } catch (e) {
      console.warn('Initial workflow check failed:', e);
    }

    // Check for crash recovery autosave, or auto-load default sample workflow if none
    if (!initialLoaded) {
      const recovered = await checkAutoSaveRecovery();
      if (!recovered && samplesData.workflows && samplesData.workflows.length > 0) {
        await loadSampleWorkflow(samplesData.workflows[0].file);
      }
    }

    if (window.appMenuBar && typeof window.appMenuBar.syncMenuStates === 'function') {
      window.appMenuBar.syncMenuStates();
    }
  } catch (err) {
    console.error('Metadata fetch error:', err);
  } finally {
    // Startup (metadata, initial/sample workflow load) is finished; UI automation can rely on this.
    window.appReady = true;
  }
});

/**
 * Handles resizable dividers for Palette, Left Configuration panel, and Bottom Results panel.
 * Supports smooth dragging, min/max constraints, and layout persistence in localStorage.
 */
function setupResizers() {
  const resizerTop = document.getElementById('resizer-top');
  const paletteRibbon = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
  const resizerLeft = document.getElementById('resizer-left');
  const configPanel = document.getElementById('config-panel') || document.getElementById('config-sidebar');
  const resizerBottom = document.getElementById('resizer-bottom');
  const resultsPanel = document.getElementById('results-panel');

  // Load saved dimensions from userSettings (falls back to localStorage)
  let savedDims = null;
  try {
    if (window.userSettings) {
      savedDims = window.userSettings.get('panel_dimensions', null);
    } else {
      const raw = localStorage.getItem('dataflow_panel_dimensions');
      if (raw) savedDims = JSON.parse(raw);
    }
  } catch (err) {
    console.warn('Failed to parse saved panel dimensions', err);
  }

  if (savedDims) {
    if (paletteRibbon && savedDims.paletteHeight) {
      paletteRibbon.style.height = `${savedDims.paletteHeight}px`;
    }
    if (configPanel && savedDims.configWidth) {
      configPanel.style.width = `${savedDims.configWidth}px`;
    }
    if (resultsPanel && savedDims.resultsHeight) {
      resultsPanel.style.height = `${savedDims.resultsHeight}px`;
    }
  }

  function saveDimensions() {
    const dims = {};
    if (paletteRibbon && paletteRibbon.offsetHeight) dims.paletteHeight = paletteRibbon.offsetHeight;
    if (configPanel && configPanel.offsetWidth) dims.configWidth = configPanel.offsetWidth;
    if (resultsPanel && resultsPanel.offsetHeight) dims.resultsHeight = resultsPanel.offsetHeight;
    if (window.userSettings) window.userSettings.set('panel_dimensions', dims);
    else localStorage.setItem('dataflow_panel_dimensions', JSON.stringify(dims));
  }

  let activeResizer = null;

  if (resizerTop && paletteRibbon) {
    resizerTop.addEventListener('mousedown', (e) => {
      e.preventDefault();
      activeResizer = 'top';
      resizerTop.classList.add('resizing');
      document.body.classList.add('resizing-layout');
      document.body.style.cursor = 'row-resize';
    });
  }

  if (resizerLeft && configPanel) {
    resizerLeft.addEventListener('mousedown', (e) => {
      e.preventDefault();
      activeResizer = 'left';
      resizerLeft.classList.add('resizing');
      document.body.classList.add('resizing-layout');
      document.body.style.cursor = 'col-resize';
    });
  }

  if (resizerBottom && resultsPanel) {
    resizerBottom.addEventListener('mousedown', (e) => {
      e.preventDefault();
      activeResizer = 'bottom';
      resizerBottom.classList.add('resizing');
      document.body.classList.add('resizing-layout');
      document.body.style.cursor = 'row-resize';
    });
  }

  window.addEventListener('mousemove', (e) => {
    if (!activeResizer) return;
    e.preventDefault();

    if (activeResizer === 'top' && paletteRibbon) {
      const ribbonRect = paletteRibbon.getBoundingClientRect();
      const newHeight = Math.max(50, Math.min(240, e.clientY - ribbonRect.top));
      paletteRibbon.style.height = `${newHeight}px`;
    } else if (activeResizer === 'left' && configPanel) {
      const newWidth = Math.max(260, Math.min(650, e.clientX));
      configPanel.style.width = `${newWidth}px`;
    } else if (activeResizer === 'bottom' && resultsPanel) {
      const newHeight = Math.max(100, Math.min(window.innerHeight * 0.75, window.innerHeight - e.clientY));
      resultsPanel.style.height = `${newHeight}px`;
    }
  });

  window.addEventListener('mouseup', () => {
    if (!activeResizer) return;
    if (resizerTop) resizerTop.classList.remove('resizing');
    if (resizerLeft) resizerLeft.classList.remove('resizing');
    if (resizerBottom) resizerBottom.classList.remove('resizing');
    document.body.classList.remove('resizing-layout');
    document.body.style.cursor = 'default';
    activeResizer = null;
    saveDimensions();
    if (window.appMiniMap) {
      window.appMiniMap.render();
    }
  });
}
