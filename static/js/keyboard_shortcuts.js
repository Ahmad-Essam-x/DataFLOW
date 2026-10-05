/**
 * Keyboard Shortcuts — global keydown handler.
 * Extracted from app.js. All shortcuts delegate to window.app.executeCommand().
 * Call registerKeyboardShortcuts() after window.app is assigned in app.js.
 */

export function registerKeyboardShortcuts() {
  window.addEventListener('keydown', (e) => {
    const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
    const isInput = activeTag === 'input' || activeTag === 'textarea' || (document.activeElement && document.activeElement.isContentEditable);
    const isCtrlOrMeta = e.ctrlKey || e.metaKey;

    // F1: Help Shortcuts
    if (e.key === 'F1') {
      e.preventDefault();
      window.app.executeCommand('help:shortcuts');
      return;
    }

    // Global UI Scaling (active everywhere, including inputs)
    if (isCtrlOrMeta && !e.altKey && (e.key === '+' || e.key === '=' || e.code === 'NumpadAdd' || e.code === 'Equal')) {
      e.preventDefault();
      window.app.executeCommand('view:zoom-in');
      return;
    }
    if (isCtrlOrMeta && !e.altKey && (e.key === '-' || e.key === '_' || e.code === 'NumpadSubtract' || e.code === 'Minus')) {
      e.preventDefault();
      window.app.executeCommand('view:zoom-out');
      return;
    }
    if (isCtrlOrMeta && !e.altKey && (e.key === '0' || e.code === 'Digit0' || e.code === 'Numpad0')) {
      e.preventDefault();
      window.app.executeCommand('view:zoom-reset');
      return;
    }

    // Ctrl+T: New Tab
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 't' || e.key === 'T')) {
      e.preventDefault();
      window.app.executeCommand('tab:new');
      return;
    }

    // Ctrl+W: Close Active Tab
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 'w' || e.key === 'W')) {
      e.preventDefault();
      window.app.executeCommand('tab:close');
      return;
    }

    // Ctrl+Tab: Next Tab
    if (isCtrlOrMeta && !e.shiftKey && e.key === 'Tab') {
      e.preventDefault();
      window.app.executeCommand('tab:next');
      return;
    }

    // Ctrl+Shift+Tab: Previous Tab
    if (isCtrlOrMeta && e.shiftKey && e.key === 'Tab') {
      e.preventDefault();
      window.app.executeCommand('tab:prev');
      return;
    }

    // Ctrl+N: New Workflow
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 'n' || e.key === 'N')) {
      e.preventDefault();
      window.app.executeCommand('file:new');
      return;
    }

    // Ctrl+Q: Exit Application
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 'q' || e.key === 'Q')) {
      e.preventDefault();
      window.app.executeCommand('file:exit');
      return;
    }

    // When focused in text inputs, only intercept Ctrl+S
    if (isInput) {
      if (isCtrlOrMeta && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        window.app.executeCommand('file:save');
      }
      return;
    }

    // Ctrl+O: Open Workflow
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 'o' || e.key === 'O')) {
      e.preventDefault();
      window.app.executeCommand('file:open');
      return;
    }

    // Ctrl+Shift+S: Save As
    if (isCtrlOrMeta && e.shiftKey && !e.altKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      window.app.executeCommand('file:save-as');
      return;
    }

    // Ctrl+S: Save
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 's' || e.key === 'S')) {
      e.preventDefault();
      window.app.executeCommand('file:save');
      return;
    }

    // Ctrl+F: Spotlight Tool Search
    if (isCtrlOrMeta && !e.shiftKey && !e.altKey && (e.key === 'f' || e.key === 'F')) {
      e.preventDefault();
      window.app.executeCommand('edit:find');
      return;
    }

    // Ctrl+Alt+T: Toggle Tool Palette
    if (isCtrlOrMeta && e.altKey && (e.key === 't' || e.key === 'T')) {
      e.preventDefault();
      window.app.executeCommand('view:toggle-palette');
      return;
    }

    // Ctrl+Alt+C: Toggle Config Panel
    if (isCtrlOrMeta && e.altKey && (e.key === 'c' || e.key === 'C')) {
      e.preventDefault();
      window.app.executeCommand('view:toggle-config');
      return;
    }

    // Ctrl+Alt+R: Toggle Results Panel
    if (isCtrlOrMeta && e.altKey && (e.key === 'r' || e.key === 'R')) {
      e.preventDefault();
      window.app.executeCommand('view:toggle-results');
      return;
    }

    // Ctrl+Alt+O: Toggle Overview MiniMap
    if (isCtrlOrMeta && e.altKey && (e.key === 'o' || e.key === 'O')) {
      e.preventDefault();
      window.app.executeCommand('view:toggle-overview');
      return;
    }

    // Ctrl+Alt+W: Toggle Wire Data Probes
    if (isCtrlOrMeta && e.altKey && (e.key === 'w' || e.key === 'W')) {
      e.preventDefault();
      window.app.executeCommand('view:toggle-wire-probes');
      return;
    }

    // Ctrl+Shift+Delete: Purge Engine Cache & Memory
    if (isCtrlOrMeta && e.shiftKey && (e.key === 'Delete' || e.key === 'Del')) {
      e.preventDefault();
      window.app.executeCommand('options:purge-cache');
      return;
    }

    // Ctrl+Enter: Run Workflow
    if (isCtrlOrMeta && e.key === 'Enter') {
      e.preventDefault();
      window.app.executeCommand('workflow:run');
      return;
    }

    // Escape: Stop Workflow if running
    if (e.key === 'Escape' && window._isWorkflowRunning) {
      e.preventDefault();
      window.app.executeCommand('workflow:stop');
      return;
    }
  });
}
