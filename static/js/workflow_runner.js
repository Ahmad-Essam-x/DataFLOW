/**
 * Workflow Runner — SSE streaming execution, run/stop lifecycle.
 * Extracted from app.js. All dependencies accessed via window.* singletons
 * set during app bootstrap in app.js.
 */

/** Returns the display name for a node event. */
export function getToolDisplayName(ev, canvasInstance = null) {
  if (!ev) return 'Tool';
  const c = canvasInstance || (window.appTabManager && window.appTabManager.activeCanvas) || window.appCanvas;
  let name = ev.node_name || ev.name;
  if ((!name || name === 'undefined') && ev.node_id && c && c.nodes) {
    const node = c.nodeMap ? c.nodeMap.get(ev.node_id) : c.nodes.find(n => n.id === ev.node_id);
    if (node) {
      name = node.name || (node.data && node.data.name) || node.type;
    }
  }
  if (!name || name === 'undefined') {
    name = ev.node_type || ev.type || ev.node_id || 'Tool';
  }
  return name;
}

export async function stopWorkflow() {
  const activeTab = window.appTabManager ? window.appTabManager.activeTab : null;
  if (!activeTab || !activeTab.isRunning) return;

  const stopBtn = document.getElementById('btn-stop');
  if (stopBtn) {
    stopBtn.classList.add('is-stopping');
    stopBtn.innerHTML = `
      <span class="spinner-sm" aria-hidden="true"></span>
      <span>Stopping...</span>
    `;
  }

  try {
    const cancelUrl = '/api/cancel' + (activeTab.activeRunId ? `/${encodeURIComponent(activeTab.activeRunId)}` : '');
    await fetch(cancelUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ run_id: activeTab.activeRunId || null })
    });
    if (window.showToast) {
      window.showToast('warning', 'Cancelling...', `Cancellation signal sent for '${activeTab.name}'.`);
    }
  } catch (e) {
    console.warn('Cancel request failed:', e);
  }
}

export async function runWorkflow() {
  const targetTab = window.appTabManager ? window.appTabManager.activeTab : null;
  if (!targetTab) return;
  if (targetTab.isRunning) {
    if (window.showToast) window.showToast('info', 'Already Running', `'${targetTab.name}' is already running.`);
    return;
  }

  const stopBtn = document.getElementById('btn-stop');
  const resultsPanel = window.appResultsPanel;

  const targetCanvas = targetTab.canvas;
  const wfData = targetCanvas.getWorkflowData();
  if (!wfData.nodes || wfData.nodes.length === 0) {
    window.showToast('info', 'Canvas is Empty', 'Add tools to the canvas before running the workflow.');
    return;
  }

  // Set target tab to running state
  targetTab.isRunning = true;
  targetTab.logs = [];
  targetTab.lastResult = null;
  targetCanvas.setRunningState(true);

  // If this tab is currently visible, update toolbar Run/Stop buttons and results panel
  if (window.appTabManager && window.appTabManager.activeTabId === targetTab.id) {
    window._isWorkflowRunning = true;
    if (stopBtn) stopBtn.classList.add('btn-stop-active');
    window.appTabManager._syncRunStopButtons(targetTab);
    if (resultsPanel && typeof resultsPanel.startRun === 'function') {
      resultsPanel.startRun();
    }
  }

  try {
    const execTimeout = parseInt(
      window.userSettings ? window.userSettings.get('execution_timeout', 60) : (localStorage.getItem('dataflow_execution_timeout') || '60')
    , 10);
    const autoCache = targetCanvas.autoCacheUpstream !== undefined ? targetCanvas.autoCacheUpstream :
      (window.userSettings ? Boolean(window.userSettings.get('auto_cache_upstream', false)) : (localStorage.getItem('dataflow_auto_cache_upstream') === 'true'));
    const useAmp = window.userSettings ? Boolean(window.userSettings.get('use_amp_engine', true)) : true;
    const maxThreads = window.userSettings ? window.userSettings.get('max_engine_threads', 'auto') : 'auto';

    const response = await fetch('/api/run-stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': targetTab.sessionId || '',
        ...(targetTab.activeRunId ? { 'X-Run-ID': targetTab.activeRunId } : {})
      },
      body: JSON.stringify({
        ...wfData,
        session_id: targetTab.sessionId,
        execution_timeout: execTimeout,
        auto_cache_upstream: autoCache,
        use_amp_engine: useAmp,
        max_threads: maxThreads
      })
    });

    if (!response.ok || !response.body) {
      throw new Error(`SSE stream unavailable (HTTP ${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let lastCompletedEvent = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop();

      for (const block of lines) {
        const trimmed = block.trim();
        if (!trimmed.startsWith('data:')) continue;
        const jsonStr = trimmed.replace(/^data:\s*/, '');
        try {
          const ev = JSON.parse(jsonStr);
          handleStreamEventForTab(ev, targetTab);
          if (ev.event === 'workflow_completed' || ev.event === 'workflow_cancelled') {
            lastCompletedEvent = ev;
          }
        } catch (e) {
          console.error('SSE chunk parse error:', e, jsonStr);
        }
      }
    }

    if (buffer.trim().startsWith('data:')) {
      try {
        const ev = JSON.parse(buffer.trim().replace(/^data:\s*/, ''));
        handleStreamEventForTab(ev, targetTab);
        if (ev.event === 'workflow_completed' || ev.event === 'workflow_cancelled') lastCompletedEvent = ev;
      } catch (e) {}
    }

    if (!lastCompletedEvent) {
      await runWorkflowFallback(wfData, targetTab);
    }

  } catch (streamErr) {
    console.warn('Streaming execution fallback to static /api/run:', streamErr);
    await runWorkflowFallback(wfData, targetTab);
  } finally {
    targetTab.isRunning = false;
    targetCanvas.setRunningState(false);
    if (window.appTabManager && window.appTabManager.activeTabId === targetTab.id) {
      window._isWorkflowRunning = false;
      window.appTabManager._syncRunStopButtons(targetTab);
    }
  }
}

export function handleStreamEventForTab(ev, targetTab) {
  const targetCanvas = targetTab.canvas;
  const resultsPanel = window.appResultsPanel;
  const timeStr = new Date().toLocaleTimeString();
  const toolName = getToolDisplayName(ev, targetCanvas);
  const toolIdStr = ev.node_id ? ` (#${ev.node_id})` : '';

  if (ev.run_id) {
    targetTab.activeRunId = ev.run_id;
    if (window.appTabManager && window.appTabManager.activeTabId === targetTab.id) {
      window.activeRunId = ev.run_id;
    }
  }

  const isActiveTab = window.appTabManager && window.appTabManager.activeTabId === targetTab.id;
  const stopBtn = isActiveTab ? document.getElementById('btn-stop') : null;

  switch (ev.event) {
    case 'node_started':
      targetCanvas.updateNodeExecutionStep({ node_id: ev.node_id, status: 'running' });
      const startLog = { time: timeStr, level: 'INFO', message: `Running tool '${toolName}'${toolIdStr}...` };
      targetTab.logs.push(startLog);
      if (isActiveTab && resultsPanel) resultsPanel.appendLog(startLog);
      break;

    case 'node_completed':
      targetCanvas.updateNodeExecutionStep({
        node_id: ev.node_id, status: 'success',
        duration_ms: ev.duration_ms, record_counts: ev.record_counts
      });
      const compLog = { time: timeStr, level: 'INFO', message: `✓ Tool '${toolName}'${toolIdStr} completed in ${ev.duration_ms}ms` };
      targetTab.logs.push(compLog);
      if (isActiveTab && resultsPanel) resultsPanel.appendLog(compLog);
      break;

    case 'node_error':
      targetCanvas.updateNodeExecutionStep({ node_id: ev.node_id, status: 'error' });
      const errLog = { time: timeStr, level: 'ERROR', message: `✗ Tool '${toolName}'${toolIdStr} error: ${ev.error}` };
      targetTab.logs.push(errLog);
      if (isActiveTab && resultsPanel) resultsPanel.appendLog(errLog);
      break;

    case 'workflow_completed':
      targetTab.lastResult = ev;
      targetCanvas.updateExecutionVisuals(ev.node_results || {});
      if (isActiveTab) {
        window.appLastResult = ev;
        if (stopBtn) stopBtn.classList.remove('btn-stop-active', 'is-stopping');
        if (resultsPanel) resultsPanel.finalizeRun(ev);
        if (ev.success) {
          document.querySelectorAll('.node-card.has-error').forEach(el => el.classList.remove('has-error'));
          window.showToast('success', 'Workflow Succeeded', `Completed all ${Object.keys(ev.node_results || {}).length} tools in ${ev.total_duration_ms}ms.`);
        } else {
          const diag = ev.diagnostic;
          const egressMatch = /\[egress:([^\]\s]+)\]/.exec(`${ev.error || ''} ${(diag && diag.message) || ''}`);
          if (egressMatch) {
            // LLM tool would send data to a remote host the user has not approved yet: ask once, then re-run.
            const host = egressMatch[1];
            if (window.confirm(`This workflow will send data (cell values) to:\n\n    ${host}\n\nOnly approve hosts you trust. Approve and run again?`)) {
              fetch('/api/ai/approve-host', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ host })
              }).then(() => runWorkflow());
            } else {
              window.showToast('warning', 'Not approved', `${host} was not approved, so the AI tool did not run.`);
            }
          } else if (diag) {
            window.showToast('error', diag.title, diag.message);
            if (resultsPanel) resultsPanel.switchToTab('messages-view');
            if (diag.node_id) targetCanvas.highlightErrorNode(diag.node_id);
          } else {
            window.showToast('error', 'Execution Error', ev.error || 'Workflow execution encountered an error.');
          }
        }
        if (targetCanvas.selectedNodeId && resultsPanel) {
          const selNode = targetCanvas.nodeMap
            ? targetCanvas.nodeMap.get(targetCanvas.selectedNodeId)
            : targetCanvas.nodes.find(n => n.id === targetCanvas.selectedNodeId);
          resultsPanel.showNodeResults(selNode);
          if (window.appConfigPanel && typeof window.appConfigPanel.render === 'function' && window.appConfigPanel.currentNode && selNode && window.appConfigPanel.currentNode.id === selNode.id) {
            window.appConfigPanel.render(selNode);
          }
        }
      } else {
        if (ev.success) {
          window.showToast('info', `${targetTab.name} Finished`, `Completed all ${Object.keys(ev.node_results || {}).length} tools in ${ev.total_duration_ms}ms.`);
        } else {
          window.showToast('warning', `${targetTab.name} Failed`, ev.error || 'Background workflow encountered an error.');
        }
      }
      break;

    case 'workflow_cancelled':
      targetTab.lastResult = ev;
      const cancelLog = { time: timeStr, level: 'WARNING', message: ev.message || 'Workflow Cancelled by User.' };
      targetTab.logs.push(cancelLog);
      if (isActiveTab && resultsPanel) {
        if (stopBtn) stopBtn.classList.remove('btn-stop-active', 'is-stopping');
        resultsPanel.appendLog(cancelLog);
        resultsPanel.finalizeRun({
          cancelled: true, success: false,
          total_duration_ms: ev.total_duration_ms || 0,
          logs: targetTab.logs
        });
      }
      window.showToast('warning', `${targetTab.name} Cancelled`, 'Workflow execution was cancelled.');
      break;
  }
}

export async function runWorkflowFallback(wfData, targetTab) {
  if (!targetTab) return;
  const resultsPanel = window.appResultsPanel;
  try {
    const execTimeout = parseInt(
      window.userSettings ? window.userSettings.get('execution_timeout', 60) : (localStorage.getItem('dataflow_execution_timeout') || '60')
    , 10);
    const autoCache = targetTab.canvas.autoCacheUpstream !== undefined ? targetTab.canvas.autoCacheUpstream :
      (window.userSettings ? Boolean(window.userSettings.get('auto_cache_upstream', false)) : (localStorage.getItem('dataflow_auto_cache_upstream') === 'true'));
    const useAmp = window.userSettings ? Boolean(window.userSettings.get('use_amp_engine', true)) : true;
    const maxThreads = window.userSettings ? window.userSettings.get('max_engine_threads', 'auto') : 'auto';

    const res = await fetch('/api/run', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': targetTab.sessionId || '',
        ...(targetTab.activeRunId ? { 'X-Run-ID': targetTab.activeRunId } : {})
      },
      body: JSON.stringify({
        ...wfData,
        session_id: targetTab.sessionId,
        execution_timeout: execTimeout,
        auto_cache_upstream: autoCache,
        use_amp_engine: useAmp,
        max_threads: maxThreads
      })
    });

    const result = await res.json();
    if (result.run_id) targetTab.activeRunId = result.run_id;
    handleStreamEventForTab({ ...result, event: 'workflow_completed' }, targetTab);
  } catch (err) {
    const errLog = { time: new Date().toLocaleTimeString(), level: 'ERROR', message: `Execution failed: ${err.message}` };
    targetTab.logs.push(errLog);
    if (window.appTabManager && window.appTabManager.activeTabId === targetTab.id && resultsPanel) {
      resultsPanel.appendLog(errLog);
      resultsPanel.finalizeRun({
        success: false,
        diagnostic: { error_code: 'NETWORK_OR_SERVER_ERROR', title: 'Execution Failed', message: err.message }
      });
    }
    window.showToast('error', 'Execution Failed', err.message);
  }
}
