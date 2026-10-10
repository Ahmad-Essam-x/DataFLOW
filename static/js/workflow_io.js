/**
 * Workflow I/O — save, open, export, import, load from server.
 * Extracted from app.js. All dependencies via window.* singletons.
 * Call initWorkflowIO() during DOMContentLoaded in app.js.
 */

export async function saveWorkflowAs() {
  const curTab = window.appTabManager ? window.appTabManager.activeTab : null;
  const nameInput = document.getElementById('workflow-name-input');
  const currentName = (nameInput ? nameInput.value.trim() : '') || curTab?.name || 'my_workflow';
  const cleanStem = currentName.replace(/[^a-zA-Z0-9_\-]/g, '_').replace(/_+/g, '_').toLowerCase();
  const suggestedName = `${cleanStem}.json`;
  const wfData = window.getActiveCanvas().getWorkflowData();
  wfData.name = currentName;

  // 1. Primary: Native Windows Explorer Save As Dialog via Chromium File System Access API
  if (typeof window.showSaveFilePicker === 'function') {
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: suggestedName,
        types: [
          { description: 'Workflow Files (*.json)', accept: { 'application/json': ['.json'] } },
          { description: 'Alteryx Workflow (*.yxmd)', accept: { 'application/xml': ['.yxmd'] } },
          { description: 'All Files (*.*)', accept: { '*/*': [] } }
        ]
      });

      if (!handle) return false;

      const savedFilename = handle.name;
      const cleanTitle = savedFilename.replace(/\.(json|yxmd)$/i, '').replace(/_/g, ' ');
      wfData.name = cleanTitle;
      if (nameInput) nameInput.value = cleanTitle;
      if (window.appTabManager) window.appTabManager.syncActiveTabName(cleanTitle);

      const writable = await handle.createWritable();
      await writable.write(JSON.stringify(wfData, null, 2));
      await writable.close();

      const fileInfo = { handle, name: savedFilename, path: savedFilename };
      window.activeWorkflowFile = fileInfo;
      if (curTab) { curTab.workflowFile = fileInfo; curTab.name = cleanTitle; curTab.isDirty = false; }

      window.markWorkflowClean();

      let actualSavedPath = savedFilename;
      try {
        const sRes = await fetch('/api/save-workflow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Session-ID': window.clientSessionId || '' },
          body: JSON.stringify({ ...wfData, target_filepath: savedFilename })
        });
        const sJson = await sRes.json();
        if (sJson && sJson.path) { actualSavedPath = sJson.path; fileInfo.path = sJson.path; }
        await fetch('/api/workflow/autosave', { method: 'DELETE', headers: { 'X-Session-ID': window.clientSessionId || '' } });
      } catch (_) {}

      window.showToast('success', 'Workflow Saved', `Saved '${savedFilename}' via Windows Explorer.`);
      await window.refreshSavedWorkflows?.();
      if (window.appMenuBar?.addRecentWorkflow) window.appMenuBar.addRecentWorkflow(cleanTitle, actualSavedPath, wfData);
      return true;
    } catch (err) {
      if (err?.name === 'AbortError') return false;
      console.warn('showSaveFilePicker error, attempting backend dialog fallback:', err);
    }
  }

  // 2. Secondary: Native Windows Explorer Save As Dialog via Python Backend
  try {
    const res = await fetch('/api/dialog/save-file', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Session-ID': window.clientSessionId || '' },
      body: JSON.stringify({ workflow: wfData, default_name: suggestedName })
    });
    const json = await res.json();
    if (json.cancelled) return false;
    if (json.success) {
      const cleanTitle = (json.name || json.filename.replace(/\.(json|yxmd)$/i, '')).replace(/_/g, ' ');
      wfData.name = cleanTitle;
      if (nameInput) nameInput.value = cleanTitle;
      if (window.appTabManager) window.appTabManager.syncActiveTabName(cleanTitle);

      const fileInfo = { handle: null, name: json.filename, path: json.path };
      window.activeWorkflowFile = fileInfo;
      if (curTab) { curTab.workflowFile = fileInfo; curTab.name = cleanTitle; curTab.isDirty = false; }

      window.markWorkflowClean();
      try {
        await fetch('/api/workflow/autosave', { method: 'DELETE', headers: { 'X-Session-ID': window.clientSessionId || '' } });
      } catch (_) {}
      window.showToast('success', 'Workflow Saved', `Saved '${json.filename}' via Windows Explorer.`);
      await window.refreshSavedWorkflows?.();
      if (window.appMenuBar?.addRecentWorkflow) window.appMenuBar.addRecentWorkflow(cleanTitle, json.path, wfData);
      return true;
    }
  } catch (dialogErr) {
    console.warn('Backend native save dialog failed, fallback to download:', dialogErr);
  }

  // 3. Fallback: Standard Export Download
  exportWorkflowJson();
  return true;
}

export async function saveWorkflow(customName = null) {
  const curTab = window.appTabManager ? window.appTabManager.activeTab : null;
  const fileInfo = (curTab && curTab.workflowFile) || window.activeWorkflowFile || {};

  if (customName || (!fileInfo.handle && !fileInfo.path)) return await saveWorkflowAs();

  const nameInput = document.getElementById('workflow-name-input');
  const wfName = (nameInput ? nameInput.value.trim() : '') || curTab?.name || fileInfo.name || 'Workflow';
  const wfData = window.getActiveCanvas().getWorkflowData();
  wfData.name = wfName;

  let handleSaved = false;
  if (fileInfo.handle) {
    try {
      const writable = await fileInfo.handle.createWritable();
      await writable.write(JSON.stringify(wfData, null, 2));
      await writable.close();
      handleSaved = true;
    } catch (handleErr) {
      console.warn('File handle write failed, falling back to server disk save:', handleErr);
    }
  }

  const targetPath = fileInfo.path || fileInfo.name;
  if (handleSaved || targetPath) {
    try {
      const res = await fetch('/api/save-workflow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-ID': window.clientSessionId || '' },
        body: JSON.stringify({ ...wfData, target_filepath: targetPath })
      });
      const json = await res.json();
      if (json.success) {
        if (json.path) fileInfo.path = json.path;
        if (json.filename) fileInfo.name = json.filename;
        if (curTab) { curTab.workflowFile = fileInfo; curTab.isDirty = false; }
        window.activeWorkflowFile = fileInfo;
        window.markWorkflowClean();
        try {
          await fetch('/api/workflow/autosave', { method: 'DELETE', headers: { 'X-Session-ID': window.clientSessionId || '' } });
        } catch (_) {}
        window.showToast('success', 'Workflow Saved', `Saved changes to '${fileInfo.name}'.`);
        await window.refreshSavedWorkflows?.();
        if (window.appMenuBar?.addRecentWorkflow) window.appMenuBar.addRecentWorkflow(wfName, fileInfo.path || fileInfo.name, wfData);
        return true;
      }
    } catch (serverErr) {
      console.warn('Server save failed, checking handle save:', serverErr);
    }
  }

  if (handleSaved) {
    window.markWorkflowClean();
    if (curTab) curTab.isDirty = false;
    window.showToast('success', 'Workflow Saved', `Saved changes to '${fileInfo.name}'.`);
    return true;
  }

  return await saveWorkflowAs();
}

/**
 * Unified workflow loader with smart multi-tab placement and file-identity tracking.
 * Reuses active tab if clean and empty; otherwise opens a fresh tab.
 */
export function openWorkflowData(wf, fileName, filePath = null, fileHandle = null) {
  if (!wf) return null;

  const genericNames = ['new workflow', 'untitled_workflow', 'untitled', 'workflow'];
  const cleanFileStem = (fileName || filePath || '')
    .split('/').pop().split('\\').pop()
    .replace(/\.(json|yxmd|zip|yxzp)$/i, '')
    .replace(/_/g, ' ')
    .trim();

  let displayName = wf.name && !genericNames.includes(String(wf.name).trim().toLowerCase())
    ? wf.name
    : (cleanFileStem || 'Workflow');

  wf.name = displayName;

  const actualFileName = fileName || (filePath ? filePath.split('/').pop().split('\\').pop() : (fileHandle ? fileHandle.name : `${displayName}.json`));
  const actualFilePath = filePath || (wf._path || null);

  const activeCanvas = window.getActiveCanvas();
  const activeTab = window.appTabManager ? window.appTabManager.activeTab : null;
  const isCurrentDirty = (activeTab && activeTab.isDirty) || !!window._activeTabIsDirty;
  const hasTools = activeCanvas && activeCanvas.nodes && activeCanvas.nodes.length > 0;

  let targetTab = null;

  if (window.appTabManager && (isCurrentDirty || hasTools)) {
    targetTab = window.appTabManager.createTab(wf, displayName, actualFilePath, fileHandle);
  } else {
    if (activeCanvas) activeCanvas.loadWorkflow(wf);
    targetTab = activeTab;
    if (targetTab) {
      targetTab.name = displayName;
      targetTab.workflowFile = { handle: fileHandle || null, name: actualFileName, path: actualFilePath };
      targetTab.isDirty = false;
      if (window.appTabManager) {
        window.appTabManager._updateTabPill(targetTab.id);
        window.appTabManager.syncActiveTabName(displayName);
      }
    }
  }

  const nameInput = document.getElementById('workflow-name-input');
  if (nameInput) nameInput.value = displayName;
  document.title = `${displayName} - Antigravity DataFlow`;

  const boundFileInfo = {
    handle: fileHandle || (targetTab && targetTab.workflowFile ? targetTab.workflowFile.handle : null),
    name: actualFileName,
    path: actualFilePath
  };
  window.activeWorkflowFile = boundFileInfo;
  if (targetTab) { targetTab.workflowFile = boundFileInfo; targetTab.isDirty = false; }

  window.appLastResult = null;
  const resultsPanel = window.appResultsPanel;
  const configPanel = window.appConfigPanel;
  if (resultsPanel) resultsPanel.clear();

  const targetCanvas = (targetTab && targetTab.canvas) || activeCanvas;
  if (targetCanvas && wf.nodes && wf.nodes.length > 0) {
    targetCanvas.selectNode(wf.nodes[0].id);
  } else {
    if (configPanel) configPanel.render(null);
    if (resultsPanel) resultsPanel.showNodeResults(null);
  }

  if (window.appHistory) window.appHistory.pushSnapshot(`Opened ${displayName}`);

  window.markWorkflowClean();

  const recentPath = actualFilePath || actualFileName;
  if (window.appMenuBar?.addRecentWorkflow) window.appMenuBar.addRecentWorkflow(displayName, recentPath, wf);

  window.showToast('success', 'Workflow Loaded', `Opened '${displayName}'.`);
  return targetTab;
}

export async function openWorkflowFileDialog() {
  // 1. Primary: Native Windows Explorer Open Dialog via Chromium File System Access API
  if (typeof window.showOpenFilePicker === 'function') {
    try {
      const [handle] = await window.showOpenFilePicker({
        types: [
          {
            description: 'Workflow Files (*.json, *.yxmd, *.zip, *.yxzp)',
            accept: {
              'application/json': ['.json'],
              'application/xml': ['.yxmd'],
              'application/zip': ['.zip', '.yxzp']
            }
          },
          { description: 'All Files (*.*)', accept: { '*/*': [] } }
        ],
        multiple: false
      });

      if (!handle) return false;
      const file = await handle.getFile();
      const fileName = file.name;
      const isPackage = fileName.endsWith('.zip') || fileName.endsWith('.yxzp');

      if (isPackage) {
        await importWorkflowPackage(file);
        window.activeWorkflowFile = { handle: null, name: fileName, path: fileName };
      } else if (fileName.endsWith('.yxmd')) {
        await importYxmdWorkflow(file);
      } else {
        const text = await file.text();
        const wf = JSON.parse(text);
        openWorkflowData(wf, fileName, null, handle);
      }
      return true;
    } catch (err) {
      if (err?.name === 'AbortError') return false;
      console.warn('showOpenFilePicker error, attempting backend dialog fallback:', err);
    }
  }

  // 2. Secondary: Native Windows Explorer Open Dialog via Python Backend
  try {
    const res = await fetch('/api/dialog/open-file', {
      method: 'POST',
      headers: { 'X-Session-ID': window.clientSessionId || '' }
    });
    const json = await res.json();
    if (json.cancelled) return false;
    if (json.success && json.workflow) {
      openWorkflowData(json.workflow, json.filename, json.path, null);
      return true;
    }
  } catch (dialogErr) {
    console.warn('Backend native open dialog failed, falling back to file input:', dialogErr);
  }

  // 3. Fallback: HTML5 file input
  const fileInput = document.getElementById('input-workflow-file');
  if (fileInput) fileInput.click();
  return true;
}

export function exportWorkflowJson() {
  const nameInput = document.getElementById('workflow-name-input');
  const wfName = (nameInput ? nameInput.value.trim() : '') || 'workflow';
  const wfData = window.getActiveCanvas().getWorkflowData();
  wfData.name = wfName;
  const blob = new Blob([JSON.stringify(wfData, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `${wfName.replace(/\s+/g, '_').toLowerCase()}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  window.showToast('success', 'Workflow Exported', `Downloaded '${wfName}.json'.`);
}

export async function exportWorkflowPackage() {
  const nameInput = document.getElementById('workflow-name-input');
  const wfName = (nameInput ? nameInput.value.trim() : '') || 'workflow';
  const wfData = window.getActiveCanvas().getWorkflowData();
  wfData.name = wfName;
  try {
    window.showToast('info', 'Packaging Workflow...', 'Compressing workflow and referenced data assets into .zip package...', 4000);
    const res = await fetch('/api/workflow/export-package', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(wfData)
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({}));
      throw new Error(errJson.error || `Server responded with status ${res.status}`);
    }
    const blob = await res.blob();
    const cleanStem = wfName.replace(/[\s\W]+/g, '_').toLowerCase();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${cleanStem}_package.zip`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    window.showToast('success', 'Package Exported', `Downloaded '${cleanStem}_package.zip'.`);
  } catch (err) {
    console.error('Package export error:', err);
    window.showToast('error', 'Packaging Failed', err.message);
  }
}

export async function importWorkflowPackage(file) {
  if (!file) return;
  try {
    window.showToast('info', 'Importing Package...', `Unpacking '${file.name}'...`, 4000);
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/workflow/import-package', { method: 'POST', body: formData });
    const json = await res.json();
    if (!res.ok || !json.success) throw new Error(json.error || 'Failed to import package.');

    if (json.workflow) {
      handleWorkflowLoaded(json.workflow, json.workflow.name || file.name.replace(/\.(zip|yxzp)$/i, ''));
      const fileCount = (json.extracted_files || []).length;
      window.showToast('success', 'Package Imported', `Loaded workflow and unpacked ${fileCount} data asset(s).`);
      await window.refreshSavedWorkflows?.();
    } else {
      throw new Error('No valid workflow definition found in package.');
    }
  } catch (err) {
    console.error('Package import failed:', err);
    window.showToast('error', 'Import Failed', err.message);
  }
}

export async function importYxmdWorkflow(file) {
  if (!file) return;
  try {
    window.showToast('info', 'Importing Alteryx Workflow...', `Converting '${file.name}'...`, 4000);
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch('/api/workflow/import-yxmd', { method: 'POST', body: formData });
    const json = await res.json();
    if (!res.ok || !json.success) throw new Error(json.error || 'Failed to import Alteryx workflow.');

    if (json.workflow) {
      handleWorkflowLoaded(json.workflow, json.filename || file.name.replace(/\.yxmd$/i, ''));
      const stats = json.stats || {};
      const coverage = stats.coverage_pct !== undefined ? `${stats.coverage_pct}%` : '100%';
      const msg = `Mapped ${stats.mapped_tools || 0} tools (${stats.fallback_tools || 0} fallbacks). Coverage: ${coverage}`;
      window.showToast('success', 'Alteryx Workflow Imported', msg);
      await window.refreshSavedWorkflows?.();
    } else {
      throw new Error('No valid workflow definition returned.');
    }
  } catch (err) {
    console.error('Alteryx import failed:', err);
    window.showToast('error', 'Import Failed', err.message);
  }
}

export function handleWorkflowLoaded(wf, defaultName = 'Workflow') {
  const filePath = (wf && (wf._path || wf.path)) ? (wf._path || wf.path) : null;
  const fileName = (wf && wf._filename) ? wf._filename : (defaultName.endsWith('.json') ? defaultName : `${defaultName}.json`);
  return openWorkflowData(wf, fileName, filePath, null);
}

export async function loadWorkflowFromServer(filename) {
  try {
    let res = await fetch(`/api/workflow/${encodeURIComponent(filename)}`);
    if (!res.ok) res = await fetch(`/api/sample-workflow/${encodeURIComponent(filename)}`);
    if (!res.ok) throw new Error(`Could not fetch workflow file (${res.status})`);
    const data = await res.json();
    const filePath = data._path || `workflows/${filename}`;
    const name = data._filename || filename;
    openWorkflowData(data, name, filePath, null);
  } catch (err) {
    console.error('Failed to load workflow:', err);
    window.showToast('error', 'Load Failed', `Could not load workflow: ${err.message}`);
  }
}

/** Registers all IO functions on window and sets up file-input change handler. */
export function initWorkflowIO() {
  window.saveWorkflowAs = saveWorkflowAs;
  window.saveWorkflow = saveWorkflow;
  window.openWorkflowData = openWorkflowData;
  window.openWorkflowFileDialog = openWorkflowFileDialog;
  window.exportWorkflowJson = exportWorkflowJson;
  window.exportWorkflowPackage = exportWorkflowPackage;
  window.importWorkflowPackage = importWorkflowPackage;
  window.importYxmdWorkflow = importYxmdWorkflow;
  window.handleWorkflowLoaded = handleWorkflowLoaded;
  window.loadWorkflowFromServer = loadWorkflowFromServer;

  // HTML5 file input fallback handler
  const fileInput = document.getElementById('input-workflow-file');
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        if (file.name.endsWith('.zip') || file.name.endsWith('.yxzp')) {
          await importWorkflowPackage(file);
        } else if (file.name.endsWith('.yxmd')) {
          await importYxmdWorkflow(file);
        } else {
          const text = await file.text();
          const wf = JSON.parse(text);
          openWorkflowData(wf, file.name, null, null);
        }
      } catch (err) {
        window.showToast('error', 'Load Failed', err.message);
      }
      e.target.value = '';
    });
  }
}
