/**
 * Interactive Visual Workflow Canvas (Alteryx Designer Parity).
 * Compact 56x56 tool glyphs, protruding arrow anchors, cubic Bézier connections,
 * marquee box multi-selection, alignment tools, context menu, spotlight quick-search,
 * undo/redo history, and live wire animation.
 */

class Canvas {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.wrapper = document.getElementById('canvas-wrapper');
    this.svg = document.getElementById('canvas-svg');
    this.wiresGroup = document.getElementById('wires-group');
    this.tempWire = document.getElementById('temp-wire');
    this.containersLayer = document.getElementById('containers-layer');
    this.commentsLayer = document.getElementById('comments-layer');
    this.nodesLayer = document.getElementById('nodes-layer');
    this.zoomText = document.getElementById('zoom-level-text');

    this.onSelectNode = options.onSelectNode || (() => {});
    this.onWorkflowChange = options.onWorkflowChange || (() => {});

    // Graph state
    this.nodes = [];
    this.connections = [];
    this.containers = [];
    this.comments = [];
    this.toolRegistry = {};

    // View transform
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.isSpacePressed = false;

    // Selection
    this.selectedNodeId = null;
    this.selectedNodeIds = new Set();
    this.selectedContainerId = null;
    this.selectedContainerIds = new Set();
    this.selectedCommentId = null;
    this.selectedCommentIds = new Set();
    this.selectedConnectionId = null;

    // Clipboard
    this.clipboard = null;

    // Frozen / Cached node tracking
    this.cachedNodeIds = new Set();

    // Wire Hover Data Probes preference (default true)
    this.wireProbesEnabled = window.userSettings
      ? window.userSettings.get('wire_probes_enabled', true)
      : localStorage.getItem('dataflow_wire_probes_enabled') !== 'false';

    // Node Execution Badges Duration (default '3000'ms, or '5000', '10000', 'always', 'off')
    this.nodeBadgeDuration = window.userSettings
      ? window.userSettings.get('node_badge_duration', '3000')
      : (localStorage.getItem('dataflow_node_badge_duration') || '3000');
    this._pillTimers = {};

    // Canvas & Visual Preferences
    const savedSnap = window.userSettings
      ? window.userSettings.get('grid_snap', 16)
      : localStorage.getItem('dataflow_grid_snap');
    this.gridSnapSize = savedSnap !== null && savedSnap !== undefined ? parseInt(savedSnap, 10) : 16;
    this.wireStyle = window.userSettings
      ? window.userSettings.get('wire_style', 'bezier')
      : (localStorage.getItem('dataflow_wire_style') || 'bezier');
    this.autoCacheUpstream = window.userSettings
      ? Boolean(window.userSettings.get('auto_cache_upstream', false))
      : localStorage.getItem('dataflow_auto_cache_upstream') === 'true';

    // Interaction states
    this.isPanning = false;
    this.panStart = { x: 0, y: 0 };
    this.draggingNode = null;
    this.dragOffset = { x: 0, y: 0 };
    this.multiDragOffsets = new Map();
    this.draggingContainer = null;
    this.resizingContainer = null;
    this.draggingComment = null;
    this.resizingComment = null;
    this.containerDragOffsets = new Map();
    this.containerDragStart = null;
    this.resizeStart = null;
    this.dragMoved = false;
    this._pendingSingleSelectOnMouseUp = null;
    this.connectingState = null;

    // Marquee box selection state
    this.marqueeStart = null;
    this.marqueeEl = null;
    this.marqueeInitialSelected = new Set();
    this.marqueeInitialContainers = new Set();
    this.marqueeInitialComments = new Set();

    // Mouse coordinates tracking for spotlight spawn
    this.lastMouseCanvas = { x: 200, y: 150 };

    // Floating wire delete button element
    this.createWireDeleteBtn();
    this.createMarqueeElement();
    this.createContextMenu();
    this.createSpotlightModal();

    this.initEvents();

    if (window.appHistory) {
      window.appHistory.setCanvas(this);
    }
  }

  createWireDeleteBtn() {
    let btn = document.getElementById('wire-delete-btn');
    if (!btn) {
      btn = document.createElement('div');
      btn.id = 'wire-delete-btn';
      btn.className = 'wire-delete-btn';
      btn.innerHTML = '&times;';
      btn.title = 'Click to delete this connection (Delete / Backspace)';
      btn.style.display = 'none';
      this.wrapper.appendChild(btn);

      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (this.selectedConnectionId) {
          this.removeConnection(this.selectedConnectionId);
        }
      });
    }
    this.wireDeleteBtn = btn;
  }

  createMarqueeElement() {
    this.marqueeEl = document.createElement('div');
    this.marqueeEl.className = 'marquee-selection';
    this.marqueeEl.style.display = 'none';
    this.wrapper.appendChild(this.marqueeEl);
  }

  createContextMenu() {
    let menu = document.getElementById('canvas-context-menu');
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'canvas-context-menu';
      menu.className = 'context-menu';
      menu.style.display = 'none';
      document.body.appendChild(menu);
    }
    this.contextMenu = menu;

    document.addEventListener('click', () => {
      if (this.contextMenu) this.contextMenu.style.display = 'none';
    });
  }

  createSpotlightModal() {
    let modal = document.getElementById('spotlight-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'spotlight-modal';
      modal.className = 'spotlight-backdrop';
      modal.style.display = 'none';
      modal.innerHTML = `
        <div class="spotlight-box">
          <div class="spotlight-input-wrap">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="11" cy="11" r="8"></circle>
              <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
            </svg>
            <input type="text" class="spotlight-input" placeholder="Search & add tool (e.g. Filter, Summarize, Select)..." spellcheck="false">
          </div>
          <div class="spotlight-results" id="spotlight-results-list"></div>
        </div>
      `;
      document.body.appendChild(modal);

      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.style.display = 'none';
      });

      const inp = modal.querySelector('.spotlight-input');
      inp.addEventListener('input', () => this.filterSpotlightResults());
      inp.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          modal.style.display = 'none';
        } else if (e.key === 'Enter') {
          const firstItem = modal.querySelector('.spotlight-item');
          if (firstItem) firstItem.click();
        }
      });
    }
    this.spotlightModal = modal;
  }

  openSpotlight(x, y) {
    if (!this.spotlightModal) return;
    if (x === undefined || x === null || y === undefined || y === null) {
      const center = this.getViewportCenter();
      x = center.x;
      y = center.y;
    }
    this.spotlightSpawnPos = { x, y };
    this.spotlightModal.style.display = 'flex';
    const inp = this.spotlightModal.querySelector('.spotlight-input');
    inp.value = '';
    this.filterSpotlightResults();
    setTimeout(() => inp.focus(), 50);
  }

  filterSpotlightResults() {
    const list = this.spotlightModal.querySelector('#spotlight-results-list');
    const query = this.spotlightModal.querySelector('.spotlight-input').value.toLowerCase().trim();
    list.innerHTML = '';

    const tools = Object.values(this.toolRegistry);
    const filtered = tools.filter(t => 
      !query || t.name.toLowerCase().includes(query) || (t.description && t.description.toLowerCase().includes(query))
    );

    if (filtered.length === 0) {
      list.innerHTML = '<div style="padding: 16px; text-align: center; color: var(--text-muted); font-size: 12px;">No matching tools</div>';
      return;
    }

    filtered.forEach((tool, idx) => {
      const item = document.createElement('div');
      item.className = `spotlight-item ${idx === 0 ? 'active' : ''}`;
      const iconSvg = window.appPalette ? window.appPalette.getToolSvg(tool.icon) : '';

      item.innerHTML = `
        <div style="width: 28px; height: 28px; border-radius: 6px; background: ${tool.color}20; color: ${tool.color}; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
          ${iconSvg}
        </div>
        <div style="flex: 1;">
          <div style="font-weight: 600; font-size: 13px;">${tool.name}</div>
          <div style="font-size: 11px; color: var(--text-secondary);">${tool.description || ''}</div>
        </div>
        <span style="font-size: 10px; font-weight: 700; text-transform: uppercase; color: ${tool.color};">${tool.category}</span>
      `;

      item.addEventListener('click', () => {
        const pos = this.spotlightSpawnPos || this.getViewportCenter();
        if (tool.type === 'tool_container') {
          this.addContainer(pos.x, pos.y);
        } else if (tool.type === 'comment') {
          this.addComment(pos.x, pos.y);
        } else {
          this.addNode(tool.type, pos.x - 28, pos.y - 28);
        }
        this.spotlightModal.style.display = 'none';
      });

      list.appendChild(item);
    });
  }

  setToolsRegistry(tools) {
    tools.forEach(t => {
      this.toolRegistry[t.type] = t;
    });
  }

  getCanvasCoords(clientX, clientY) {
    const rect = this.container.getBoundingClientRect();
    return {
      x: (clientX - rect.left - this.panX) / this.zoom,
      y: (clientY - rect.top - this.panY) / this.zoom
    };
  }

  snapCoord(val) {
    if (!this.gridSnapSize || this.gridSnapSize <= 0) return Math.round(val);
    return Math.round(val / this.gridSnapSize) * this.gridSnapSize;
  }

  initEvents() {
    // Canvas mouse tracker for quick spawn
    this.container.addEventListener('mousemove', (e) => {
      this.lastMouseCanvas = this.getCanvasCoords(e.clientX, e.clientY);
    });

    // Keyboard shortcuts on canvas
    window.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'input' || activeTag === 'textarea' || document.activeElement.isContentEditable) {
        return;
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        this.deleteSelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        e.preventDefault();
        this.copySelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'x') {
        e.preventDefault();
        this.cutSelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'v') {
        e.preventDefault();
        this.pasteClipboard();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'd') {
        e.preventDefault();
        this.duplicateSelected();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        e.preventDefault();
        this.selectAll();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'g') {
        e.preventDefault();
        if (this.selectedNodeIds.size > 0) {
          this.addContainerFromSelection(Array.from(this.selectedNodeIds));
        }
      } else if (e.key === 'Tab') {
        e.preventDefault();
        this.openSpotlight(this.lastMouseCanvas.x, this.lastMouseCanvas.y);
      } else if (e.code === 'Space' && !this.isSpacePressed) {
        this.isSpacePressed = true;
        this.container.style.cursor = 'grab';
        e.preventDefault();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        const step = e.shiftKey ? 120 : 40;
        this.panY += step;
        this.updateTransform();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        const step = e.shiftKey ? 120 : 40;
        this.panY -= step;
        this.updateTransform();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        const step = e.shiftKey ? 120 : 40;
        this.panX += step;
        this.updateTransform();
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        const step = e.shiftKey ? 120 : 40;
        this.panX -= step;
        this.updateTransform();
      }
    });

    window.addEventListener('keyup', (e) => {
      if (e.code === 'Space') {
        this.isSpacePressed = false;
        if (!this.isPanning) {
          this.container.style.cursor = 'default';
        }
      }
    });

    // Double-click on canvas background opens Spotlight Quick Search
    this.container.addEventListener('dblclick', (e) => {
      const isBackground = e.target === this.container || e.target === this.wrapper || 
                           e.target === this.svg || e.target === this.containersLayer || 
                           e.target === this.commentsLayer || e.target === this.nodesLayer;
      if (isBackground) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        this.openSpotlight(mouse.x, mouse.y);
      }
    });

    // Context Menu on Right Click
    this.container.addEventListener('contextmenu', (e) => {
      e.preventDefault();
      const nodeCard = e.target.closest('.node-card');
      const containerCard = e.target.closest('.tool-container');
      const commentCard = e.target.closest('.comment-note');
      const mouse = this.getCanvasCoords(e.clientX, e.clientY);

      if (nodeCard) {
        const nodeId = nodeCard.id.replace('node-elem-', '');
        if (!this.selectedNodeIds.has(nodeId)) {
          this.selectNode(nodeId);
        }
        this.showNodeContextMenu(e.clientX, e.clientY);
      } else if (containerCard) {
        const cId = containerCard.id.replace('container-elem-', '');
        this.selectContainer(cId);
        this.showContainerContextMenu(cId, e.clientX, e.clientY);
      } else if (commentCard) {
        const commId = commentCard.id.replace('comment-elem-', '');
        this.selectComment(commId);
        this.showNodeContextMenu(e.clientX, e.clientY);
      } else {
        this.showCanvasContextMenu(e.clientX, e.clientY, mouse.x, mouse.y);
      }
    });

    // 1. Pan & Marquee with mouse drag on background
    this.container.addEventListener('mousedown', (e) => {
      if (this.isSpacePressed || e.button === 1) {
        e.preventDefault();
        this.clearSelection();
        this.isPanning = true;
        this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
        this.container.style.cursor = 'grabbing';
        return;
      }

      const isBackground = e.target === this.container || e.target === this.wrapper || 
                           e.target === this.svg || e.target === this.containersLayer || 
                           e.target === this.commentsLayer || e.target === this.nodesLayer;
      if (isBackground) {
        this.hideWireProbe();
        if (this.connectingState) {
          this.cancelConnecting();
          return;
        }

        if (e.button === 0 && e.shiftKey && e.altKey) {
          // Shift+Alt+Left Click = Panning
          this.clearSelection();
          this.isPanning = true;
          this.panStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
          this.container.style.cursor = 'grabbing';
        } else if (e.button === 0) {
          // Normal Left Click on background = Marquee Box Selection
          const isModifier = e.ctrlKey || e.metaKey || e.shiftKey;
          if (!isModifier) {
            this.clearSelection();
          }
          const mouse = this.getCanvasCoords(e.clientX, e.clientY);
          this.marqueeStart = mouse;
          this.marqueeInitialSelected = new Set(this.selectedNodeIds);
          this.marqueeInitialContainers = new Set(this.selectedContainerIds);
          this.marqueeInitialComments = new Set(this.selectedCommentIds);

          this.marqueeEl.style.left = `${mouse.x}px`;
          this.marqueeEl.style.top = `${mouse.y}px`;
          this.marqueeEl.style.width = '0px';
          this.marqueeEl.style.height = '0px';
          this.marqueeEl.style.display = 'block';
        }
      }
    });

    window.addEventListener('mousemove', (e) => {
      // Panning
      if (this.isPanning) {
        this.panX = e.clientX - this.panStart.x;
        this.panY = e.clientY - this.panStart.y;
        this.updateTransform();
        return;
      }

      // Marquee selection
      if (this.marqueeStart) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        const minX = Math.min(this.marqueeStart.x, mouse.x);
        const maxX = Math.max(this.marqueeStart.x, mouse.x);
        const minY = Math.min(this.marqueeStart.y, mouse.y);
        const maxY = Math.max(this.marqueeStart.y, mouse.y);

        this.marqueeEl.style.left = `${minX}px`;
        this.marqueeEl.style.top = `${minY}px`;
        this.marqueeEl.style.width = `${maxX - minX}px`;
        this.marqueeEl.style.height = `${maxY - minY}px`;

        // Intersections with compact 56x56 nodes
        const nextSelectedNodes = new Set(this.marqueeInitialSelected);
        this.nodes.forEach(node => {
          const intersects = (node.x + 56 >= minX && node.x <= maxX && node.y + 56 >= minY && node.y <= maxY);
          if (intersects) nextSelectedNodes.add(node.id);
        });
        this.selectedNodeIds = nextSelectedNodes;

        // Intersections with containers
        const nextSelectedContainers = new Set(this.marqueeInitialContainers);
        this.containers.forEach(c => {
          const intersects = (c.x + c.width >= minX && c.x <= maxX && c.y + c.height >= minY && c.y <= maxY);
          if (intersects) nextSelectedContainers.add(c.id);
        });
        this.selectedContainerIds = nextSelectedContainers;

        // Intersections with comments
        const nextSelectedComments = new Set(this.marqueeInitialComments);
        this.comments.forEach(comm => {
          const intersects = (comm.x + comm.width >= minX && comm.x <= maxX && comm.y + comm.height >= minY && comm.y <= maxY);
          if (intersects) nextSelectedComments.add(comm.id);
        });
        this.selectedCommentIds = nextSelectedComments;

        this.updateSelectionVisuals();
        return;
      }

      // Dragging nodes (single or multi-selection group drag)
      if (this.draggingNode) {
        this.dragMoved = true;
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        const dx = this.snapCoord(mouse.x - this.dragOffset.x) - this.draggingNode.x;
        const dy = this.snapCoord(mouse.y - this.dragOffset.y) - this.draggingNode.y;

        if (this.selectedNodeIds.size > 1 && this.selectedNodeIds.has(this.draggingNode.id)) {
          // Move all selected nodes in unison
          this.selectedNodeIds.forEach(id => {
            const n = this.nodes.find(node => node.id === id);
            if (n) {
              const initPos = this.multiDragOffsets.get(id);
              if (initPos) {
                n.x = this.snapCoord(initPos.x + dx);
                n.y = this.snapCoord(initPos.y + dy);
                this.updateNodeElementPosition(n);
              }
            }
          });
        } else {
          this.draggingNode.x = this.snapCoord(mouse.x - this.dragOffset.x);
          this.draggingNode.y = this.snapCoord(mouse.y - this.dragOffset.y);
          this.updateNodeElementPosition(this.draggingNode);
        }

        this.renderWires();
        return;
      }

      // Dragging a Container and its enclosed tools
      if (this.draggingContainer) {
        this.dragMoved = true;
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        const newX = this.snapCoord(mouse.x - this.dragOffset.x);
        const newY = this.snapCoord(mouse.y - this.dragOffset.y);
        const startX = this.containerDragStart ? this.containerDragStart.x : this.draggingContainer.x;
        const startY = this.containerDragStart ? this.containerDragStart.y : this.draggingContainer.y;
        const totalDx = newX - startX;
        const totalDy = newY - startY;

        this.draggingContainer.x = newX;
        this.draggingContainer.y = newY;
        const cEl = document.getElementById(`container-elem-${this.draggingContainer.id}`);
        if (cEl) {
          cEl.style.left = `${newX}px`;
          cEl.style.top = `${newY}px`;
        }

        // Move all enclosed nodes by totalDx, totalDy from their initial positions
        this.containerDragOffsets.forEach((initPos, nid) => {
          const n = this.nodes.find(node => node.id === nid);
          if (n) {
            n.x = this.snapCoord(initPos.x + totalDx);
            n.y = this.snapCoord(initPos.y + totalDy);
            this.updateNodeElementPosition(n);
          }
        });

        this.renderWires();
        return;
      }

      // Resizing a Container
      if (this.resizingContainer) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        const dx = mouse.x - this.resizeStart.mouseX;
        const dy = mouse.y - this.resizeStart.mouseY;
        this.resizingContainer.width = Math.max(160, this.snapCoord(this.resizeStart.initW + dx));
        this.resizingContainer.height = Math.max(70, this.snapCoord(this.resizeStart.initH + dy));
        const cEl = document.getElementById(`container-elem-${this.resizingContainer.id}`);
        if (cEl) {
          cEl.style.width = `${this.resizingContainer.width}px`;
          if (!this.resizingContainer.collapsed) {
            cEl.style.height = `${this.resizingContainer.height}px`;
          }
        }
        this.updateContainerEnclosedNodes(this.resizingContainer);
        this.renderWires();
        return;
      }

      // Dragging a Comment Note
      if (this.draggingComment) {
        this.dragMoved = true;
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        this.draggingComment.x = this.snapCoord(mouse.x - this.dragOffset.x);
        this.draggingComment.y = this.snapCoord(mouse.y - this.dragOffset.y);
        const commEl = document.getElementById(`comment-elem-${this.draggingComment.id}`);
        if (commEl) {
          commEl.style.left = `${this.draggingComment.x}px`;
          commEl.style.top = `${this.draggingComment.y}px`;
        }
        return;
      }

      // Resizing a Comment Note
      if (this.resizingComment) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        const dx = mouse.x - this.resizeStart.mouseX;
        const dy = mouse.y - this.resizeStart.mouseY;
        this.resizingComment.width = Math.max(140, Math.round(this.resizeStart.initW + dx));
        this.resizingComment.height = Math.max(60, Math.round(this.resizeStart.initH + dy));
        const commEl = document.getElementById(`comment-elem-${this.resizingComment.id}`);
        if (commEl) {
          commEl.style.width = `${this.resizingComment.width}px`;
          commEl.style.height = `${this.resizingComment.height}px`;
        }
        return;
      }

      // Wiring connection
      if (this.connectingState) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        if (Math.hypot(mouse.x - this.connectingState.startX, mouse.y - this.connectingState.startY) > 3) {
          this.connectingState.moved = true;
        }

        // Magnetic snapping near candidate ports
        const candidate = this.findCandidatePortNear(mouse.x, mouse.y);
        if (candidate) {
          this.connectingState.snappedPort = candidate;
          document.querySelectorAll('.port.snap-target').forEach(p => p.classList.remove('snap-target'));
          candidate.element.classList.add('snap-target');

          if (this.connectingState.sourceType === 'output') {
            this.updateTempWire(this.connectingState.startX, this.connectingState.startY, candidate.x, candidate.y);
          } else {
            this.updateTempWire(candidate.x, candidate.y, this.connectingState.startX, this.connectingState.startY);
          }
        } else {
          this.connectingState.snappedPort = null;
          document.querySelectorAll('.port.snap-target').forEach(p => p.classList.remove('snap-target'));

          if (this.connectingState.sourceType === 'output') {
            this.updateTempWire(this.connectingState.startX, this.connectingState.startY, mouse.x, mouse.y);
          } else {
            this.updateTempWire(mouse.x, mouse.y, this.connectingState.startX, this.connectingState.startY);
          }
        }
      }
    });

    window.addEventListener('mouseup', () => {
      if (this.isPanning) {
        this.isPanning = false;
        this.container.style.cursor = this.isSpacePressed ? 'grab' : 'default';
      }

      if (this.marqueeStart) {
        this.marqueeStart = null;
        this.marqueeEl.style.display = 'none';
        this.updateSelectionVisuals();
        if (this.selectedNodeIds.size === 1) {
          this.selectedNodeId = Array.from(this.selectedNodeIds)[0];
          const node = this.nodes.find(n => n.id === this.selectedNodeId);
          this.onSelectNode(node);
        } else if (this.selectedNodeIds.size === 0 && this.selectedContainerIds.size === 1) {
          this.selectContainer(Array.from(this.selectedContainerIds)[0]);
        } else if (this.selectedNodeIds.size === 0 && this.selectedCommentIds.size === 1) {
          this.selectComment(Array.from(this.selectedCommentIds)[0]);
        }
      }

      if (this.draggingNode) {
        if (!this.dragMoved && this._pendingSingleSelectOnMouseUp) {
          this.selectNode(this._pendingSingleSelectOnMouseUp, false);
        }
        this._pendingSingleSelectOnMouseUp = null;
        this.draggingNode = null;
        this.multiDragOffsets.clear();
        this.containers.forEach(c => this.updateContainerEnclosedNodes(c));
        this.renderWires();
        this.onWorkflowChange();
        if (this.dragMoved && window.appHistory) window.appHistory.pushSnapshot('Move Nodes');
      }

      if (this.draggingContainer) {
        const movedContainer = this.draggingContainer;
        this.draggingContainer = null;
        this.containerDragOffsets.clear();
        this.containerDragStart = null;
        this.updateContainerEnclosedNodes(movedContainer);
        this.renderWires();
        this.onWorkflowChange();
        if (this.dragMoved && window.appHistory) window.appHistory.pushSnapshot('Move Container');
      }

      if (this.resizingContainer) {
        const resized = this.resizingContainer;
        this.resizingContainer = null;
        this.updateContainerEnclosedNodes(resized);
        this.renderWires();
        this.onWorkflowChange();
        if (window.appHistory) window.appHistory.pushSnapshot('Resize Container');
      }

      if (this.draggingComment) {
        this.draggingComment = null;
        this.onWorkflowChange();
        if (this.dragMoved && window.appHistory) window.appHistory.pushSnapshot('Move Note');
      }

      if (this.resizingComment) {
        this.resizingComment = null;
        this.onWorkflowChange();
        if (window.appHistory) window.appHistory.pushSnapshot('Resize Note');
      }

      if (this.connectingState) {
        if (this.connectingState.moved) {
          if (this.connectingState.snappedPort) {
            const sp = this.connectingState.snappedPort;
            if (this.connectingState.sourceType === 'output') {
              this.addConnection(this.connectingState.sourceNodeId, this.connectingState.sourceHandle, sp.nodeId, sp.portName);
            } else {
              this.addConnection(sp.nodeId, sp.portName, this.connectingState.sourceNodeId, this.connectingState.sourceHandle);
            }
          }
          this.cancelConnecting();
          this._suppressNextPortClick = true;
          setTimeout(() => { this._suppressNextPortClick = false; }, 120);
        }
      }
    });

    // 2D Scroll / Pan & Zoom via wheel
    this.container.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        // Zoom via Ctrl/Cmd + Wheel or trackpad pinch gesture
        const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
        this.zoomAtPoint(zoomFactor, e.clientX, e.clientY);
      } else {
        // 2D Scroll / Pan Navigation
        let multiplier = 1;
        if (e.deltaMode === 1) multiplier = 24;
        else if (e.deltaMode === 2) multiplier = this.container.clientHeight || 500;

        let dx = e.deltaX * multiplier;
        let dy = e.deltaY * multiplier;

        if (e.shiftKey && dx === 0) {
          // Shift + vertical mouse wheel rotates to horizontal scroll
          dx = dy;
          dy = 0;
        }

        this.panX -= dx;
        this.panY -= dy;
        this.updateTransform();
      }
    }, { passive: false });

    // Drag and Drop (from Tool Palette and Native OS Files)
    this.fileDragCounter = 0;

    const isNativeFileDrag = (e) => {
      if (!e.dataTransfer || !e.dataTransfer.types) return false;
      return e.dataTransfer.types.includes('Files') || e.dataTransfer.types.includes('application/x-moz-file');
    };

    const showDropzone = () => {
      const overlay = document.getElementById('canvas-dropzone-overlay');
      if (overlay) {
        overlay.style.display = 'flex';
        overlay.classList.add('drag-active');
      }
    };

    const hideDropzone = () => {
      const overlay = document.getElementById('canvas-dropzone-overlay');
      if (overlay) {
        overlay.style.display = 'none';
        overlay.classList.remove('drag-active');
      }
    };

    this.container.addEventListener('dragenter', (e) => {
      if (isNativeFileDrag(e)) {
        this.fileDragCounter++;
        showDropzone();
      }
    });

    this.container.addEventListener('dragover', (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'copy';
      if (isNativeFileDrag(e) && this.fileDragCounter <= 0) {
        this.fileDragCounter = 1;
        showDropzone();
      }
    });

    this.container.addEventListener('dragleave', (e) => {
      if (isNativeFileDrag(e)) {
        this.fileDragCounter--;
        if (this.fileDragCounter <= 0) {
          this.fileDragCounter = 0;
          hideDropzone();
        }
      }
    });

    this.container.addEventListener('drop', (e) => {
      e.preventDefault();
      this.fileDragCounter = 0;
      hideDropzone();

      const coords = this.getCanvasCoords(e.clientX, e.clientY);

      // 1. Native OS File Drop (.csv, .xlsx, .xls, .tsv, .txt, .json)
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        this.handleDroppedFiles(e.dataTransfer.files, coords);
        return;
      }

      // 2. Palette Tool Drop (application/json)
      const rawData = e.dataTransfer.getData('application/json');
      if (rawData) {
        try {
          const tool = JSON.parse(rawData);
          if (tool.type === 'tool_container') {
            this.addContainer(coords.x, coords.y);
          } else if (tool.type === 'comment') {
            this.addComment(coords.x, coords.y);
          } else {
            this.addNode(tool.type, coords.x - 28, coords.y - 28);
          }
        } catch (err) {
          console.error('Failed to parse dropped tool data:', err);
        }
      }
    });
  }

  showNodeContextMenu(x, y) {
    if (!this.contextMenu) return;
    const hasMultiple = this.selectedNodeIds.size > 1;
    const hasSelectedNodes = this.selectedNodeIds.size > 0;
    const singleNodeId = this.selectedNodeIds.size === 1 ? Array.from(this.selectedNodeIds)[0] : null;
    const isCached = singleNodeId && this.cachedNodeIds.has(singleNodeId);

    this.contextMenu.innerHTML = `
      ${hasSelectedNodes ? `
        <div class="context-menu-item" id="ctx-add-to-container">
          <span>📦 Add to New Container</span>
          <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+G</kbd>
        </div>
        <div class="context-menu-divider"></div>
      ` : ''}
      ${hasMultiple ? `
        <div class="context-menu-item" id="ctx-align-h">
          <span>↔️ Align Horizontally</span>
        </div>
        <div class="context-menu-item" id="ctx-align-v">
          <span>↕️ Align Vertically</span>
        </div>
        <div class="context-menu-divider"></div>
      ` : ''}
      <div class="context-menu-item" id="ctx-copy">
        <span>📋 Copy</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+C</kbd>
      </div>
      <div class="context-menu-item" id="ctx-cut">
        <span>✂️ Cut</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+X</kbd>
      </div>
      <div class="context-menu-item" id="ctx-duplicate">
        <span>📄 Duplicate</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+D</kbd>
      </div>
      <div class="context-menu-item" id="ctx-delete" style="color:var(--color-error);">
        <span>🗑️ Delete</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Del</kbd>
      </div>
      <div class="context-menu-divider"></div>
      ${singleNodeId ? `
        <div class="context-menu-item" id="ctx-cache-toggle" style="color: #0284c7;">
          <span>${isCached ? '🔓 Clear Cache' : '❄️ Cache and Run Workflow'}</span>
        </div>
      ` : ''}
      <div class="context-menu-item" id="ctx-view-data">
        <span>👁️ View Results Data</span>
      </div>
    `;

    this.contextMenu.style.left = `${Math.min(window.innerWidth - 220, x)}px`;
    this.contextMenu.style.top = `${Math.min(window.innerHeight - 320, y)}px`;
    this.contextMenu.style.display = 'flex';

    this.contextMenu.querySelector('#ctx-add-to-container')?.addEventListener('click', () => {
      if (this.selectedNodeIds.size > 0) {
        this.addContainerFromSelection(Array.from(this.selectedNodeIds));
      }
    });
    this.contextMenu.querySelector('#ctx-align-h')?.addEventListener('click', () => this.alignHorizontally());
    this.contextMenu.querySelector('#ctx-align-v')?.addEventListener('click', () => this.alignVertically());
    this.contextMenu.querySelector('#ctx-copy')?.addEventListener('click', () => this.copySelected());
    this.contextMenu.querySelector('#ctx-cut')?.addEventListener('click', () => this.cutSelected());
    this.contextMenu.querySelector('#ctx-duplicate')?.addEventListener('click', () => this.duplicateSelected());
    this.contextMenu.querySelector('#ctx-delete')?.addEventListener('click', () => this.deleteSelected());
    this.contextMenu.querySelector('#ctx-cache-toggle')?.addEventListener('click', () => {
      if (singleNodeId) {
        if (isCached) {
          this.clearNodeCache(singleNodeId);
        } else {
          this.cacheAndRunNode(singleNodeId);
        }
      }
    });
    this.contextMenu.querySelector('#ctx-view-data')?.addEventListener('click', () => {
      if (this.selectedNodeId && window.appResultsPanel) {
        const selNode = this.nodes.find(n => n.id === this.selectedNodeId);
        window.appResultsPanel.showNodeResults(selNode);
      }
    });
  }

  showContainerContextMenu(containerId, clientX, clientY) {
    if (!this.contextMenu) return;
    const c = this.containers.find(item => item.id === containerId);
    if (!c) return;

    const count = (c.nodeIds || []).length;

    this.contextMenu.innerHTML = `
      <div class="context-menu-item" id="ctx-cnt-collapse">
        <span>${c.collapsed ? '▶ Expand Container' : '▼ Collapse Container'}</span>
      </div>
      <div class="context-menu-item" id="ctx-cnt-toggle">
        <span>${c.disabled ? '🟢 Enable Container' : '🔴 Disable Container (Bypass)'}</span>
      </div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" id="ctx-cnt-autofit" ${count === 0 ? 'style="opacity:0.5; pointer-events:none;"' : ''}>
        <span>📐 Auto-Fit Boundary to Tools</span>
      </div>
      <div class="context-menu-item" id="ctx-cnt-select-tools" ${count === 0 ? 'style="opacity:0.5; pointer-events:none;"' : ''}>
        <span>🔍 Select All Enclosed Tools (${count})</span>
      </div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" id="ctx-cnt-ungroup">
        <span>📦 Un-group (Remove Container, Keep Tools)</span>
      </div>
      <div class="context-menu-item" id="ctx-cnt-delete-all" style="color:var(--color-error);">
        <span>🗑️ Delete Container & Tools (${count})</span>
      </div>
    `;

    this.contextMenu.style.left = `${Math.min(window.innerWidth - 240, clientX)}px`;
    this.contextMenu.style.top = `${Math.min(window.innerHeight - 280, clientY)}px`;
    this.contextMenu.style.display = 'flex';

    this.contextMenu.querySelector('#ctx-cnt-collapse')?.addEventListener('click', () => {
      this.toggleContainerCollapse(c.id);
    });
    this.contextMenu.querySelector('#ctx-cnt-toggle')?.addEventListener('click', () => {
      this.toggleContainerDisabled(c.id);
    });
    this.contextMenu.querySelector('#ctx-cnt-autofit')?.addEventListener('click', () => {
      this.autoFitContainer(c.id, c.margin || 24);
    });
    this.contextMenu.querySelector('#ctx-cnt-select-tools')?.addEventListener('click', () => {
      this.selectEnclosedTools(c.id);
    });
    this.contextMenu.querySelector('#ctx-cnt-ungroup')?.addEventListener('click', () => {
      this.removeContainer(c.id, false);
      if (window.appHistory) window.appHistory.pushSnapshot('Un-group Container');
      if (window.showToast) window.showToast('info', 'Container Removed', 'Tools preserved on canvas.');
    });
    this.contextMenu.querySelector('#ctx-cnt-delete-all')?.addEventListener('click', () => {
      if (count === 0 || confirm(`Delete container '${c.title || 'Tool Container'}' and all ${count} enclosed tool(s)?`)) {
        this.removeContainer(c.id, true);
        if (window.appHistory) window.appHistory.pushSnapshot('Delete Container and Tools');
        if (window.showToast) window.showToast('info', 'Container Deleted', `Deleted container and ${count} tool(s).`);
      }
    });
  }

  showCanvasContextMenu(clientX, clientY, canvasX, canvasY) {
    if (!this.contextMenu) return;
    this.contextMenu.innerHTML = `
      <div class="context-menu-item" id="ctx-add-tool">
        <span>➕ Add Tool...</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Tab</kbd>
      </div>
      <div class="context-menu-item" id="ctx-add-container">
        <span>📦 Add Tool Container</span>
      </div>
      <div class="context-menu-item" id="ctx-add-comment">
        <span>📝 Add Comment Note</span>
      </div>
      ${this.clipboard ? `
        <div class="context-menu-divider"></div>
        <div class="context-menu-item" id="ctx-paste">
          <span>📋 Paste</span>
          <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+V</kbd>
        </div>
      ` : ''}
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" id="ctx-align-flow">
        <span>⚡ Auto-Layout Flow</span>
      </div>
      <div class="context-menu-item" id="ctx-select-all">
        <span>Select All</span>
        <kbd style="font-size:10px; margin-left:auto; color:var(--text-muted);">Ctrl+A</kbd>
      </div>
      <div class="context-menu-divider"></div>
      <div class="context-menu-item" id="ctx-clear-canvas" style="color:var(--color-error);">
        <span>Clear Canvas</span>
      </div>
    `;

    this.contextMenu.style.left = `${Math.min(window.innerWidth - 210, clientX)}px`;
    this.contextMenu.style.top = `${Math.min(window.innerHeight - 280, clientY)}px`;
    this.contextMenu.style.display = 'flex';

    this.contextMenu.querySelector('#ctx-add-tool')?.addEventListener('click', () => this.openSpotlight(canvasX, canvasY));
    this.contextMenu.querySelector('#ctx-add-container')?.addEventListener('click', () => this.addContainer(canvasX, canvasY));
    this.contextMenu.querySelector('#ctx-add-comment')?.addEventListener('click', () => this.addComment(canvasX, canvasY));
    this.contextMenu.querySelector('#ctx-paste')?.addEventListener('click', () => this.pasteClipboard());
    this.contextMenu.querySelector('#ctx-align-flow')?.addEventListener('click', () => this.autoLayout());
    this.contextMenu.querySelector('#ctx-select-all')?.addEventListener('click', () => this.selectAll());
    this.contextMenu.querySelector('#ctx-clear-canvas')?.addEventListener('click', () => this.clearCanvas());
  }

  alignHorizontally() {
    if (this.selectedNodeIds.size < 2) return;
    const selected = this.nodes.filter(n => this.selectedNodeIds.has(n.id));
    const avgY = Math.round(selected.reduce((acc, n) => acc + n.y, 0) / selected.length);
    selected.forEach(n => {
      n.y = avgY;
      this.updateNodeElementPosition(n);
    });
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Align Horizontally');
    if (window.showToast) window.showToast('info', 'Aligned', `Aligned ${selected.length} tools horizontally.`);
  }

  alignVertically() {
    if (this.selectedNodeIds.size < 2) return;
    const selected = this.nodes.filter(n => this.selectedNodeIds.has(n.id));
    const avgX = Math.round(selected.reduce((acc, n) => acc + n.x, 0) / selected.length);
    selected.forEach(n => {
      n.x = avgX;
      this.updateNodeElementPosition(n);
    });
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Align Vertically');
    if (window.showToast) window.showToast('info', 'Aligned', `Aligned ${selected.length} tools vertically.`);
  }

  selectAll() {
    this.selectedNodeIds = new Set(this.nodes.map(n => n.id));
    this.selectedContainerIds = new Set(this.containers.map(c => c.id));
    this.selectedCommentIds = new Set(this.comments.map(comm => comm.id));
    this.updateSelectionVisuals();
  }

  selectAllNodes() {
    this.selectAll();
  }

  copySelected() {
    const selectedNodes = this.nodes.filter(n => this.selectedNodeIds.has(n.id));
    const selectedContainers = this.containers.filter(c => this.selectedContainerIds.has(c.id));
    const selectedComments = this.comments.filter(comm => this.selectedCommentIds.has(comm.id));

    // Internal connections where both source and target are selected
    const internalConnections = this.connections.filter(c => 
      this.selectedNodeIds.has(c.source) && this.selectedNodeIds.has(c.target)
    );

    if (selectedNodes.length === 0 && selectedContainers.length === 0 && selectedComments.length === 0) {
      return;
    }

    this.clipboard = {
      nodes: JSON.parse(JSON.stringify(selectedNodes)),
      connections: JSON.parse(JSON.stringify(internalConnections)),
      containers: JSON.parse(JSON.stringify(selectedContainers)),
      comments: JSON.parse(JSON.stringify(selectedComments))
    };

    const count = selectedNodes.length + selectedContainers.length + selectedComments.length;
    if (window.showToast) {
      window.showToast('info', 'Copied', `Copied ${count} item${count > 1 ? 's' : ''} to clipboard`);
    }
  }

  cutSelected() {
    this.copySelected();
    this.deleteSelected();
    if (window.showToast) {
      window.showToast('info', 'Cut', 'Cut selected items to clipboard');
    }
  }

  pasteClipboard() {
    if (!this.clipboard) return;
    const { nodes, connections, containers, comments } = this.clipboard;
    if ((!nodes || nodes.length === 0) && (!containers || containers.length === 0) && (!comments || comments.length === 0)) return;

    this.clearSelection();

    const idMap = {};
    const OFFSET = 40;

    // Paste containers
    const newContainers = [];
    (containers || []).forEach(c => {
      const newId = `container_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
      idMap[c.id] = newId;
      const copy = {
        ...JSON.parse(JSON.stringify(c)),
        id: newId,
        x: c.x + OFFSET,
        y: c.y + OFFSET,
        nodeIds: []
      };
      this.containers.push(copy);
      this.renderContainerElement(copy);
      this.selectedContainerIds.add(newId);
      newContainers.push(copy);
    });

    // Paste comments
    (comments || []).forEach(comm => {
      const newId = `comment_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
      const copy = {
        ...JSON.parse(JSON.stringify(comm)),
        id: newId,
        x: comm.x + OFFSET,
        y: comm.y + OFFSET
      };
      this.comments.push(copy);
      this.renderCommentElement(copy);
      this.selectedCommentIds.add(newId);
    });

    // Paste nodes
    const newNodes = [];
    (nodes || []).forEach(n => {
      const newId = `node_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
      idMap[n.id] = newId;
      const copy = {
        ...JSON.parse(JSON.stringify(n)),
        id: newId,
        name: `${n.name}`,
        x: n.x + OFFSET,
        y: n.y + OFFSET,
        container_id: n.container_id && idMap[n.container_id] ? idMap[n.container_id] : null
      };
      this.nodes.push(copy);
      this.renderNodeElement(copy);
      this.selectedNodeIds.add(newId);
      newNodes.push(copy);
    });

    // Paste internal connections remapped to new node IDs
    (connections || []).forEach(conn => {
      const newSource = idMap[conn.source];
      const newTarget = idMap[conn.target];
      if (newSource && newTarget) {
        const newConnId = `conn_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
        this.connections.push({
          id: newConnId,
          source: newSource,
          sourceHandle: conn.sourceHandle || 'O',
          target: newTarget,
          targetHandle: conn.targetHandle || 'I'
        });
      }
    });

    // Update container containment for newly added containers & nodes
    this.containers.forEach(c => this.updateContainerEnclosedNodes(c));

    this.renderWires();
    this.updateSelectionVisuals();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Paste');
    if (window.showToast) {
      const total = newNodes.length + newContainers.length + (comments || []).length;
      window.showToast('info', 'Pasted', `Pasted ${total} item${total > 1 ? 's' : ''}`);
    }
  }

  duplicateSelected() {
    this.copySelected();
    this.pasteClipboard();
  }

  duplicateSelectedNodes() {
    this.duplicateSelected();
  }

  deleteSelected() {
    if (this.selectedConnectionId) {
      this.removeConnection(this.selectedConnectionId);
      return;
    }

    const nodeIds = Array.from(this.selectedNodeIds);
    const containerIds = Array.from(this.selectedContainerIds);
    const commentIds = Array.from(this.selectedCommentIds);

    if (nodeIds.length === 0 && containerIds.length === 0 && commentIds.length === 0) {
      return;
    }

    // Delete selected nodes
    nodeIds.forEach(id => {
      this.removeNode(id);
    });

    // Delete selected containers
    containerIds.forEach(id => {
      this.removeContainer(id);
    });

    // Delete selected comments
    commentIds.forEach(id => {
      this.removeComment(id);
    });

    this.clearSelection();
    if (window.appHistory) window.appHistory.pushSnapshot('Delete Selected');
    if (window.showToast) {
      const total = nodeIds.length + containerIds.length + commentIds.length;
      window.showToast('info', 'Deleted', `Deleted ${total} item${total > 1 ? 's' : ''}`);
    }
  }

  removeSelectedNodes() {
    this.deleteSelected();
  }

  // --------------------------------------------------------------------
  // Tool Containers
  // --------------------------------------------------------------------
  hexToRgba(hex, opacityPercent = 12) {
    if (!hex) hex = '#0284c7';
    let c = hex.replace('#', '');
    if (c.length === 3) c = c.split('').map(x => x + x).join('');
    const num = parseInt(c, 16);
    if (isNaN(num)) return `rgba(2, 132, 199, ${opacityPercent / 100})`;
    const r = (num >> 16) & 255;
    const g = (num >> 8) & 255;
    const b = num & 255;
    const alpha = Math.max(0, Math.min(1, (opacityPercent || 12) / 100));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  addContainer(x, y, title = 'Tool Container', width = 320, height = 220, color = '#0284c7') {
    const id = `container_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const newContainer = {
      id: id,
      title: title,
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(160, Math.round(width)),
      height: Math.max(70, Math.round(height)),
      color: color,
      textColor: '#ffffff',
      borderStyle: 'solid',
      borderWidth: 2,
      fillOpacity: 12,
      margin: 24,
      collapsed: false,
      disabled: false,
      nodeIds: []
    };
    this.containers.push(newContainer);
    this.renderContainerElement(newContainer);
    this.updateContainerEnclosedNodes(newContainer);
    this.renderWires();
    this.selectContainer(id);
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Add Container');
    return newContainer;
  }

  addContainerFromSelection(nodeIds, margin = 24) {
    if (!nodeIds || nodeIds.length === 0) return null;
    const selectedNodes = this.nodes.filter(n => nodeIds.includes(n.id));
    if (selectedNodes.length === 0) return null;

    const minX = Math.min(...selectedNodes.map(n => n.x));
    const minY = Math.min(...selectedNodes.map(n => n.y));
    const maxX = Math.max(...selectedNodes.map(n => n.x + 56));
    const maxY = Math.max(...selectedNodes.map(n => n.y + 56));

    const cx = Math.max(0, minX - margin);
    const cy = Math.max(0, minY - margin - 34);
    const cw = Math.max(180, (maxX - minX) + margin * 2);
    const ch = Math.max(80, (maxY - minY) + margin * 2 + 34);

    const newContainer = this.addContainer(cx, cy, 'Tool Container', cw, ch);
    newContainer.margin = margin;
    this.updateContainerEnclosedNodes(newContainer);
    this.renderWires();
    this.selectContainer(newContainer.id);
    if (window.showToast) {
      window.showToast('success', 'Container Created', `Created container enclosing ${selectedNodes.length} tool(s).`);
    }
    return newContainer;
  }

  autoFitContainer(containerId, margin = 24) {
    const c = this.containers.find(item => item.id === containerId);
    if (!c) return;
    if (!c.nodeIds || c.nodeIds.length === 0) {
      if (window.showToast) window.showToast('warning', 'Empty Container', 'There are no enclosed tools to fit bounds to.');
      return;
    }

    const enclosedNodes = this.nodes.filter(n => c.nodeIds.includes(n.id));
    if (enclosedNodes.length === 0) return;

    const minX = Math.min(...enclosedNodes.map(n => n.x));
    const minY = Math.min(...enclosedNodes.map(n => n.y));
    const maxX = Math.max(...enclosedNodes.map(n => n.x + 56));
    const maxY = Math.max(...enclosedNodes.map(n => n.y + 56));

    c.x = Math.max(0, minX - margin);
    c.y = Math.max(0, minY - margin - 34);
    c.width = Math.max(160, (maxX - minX) + margin * 2);
    c.height = Math.max(70, (maxY - minY) + margin * 2 + 34);
    c.margin = margin;

    this.renderContainerElement(c);
    this.updateContainerEnclosedNodes(c);
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Auto-Fit Container Boundary');
    if (window.showToast) window.showToast('info', 'Container Adjusted', `Auto-fitted bounds around ${enclosedNodes.length} tools.`);
  }

  selectEnclosedTools(containerId) {
    const c = this.containers.find(item => item.id === containerId);
    if (!c || !c.nodeIds || c.nodeIds.length === 0) return;
    this.clearSelection();
    c.nodeIds.forEach(nid => this.selectedNodeIds.add(nid));
    this.updateSelectionVisuals();
    if (this.selectedNodeIds.size === 1) {
      this.selectedNodeId = Array.from(this.selectedNodeIds)[0];
      const node = this.nodes.find(n => n.id === this.selectedNodeId);
      this.onSelectNode(node);
    } else if (this.selectedNodeIds.size > 1) {
      if (this.onSelectNode) {
        this.onSelectNode({
          id: 'multi_selection',
          type: 'multi_selection',
          name: `Selected Tools (${this.selectedNodeIds.size})`,
          config: {}
        });
      }
    }
  }

  removeContainer(containerId, deleteEnclosedNodes = false) {
    const c = this.containers.find(item => item.id === containerId);
    const enclosedIds = c ? [...(c.nodeIds || [])] : [];

    this.containers = this.containers.filter(item => item.id !== containerId);
    const el = document.getElementById(`container-elem-${containerId}`);
    if (el) el.remove();
    this.selectedContainerIds.delete(containerId);
    if (this.selectedContainerId === containerId) {
      this.selectedContainerId = null;
    }

    if (deleteEnclosedNodes && enclosedIds.length > 0) {
      enclosedIds.forEach(nid => {
        this.removeNode(nid);
      });
    } else {
      // Unlink nodes
      this.nodes.forEach(n => {
        if (n.container_id === containerId) {
          n.container_id = null;
          const nodeCard = document.getElementById(`node-elem-${n.id}`);
          if (nodeCard) {
            nodeCard.classList.remove('container-disabled');
            nodeCard.style.display = '';
          }
        }
      });
    }

    this.renderWires();
    this.onWorkflowChange();
  }

  showDeleteContainerDialog(c) {
    const existing = document.getElementById('container-delete-modal');
    if (existing) existing.remove();

    const count = (c.nodeIds || []).length;
    const modal = document.createElement('div');
    modal.id = 'container-delete-modal';
    modal.className = 'canvas-floating-modal';
    modal.innerHTML = `
      <div class="floating-modal-header">
        <strong>Delete Tool Container</strong>
        <button class="floating-modal-close">&times;</button>
      </div>
      <div class="floating-modal-body">
        <p style="margin:0 0 8px 0; font-size:13px; color:var(--text-primary);">
          Container <strong>'${this.escapeHtml(c.title || 'Tool Container')}'</strong> encloses <strong>${count}</strong> tool${count > 1 ? 's' : ''}.
        </p>
        <p style="margin:0; font-size:12px; color:var(--text-secondary);">
          Choose whether to un-group and keep the tools on the canvas or delete both:
        </p>
      </div>
      <div class="floating-modal-footer" style="display:flex; gap:8px; justify-content:flex-end; padding-top:10px;">
        <button class="btn btn-secondary btn-sm" id="btn-del-ungroup">📦 Un-group (Keep Tools)</button>
        <button class="btn btn-danger btn-sm" id="btn-del-all">🗑️ Delete All</button>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => {
      modal.remove();
      window.removeEventListener('click', outsideClick);
    };

    const outsideClick = (e) => {
      if (!modal.contains(e.target)) closeModal();
    };
    setTimeout(() => window.addEventListener('click', outsideClick), 50);

    modal.querySelector('.floating-modal-close').onclick = closeModal;

    modal.querySelector('#btn-del-ungroup').onclick = () => {
      closeModal();
      this.removeContainer(c.id, false);
      if (window.appHistory) window.appHistory.pushSnapshot('Un-group Container');
      if (window.showToast) window.showToast('info', 'Container Removed', 'Enclosed tools preserved.');
    };

    modal.querySelector('#btn-del-all').onclick = () => {
      closeModal();
      this.removeContainer(c.id, true);
      if (window.appHistory) window.appHistory.pushSnapshot('Delete Container and Tools');
      if (window.showToast) window.showToast('info', 'Container Deleted', `Deleted container and ${count} tool(s).`);
    };
  }

  renderContainerElement(c) {
    let el = document.getElementById(`container-elem-${c.id}`);
    if (!el) {
      el = document.createElement('div');
      el.id = `container-elem-${c.id}`;
      this.containersLayer.appendChild(el);
    }

    el.className = `tool-container ${this.selectedContainerIds.has(c.id) ? 'selected' : ''} ${c.disabled ? 'disabled' : ''} ${c.collapsed ? 'collapsed' : ''}`;
    el.style.left = `${c.x}px`;
    el.style.top = `${c.y}px`;
    el.style.width = `${c.width}px`;
    if (!c.collapsed) {
      el.style.height = `${c.height}px`;
    } else {
      el.style.height = '';
    }

    const themeColor = c.color || '#0284c7';
    const textColor = c.textColor || '#ffffff';
    const fillOpacity = c.fillOpacity !== undefined ? c.fillOpacity : (c.transparency !== undefined ? c.transparency : 12);
    const borderStyle = c.borderStyle || (c.disabled ? 'dashed' : 'solid');
    const borderWidth = c.borderWidth || 2;

    el.style.setProperty('--container-color', themeColor);
    el.style.borderColor = themeColor;
    el.style.borderStyle = borderStyle;
    el.style.borderWidth = `${borderWidth}px`;
    el.style.backgroundColor = this.hexToRgba(themeColor, fillOpacity);

    const count = (c.nodeIds || []).length;

    el.innerHTML = `
      <div class="container-header" style="background-color: ${themeColor}; color: ${textColor};">
        <button class="container-btn-collapse" style="color: ${textColor};" title="${c.collapsed ? 'Expand Container' : 'Collapse Container'}">
          ${c.collapsed ? '▶' : '▼'}
        </button>
        <span class="container-title" style="color: ${textColor};" title="Double-click to rename">${this.escapeHtml(c.title || 'Tool Container')}</span>
        <div class="container-actions">
          <button class="container-btn-toggle ${c.disabled ? 'is-disabled' : 'is-active'}" title="${c.disabled ? 'Enable Container' : 'Disable Container'}">
            <span class="toggle-dot"></span>
            <span>${c.disabled ? 'Disabled' : 'Enabled'}</span>
          </button>
          <button class="container-btn-delete" style="color: ${textColor}; opacity: 0.85;" title="Delete Container">&times;</button>
        </div>
      </div>
      <div class="container-body">
        <div class="container-status-badge">
          ${count === 1 ? '1 tool inside' : `${count} tools inside`}
        </div>
      </div>
      <div class="container-resize-handle" style="background: linear-gradient(135deg, transparent 50%, ${themeColor} 50%);"></div>
    `;

    // Container selection & dragging (from header, body, or borders)
    el.addEventListener('mousedown', (e) => {
      if (e.target.closest('.container-btn-collapse') || 
          e.target.closest('.container-btn-toggle') || 
          e.target.closest('.container-btn-delete') || 
          e.target.closest('.container-resize-handle') || 
          e.target.closest('.container-title-input')) {
        return;
      }
      e.stopPropagation();
      const isMulti = e.ctrlKey || e.metaKey || e.shiftKey;
      this.selectContainer(c.id, isMulti);

      // Refresh enclosed node membership before dragging begins
      this.updateContainerEnclosedNodes(c);

      const mouse = this.getCanvasCoords(e.clientX, e.clientY);
      this.draggingContainer = c;
      this.dragMoved = false;
      this.containerDragStart = { x: c.x, y: c.y };
      this.dragOffset = {
        x: mouse.x - c.x,
        y: mouse.y - c.y
      };

      this.containerDragOffsets.clear();
      const enclosedIds = new Set(c.nodeIds || []);
      this.nodes.forEach(n => {
        if (n.container_id === c.id) {
          enclosedIds.add(n.id);
        }
      });

      enclosedIds.forEach(nid => {
        const n = this.nodes.find(node => node.id === nid);
        if (n) {
          this.containerDragOffsets.set(nid, { x: n.x, y: n.y });
        }
      });
    });

    // Collapse toggle button
    const collapseBtn = el.querySelector('.container-btn-collapse');
    collapseBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleContainerCollapse(c.id);
    });

    // Disable / Enable toggle button
    const toggleBtn = el.querySelector('.container-btn-toggle');
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggleContainerDisabled(c.id);
    });

    // Delete button
    const deleteBtn = el.querySelector('.container-btn-delete');
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const enclosedCount = (c.nodeIds || []).length;
      if (enclosedCount === 0) {
        this.removeContainer(c.id, false);
        if (window.appHistory) window.appHistory.pushSnapshot('Delete Container');
        return;
      }
      this.showDeleteContainerDialog(c);
    });

    // Resize handle
    const resizeHandle = el.querySelector('.container-resize-handle');
    resizeHandle.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      const mouse = this.getCanvasCoords(e.clientX, e.clientY);
      this.resizingContainer = c;
      this.resizeStart = {
        mouseX: mouse.x,
        mouseY: mouse.y,
        initW: c.width,
        initH: c.height
      };
    });

    // Inline title edit on double-click
    const titleSpan = el.querySelector('.container-title');
    titleSpan.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'container-title-input';
      input.value = c.title || '';
      titleSpan.replaceWith(input);
      input.focus();
      input.select();

      const finishRename = () => {
        c.title = input.value.trim() || 'Tool Container';
        this.renderContainerElement(c);
        this.onWorkflowChange();
        if (window.appHistory) window.appHistory.pushSnapshot('Rename Container');
      };

      input.addEventListener('blur', finishRename);
      input.addEventListener('keydown', (ke) => {
        if (ke.key === 'Enter') {
          input.blur();
        } else if (ke.key === 'Escape') {
          input.value = c.title || '';
          input.blur();
        }
      });
    });
  }

  updateContainerEnclosedNodes(c) {
    if (!c) return;
    const enclosedIds = [];
    this.nodes.forEach(n => {
      const centerX = n.x + 28;
      const centerY = n.y + 28;
      // When collapsed, preserve existing membership of enclosed nodes
      if (c.collapsed && n.container_id === c.id) {
        enclosedIds.push(n.id);
        return;
      }
      const isInside = (centerX >= c.x && centerX <= c.x + c.width &&
                        centerY >= c.y && centerY <= c.y + c.height);
      if (isInside) {
        enclosedIds.push(n.id);
        n.container_id = c.id;
      } else if (n.container_id === c.id) {
        n.container_id = null;
      }
    });
    c.nodeIds = enclosedIds;

    this.applyContainerVisibility(c);

    const cEl = document.getElementById(`container-elem-${c.id}`);
    if (cEl) {
      const badge = cEl.querySelector('.container-status-badge');
      if (badge) {
        const count = enclosedIds.length;
        badge.textContent = count === 1 ? '1 tool inside' : `${count} tools inside`;
      }
    }
  }

  applyContainerVisibility(c) {
    if (!c) return;
    (c.nodeIds || []).forEach(nid => {
      const nodeEl = document.getElementById(`node-elem-${nid}`);
      if (nodeEl) {
        nodeEl.classList.toggle('container-disabled', Boolean(c.disabled));
        if (c.collapsed) {
          nodeEl.style.display = 'none';
        } else {
          nodeEl.style.display = '';
        }
      }
    });

    this.renderWires();
  }

  toggleContainerCollapse(containerId) {
    const c = this.containers.find(item => item.id === containerId);
    if (!c) return;
    c.collapsed = !c.collapsed;
    this.renderContainerElement(c);
    this.applyContainerVisibility(c);
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot(c.collapsed ? 'Collapse Container' : 'Expand Container');
  }

  toggleContainerDisabled(containerId) {
    const c = this.containers.find(item => item.id === containerId);
    if (!c) return;
    c.disabled = !c.disabled;
    this.renderContainerElement(c);
    this.applyContainerVisibility(c);
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot(c.disabled ? 'Disable Container' : 'Enable Container');
    if (window.showToast) {
      window.showToast('info', c.disabled ? 'Container Disabled' : 'Container Enabled', 
        c.disabled ? 'Enclosed tools will be bypassed during execution.' : 'Enclosed tools are active.');
    }
  }

  selectContainer(cId, multi = false) {
    if (!multi) {
      this.clearSelection();
      this.selectedContainerIds.add(cId);
    } else {
      if (this.selectedContainerIds.has(cId)) {
        this.selectedContainerIds.delete(cId);
      } else {
        this.selectedContainerIds.add(cId);
      }
    }
    this.updateSelectionVisuals();
    if (this.selectedContainerIds.size === 1 && !multi) {
      const c = this.containers.find(item => item.id === cId);
      if (c && this.onSelectNode) {
        this.onSelectNode({
          id: c.id,
          type: 'tool_container',
          name: c.title || 'Tool Container',
          config: c
        });
      }
    }
  }

  // --------------------------------------------------------------------
  // Comment Notes
  // --------------------------------------------------------------------
  addComment(x, y, text = '## Note\nEnter documentation or comments here...', width = 220, height = 140, color = '#fef08a') {
    const id = `comment_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const newComment = {
      id: id,
      text: text,
      color: color,
      textColor: '#1e293b',
      fontSize: 13,
      x: Math.round(x),
      y: Math.round(y),
      width: Math.max(140, Math.round(width)),
      height: Math.max(60, Math.round(height))
    };
    this.comments.push(newComment);
    this.renderCommentElement(newComment);
    this.selectComment(id);
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Add Note');
    return newComment;
  }

  removeComment(commentId) {
    this.comments = this.comments.filter(comm => comm.id !== commentId);
    const el = document.getElementById(`comment-elem-${commentId}`);
    if (el) el.remove();
    this.selectedCommentIds.delete(commentId);
    this.onWorkflowChange();
  }

  renderCommentElement(comm) {
    let el = document.getElementById(`comment-elem-${comm.id}`);
    if (!el) {
      el = document.createElement('div');
      el.id = `comment-elem-${comm.id}`;
      this.commentsLayer.appendChild(el);
    }

    el.className = `comment-note ${this.selectedCommentIds.has(comm.id) ? 'selected' : ''}`;
    el.style.left = `${comm.x}px`;
    el.style.top = `${comm.y}px`;
    el.style.width = `${comm.width}px`;
    el.style.height = `${comm.height}px`;
    el.style.backgroundColor = comm.color || '#fef08a';
    el.style.color = comm.textColor || '#1e293b';
    el.style.fontSize = `${comm.fontSize || 13}px`;

    el.innerHTML = `
      <div class="comment-header">
        <span class="comment-grip">&#8942;&#8942;</span>
        <span class="comment-header-title">Note</span>
        <button class="comment-btn-edit" title="Edit text">✎</button>
        <button class="comment-btn-delete" title="Delete note">&times;</button>
      </div>
      <div class="comment-content">${this.renderMarkdown(comm.text)}</div>
      <textarea class="comment-editor" style="display: none;">${this.escapeHtml(comm.text || '')}</textarea>
      <div class="comment-resize-handle"></div>
    `;

    el.addEventListener('mousedown', (e) => {
      if (e.target.closest('.comment-btn-edit') || 
          e.target.closest('.comment-btn-delete') || 
          e.target.closest('.comment-resize-handle') || 
          e.target.closest('.comment-editor')) {
        return;
      }
      e.stopPropagation();
      const isMulti = e.ctrlKey || e.metaKey || e.shiftKey;
      this.selectComment(comm.id, isMulti);

      if (e.target.closest('.comment-header')) {
        const mouse = this.getCanvasCoords(e.clientX, e.clientY);
        this.draggingComment = comm;
        this.dragMoved = false;
        this.dragOffset = {
          x: mouse.x - comm.x,
          y: mouse.y - comm.y
        };
      }
    });

    const contentDiv = el.querySelector('.comment-content');
    const editor = el.querySelector('.comment-editor');
    const editBtn = el.querySelector('.comment-btn-edit');
    const deleteBtn = el.querySelector('.comment-btn-delete');
    const resizeHandle = el.querySelector('.comment-resize-handle');

    const startEditing = () => {
      contentDiv.style.display = 'none';
      editor.style.display = 'block';
      editor.value = comm.text || '';
      editor.focus();
    };

    const stopEditing = () => {
      editor.style.display = 'none';
      contentDiv.style.display = 'block';
      comm.text = editor.value;
      contentDiv.innerHTML = this.renderMarkdown(comm.text);
      this.onWorkflowChange();
      if (window.appHistory) window.appHistory.pushSnapshot('Edit Note');
    };

    contentDiv.addEventListener('dblclick', (e) => {
      e.stopPropagation();
      startEditing();
    });

    editBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      if (editor.style.display === 'none') {
        startEditing();
      } else {
        stopEditing();
      }
    });

    editor.addEventListener('blur', stopEditing);
    editor.addEventListener('keydown', (ke) => {
      if (ke.key === 'Escape') {
        editor.value = comm.text || '';
        stopEditing();
      }
    });

    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.removeComment(comm.id);
      if (window.appHistory) window.appHistory.pushSnapshot('Delete Note');
    });

    resizeHandle.addEventListener('mousedown', (e) => {
      e.stopPropagation();
      const mouse = this.getCanvasCoords(e.clientX, e.clientY);
      this.resizingComment = comm;
      this.resizeStart = {
        mouseX: mouse.x,
        mouseY: mouse.y,
        initW: comm.width,
        initH: comm.height
      };
    });
  }

  selectComment(commId, multi = false) {
    if (!multi) {
      this.clearSelection();
      this.selectedCommentIds.add(commId);
    } else {
      if (this.selectedCommentIds.has(commId)) {
        this.selectedCommentIds.delete(commId);
      } else {
        this.selectedCommentIds.add(commId);
      }
    }
    this.updateSelectionVisuals();
    if (this.selectedCommentIds.size === 1 && !multi) {
      const comm = this.comments.find(item => item.id === commId);
      if (comm && this.onSelectNode) {
        this.onSelectNode({
          id: comm.id,
          type: 'comment',
          name: 'Comment Note',
          config: comm
        });
      }
    }
  }

  renderMarkdown(text) {
    if (!text || !text.trim()) return '<em>Empty note. Double-click or click ✎ to edit...</em>';
    let html = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    html = html.replace(/^### (.*$)/gim, '<h4 style="margin:4px 0; font-size:1.1em; font-weight:700;">$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3 style="margin:6px 0; font-size:1.2em; font-weight:700;">$1</h3>');
    html = html.replace(/^# (.*$)/gim, '<h2 style="margin:8px 0; font-size:1.35em; font-weight:700;">$1</h2>');
    html = html.replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/gim, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/gim, '<code style="background:rgba(0,0,0,0.12); padding:1px 4px; border-radius:3px; font-size:0.9em;">$1</code>');
    html = html.replace(/^\s*-\s+(.*$)/gim, '<div style="margin-left:12px;">&bull; $1</div>');
    html = html.replace(/\n/gim, '<br>');
    return html;
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  zoomAtPoint(factor, clientX, clientY) {
    const rect = this.container.getBoundingClientRect();
    const mouseX = clientX - rect.left;
    const mouseY = clientY - rect.top;

    const newZoom = Math.min(2.5, Math.max(0.25, this.zoom * factor));
    if (newZoom === this.zoom) return;

    // Pan towards mouse
    this.panX = mouseX - (mouseX - this.panX) * (newZoom / this.zoom);
    this.panY = mouseY - (mouseY - this.panY) * (newZoom / this.zoom);
    this.zoom = newZoom;

    this.updateTransform();
  }

  zoomIn() {
    const rect = this.container.getBoundingClientRect();
    this.zoomAtPoint(1.2, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  zoomOut() {
    const rect = this.container.getBoundingClientRect();
    this.zoomAtPoint(0.8, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  resetZoom() {
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.updateTransform();
  }

  resetView() {
    this.resetZoom();
  }

  applyZoom(zoomLevel) {
    if (this.zoom <= 0) return;
    const factor = zoomLevel / this.zoom;
    const rect = this.container.getBoundingClientRect();
    this.zoomAtPoint(factor, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }

  updateTransform() {
    this.wrapper.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
    if (this.zoomText) {
      this.zoomText.textContent = `${Math.round(this.zoom * 100)}%`;
    }
    if (typeof this.onTransformChange === 'function') {
      this.onTransformChange();
    }
  }

  panTo(worldX, worldY) {
    const rect = this.container.getBoundingClientRect();
    this.panX = rect.width / 2 - worldX * this.zoom;
    this.panY = rect.height / 2 - worldY * this.zoom;
    this.updateTransform();
  }

  getVisibleWorldBounds() {
    const rect = this.container.getBoundingClientRect();
    const minX = -this.panX / this.zoom;
    const minY = -this.panY / this.zoom;
    const maxX = (rect.width - this.panX) / this.zoom;
    const maxY = (rect.height - this.panY) / this.zoom;
    return {
      minX,
      minY,
      maxX,
      maxY,
      width: Math.max(1, maxX - minX),
      height: Math.max(1, maxY - minY)
    };
  }

  getViewportCenter() {
    const rect = this.container.getBoundingClientRect();
    const cx = (rect.width / 2 - this.panX) / this.zoom;
    const cy = (rect.height / 2 - this.panY) / this.zoom;
    return { x: Math.round(cx - 28), y: Math.round(cy - 28) };
  }

  // --------------------------------------------------------------------
  // Graph Management
  // --------------------------------------------------------------------
  loadWorkflow(workflow) {
    if (!workflow) workflow = { nodes: [], connections: [], containers: [], comments: [] };

    // 1. Normalize containers
    this.containers = (workflow.containers || []).map(c => ({
      id: String(c.id),
      title: c.title || 'Tool Container',
      color: c.color || '#0284c7',
      textColor: c.textColor || '#ffffff',
      borderStyle: c.borderStyle || 'solid',
      borderWidth: typeof c.borderWidth === 'number' ? c.borderWidth : 2,
      fillOpacity: typeof c.fillOpacity === 'number' ? c.fillOpacity : (typeof c.transparency === 'number' ? c.transparency : 12),
      margin: typeof c.margin === 'number' ? c.margin : 24,
      x: typeof c.x === 'number' ? Math.round(c.x) : 100,
      y: typeof c.y === 'number' ? Math.round(c.y) : 100,
      width: typeof c.width === 'number' ? Math.max(160, Math.round(c.width)) : 320,
      height: typeof c.height === 'number' ? Math.max(70, Math.round(c.height)) : 220,
      collapsed: Boolean(c.collapsed),
      disabled: Boolean(c.disabled),
      nodeIds: Array.isArray(c.nodeIds || c.node_ids) ? (c.nodeIds || c.node_ids).map(String) : []
    }));

    // 2. Normalize comments
    this.comments = (workflow.comments || []).map(comm => ({
      id: String(comm.id),
      text: comm.text || '',
      color: comm.color || '#fef08a',
      textColor: comm.textColor || '#1e293b',
      fontSize: comm.fontSize || 13,
      x: typeof comm.x === 'number' ? Math.round(comm.x) : 100,
      y: typeof comm.y === 'number' ? Math.round(comm.y) : 100,
      width: typeof comm.width === 'number' ? Math.max(140, Math.round(comm.width)) : 220,
      height: typeof comm.height === 'number' ? Math.max(60, Math.round(comm.height)) : 140
    }));

    // 3. Normalize nodes
    this.nodes = (workflow.nodes || []).map(n => ({
      id: String(n.id),
      type: n.type,
      name: n.name || (this.toolRegistry[n.type] ? this.toolRegistry[n.type].name : n.type),
      x: typeof n.x === 'number' ? Math.round(n.x) : 100,
      y: typeof n.y === 'number' ? Math.round(n.y) : 100,
      config: n.config ? JSON.parse(JSON.stringify(n.config)) : {},
      container_id: n.container_id || null,
      is_cached: Boolean(n.is_cached)
    }));

    // Restore cached node IDs from workflow
    this.cachedNodeIds = new Set();
    this.nodes.forEach(n => {
      if (n.is_cached) this.cachedNodeIds.add(n.id);
    });
    (workflow.cached_node_ids || []).forEach(id => this.cachedNodeIds.add(String(id)));

    // 4. Normalize connections & prune dangling wires
    const validNodeIds = new Set(this.nodes.map(n => n.id));
    this.connections = (workflow.connections || [])
      .filter(c => {
        const src = String(c.source || c.from_node || '');
        const tgt = String(c.target || c.to_node || '');
        return src && tgt && validNodeIds.has(src) && validNodeIds.has(tgt);
      })
      .map((c, idx) => ({
        id: c.id || `conn_${c.source || c.from_node}_${c.target || c.to_node}_${idx}`,
        source: String(c.source || c.from_node),
        sourceHandle: c.sourceHandle || c.from_port || 'O',
        target: String(c.target || c.to_node),
        targetHandle: c.targetHandle || c.to_port || 'I'
      }));

    // Store metadata
    this.workflowMetadata = workflow.metadata || {
      description: workflow.description || '',
      author: workflow.author || '',
      version: workflow.version || '2.1.0'
    };

    // 5. Restore Viewport if persisted
    if (workflow.viewport && typeof workflow.viewport === 'object') {
      const z = parseFloat(workflow.viewport.zoom);
      if (!isNaN(z) && z >= 0.1 && z <= 4.0) {
        this.zoom = z;
      }
      if (typeof workflow.viewport.panX === 'number' && !isNaN(workflow.viewport.panX)) {
        this.panX = workflow.viewport.panX;
      }
      if (typeof workflow.viewport.panY === 'number' && !isNaN(workflow.viewport.panY)) {
        this.panY = workflow.viewport.panY;
      }
      this.updateTransform();
    }

    // 6. Reset selection and config panel
    this.selectedNodeId = null;
    this.selectedNodeIds.clear();
    this.selectedContainerIds.clear();
    this.selectedCommentIds.clear();
    this.selectedConnectionId = null;
    if (this.onSelectNode) {
      this.onSelectNode(null);
    }

    // 7. Re-render DOM elements and wires
    this.renderAll();

    // 8. Select first node if available
    if (this.nodes.length > 0) {
      this.selectNode(this.nodes[0].id);
    }

    // 9. Notify workflow change
    this.onWorkflowChange();

    // 10. Validate all nodes after loading
    this.validateAllNodes();
  }

  getWorkflowData() {
    // Mark nodes as cached for serialization
    this.nodes.forEach(n => {
      n.is_cached = this.cachedNodeIds.has(n.id);
    });
    const nameInput = document.getElementById('workflow-name-input');
    const wfName = (nameInput ? nameInput.value.trim() : '') || 'Workflow';
    return {
      name: wfName,
      description: (this.workflowMetadata && this.workflowMetadata.description) || '',
      metadata: this.workflowMetadata || {},
      viewport: {
        zoom: this.zoom,
        panX: this.panX,
        panY: this.panY
      },
      nodes: this.nodes,
      connections: this.connections,
      containers: this.containers,
      comments: this.comments,
      cached_node_ids: Array.from(this.cachedNodeIds),
      auto_cache_upstream: this.autoCacheUpstream
    };
  }

  setGridSnapSize(size) {
    this.gridSnapSize = Math.max(0, parseInt(size, 10) || 0);
    if (window.userSettings) window.userSettings.set('grid_snap', this.gridSnapSize);
    else localStorage.setItem('dataflow_grid_snap', this.gridSnapSize);
  }

  setWireStyle(style) {
    this.wireStyle = style === 'orthogonal' ? 'orthogonal' : 'bezier';
    if (window.userSettings) window.userSettings.set('wire_style', this.wireStyle);
    else localStorage.setItem('dataflow_wire_style', this.wireStyle);
    this.renderWires();
    if (window.appMiniMap) window.appMiniMap.render();
  }

  setAutoCacheUpstream(enabled) {
    this.autoCacheUpstream = Boolean(enabled);
    if (window.userSettings) window.userSettings.set('auto_cache_upstream', this.autoCacheUpstream);
    else localStorage.setItem('dataflow_auto_cache_upstream', this.autoCacheUpstream);
  }

  addNode(type, x, y, customName = null, initialConfig = {}) {
    const meta = this.toolRegistry[type] || {
      name: type,
      category: 'preparation',
      inputs: ['I'],
      outputs: ['O']
    };

    const id = `node_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    const newNode = {
      id: id,
      type: type,
      name: customName || meta.name,
      x: this.snapCoord(x),
      y: this.snapCoord(y),
      config: initialConfig
    };

    this.nodes.push(newNode);
    this.renderNodeElement(newNode);
    this.containers.forEach(c => this.updateContainerEnclosedNodes(c));
    this.renderWires();
    this.selectNode(id);
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Add Node');
    this.updateNodeValidation(newNode);
    return newNode;
  }

  // --------------------------------------------------------------------
  // Drag & Drop File Ingestion (CSV, TSV, TXT, Excel .xlsx/.xls, JSON)
  // --------------------------------------------------------------------
  async handleDroppedFiles(fileList, baseCoords) {
    if (!fileList || fileList.length === 0) return;
    const files = Array.from(fileList);

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const ext = (file.name.split('.').pop() || '').toLowerCase();

      // Check if dropped file is a Workflow JSON
      if (ext === 'json') {
        const reader = new FileReader();
        reader.onload = (ev) => {
          try {
            const data = JSON.parse(ev.target.result);
            if (data && (Array.isArray(data.nodes) || Array.isArray(data.connections))) {
              const wfName = file.name.replace(/\.json$/i, '');
              if (typeof window.handleWorkflowLoaded === 'function') {
                window.handleWorkflowLoaded(data, wfName);
              } else {
                this.loadWorkflow(data);
                const nameInput = document.getElementById('workflow-name-input');
                if (nameInput) nameInput.value = wfName;
              }
              if (window.showToast) window.showToast('success', 'Workflow Loaded', `Loaded '${file.name}' onto canvas.`);
              return;
            }
          } catch (jsonErr) {
            console.warn('Dropped JSON is not a workflow:', jsonErr);
          }
        };
        reader.readAsText(file);
        continue;
      }

      // Check if dropped file is a Workflow Package (.zip or .yxzp)
      if (ext === 'zip' || ext === 'yxzp') {

        const formData = new FormData();
        formData.append('file', file);
        if (window.showToast) window.showToast('info', 'Importing Package', `Extracting workflow package '${file.name}'...`, 3000);
        
        fetch('/api/workflow/import-package', {
          method: 'POST',
          body: formData
        })
        .then(r => r.json())
        .then(res => {
          if (res.success && res.workflow) {
            const wfName = res.workflow.name || file.name.replace(/\.(zip|yxzp)$/i, '');
            if (typeof window.handleWorkflowLoaded === 'function') {
              window.handleWorkflowLoaded(res.workflow, wfName);
            } else {
              this.loadWorkflow(res.workflow);
              const nameInput = document.getElementById('workflow-name-input');
              if (nameInput) nameInput.value = wfName;
            }
            if (window.showToast) {
              window.showToast('success', 'Package Imported', res.message || `Loaded package '${file.name}' onto canvas.`);
            }
          } else {
            if (window.showToast) {
              window.showToast('error', 'Import Failed', res.error || 'Failed to import workflow package.');
            }
          }
        })
        .catch(err => {
          if (window.showToast) {
            window.showToast('error', 'Import Failed', err.message);
          }
        });
        continue;
      }


      // Check supported data extensions
      const supportedExts = ['csv', 'tsv', 'txt', 'xlsx', 'xls', 'xlsm', 'xlsb', 'parquet', 'json'];
      if (!supportedExts.includes(ext)) {
        if (window.showToast) {
          window.showToast('warning', 'Unsupported File Format', `'${file.name}' is not supported. Please drop .csv, .xlsx, .xlsm, .tsv, .parquet, or .json data files.`);
        }
        continue;
      }

      // Calculate cascade offset for multiple dropped files
      const offsetX = (i % 4) * 48;
      const offsetY = i * 88;
      const nodeX = this.snapCoord(baseCoords.x - 28 + offsetX);
      const nodeY = this.snapCoord(baseCoords.y - 28 + offsetY);

      if (window.showToast) {
        window.showToast('info', 'Uploading Data', `Importing '${file.name}'...`, 2500);
      }

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        const json = await res.json();

        if (!json.success) {
          if (window.showToast) {
            window.showToast('error', 'Import Failed', json.error || `Could not parse '${file.name}'`);
          }
          continue;
        }

        // Handle Excel with multiple sheets
        if (json.file_type === 'excel' && json.sheets && json.sheets.length > 1) {
          this.promptExcelSheetSelection(json, { x: nodeX, y: nodeY }, file.name);
        } else {
          // Single-sheet Excel or CSV / TSV / TXT
          const defaultSheet = (json.file_type === 'excel' && json.sheets && json.sheets.length > 0) ? json.sheets[0] : null;
          const initialConfig = {
            file_path: json.file_name,
            original_file_name: json.original_name || file.name,
            file_type: json.file_type,
            delimiter: json.delimiter || ',',
            has_header: true,
            start_row: 1,
            columns: json.columns || [],
            row_count: json.row_count || 0
          };
          if (defaultSheet) {
            initialConfig.sheet_name = defaultSheet;
          }

          const nodeName = file.name;
          const newNode = this.addNode('input_data', nodeX, nodeY, nodeName, initialConfig);
          this.selectNode(newNode.id);

          if (window.showToast) {
            const countStr = (json.row_count !== undefined && json.row_count >= 0) ? ` (${json.row_count.toLocaleString()} rows)` : '';
            window.showToast('success', 'File Imported', `Created Input Data tool for '${file.name}'${countStr}.`);
          }
        }

      } catch (uploadErr) {
        console.error('File drop upload error:', uploadErr);
        if (window.showToast) {
          window.showToast('error', 'Upload Error', `Failed to upload '${file.name}': ${uploadErr.message}`);
        }
      }
    }
  }

  promptExcelSheetSelection(json, coords, fileName) {
    const modal = document.getElementById('modal-excel-sheet');
    if (!modal) {
      const initialConfig = {
        file_path: json.file_name,
        original_file_name: json.original_name || fileName,
        file_type: 'excel',
        sheet_name: json.sheets[0],
        has_header: true,
        start_row: 1,
        columns: json.columns || [],
        row_count: json.row_count || 0
      };
      const newNode = this.addNode('input_data', coords.x, coords.y, fileName, initialConfig);
      this.selectNode(newNode.id);
      return;
    }

    const titleSubtitle = document.getElementById('excel-modal-filename');
    if (titleSubtitle) {
      titleSubtitle.textContent = `Workbook: ${fileName} (${json.sheets.length} worksheets detected)`;
    }

    const listEl = document.getElementById('excel-sheet-list');
    if (listEl) {
      listEl.innerHTML = json.sheets.map((sheet, idx) => `
        <label class="excel-sheet-option ${idx === 0 ? 'selected' : ''}" data-sheet="${this.escapeHtml(sheet)}">
          <input type="radio" name="excel_sheet_radio" value="${this.escapeHtml(sheet)}" ${idx === 0 ? 'checked' : ''}>
          <div class="excel-sheet-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
              <line x1="3" y1="9" x2="21" y2="9"></line>
              <line x1="3" y1="15" x2="21" y2="15"></line>
              <line x1="9" y1="3" x2="9" y2="21"></line>
              <line x1="15" y1="3" x2="15" y2="21"></line>
            </svg>
          </div>
          <div class="excel-sheet-info">
            <span class="excel-sheet-name">${this.escapeHtml(sheet)}</span>
            <span class="excel-sheet-meta">${idx === 0 ? 'First Worksheet (Default)' : 'Worksheet Table'}</span>
          </div>
        </label>
      `).join('');

      listEl.querySelectorAll('.excel-sheet-option').forEach(opt => {
        opt.addEventListener('click', () => {
          listEl.querySelectorAll('.excel-sheet-option').forEach(o => o.classList.remove('selected'));
          opt.classList.add('selected');
          const radio = opt.querySelector('input[type="radio"]');
          if (radio) radio.checked = true;
        });
      });
    }

    modal.style.display = 'flex';

    const confirmBtn = document.getElementById('btn-excel-confirm-sheet');
    const importAllBtn = document.getElementById('btn-excel-import-all');

    if (confirmBtn) {
      confirmBtn.onclick = () => {
        const selectedRadio = modal.querySelector('input[name="excel_sheet_radio"]:checked');
        const selectedSheet = selectedRadio ? selectedRadio.value : json.sheets[0];
        modal.style.display = 'none';

        const initialConfig = {
          file_path: json.file_name,
          original_file_name: json.original_name || fileName,
          file_type: 'excel',
          sheet_name: selectedSheet,
          has_header: true,
          start_row: 1,
          columns: json.columns || [],
          row_count: json.row_count || 0
        };
        const nodeName = `${fileName} - ${selectedSheet}`;
        const newNode = this.addNode('input_data', coords.x, coords.y, nodeName, initialConfig);
        this.selectNode(newNode.id);
        if (window.showToast) {
          window.showToast('success', 'Excel Sheet Imported', `Loaded sheet '${selectedSheet}' from '${fileName}'.`);
        }
      };
    }

    if (importAllBtn) {
      importAllBtn.onclick = () => {
        modal.style.display = 'none';
        json.sheets.forEach((sheet, idx) => {
          const posX = this.snapCoord(coords.x + (idx % 3) * 48);
          const posY = this.snapCoord(coords.y + idx * 88);
          const initialConfig = {
            file_path: json.file_name,
            original_file_name: json.original_name || fileName,
            file_type: 'excel',
            sheet_name: sheet,
            has_header: true,
            start_row: 1,
            columns: idx === 0 ? (json.columns || []) : [],
            row_count: idx === 0 ? (json.row_count || 0) : 0
          };
          const nodeName = `${fileName} - ${sheet}`;
          this.addNode('input_data', posX, posY, nodeName, initialConfig);
        });
        if (window.showToast) {
          window.showToast('success', 'All Sheets Imported', `Created ${json.sheets.length} Input Data tools for all worksheets in '${fileName}'.`);
        }
      };
    }
  }

  removeNode(nodeId) {
    this.connections = this.connections.filter(c => c.source !== nodeId && c.target !== nodeId);
    this.nodes = this.nodes.filter(n => n.id !== nodeId);

    const el = document.getElementById(`node-elem-${nodeId}`);
    if (el) el.remove();

    this.selectedNodeIds.delete(nodeId);
    if (this.selectedNodeId === nodeId) {
      this.selectedNodeId = null;
      this.onSelectNode(null);
    }
    this.renderWires();
    this.onWorkflowChange();
  }

  addConnection(sourceNodeId, sourceHandle, targetNodeId, targetHandle) {
    if (sourceNodeId === targetNodeId) return;

    const exists = this.connections.some(c => 
      c.source === sourceNodeId &&
      c.sourceHandle === sourceHandle &&
      c.target === targetNodeId &&
      c.targetHandle === targetHandle
    );
    if (exists) return;

    const targetNode = this.nodes.find(n => n.id === targetNodeId);
    if (targetNode && targetNode.type !== 'union' && targetNode.type !== 'join_multiple') {
      this.connections = this.connections.filter(c => 
        !(c.target === targetNodeId && c.targetHandle === targetHandle)
      );
    }

    const id = `conn_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
    this.connections.push({
      id: id,
      source: sourceNodeId,
      sourceHandle: sourceHandle || 'O',
      target: targetNodeId,
      targetHandle: targetHandle || 'I'
    });

    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Add Connection');
  }

  removeConnection(connId) {
    this.connections = this.connections.filter(c => c.id !== connId);
    if (this.selectedConnectionId === connId) {
      this.selectedConnectionId = null;
      if (this.wireDeleteBtn) this.wireDeleteBtn.style.display = 'none';
    }
    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Remove Connection');
  }

  clearSelection() {
    this.selectedNodeIds.clear();
    this.selectedNodeId = null;
    this.selectedContainerIds.clear();
    this.selectedCommentIds.clear();
    document.querySelectorAll('.node-card.selected, .node-card.multi-selected').forEach(el => {
      el.classList.remove('selected', 'multi-selected');
    });
    document.querySelectorAll('.tool-container.selected').forEach(el => {
      el.classList.remove('selected');
    });
    document.querySelectorAll('.comment-note.selected').forEach(el => {
      el.classList.remove('selected');
    });

    if (this.selectedConnectionId) {
      const prevWire = document.getElementById(`wire-${this.selectedConnectionId}`);
      if (prevWire) {
        prevWire.classList.remove('selected');
        prevWire.setAttribute('stroke', '#64748b');
        prevWire.setAttribute('marker-end', 'url(#arrow)');
      }
      this.selectedConnectionId = null;
      if (this.wireDeleteBtn) this.wireDeleteBtn.style.display = 'none';
    }
    this.onSelectNode(null);
  }

  selectNode(nodeId, multi = false) {
    if (!multi) {
      this.clearSelection();
      this.selectedNodeId = nodeId;
      this.selectedNodeIds.add(nodeId);
    } else {
      if (this.selectedNodeIds.has(nodeId)) {
        this.selectedNodeIds.delete(nodeId);
      } else {
        this.selectedNodeIds.add(nodeId);
      }
      this.selectedNodeId = this.selectedNodeIds.size === 1 ? Array.from(this.selectedNodeIds)[0] : null;
    }

    this.updateSelectionVisuals();
    const node = this.selectedNodeId ? this.nodes.find(n => n.id === this.selectedNodeId) : null;
    this.onSelectNode(node);
  }

  updateSelectionVisuals() {
    document.querySelectorAll('.node-card').forEach(el => {
      const id = el.id.replace('node-elem-', '');
      const isSelected = this.selectedNodeIds.has(id);
      el.classList.toggle('selected', isSelected && this.selectedNodeIds.size === 1);
      el.classList.toggle('multi-selected', isSelected && this.selectedNodeIds.size > 1);
    });

    document.querySelectorAll('.tool-container').forEach(el => {
      const id = el.id.replace('container-elem-', '');
      el.classList.toggle('selected', this.selectedContainerIds.has(id));
    });

    document.querySelectorAll('.comment-note').forEach(el => {
      const id = el.id.replace('comment-elem-', '');
      el.classList.toggle('selected', this.selectedCommentIds.has(id));
    });
  }

  selectConnection(connId) {
    this.clearSelection();
    this.selectedConnectionId = connId;
    const wire = document.getElementById(`wire-${connId}`);
    if (wire) {
      wire.classList.add('selected');
      wire.setAttribute('stroke', '#f43f5e');
      wire.setAttribute('marker-end', 'url(#arrow-selected)');
      this.positionWireDeleteBtn(connId);
    }
  }

  positionWireDeleteBtn(connId) {
    const conn = this.connections.find(c => c.id === connId);
    if (!conn || !this.wireDeleteBtn) return;

    const p1 = this.getPortPosition(conn.source, conn.sourceHandle, 'output');
    const p2 = this.getPortPosition(conn.target, conn.targetHandle, 'input');
    const midX = (p1.x + p2.x) / 2;
    const midY = (p1.y + p2.y) / 2;

    this.wireDeleteBtn.style.left = `${midX - 11}px`;
    this.wireDeleteBtn.style.top = `${midY - 11}px`;
    this.wireDeleteBtn.style.display = 'flex';
  }

  renderAll() {
    if (this.containersLayer) this.containersLayer.innerHTML = '';
    if (this.commentsLayer) this.commentsLayer.innerHTML = '';
    if (this.nodesLayer) this.nodesLayer.innerHTML = '';

    this.containers.forEach(c => this.renderContainerElement(c));
    this.comments.forEach(comm => this.renderCommentElement(comm));
    this.nodes.forEach(node => this.renderNodeElement(node));
    this.containers.forEach(c => this.updateContainerEnclosedNodes(c));
    this.renderWires();
  }

  // --------------------------------------------------------------------
  // Authentic Compact Alteryx Tool Rendering
  // --------------------------------------------------------------------
  renderNodeElement(node) {
    const meta = this.toolRegistry[node.type] || {
      name: node.type,
      category: 'preparation',
      color: '#0072ce',
      icon: 'code',
      inputs: ['I'],
      outputs: ['O']
    };

    const nodeEl = document.createElement('div');
    nodeEl.id = `node-elem-${node.id}`;
    nodeEl.className = `node-card ${this.selectedNodeIds.has(node.id) ? 'selected' : ''} ${this.cachedNodeIds.has(node.id) ? 'is-cached' : ''}`;
    nodeEl.style.left = `${node.x}px`;
    nodeEl.style.top = `${node.y}px`;

    // Category accent top bar (5px)
    const headerBar = document.createElement('div');
    headerBar.className = 'node-header-bar';
    headerBar.style.backgroundColor = meta.color || '#0072ce';
    nodeEl.appendChild(headerBar);

    // Inner icon container
    const inner = document.createElement('div');
    inner.className = 'node-inner';

    const iconSvg = window.appPalette ? window.appPalette.getToolSvg(meta.icon) : '';

    inner.innerHTML = `
      <div class="node-icon-wrap" style="color: ${meta.color || '#0072ce'};">
        ${iconSvg}
      </div>
      <div class="node-status-badge" id="badge-${node.id}"></div>
      <div class="node-records-pill" id="pill-${node.id}" style="display: none;"></div>
    `;
    nodeEl.appendChild(inner);

    // Freeze / Cache indicator badge (snowflake)
    if (this.cachedNodeIds.has(node.id)) {
      const freezeBadge = document.createElement('div');
      freezeBadge.className = 'node-freeze-badge';
      freezeBadge.innerHTML = '❄️';
      freezeBadge.title = 'This node is cached. Right-click to clear cache.';
      freezeBadge.addEventListener('click', (e) => {
        e.stopPropagation();
        this.clearNodeCache(node.id);
      });
      nodeEl.appendChild(freezeBadge);
    }

    // Validation Warning badge
    const warningBadge = document.createElement('div');
    warningBadge.className = 'node-warning-badge';
    warningBadge.id = `warning-${node.id}`;
    warningBadge.innerHTML = '!';
    warningBadge.style.display = 'none';
    warningBadge.title = '';
    nodeEl.appendChild(warningBadge);

    // Tool label / annotation rendered cleanly underneath
    const annot = document.createElement('div');
    annot.className = 'node-annotation';
    annot.textContent = node.name;
    annot.title = node.name;
    nodeEl.appendChild(annot);

    // Render Input Ports (Left side)
    const inputs = meta.inputs || [];
    inputs.forEach((portName, idx) => {
      const portEl = document.createElement('div');
      portEl.className = 'port port-input';
      portEl.dataset.port = portName;
      portEl.dataset.nodeId = node.id;
      portEl.dataset.portType = 'input';
      portEl.title = this.getInputPortTooltip(node.type, portName);
      portEl.textContent = portName;

      const total = inputs.length;
      let topPercent = 50;
      if (total === 2) {
        topPercent = idx === 0 ? 30 : 70;
      } else if (total === 3) {
        topPercent = idx === 0 ? 20 : (idx === 1 ? 50 : 80);
      }
      portEl.style.top = `${topPercent}%`;

      this.attachPortEvents(portEl, node.id, portName, 'input');
      nodeEl.appendChild(portEl);
    });

    // Render Output Ports (Right side)
    const outputs = meta.outputs || [];
    outputs.forEach((portName, idx) => {
      const portEl = document.createElement('div');
      portEl.className = 'port port-output';
      portEl.dataset.port = portName;
      portEl.dataset.nodeId = node.id;
      portEl.dataset.portType = 'output';
      portEl.title = this.getPortTooltip(node.type, portName);
      portEl.textContent = portName;

      const total = outputs.length;
      let topPercent = 50;
      if (total === 2) {
        topPercent = idx === 0 ? 30 : 70;
      } else if (total === 3) {
        topPercent = idx === 0 ? 20 : (idx === 1 ? 50 : 80);
      }
      portEl.style.top = `${topPercent}%`;

      this.attachPortEvents(portEl, node.id, portName, 'output');
      nodeEl.appendChild(portEl);
    });

    // Node Selection & Multi-drag
    nodeEl.addEventListener('mousedown', (e) => {
      if (e.target.classList.contains('port')) return;
      if (e.button === 2) return; // handled by context menu

      e.stopPropagation();
      const isMulti = e.ctrlKey || e.metaKey || e.shiftKey;
      if (!isMulti && !this.selectedNodeIds.has(node.id)) {
        this.selectNode(node.id, false);
      } else if (!isMulti && this.selectedNodeIds.has(node.id)) {
        if (this.selectedNodeIds.size > 1) {
          this._pendingSingleSelectOnMouseUp = node.id;
        }
      } else if (isMulti) {
        this.selectNode(node.id, true);
      }

      const mouse = this.getCanvasCoords(e.clientX, e.clientY);
      this.draggingNode = node;
      this.dragMoved = false;
      this.dragOffset = {
        x: mouse.x - node.x,
        y: mouse.y - node.y
      };

      // Store initial positions for all selected nodes
      this.multiDragOffsets.clear();
      this.selectedNodeIds.forEach(id => {
        const n = this.nodes.find(item => item.id === id);
        if (n) {
          this.multiDragOffsets.set(id, { x: n.x, y: n.y });
        }
      });
    });

    this.nodesLayer.appendChild(nodeEl);
  }

  getInputPortTooltip(nodeType, portName) {
    if (nodeType === 'join') {
      return portName === 'L' ? 'Left (L): Main input dataset' : 'Right (R): Lookup/join input dataset';
    }
    if (nodeType === 'join_multiple') {
      return 'Input (I): Connect 2 or more datasets to join (#1, #2, #3...)';
    }
    if (nodeType === 'find_replace') {
      return portName === 'F' ? 'Find (F): Main input stream to search' : 'Replace (R): Reference lookup table';
    }
    if (nodeType === 'append_fields') {
      return portName === 'T' ? 'Target (T): Primary stream to receive appended fields' : 'Source (S): Source fields stream to duplicate across target';
    }
    return `Input Port (${portName})`;
  }

  getPortTooltip(nodeType, portName) {
    if (nodeType === 'filter') {
      return portName === 'T' ? 'True (T): Matching records' : 'False (F): Non-matching records';
    }
    if (nodeType === 'join') {
      if (portName === 'J') return 'Joined (J): Key-matched records';
      if (portName === 'L') return 'Left Unmatched (L): Left records with no match';
      if (portName === 'R') return 'Right Unmatched (R): Right records with no match';
    }
    if (nodeType === 'join_multiple') {
      return 'Joined (J): Combined joined records from all inputs';
    }
    if (nodeType === 'unique') {
      return portName === 'U' ? 'Unique (U): Deduplicated records' : 'Duplicates (D): Duplicate records';
    }
    if (nodeType === 'find_replace') {
      return 'Output (O): Replaced or appended data stream';
    }
    return `Output Port (${portName})`;
  }

  updateNodeElementPosition(node) {
    const el = document.getElementById(`node-elem-${node.id}`);
    if (el) {
      el.style.left = `${node.x}px`;
      el.style.top = `${node.y}px`;
    }
  }

  updateNodeLabel(nodeId, newName) {
    const node = this.nodes.find(n => n.id === nodeId);
    if (node) {
      node.name = newName;
      const el = document.getElementById(`node-elem-${nodeId}`);
      if (el) {
        const labelEl = el.querySelector('.node-annotation');
        if (labelEl) {
          labelEl.textContent = newName;
          labelEl.title = newName;
        }
      }
    }
  }

  // --------------------------------------------------------------------
  // Magnetic Ports & Bidirectional Wiring Interaction
  // --------------------------------------------------------------------
  attachPortEvents(portEl, nodeId, portName, type) {
    const handleStartOrFinish = (e) => {
      e.preventDefault();
      e.stopPropagation();

      if (this._suppressNextPortClick) return;

      if (this.connectingState) {
        if (this.connectingState.sourceType !== type && this.connectingState.sourceNodeId !== nodeId) {
          if (this.connectingState.sourceType === 'output') {
            this.addConnection(this.connectingState.sourceNodeId, this.connectingState.sourceHandle, nodeId, portName);
          } else {
            this.addConnection(nodeId, portName, this.connectingState.sourceNodeId, this.connectingState.sourceHandle);
          }
          this.cancelConnecting();
          this._suppressNextPortClick = true;
          setTimeout(() => { this._suppressNextPortClick = false; }, 120);
          return;
        } else if (this.connectingState.sourceNodeId === nodeId && this.connectingState.sourceHandle === portName) {
          this.cancelConnecting();
          return;
        }
      }

      const portPos = this.getPortPosition(nodeId, portName, type);
      this.connectingState = {
        sourceNodeId: nodeId,
        sourceHandle: portName,
        sourceType: type,
        startX: portPos.x,
        startY: portPos.y,
        snappedPort: null,
        moved: false,
        startTime: Date.now()
      };

      this.highlightCandidatePorts(nodeId, type);
    };

    portEl.addEventListener('mousedown', handleStartOrFinish);
    portEl.addEventListener('click', (e) => {
      e.stopPropagation();
      if (this._suppressNextPortClick) return;
      if (this.connectingState && this.connectingState.sourceNodeId !== nodeId && this.connectingState.sourceType !== type) {
        if (this.connectingState.sourceType === 'output') {
          this.addConnection(this.connectingState.sourceNodeId, this.connectingState.sourceHandle, nodeId, portName);
        } else {
          this.addConnection(nodeId, portName, this.connectingState.sourceNodeId, this.connectingState.sourceHandle);
        }
        this.cancelConnecting();
        this._suppressNextPortClick = true;
        setTimeout(() => { this._suppressNextPortClick = false; }, 120);
      }
    });
  }

  highlightCandidatePorts(sourceNodeId, sourceType) {
    const targetType = sourceType === 'output' ? 'input' : 'output';
    const ports = document.querySelectorAll(`.port[data-port-type="${targetType}"]`);
    ports.forEach(p => {
      if (p.dataset.nodeId !== sourceNodeId) {
        p.classList.add('candidate-port');
      }
    });
  }

  findCandidatePortNear(mouseX, mouseY) {
    if (!this.connectingState) return null;
    const targetType = this.connectingState.sourceType === 'output' ? 'input' : 'output';
    const ports = document.querySelectorAll(`.port[data-port-type="${targetType}"]`);

    let closest = null;
    let minDist = 45; // 45px magnetic snap radius

    ports.forEach(p => {
      const nId = p.dataset.nodeId;
      if (nId === this.connectingState.sourceNodeId) return;

      const pName = p.dataset.port;
      const pos = this.getPortPosition(nId, pName, targetType);
      const dist = Math.hypot(pos.x - mouseX, pos.y - mouseY);

      if (dist < minDist) {
        minDist = dist;
        closest = { nodeId: nId, portName: pName, type: targetType, element: p, x: pos.x, y: pos.y };
      }
    });

    return closest;
  }

  cancelConnecting() {
    this.connectingState = null;
    if (this.tempWire) {
      this.tempWire.setAttribute('d', '');
    }
    document.querySelectorAll('.port.snap-target').forEach(p => p.classList.remove('snap-target'));
    document.querySelectorAll('.port.candidate-port').forEach(p => p.classList.remove('candidate-port'));
  }

  computeWirePath(p1, p2, style = this.wireStyle) {
    if (style === 'orthogonal') {
      const minStep = 24;
      if (p2.x >= p1.x + minStep * 2) {
        const midX = Math.round((p1.x + p2.x) / 2);
        return `M ${p1.x} ${p1.y} L ${midX} ${p1.y} L ${midX} ${p2.y} L ${p2.x} ${p2.y}`;
      } else {
        const xA = p1.x + minStep;
        const xB = p2.x - minStep;
        const midY = p1.y < p2.y ? Math.round((p1.y + p2.y) / 2) : p1.y + 40;
        return `M ${p1.x} ${p1.y} L ${xA} ${p1.y} L ${xA} ${midY} L ${xB} ${midY} L ${xB} ${p2.y} L ${p2.x} ${p2.y}`;
      }
    }
    const dx = Math.max(35, Math.abs(p2.x - p1.x) * 0.5);
    return `M ${p1.x} ${p1.y} C ${p1.x + dx} ${p1.y}, ${p2.x - dx} ${p2.y}, ${p2.x} ${p2.y}`;
  }

  updateTempWire(x1, y1, x2, y2) {
    const d = this.computeWirePath({ x: x1, y: y1 }, { x: x2, y: y2 }, this.wireStyle);
    this.tempWire.setAttribute('d', d);
    this.tempWire.setAttribute('fill', 'none');
    this.tempWire.setAttribute('stroke', '#0072ce');
    this.tempWire.setAttribute('stroke-width', '2.5');
    this.tempWire.setAttribute('stroke-linecap', 'round');
    this.tempWire.setAttribute('marker-end', 'url(#arrow-selected)');
  }

  getPortPosition(nodeId, portName, type) {
    const node = this.nodes.find(n => n.id === nodeId);
    if (!node) return { x: 0, y: 0 };

    // When enclosed in a collapsed container, route connection to container header edge
    if (node.container_id) {
      const c = this.containers.find(item => item.id === node.container_id);
      if (c && c.collapsed) {
        const headerY = c.y + 17;
        const edgeX = type === 'input' ? c.x : (c.x + c.width);
        return { x: edgeX, y: headerY };
      }
    }

    const meta = this.toolRegistry[node.type] || { inputs: ['I'], outputs: ['O'] };
    const ports = type === 'input' ? (meta.inputs || []) : (meta.outputs || []);
    const idx = Math.max(0, ports.indexOf(portName));
    const total = Math.max(1, ports.length);

    let yOffset = 28;
    if (total === 2) {
      yOffset = idx === 0 ? 17 : 39;
    } else if (total === 3) {
      yOffset = idx === 0 ? 11 : (idx === 1 ? 28 : 45);
    }

    // Physical apex of the protruding anchors:
    // Output port apex is at node.x + 57 (emerging directly from the right-hand anchor tip)
    // Input port entry is at node.x - 1 (entering directly into the left-hand anchor)
    const x = type === 'input' ? (node.x - 1) : (node.x + 57);
    const y = node.y + yOffset;

    return { x, y };
  }

  renderWires() {
    this.wiresGroup.innerHTML = '';

    // Update port-connected classes on all ports
    document.querySelectorAll('.port.port-connected').forEach(p => p.classList.remove('port-connected'));

    this.connections.forEach(conn => {
      // If both source and target are inside the same collapsed container, hide the internal wire
      const srcNode = this.nodes.find(n => n.id === conn.source);
      const tgtNode = this.nodes.find(n => n.id === conn.target);
      if (srcNode && tgtNode && srcNode.container_id && srcNode.container_id === tgtNode.container_id) {
        const c = this.containers.find(item => item.id === srcNode.container_id);
        if (c && c.collapsed) {
          return;
        }
      }

      // Mark connected source & target ports
      const srcPortEl = document.querySelector(`.port[data-node-id="${conn.source}"][data-port="${conn.sourceHandle}"][data-port-type="output"]`);
      if (srcPortEl) srcPortEl.classList.add('port-connected');
      const tgtPortEl = document.querySelector(`.port[data-node-id="${conn.target}"][data-port="${conn.targetHandle}"][data-port-type="input"]`);
      if (tgtPortEl) tgtPortEl.classList.add('port-connected');

      const p1 = this.getPortPosition(conn.source, conn.sourceHandle, 'output');
      const p2 = this.getPortPosition(conn.target, conn.targetHandle, 'input');

      const d = this.computeWirePath(p1, p2, this.wireStyle);

      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      g.className.baseVal = 'wire-group';

      const hitZone = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      hitZone.setAttribute('d', d);
      hitZone.className.baseVal = 'wire-hit-zone';

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.id = `wire-${conn.id}`;
      path.setAttribute('d', d);
      path.className.baseVal = `wire ${conn.id === this.selectedConnectionId ? 'selected' : ''}`;
      path.setAttribute('marker-end', conn.id === this.selectedConnectionId ? 'url(#arrow-selected)' : 'url(#arrow)');

      const handleWireSelect = (e) => {
        e.stopPropagation();
        this.selectConnection(conn.id);
      };

      hitZone.addEventListener('click', handleWireSelect);
      path.addEventListener('click', handleWireSelect);

      // Wire Hover Data Probe
      hitZone.addEventListener('mouseenter', (e) => {
        clearTimeout(this._wireProbeTimeout);
        this.showWireProbe(conn, e.clientX, e.clientY);
      });
      hitZone.addEventListener('mouseleave', () => {
        this.hideWireProbe(350);
      });

      path.addEventListener('mouseenter', (e) => {
        clearTimeout(this._wireProbeTimeout);
        this.showWireProbe(conn, e.clientX, e.clientY);
      });
      path.addEventListener('mouseleave', () => {
        this.hideWireProbe(350);
      });

      g.appendChild(hitZone);
      g.appendChild(path);
      this.wiresGroup.appendChild(g);
    });

    if (this.selectedConnectionId) {
      this.positionWireDeleteBtn(this.selectedConnectionId);
    }
  }

  showWireProbe(conn, mouseX, mouseY) {
    if (!this.wireProbesEnabled) return;
    this.hideWireProbe();
    const srcNode = this.nodes.find(n => n.id === conn.source);
    const tgtNode = this.nodes.find(n => n.id === conn.target);
    if (!srcNode || !tgtNode) return;

    const res = this.lastExecutionResults ? this.lastExecutionResults[conn.source] : null;
    let recCount = null;
    if (res && res.record_counts && res.record_counts[conn.sourceHandle] !== undefined) {
      recCount = res.record_counts[conn.sourceHandle];
    } else if (res && res.record_counts && Object.values(res.record_counts).length > 0) {
      recCount = Object.values(res.record_counts)[0];
    }

    const card = document.createElement('div');
    card.id = 'active-wire-probe';
    card.className = 'wire-probe-card';
    card.style.left = `${Math.min(window.innerWidth - 230, mouseX + 12)}px`;
    card.style.top = `${Math.min(window.innerHeight - 150, Math.max(10, mouseY - 20))}px`;

    const statusHtml = res ? (res.status === 'success' ? '<span style="color: var(--color-success); font-weight:600;">✓ Succeeded</span>' : '<span style="color: var(--color-error); font-weight:600;">✗ Failed</span>') : '<span style="color: var(--text-muted)">Not executed</span>';
    const recStr = recCount !== null ? `${recCount.toLocaleString()} records` : (res ? 'No output cached' : 'Pending run');

    card.innerHTML = `
      <div class="wire-probe-header">
        <span>${this.escapeHtml(srcNode.name || srcNode.type)} [${conn.sourceHandle}] ➔ ${this.escapeHtml(tgtNode.name || tgtNode.type)}</span>
      </div>
      <div class="wire-probe-stats">
        <div>Status: ${statusHtml}</div>
        <div>Stream: <b>${recStr}</b></div>
        ${res && res.duration_ms !== undefined ? `<div>Execution Time: <b>${res.duration_ms}ms</b></div>` : ''}
      </div>
      <button class="btn btn-secondary btn-sm wire-probe-btn" id="btn-wire-probe-inspect">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
        <span>Inspect Data</span>
      </button>
    `;

    card.addEventListener('mouseenter', () => {
      clearTimeout(this._wireProbeTimeout);
    });
    card.addEventListener('mouseleave', () => {
      this.hideWireProbe(200);
    });

    const inspectBtn = card.querySelector('#btn-wire-probe-inspect');
    if (inspectBtn) {
      inspectBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectNode(srcNode.id);
        if (window.appResultsPanel) {
          window.appResultsPanel.showNodeResults(srcNode, conn.sourceHandle);
          window.appResultsPanel.switchToTab('data-view');
        }
        this.hideWireProbe();
      });
    }

    document.body.appendChild(card);
    this._wireProbeCard = card;
  }

  setWireProbesEnabled(enabled) {
    this.wireProbesEnabled = !!enabled;
    if (window.userSettings) window.userSettings.set('wire_probes_enabled', this.wireProbesEnabled);
    else localStorage.setItem('dataflow_wire_probes_enabled', this.wireProbesEnabled ? 'true' : 'false');
    if (!this.wireProbesEnabled) {
      this.hideWireProbe();
    }
    const checkEl = document.getElementById('check-view-wire-probes') || document.getElementById('check-wire-probes');
    if (checkEl) {
      checkEl.textContent = this.wireProbesEnabled ? '✓' : '';
    }
    const badgeEl = document.getElementById('menu-wire-probe-status');
    if (badgeEl) {
      const probeText = badgeEl.querySelector('.probe-text');
      if (probeText) probeText.textContent = `Wire Probes: ${this.wireProbesEnabled ? 'ON' : 'OFF'}`;
      badgeEl.classList.toggle('disabled', !this.wireProbesEnabled);
    }
    const settingCheckbox = document.getElementById('setting-wire-probes');
    if (settingCheckbox) {
      settingCheckbox.checked = this.wireProbesEnabled;
    }
    if (window.showToast) {
      window.showToast('info', 'Wire Data Probes', `Connection wire hover data probes are now ${this.wireProbesEnabled ? 'Enabled' : 'Disabled'}.`);
    }
  }

  setNodeBadgeDuration(duration) {
    this.nodeBadgeDuration = String(duration || '3000');
    if (window.userSettings) window.userSettings.set('node_badge_duration', this.nodeBadgeDuration);
    else localStorage.setItem('dataflow_node_badge_duration', this.nodeBadgeDuration);
    if (this.nodeBadgeDuration === 'off') {
      this.clearPillTimers();
      document.querySelectorAll('.node-records-pill').forEach(p => {
        p.style.display = 'none';
        p.classList.remove('fade-out');
      });
    } else if (this.nodeBadgeDuration === 'always') {
      this.clearPillTimers();
      if (this.lastExecutionResults) {
        this.nodes.forEach(node => {
          const res = this.lastExecutionResults[node.id];
          const pill = document.getElementById(`pill-${node.id}`);
          if (res && res.status === 'success' && res.record_counts && pill) {
            pill.classList.remove('fade-out');
            pill.style.display = 'block';
            pill.style.opacity = '1';
          }
        });
      }
    }
    const settingSelect = document.getElementById('setting-node-badge-duration');
    if (settingSelect) {
      settingSelect.value = this.nodeBadgeDuration;
    }
    if (window.appMenuBar) window.appMenuBar.syncMenuStates();
  }

  showNodeRecordPill(pill, nodeId) {
    if (!pill) return;
    const mode = this.nodeBadgeDuration || '3000';
    if (mode === 'off') {
      pill.style.display = 'none';
      return;
    }

    if (this._pillTimers && this._pillTimers[nodeId]) {
      clearTimeout(this._pillTimers[nodeId]);
      delete this._pillTimers[nodeId];
    }
    if (!this._pillTimers) this._pillTimers = {};

    pill.classList.remove('fade-out');
    pill.style.display = 'block';
    pill.style.opacity = '1';

    if (mode === 'always') return;

    const durationMs = parseInt(mode, 10) || 3000;
    this._pillTimers[nodeId] = setTimeout(() => {
      pill.classList.add('fade-out');
      setTimeout(() => {
        if (pill.classList.contains('fade-out')) {
          pill.style.display = 'none';
        }
      }, 450);
      if (this._pillTimers) delete this._pillTimers[nodeId];
    }, durationMs);
  }

  clearPillTimers() {
    if (this._pillTimers) {
      Object.values(this._pillTimers).forEach(timerId => clearTimeout(timerId));
      this._pillTimers = {};
    }
  }

  hideWireProbe(delay = 0) {
    clearTimeout(this._wireProbeTimeout);
    if (delay > 0) {
      this._wireProbeTimeout = setTimeout(() => {
        if (this._wireProbeCard) {
          this._wireProbeCard.remove();
          this._wireProbeCard = null;
        }
      }, delay);
    } else {
      if (this._wireProbeCard) {
        this._wireProbeCard.remove();
        this._wireProbeCard = null;
      }
    }
  }

  escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --------------------------------------------------------------------
  // Execution Visuals & Real-Time Pulse
  // --------------------------------------------------------------------
  setRunningState(isRunning) {
    document.querySelectorAll('.wire').forEach(w => {
      w.classList.toggle('running', isRunning);
    });
    if (isRunning) {
      this.clearPillTimers();
      this.hideWireProbe();
      document.querySelectorAll('.node-status-badge').forEach(b => {
        b.className = 'node-status-badge running';
        b.innerHTML = '';
      });
      document.querySelectorAll('.node-records-pill').forEach(p => {
        p.classList.remove('fade-out');
        p.style.display = 'none';
      });
      document.querySelectorAll('.port-record-badge').forEach(b => {
        b.remove();
      });
    }
  }

  updateNodeExecutionStep(stepData) {
    const { node_id, status, duration_ms, record_counts } = stepData;
    const badge = document.getElementById(`badge-${node_id}`);
    const pill = document.getElementById(`pill-${node_id}`);

    if (badge) {
      if (status === 'running') {
        badge.className = 'node-status-badge running';
        badge.innerHTML = '●';
      } else if (status === 'success') {
        badge.className = 'node-status-badge success';
        badge.innerHTML = '✓';
      } else if (status === 'error') {
        badge.className = 'node-status-badge error';
        badge.innerHTML = '!';
      }
    }

    if (pill && record_counts && status === 'success') {
      const parts = Object.entries(record_counts).map(([port, count]) => {
        return Object.keys(record_counts).length > 1 ? `[${port}]: ${count}` : `${count.toLocaleString()} recs`;
      });
      pill.textContent = `${parts.join(' ')} (${duration_ms}ms)`;
      this.showNodeRecordPill(pill, node_id);
    }
  }

  updateExecutionVisuals(nodeResults = {}) {
    this.lastExecutionResults = nodeResults;
    document.querySelectorAll('.port-record-badge').forEach(b => b.remove());

    this.nodes.forEach(node => {
      const res = nodeResults[node.id];
      const badge = document.getElementById(`badge-${node.id}`);
      const pill = document.getElementById(`pill-${node.id}`);
      const card = document.getElementById(`node-elem-${node.id}`);

      if (!res) {
        if (badge) { badge.className = 'node-status-badge'; badge.innerHTML = ''; }
        if (pill) {
          pill.style.display = 'none';
          pill.classList.remove('fade-out');
        }
        if (card) card.classList.remove('has-error');
        return;
      }

      if (badge) {
        if (res.status === 'success') {
          badge.className = 'node-status-badge success';
          badge.innerHTML = '✓';
        } else if (res.status === 'error') {
          badge.className = 'node-status-badge error';
          badge.innerHTML = '!';
        } else {
          badge.className = 'node-status-badge';
          badge.innerHTML = '';
        }
      }

      if (pill) {
        if (res.status === 'success' && res.record_counts) {
          const parts = Object.entries(res.record_counts).map(([port, count]) => {
            return Object.keys(res.record_counts).length > 1 ? `[${port}]: ${count}` : `${count.toLocaleString()} recs`;
          });
          pill.textContent = `${parts.join(' ')} (${res.duration_ms}ms)`;
          this.showNodeRecordPill(pill, node.id);
        } else {
          pill.style.display = 'none';
          pill.classList.remove('fade-out');
        }
      }

      // Attach output port record count badges
      if (res.status === 'success' && res.record_counts && card) {
        Object.entries(res.record_counts).forEach(([portName, count]) => {
          const portEl = card.querySelector(`.port[data-port="${portName}"][data-port-type="output"]`);
          if (portEl) {
            const b = document.createElement('span');
            b.className = 'port-record-badge';
            b.textContent = count > 9999 ? `${(count/1000).toFixed(1)}k` : `${count.toLocaleString()}`;
            b.title = `${count.toLocaleString()} output records`;
            portEl.appendChild(b);
          }
        });
      }

      if (card) {
        card.classList.toggle('has-error', res.status === 'error');
      }
    });
  }

  highlightErrorNode(nodeId) {
    const card = document.getElementById(`node-elem-${nodeId}`);
    if (card) {
      card.classList.add('has-error');
      this.selectNode(nodeId);
    }
  }

  autoLayout() {
    if (this.nodes.length === 0) return;

    // Simple left-to-right topological layout
    const inDegree = {};
    const adj = {};
    this.nodes.forEach(n => {
      inDegree[n.id] = 0;
      adj[n.id] = [];
    });

    this.connections.forEach(c => {
      if (adj[c.source]) adj[c.source].push(c.target);
      if (inDegree[c.target] !== undefined) inDegree[c.target]++;
    });

    const queue = this.nodes.filter(n => inDegree[n.id] === 0).map(n => n.id);
    const levels = {};
    queue.forEach(id => { levels[id] = 0; });

    while (queue.length > 0) {
      const curr = queue.shift();
      const currLevel = levels[curr];
      (adj[curr] || []).forEach(nxt => {
        levels[nxt] = Math.max(levels[nxt] || 0, currLevel + 1);
        inDegree[nxt]--;
        if (inDegree[nxt] === 0) queue.push(nxt);
      });
    }

    const byLevel = {};
    this.nodes.forEach(n => {
      const lvl = levels[n.id] || 0;
      if (!byLevel[lvl]) byLevel[lvl] = [];
      byLevel[lvl].push(n);
    });

    const START_X = 100;
    const START_Y = 120;
    const SPACING_X = 140;
    const SPACING_Y = 90;

    Object.keys(byLevel).sort((a, b) => a - b).forEach(lvl => {
      const colNodes = byLevel[lvl];
      colNodes.forEach((node, rowIdx) => {
        node.x = START_X + parseInt(lvl) * SPACING_X;
        node.y = START_Y + rowIdx * SPACING_Y;
        this.updateNodeElementPosition(node);
      });
    });

    this.renderWires();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Auto Layout');
    if (window.showToast) window.showToast('info', 'Auto Layout', 'Flow organized left-to-right.');
  }

  clearCanvas() {
    this.nodes = [];
    this.connections = [];
    this.containers = [];
    this.comments = [];
    this.cachedNodeIds.clear();
    this.clearSelection();
    this.renderAll();
    this.onWorkflowChange();
    if (window.appHistory) window.appHistory.pushSnapshot('Clear Canvas');
  }

  // --------------------------------------------------------------------
  // Node Configuration Validation (Client-Side)
  // --------------------------------------------------------------------
  validateNodeConfig(node) {
    if (!node || !node.type) return { valid: true, warnings: [] };
    const cfg = node.config || {};
    const warnings = [];
    const t = node.type;

    if (t === 'input_data') {
      if (!cfg.file_name && !cfg.file_path && !cfg.filename) {
        warnings.push('No data file selected. Please choose or upload a CSV or Excel file.');
      }
    } else if (t === 'text_input') {
      const text = cfg.text || '';
      const rawText = cfg.raw_text || '';
      const data = cfg.data || [];
      const cols = cfg.columns || [];
      const hasGridData = cols.length > 0 && data.length > 0 && data.some(row => Array.isArray(row) && row.some(cell => String(cell).trim()));
      if (!text.trim() && !rawText.trim() && !hasGridData) {
        warnings.push('No text data entered. Provide CSV/tabular text data.');
      }
    } else if (t === 'filter') {
      const mode = cfg.mode || 'basic';
      if (mode === 'custom') {
        const expr = cfg.expression || '';
        if (!expr.trim()) {
          warnings.push('No filter expression configured.');
        }
      } else {
        const conditions = cfg.conditions;
        if (Array.isArray(conditions)) {
          if (conditions.length === 0) {
            warnings.push('No filter conditions configured. Add at least one condition.');
          } else {
            conditions.forEach((c, idx) => {
              if (!c || !c.column) {
                warnings.push(`Condition #${idx + 1}: No filter column selected.`);
              }
              const unaryOps = new Set(['is_null', 'is_not_null', 'is_empty', 'is_not_empty']);
              if (c && c.column && !unaryOps.has(c.operator || '==')) {
                if (c.value === undefined || c.value === null || String(c.value).trim() === '') {
                  warnings.push(`Condition #${idx + 1}: Comparison value is missing for operator '${c.operator || '=='}'.`);
                }
              }
            });
          }
        } else {
          if (!cfg.column) warnings.push('No filter column selected.');
          const unaryOps = new Set(['is_null', 'is_not_null', 'is_empty', 'is_not_empty']);
          if (cfg.column && !unaryOps.has(cfg.operator || '==')) {
            if (cfg.value === undefined || cfg.value === null || String(cfg.value).trim() === '') {
              warnings.push(`Comparison value is missing for operator '${cfg.operator || '=='}'.`);
            }
          }
        }
      }
    } else if (t === 'formula') {
      const formulas = cfg.formulas || [];
      const exprs = cfg.expressions || [];
      const validFormulas = formulas.filter(f => f && f.output_field && String(f.expression || '').trim());
      const validExprs = exprs.filter(e => e && e.column && String(e.expression || '').trim());
      if (validFormulas.length === 0 && validExprs.length === 0) {
        warnings.push('No formula expression configured. Specify target column and formula.');
      }
    } else if (t === 'select') {
      const cols = cfg.columns;
      const fields = cfg.fields;
      if (Array.isArray(cols) && cols.length > 0) {
        const selected = cols.filter(c => c && c.selected !== false);
        if (selected.length === 0) warnings.push('All output columns are deselected.');
      } else if (Array.isArray(fields) && fields.length > 0) {
        const kept = fields.filter(f => f && f.keep !== false);
        if (kept.length === 0) warnings.push('All output columns are deselected.');
      }
    } else if (t === 'sort') {
      const sortBy = cfg.sort_by || [];
      const rules = cfg.rules || [];
      const validSortBy = sortBy.filter(s => s && s.column);
      const validRules = rules.filter(r => r && r.column);
      if (!validSortBy.length && !validRules.length && !cfg.column) {
        warnings.push('No sort column specified.');
      }
    } else if (t === 'summarize') {
      const actions = cfg.actions || [];
      const validA = actions.filter(a => a && a.field && a.action);
      if (!validA.length) {
        warnings.push('No summary actions configured. Add at least one aggregation or group by.');
      }
    } else if (t === 'join') {
      const joinMode = cfg.join_mode || 'specific_fields';
      if (joinMode !== 'record_position') {
        const joinKeys = cfg.join_keys || [];
        const validKeys = joinKeys.filter(k => k && k.left_key && k.right_key);
        const leftKey = cfg.left_key || cfg.left_field;
        const rightKey = cfg.right_key || cfg.right_field;
        if (!validKeys.length && (!leftKey || !rightKey)) {
          warnings.push('Both Left and Right join key columns must be specified.');
        }
      }
    } else if (t === 'find_replace') {
      const findField = cfg.find_field;
      const action = cfg.action || 'replace';
      const replaceField = cfg.replace_field || cfg.replace_with_field;
      const appendFields = cfg.append_fields || [];
      if (!findField) {
        warnings.push('Find target field must be selected.');
      } else if (action === 'append') {
        if (!appendFields.length) warnings.push('At least one field to append must be selected.');
      } else if (!replaceField) {
        warnings.push('Replace target field must be selected.');
      }
    } else if (t === 'unique') {
      if (!cfg.columns || cfg.columns.length === 0) {
        warnings.push('No deduplication columns selected.');
      }
    } else if (t === 'sample') {
      const sampleType = cfg.sample_type || 'first_n';
      if (sampleType === 'percent') {
        const pct = parseFloat(cfg.percent);
        if (isNaN(pct) || pct <= 0 || pct > 100) {
          warnings.push('Sample percentage must be between 1 and 100.');
        }
      } else {
        const n = parseInt(cfg.n_records !== undefined ? cfg.n_records : cfg.n, 10);
        if (isNaN(n) || n <= 0) {
          warnings.push('Sample size must be greater than 0.');
        }
      }
    } else if (t === 'transpose') {
      const dataFields = cfg.data_fields || cfg.data_columns || [];
      if (!dataFields.length) {
        warnings.push('At least one data field must be selected for transposing.');
      }
    } else if (t === 'crosstab') {
      const headerField = cfg.header_field;
      const dataField = cfg.data_field || cfg.value_field;
      if (!headerField || !dataField) {
        warnings.push('Both Header column and Data value column must be selected.');
      }
    } else if (t === 'text_to_columns') {
      const delim = cfg.delimiter || cfg.delimiters;
      if (!cfg.column || !delim) {
        warnings.push('Target column and delimiter must be specified.');
      }
    } else if (t === 'output_data') {
      if (!cfg.file_name && !cfg.filename) {
        warnings.push('Output file name must be specified.');
      }
    }

    return { valid: warnings.length === 0, warnings };
  }

  updateNodeValidation(node) {
    if (!node || !node.id) return;
    const result = this.validateNodeConfig(node);
    const warningBadge = document.getElementById(`warning-${node.id}`);
    if (!warningBadge) return;

    if (result.valid) {
      warningBadge.style.display = 'none';
      warningBadge.title = '';
    } else {
      warningBadge.style.display = 'flex';
      warningBadge.title = result.warnings.join('\n');
    }
  }

  validateAllNodes() {
    this.nodes.forEach(n => this.updateNodeValidation(n));
  }

  // --------------------------------------------------------------------
  // Frozen Node Cache ("Cache & Run")
  // --------------------------------------------------------------------
  async cacheAndRunNode(nodeId) {
    this.cachedNodeIds.add(nodeId);
    const node = this.nodes.find(n => n.id === nodeId);
    if (node) node.is_cached = true;

    // Re-render the node to show the freeze badge
    const existingEl = document.getElementById(`node-elem-${nodeId}`);
    if (existingEl) existingEl.remove();
    if (node) this.renderNodeElement(node);
    this.renderWires();
    this.updateSelectionVisuals();

    this.onWorkflowChange();
    if (window.showToast) window.showToast('info', 'Node Cached', `Tool '${node ? node.name : nodeId}' marked for caching. Running workflow...`);

    // Trigger the workflow run
    const runBtn = document.getElementById('btn-run');
    if (runBtn && !runBtn.classList.contains('loading')) {
      runBtn.click();
    }
  }

  async clearNodeCache(nodeId) {
    this.cachedNodeIds.delete(nodeId);
    const node = this.nodes.find(n => n.id === nodeId);
    if (node) node.is_cached = false;

    // Notify backend to clear cached data
    try {
      await fetch('/api/node-cache/clear', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId })
      });
    } catch (e) {
      console.warn('Failed to clear server cache:', e);
    }

    // Re-render the node to remove the freeze badge
    const existingEl = document.getElementById(`node-elem-${nodeId}`);
    if (existingEl) existingEl.remove();
    if (node) this.renderNodeElement(node);
    this.renderWires();
    this.updateSelectionVisuals();

    this.onWorkflowChange();
    if (window.showToast) window.showToast('info', 'Cache Cleared', `Cache cleared for tool '${node ? node.name : nodeId}'.`);
  }
}
