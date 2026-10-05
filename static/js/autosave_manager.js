/**
 * Autosave Manager — dirty-state tracking, debounced autosave, crash recovery, exit guard.
 * Extracted from app.js. Call initAutosaveManager() during DOMContentLoaded in app.js.
 */

// Module-level state
let isWorkflowDirty = false;
let _dirtySyncTimer = null;
let _autosaveDebounceTimer = null;
let _isAutosaving = false;

const baseDocumentTitle = 'Antigravity DataFlow';

function getDirtyBadge() { return document.getElementById('workflow-dirty-badge'); }

export function syncDirtyStateToServer() {
  clearTimeout(_dirtySyncTimer);
  _dirtySyncTimer = setTimeout(() => {
    let isDirty = false;
    let dirtyCount = 0;
    if (window.appTabManager && window.appTabManager.tabs) {
      window.appTabManager.tabs.forEach(t => {
        if (t.isDirty && t.canvas && t.canvas.nodes && t.canvas.nodes.length > 0) {
          isDirty = true;
          dirtyCount++;
        }
      });
    } else if (isWorkflowDirty && window.getActiveCanvas() && window.getActiveCanvas().nodes && window.getActiveCanvas().nodes.length > 0) {
      isDirty = true;
      dirtyCount = 1;
    }
    fetch('/api/app/dirty-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_dirty: isDirty, dirty_tabs_count: dirtyCount })
    }).catch(() => {});
  }, 120);
}

export function markWorkflowDirty() {
  isWorkflowDirty = true;
  const dirtyBadge = getDirtyBadge();
  if (dirtyBadge) {
    dirtyBadge.textContent = '● Unsaved';
    dirtyBadge.classList.remove('is-clean');
    dirtyBadge.classList.add('is-dirty');
    dirtyBadge.title = 'Unsaved changes (Ctrl+S to save)';
  }
  const nameInput = document.getElementById('workflow-name-input');
  const wfName = (nameInput ? nameInput.value.trim() : '') || 'Workflow';
  document.title = `* ${wfName} - ${baseDocumentTitle}`;
  if (window.appTabManager) window.appTabManager.markActiveDirty();
  scheduleDebouncedAutosave();
  syncDirtyStateToServer();
}

export function markWorkflowClean() {
  isWorkflowDirty = false;
  const dirtyBadge = getDirtyBadge();
  if (dirtyBadge) {
    dirtyBadge.textContent = '✓ Saved';
    dirtyBadge.classList.remove('is-dirty');
    dirtyBadge.classList.add('is-clean');
    dirtyBadge.title = 'All changes saved locally';
  }
  const nameInput = document.getElementById('workflow-name-input');
  const wfName = (nameInput ? nameInput.value.trim() : '') || 'Workflow';
  document.title = `${wfName} - ${baseDocumentTitle}`;
  if (window.appTabManager) window.appTabManager.markActiveClean();
  syncDirtyStateToServer();
}

export async function triggerAutosave() {
  if (_isAutosaving) return;
  const statusBadge = document.getElementById('autosave-status-badge');

  const tabsToSave = [];
  if (window.appTabManager && window.appTabManager.tabs) {
    window.appTabManager.tabs.forEach(tab => {
      if (tab.isDirty && tab.canvas && tab.canvas.nodes && tab.canvas.nodes.length > 0) {
        tabsToSave.push({
          sessionId: tab.sessionId,
          canvas: tab.canvas,
          name: tab.name || 'Untitled Workflow',
          tab: tab
        });
      }
    });
  } else if (isWorkflowDirty) {
    const activeCanvas = window.getActiveCanvas();
    if (activeCanvas && activeCanvas.nodes && activeCanvas.nodes.length > 0) {
      const nameInput = document.getElementById('workflow-name-input');
      tabsToSave.push({
        sessionId: window.clientSessionId || 'default_session',
        canvas: activeCanvas,
        name: (nameInput ? nameInput.value.trim() : '') || 'Untitled Workflow',
        tab: null
      });
    }
  }

  if (tabsToSave.length === 0) return;

  _isAutosaving = true;
  if (statusBadge) {
    statusBadge.classList.add('is-saving');
    statusBadge.textContent = '● Saving...';
  }

  try {
    for (const item of tabsToSave) {
      const wfData = item.canvas.getWorkflowData();
      wfData.name = item.name;
      if (item.tab && item.tab.workflowFile && item.tab.workflowFile.path) {
        if (!wfData.metadata) wfData.metadata = {};
        wfData.metadata.saved_file = item.tab.workflowFile.path;
      }
      await fetch('/api/workflow/autosave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-ID': item.sessionId },
        body: JSON.stringify(wfData)
      });
    }
    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    if (statusBadge) {
      statusBadge.textContent = `● Autosaved ${timeStr}`;
      statusBadge.title = `Autosave active. Last protected at ${timeStr}.`;
    }
  } catch (_) {
    // Non-intrusive background failure
  } finally {
    _isAutosaving = false;
    if (statusBadge) statusBadge.classList.remove('is-saving');
  }
}

export function scheduleDebouncedAutosave() {
  clearTimeout(_autosaveDebounceTimer);
  _autosaveDebounceTimer = setTimeout(triggerAutosave, 3500);
}

export async function checkAutoSaveRecovery() {
  try {
    const res = await fetch('/api/workflow/recovery/available');
    const data = await res.json();
    if (!data.success || !data.recoveries || data.recoveries.length === 0) return false;

    const recoveries = data.recoveries;
    const modal = document.getElementById('modal-workflow-recovery');
    const card = document.getElementById('recovery-details-card');
    if (!modal || !card) return false;

    let cardHtml = '';
    recoveries.forEach((rec, idx) => {
      cardHtml += `
        <div style="padding: 10px 12px; border-radius: 5px; background: var(--bg-card); border: 1px solid var(--border-subtle); ${idx > 0 ? 'margin-top: 8px;' : ''}">
          <div style="font-weight: 600; font-size: 13px; color: var(--color-primary); margin-bottom: 3px;">
            ${rec.workflow_name || 'Untitled Workflow'}
          </div>
          <div style="color: var(--text-secondary); font-size: 11px; line-height: 1.5;">
              <div>🕒 Last modified: <strong>${rec.saved_at || 'Recent session'}</strong></div>
              <div>🧩 Contains: <strong>${rec.node_count || 0} tools</strong>, <strong>${rec.connection_count || 0} connections</strong></div>
            </div>
          </div>
        `;
    });
    card.innerHTML = cardHtml;
    modal.style.display = 'flex';

    const applyBtn = document.getElementById('btn-apply-recovery');
    const discardBtn = document.getElementById('btn-discard-recovery');

    if (applyBtn) {
      applyBtn.onclick = () => {
        recoveries.forEach((rec, idx) => {
          if (idx === 0) {
            window.handleWorkflowLoaded(rec.workflow, rec.workflow_name || 'Recovered Workflow');
            markWorkflowDirty();
          } else if (window.appTabManager) {
            const tab = window.appTabManager.createTab(rec.workflow, rec.workflow_name || `Recovered Workflow ${idx + 1}`);
            if (tab) tab.isDirty = true;
          }
        });
        modal.style.display = 'none';
        window.showToast('warning', 'Session Recovered', `Restored ${recoveries.length} auto-saved workflow(s). Save when ready.`);
      };
    }

    if (discardBtn) {
      discardBtn.onclick = async () => {
        try { await fetch('/api/workflow/recovery/clear-all', { method: 'POST' }); } catch (_) {}
        modal.style.display = 'none';
        window.showToast('info', 'Auto-Save Discarded', 'Cleared emergency recovery snapshots.');
      };
    }
    return true;
  } catch (_) {}
  return false;
}

export function showExitConfirmationDialog() {
  const dirtyTabs = [];
  if (window.appTabManager && window.appTabManager.tabs) {
    window.appTabManager.tabs.forEach(t => {
      if (t.isDirty && t.canvas && t.canvas.nodes && t.canvas.nodes.length > 0) {
        dirtyTabs.push(t);
      }
    });
  } else if (isWorkflowDirty && window.getActiveCanvas() && window.getActiveCanvas().nodes && window.getActiveCanvas().nodes.length > 0) {
    const nameInput = document.getElementById('workflow-name-input');
    dirtyTabs.push({
      name: (nameInput ? nameInput.value.trim() : '') || 'Untitled Workflow',
      canvas: window.getActiveCanvas(),
      isDirty: true
    });
  }

  if (dirtyTabs.length === 0) { doCleanExit(true); return; }

  const modal = document.getElementById('modal-unsaved-exit');
  const listEl = document.getElementById('unsaved-exit-list');
  if (!modal || !listEl) {
    if (confirm('You have unsaved changes in your workflow. Exit anyway?')) doCleanExit(true);
    return;
  }

  listEl.innerHTML = dirtyTabs.map(t => `
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 7px 10px; border-radius: 4px; background: var(--bg-hover); border: 1px solid var(--border-subtle); font-size: 11.5px;">
      <span style="font-weight: 500; color: var(--text-primary);">● ${t.name || 'Untitled Workflow'}</span>
      <span style="color: var(--text-muted); font-size: 10.5px;">${t.canvas.nodes.length} tools</span>
    </div>
  `).join('');

  modal.style.display = 'flex';

  const cancelBtn = document.getElementById('btn-exit-cancel');
  const discardBtn2 = document.getElementById('btn-exit-discard');
  const saveAllBtn = document.getElementById('btn-exit-save-all');

  if (cancelBtn) cancelBtn.onclick = () => { modal.style.display = 'none'; };

  if (discardBtn2) {
    discardBtn2.onclick = async () => {
      modal.style.display = 'none';
      await doCleanExit(true);
    };
  }

  if (saveAllBtn) {
    saveAllBtn.onclick = async () => {
      saveAllBtn.disabled = true;
      saveAllBtn.textContent = 'Saving...';
      try {
        for (const t of dirtyTabs) {
          const wfData = t.canvas.getWorkflowData();
          await fetch('/api/save-workflow', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ...wfData, name: t.name || 'Workflow' })
          });
          t.isDirty = false;
        }
      } catch (_) {}
      modal.style.display = 'none';
      await doCleanExit(true);
    };
  }
}

export async function doCleanExit(clearAutosaves = false) {
  if (window.showToast) window.showToast('info', 'Exiting', 'Antigravity DataFlow is closing...');
  try {
    await fetch('/api/app/exit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ clear_autosave: clearAutosaves })
    });
  } catch (_) {}
  setTimeout(() => { try { window.close(); } catch (_) {} }, 350);
}

/**
 * Registers event listeners and starts the autosave heartbeat.
 * Must be called once during DOMContentLoaded after window.* singletons are set.
 */
export function initAutosaveManager() {
  // Unsaved-changes safety guard on window exit / refresh
  window.addEventListener('beforeunload', (e) => {
    const hasDirty = (window.appTabManager && window.appTabManager.tabs.some(t => t.isDirty && t.canvas.nodes && t.canvas.nodes.length > 0)) ||
                     (isWorkflowDirty && window.getActiveCanvas() && window.getActiveCanvas().nodes && window.getActiveCanvas().nodes.length > 0);
    if (hasDirty) {
      e.preventDefault();
      e.returnValue = 'You have unsaved changes in your workflow. Are you sure you want to leave?';
      return e.returnValue;
    }
  });

  // Workflow name input → dirty + tab pill sync
  const nameInputEl = document.getElementById('workflow-name-input');
  if (nameInputEl) {
    nameInputEl.addEventListener('input', () => {
      markWorkflowDirty();
      if (window.appTabManager) {
        window.appTabManager.syncActiveTabName(nameInputEl.value.trim() || 'Untitled');
      }
    });
  }

  // Periodic safety heartbeat autosave (every 30s)
  setInterval(triggerAutosave, 30000);

  // Expose on window for classic-script callers
  window.syncDirtyStateToServer = syncDirtyStateToServer;
  window.markWorkflowDirty = markWorkflowDirty;
  window.markWorkflowClean = markWorkflowClean;
  window.triggerAutosave = triggerAutosave;
  window.scheduleDebouncedAutosave = scheduleDebouncedAutosave;
  window.checkAutoSaveRecovery = checkAutoSaveRecovery;
  window.showExitConfirmationDialog = showExitConfirmationDialog;
}
