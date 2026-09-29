/**
 * Undo / Redo History Manager for Visual Workflow Canvas.
 * Implements the Memento pattern with a maximum stack size and state serialization.
 */
class HistoryManager {
  constructor(canvas, maxHistory = 40) {
    this.canvas = canvas;
    this.maxHistory = maxHistory;
    this.undoStack = [];
    this.redoStack = [];
    this.isApplying = false;
  }

  setCanvas(canvas) {
    this.canvas = canvas;
  }

  pushSnapshot(description = 'Action') {
    if (this.isApplying || !this.canvas) return;

    const snapshot = JSON.stringify({
      nodes: this.canvas.nodes,
      connections: this.canvas.connections,
      containers: this.canvas.containers || [],
      comments: this.canvas.comments || []
    });

    // Don't push identical consecutive snapshots
    if (this.undoStack.length > 0 && this.undoStack[this.undoStack.length - 1] === snapshot) {
      return;
    }

    this.undoStack.push(snapshot);
    if (this.undoStack.length > this.maxHistory) {
      this.undoStack.shift();
    }
    // Clear redo stack on new user action
    this.redoStack = [];
    this.updateUI();
  }

  undo() {
    if (this.undoStack.length <= 1 || !this.canvas) return false;

    this.isApplying = true;
    try {
      const current = this.undoStack.pop();
      this.redoStack.push(current);

      const target = this.undoStack[this.undoStack.length - 1];
      const state = JSON.parse(target);
      this.canvas.loadWorkflow(state);
      if (window.showToast) window.showToast('info', 'Undo', 'Reverted previous action.');
    } finally {
      this.isApplying = false;
      this.updateUI();
    }
    return true;
  }

  redo() {
    if (this.redoStack.length === 0 || !this.canvas) return false;

    this.isApplying = true;
    try {
      const target = this.redoStack.pop();
      this.undoStack.push(target);

      const state = JSON.parse(target);
      this.canvas.loadWorkflow(state);
      if (window.showToast) window.showToast('info', 'Redo', 'Restored action.');
    } finally {
      this.isApplying = false;
      this.updateUI();
    }
    return true;
  }

  canUndo() {
    return this.undoStack.length > 1;
  }

  canRedo() {
    return this.redoStack.length > 0;
  }

  updateUI() {
    if (window.appEventBus) {
      window.appEventBus.emit('history:changed', {
        canUndo: this.canUndo(),
        canRedo: this.canRedo()
      });
    }
  }
}

window.appHistory = new HistoryManager(null);

// ── Single Global Undo/Redo Shortcut Listener (Tab-Aware) ──
// Operates exclusively on whichever TabContext's HistoryManager is active in window.appHistory
window.addEventListener('keydown', (e) => {
  const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
  if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement && document.activeElement.isContentEditable)) {
    return;
  }

  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
    if (e.shiftKey) {
      e.preventDefault();
      if (window.appHistory && typeof window.appHistory.redo === 'function') {
        window.appHistory.redo();
      }
    } else {
      e.preventDefault();
      if (window.appHistory && typeof window.appHistory.undo === 'function') {
        window.appHistory.undo();
      }
    }
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') {
    e.preventDefault();
    if (window.appHistory && typeof window.appHistory.redo === 'function') {
      window.appHistory.redo();
    }
  }
});
