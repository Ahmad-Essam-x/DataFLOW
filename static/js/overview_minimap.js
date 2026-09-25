/**
 * Alteryx-style Canvas Overview (MiniMap) Navigator
 *
 * Provides a miniature interactive canvas rendering workflow nodes, containers,
 * comments, and connections with a dynamic active viewport box.
 * Supports Click-to-Center and Drag-to-Pan navigation, collapsible minimize state,
 * and visibility persistence.
 */

class CanvasMiniMap {
  constructor(canvas) {
    this._canvas = canvas;
    this.container = document.getElementById('canvas-overview-navigator');
    this.header = document.getElementById('overview-header');
    this.body = document.getElementById('overview-body');
    this.canvasEl = document.getElementById('overview-canvas');
    this.ctx = this.canvasEl ? this.canvasEl.getContext('2d') : null;
    this.viewportBox = document.getElementById('overview-viewport-box');
    this.toggleBtn = document.getElementById('btn-overview-toggle');
    this.closeBtn = document.getElementById('btn-overview-close');

    // Persistence states
    this.visible = window.userSettings
      ? Boolean(window.userSettings.get('minimap_visible', true))
      : localStorage.getItem('dataflow_overview_enabled') !== 'false';
    this.collapsed = window.userSettings
      ? Boolean(window.userSettings.get('minimap_collapsed', false))
      : localStorage.getItem('dataflow_overview_collapsed') === 'true';

    this.transform = {
      minX: 0,
      minY: 0,
      maxX: 1000,
      maxY: 800,
      scale: 0.2,
      offsetX: 0,
      offsetY: 0,
      vMinX: 0,
      vMinY: 0,
      vMaxX: 1000,
      vMaxY: 800
    };

    this.isDraggingViewport = false;
    this.dragStart = null;

    this.init();
  }

  get canvas() {
    return (window.appTabManager && window.appTabManager.activeCanvas) || window.appCanvas || this._canvas;
  }

  set canvas(c) {
    this._canvas = c;
    this.hookCanvas();
  }

  init() {
    if (!this.container) return;

    this.applyVisibility();
    this.applyCollapsed();
    this.bindEvents();
    this.hookCanvas();

    // Initial render
    setTimeout(() => this.render(), 100);
  }

  hookCanvas() {
    const c = this.canvas;
    if (!c || c._minimapHooked) return;
    c._minimapHooked = true;

    // Hook onTransformChange to sync viewport in real time
    const origOnTransform = c.onTransformChange;
    c.onTransformChange = () => {
      if (typeof origOnTransform === 'function') origOnTransform();
      if (this.visible && !this.collapsed) this.render();
    };

    // Hook onWorkflowChange to sync nodes, containers, comments, wires
    const origOnWorkflow = c.onWorkflowChange;
    c.onWorkflowChange = () => {
      if (typeof origOnWorkflow === 'function') origOnWorkflow();
      if (this.visible && !this.collapsed) this.render();
    };
  }

  bindEvents() {
    // Header click collapses or restores (ignoring button clicks)
    if (this.header) {
      this.header.addEventListener('click', (e) => {
        if (e.target.closest('.overview-btn')) return;
        this.toggleCollapsed();
      });
    }

    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleCollapsed();
      });
    }

    if (this.closeBtn) {
      this.closeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggle(false);
      });
    }

    // Click anywhere on body (outside viewport box) to center
    if (this.body) {
      this.body.addEventListener('mousedown', (e) => {
        if (e.target === this.viewportBox) return;
        e.preventDefault();
        this.handleClickToCenter(e);
      });
    }

    // Dragging the viewport box
    if (this.viewportBox) {
      this.viewportBox.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        e.preventDefault();
        this.isDraggingViewport = true;
        const boxRect = this.viewportBox.getBoundingClientRect();
        this.dragStart = {
          grabX: e.clientX - boxRect.left,
          grabY: e.clientY - boxRect.top,
          boxWidth: boxRect.width,
          boxHeight: boxRect.height
        };
        document.body.classList.add('resizing-layout');
      });
    }

    window.addEventListener('mousemove', (e) => {
      if (!this.isDraggingViewport || !this.dragStart) return;
      e.preventDefault();
      this.handleDragViewport(e);
    });

    window.addEventListener('mouseup', () => {
      if (this.isDraggingViewport) {
        this.isDraggingViewport = false;
        this.dragStart = null;
        document.body.classList.remove('resizing-layout');
      }
    });

    window.addEventListener('resize', () => {
      if (this.visible && !this.collapsed) {
        this.render();
      }
    });
  }

  toggle(forceState) {
    if (typeof forceState === 'boolean') {
      this.visible = forceState;
    } else {
      this.visible = !this.visible;
    }
    if (window.userSettings) window.userSettings.set('minimap_visible', this.visible);
    else localStorage.setItem('dataflow_overview_enabled', this.visible);
    this.applyVisibility();

    if (window.appMenuBar && typeof window.appMenuBar.syncMenuStates === 'function') {
      window.appMenuBar.syncMenuStates();
    } else if (window.menuBar && typeof window.menuBar.syncMenuStates === 'function') {
      window.menuBar.syncMenuStates();
    }

    if (this.visible && !this.collapsed) {
      this.render();
    }
  }

  applyVisibility() {
    if (!this.container) return;
    if (this.visible) {
      this.container.classList.remove('hidden');
    } else {
      this.container.classList.add('hidden');
    }

    const check = document.getElementById('check-view-overview');
    if (check) {
      check.textContent = this.visible ? '✓' : '';
    }
  }

  toggleCollapsed(forceState) {
    if (typeof forceState === 'boolean') {
      this.collapsed = forceState;
    } else {
      this.collapsed = !this.collapsed;
    }
    if (window.userSettings) window.userSettings.set('minimap_collapsed', this.collapsed);
    else localStorage.setItem('dataflow_overview_collapsed', this.collapsed);
    this.applyCollapsed();
  }

  applyCollapsed() {
    if (!this.container) return;
    if (this.collapsed) {
      this.container.classList.add('collapsed');
      if (this.toggleBtn) this.toggleBtn.textContent = '+';
    } else {
      this.container.classList.remove('collapsed');
      if (this.toggleBtn) this.toggleBtn.textContent = '–';
      this.render();
    }
  }

  handleClickToCenter(e) {
    if (!this.body || !this.transform.scale) return;
    const bodyRect = this.body.getBoundingClientRect();
    const clickMx = e.clientX - bodyRect.left;
    const clickMy = e.clientY - bodyRect.top;

    const t = this.transform;
    const targetWorldX = t.minX + (clickMx - t.offsetX) / t.scale;
    const targetWorldY = t.minY + (clickMy - t.offsetY) / t.scale;

    this.canvas.panTo(targetWorldX, targetWorldY);
  }

  handleDragViewport(e) {
    if (!this.body || !this.transform.scale || !this.dragStart) return;
    const bodyRect = this.body.getBoundingClientRect();
    const newBoxLeft = (e.clientX - bodyRect.left) - this.dragStart.grabX;
    const newBoxTop = (e.clientY - bodyRect.top) - this.dragStart.grabY;

    const centerMx = newBoxLeft + this.dragStart.boxWidth / 2;
    const centerMy = newBoxTop + this.dragStart.boxHeight / 2;

    const t = this.transform;
    const targetWorldX = t.minX + (centerMx - t.offsetX) / t.scale;
    const targetWorldY = t.minY + (centerMy - t.offsetY) / t.scale;

    this.canvas.panTo(targetWorldX, targetWorldY);
  }

  computeWorldBounds() {
    const containerRect = this.canvas.container.getBoundingClientRect();
    const cWidth = containerRect.width || 800;
    const cHeight = containerRect.height || 600;

    const vMinX = -this.canvas.panX / this.canvas.zoom;
    const vMinY = -this.canvas.panY / this.canvas.zoom;
    const vMaxX = (cWidth - this.canvas.panX) / this.canvas.zoom;
    const vMaxY = (cHeight - this.canvas.panY) / this.canvas.zoom;

    let minX = vMinX;
    let minY = vMinY;
    let maxX = vMaxX;
    let maxY = vMaxY;

    // Enclose nodes
    (this.canvas.nodes || []).forEach(n => {
      minX = Math.min(minX, n.x);
      minY = Math.min(minY, n.y);
      maxX = Math.max(maxX, n.x + 56);
      maxY = Math.max(maxY, n.y + 56);
    });

    // Enclose containers
    (this.canvas.containers || []).forEach(c => {
      minX = Math.min(minX, c.x);
      minY = Math.min(minY, c.y);
      maxX = Math.max(maxX, c.x + (c.width || 200));
      maxY = Math.max(maxY, c.y + (c.height || 150));
    });

    // Enclose comments
    (this.canvas.comments || []).forEach(comm => {
      minX = Math.min(minX, comm.x);
      minY = Math.min(minY, comm.y);
      maxX = Math.max(maxX, comm.x + (comm.width || 180));
      maxY = Math.max(maxY, comm.y + (comm.height || 100));
    });

    // Add breathing room margin
    const pad = 120;
    minX -= pad;
    minY -= pad;
    maxX += pad;
    maxY += pad;

    const worldW = Math.max(250, maxX - minX);
    const worldH = Math.max(160, maxY - minY);

    const cw = (this.canvasEl && this.canvasEl.width) ? this.canvasEl.width : 220;
    const ch = (this.canvasEl && this.canvasEl.height) ? this.canvasEl.height : 140;

    const scale = Math.min(cw / worldW, ch / worldH);
    const offsetX = (cw - worldW * scale) / 2;
    const offsetY = (ch - worldH * scale) / 2;

    this.transform = {
      minX,
      minY,
      maxX,
      maxY,
      scale,
      offsetX,
      offsetY,
      vMinX,
      vMinY,
      vMaxX,
      vMaxY
    };

    return this.transform;
  }

  render() {
    if (!this.visible || this.collapsed || !this.ctx || !this.canvasEl) return;

    const t = this.computeWorldBounds();
    const cw = this.canvasEl.width;
    const ch = this.canvasEl.height;

    this.ctx.clearRect(0, 0, cw, ch);

    const toM = (wx, wy) => ({
      x: t.offsetX + (wx - t.minX) * t.scale,
      y: t.offsetY + (wy - t.minY) * t.scale
    });

    // 1. Draw Containers
    (this.canvas.containers || []).forEach(c => {
      const p = toM(c.x, c.y);
      const w = (c.width || 200) * t.scale;
      const h = (c.height || 150) * t.scale;
      const color = c.color || '#3b82f6';

      this.ctx.fillStyle = color.startsWith('#') ? color + '1a' : 'rgba(59, 130, 246, 0.12)';
      this.ctx.fillRect(p.x, p.y, w, h);

      this.ctx.strokeStyle = color;
      this.ctx.lineWidth = 1;
      this.ctx.strokeRect(p.x, p.y, w, h);

      // Header strip
      this.ctx.fillStyle = color;
      this.ctx.fillRect(p.x, p.y, w, Math.min(h, Math.max(3, 22 * t.scale)));
    });

    // 2. Draw Comments / Annotations
    (this.canvas.comments || []).forEach(comm => {
      const p = toM(comm.x, comm.y);
      const w = (comm.width || 180) * t.scale;
      const h = (comm.height || 100) * t.scale;
      const color = comm.color || '#eab308';

      this.ctx.fillStyle = color.startsWith('#') ? color + '33' : 'rgba(234, 179, 8, 0.2)';
      this.ctx.fillRect(p.x, p.y, w, h);

      this.ctx.strokeStyle = color;
      this.ctx.lineWidth = 0.8;
      this.ctx.strokeRect(p.x, p.y, w, h);
    });

    // 3. Draw Connections (Wires)
    this.ctx.lineWidth = 1.2;
    this.ctx.strokeStyle = 'rgba(148, 163, 184, 0.5)';
    (this.canvas.connections || []).forEach(conn => {
      const sNode = (this.canvas.nodes || []).find(n => n.id === (conn.source || conn.sourceId));
      const tNode = (this.canvas.nodes || []).find(n => n.id === (conn.target || conn.targetId));
      if (sNode && tNode) {
        const sp = toM(sNode.x + 56, sNode.y + 28);
        const tp = toM(tNode.x, tNode.y + 28);
        this.ctx.beginPath();
        this.ctx.moveTo(sp.x, sp.y);
        if (this.canvas.wireStyle === 'orthogonal') {
          const midX = (sp.x + tp.x) / 2;
          this.ctx.lineTo(midX, sp.y);
          this.ctx.lineTo(midX, tp.y);
        }
        this.ctx.lineTo(tp.x, tp.y);
        this.ctx.stroke();
      }
    });

    // 4. Draw Nodes
    (this.canvas.nodes || []).forEach(node => {
      const p = toM(node.x, node.y);
      const nw = Math.max(5, 56 * t.scale);
      const nh = Math.max(5, 56 * t.scale);

      const meta = (this.canvas.toolRegistry && this.canvas.toolRegistry[node.type]) || {};
      const color = meta.color || '#0072ce';

      // Node box
      this.ctx.fillStyle = color;
      this.ctx.fillRect(p.x, p.y, nw, nh);

      // Selected / Border accent
      const isSelected = this.canvas.selectedNodeIds && this.canvas.selectedNodeIds.has(node.id);
      this.ctx.strokeStyle = isSelected ? '#f59e0b' : '#ffffff';
      this.ctx.lineWidth = isSelected ? 1.5 : 0.8;
      this.ctx.strokeRect(p.x, p.y, nw, nh);

      // Cached dot indicator
      if (this.canvas.cachedNodeIds && this.canvas.cachedNodeIds.has(node.id)) {
        this.ctx.fillStyle = '#38bdf8';
        this.ctx.beginPath();
        this.ctx.arc(p.x + nw - 2, p.y + 2, 2, 0, Math.PI * 2);
        this.ctx.fill();
      }
    });

    // 5. Update Viewport Box position
    if (this.viewportBox) {
      const vpLeft = t.offsetX + (t.vMinX - t.minX) * t.scale;
      const vpTop = t.offsetY + (t.vMinY - t.minY) * t.scale;
      const vpWidth = (t.vMaxX - t.vMinX) * t.scale;
      const vpHeight = (t.vMaxY - t.vMinY) * t.scale;

      this.viewportBox.style.left = `${Math.round(vpLeft)}px`;
      this.viewportBox.style.top = `${Math.round(vpTop)}px`;
      this.viewportBox.style.width = `${Math.max(14, Math.round(vpWidth))}px`;
      this.viewportBox.style.height = `${Math.max(10, Math.round(vpHeight))}px`;
    }
  }
}

// Attach to window
window.CanvasMiniMap = CanvasMiniMap;
