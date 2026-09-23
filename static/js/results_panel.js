/**
 * Results & Data Profiling Panel.
 * Manages paginated data inspection, column profiling, interactive charting,
 * in-grid distribution sparklines, execution logs, and data exports.
 */

class ResultsPanel {
  constructor() {
    this.currentNodeId = null;
    this.currentPort = 'O';
    this.currentPage = 1;
    const savedPageSize = localStorage.getItem('dataflow_page_size');
    this.pageSize = savedPageSize ? parseInt(savedPageSize, 10) : 100;
    this.searchQuery = '';
    this.currentTab = 'data-view';
    const savedHist = localStorage.getItem('dataflow_show_histograms');
    this.showHistograms = savedHist !== null ? (savedHist === 'true') : false;

    this.panel = document.getElementById('results-panel');
    this.nodeBadge = document.getElementById('results-node-badge');
    this.portTabsContainer = document.getElementById('results-port-tabs');
    this.recordCountText = document.getElementById('results-record-count');
    this.gridWrapper = document.getElementById('grid-wrapper');
    this.profilerContainer = document.getElementById('profiler-container');
    this.messagesLog = document.getElementById('messages-log');
    this.messagesCountPill = document.getElementById('messages-count-pill');
    this.paginationText = document.getElementById('pagination-text');
    this.searchInput = document.getElementById('grid-search-input');

    // Chart builder elements
    this.chartViewport = document.getElementById('chart-viewport');
    this.chartTypeSelect = document.getElementById('chart-type-select');
    this.chartXSelect = document.getElementById('chart-x-select');
    this.chartYSelect = document.getElementById('chart-y-select');
    this.chartAggSelect = document.getElementById('chart-agg-select');

    this.lastRenderedData = null;
    this.lastChartData = null;
    this.activeQuickfilterPopover = null;

    // Preview Performance & Large Dataset Optimizations
    this.sampleMode = 'page';
    this.hiddenColumns = new Set();
    this.activeColumnExplorer = null;
    this.activeCellModal = null;
    this.partialBanner = document.getElementById('partial-results-banner');

    // Cell Selection & Copying State
    this.selectedCells = new Set();
    this.selectionAnchor = null;
    this.isSelecting = false;
    this.activeContextMenu = null;
    this.activeColumns = [];

    // Execution Messages Run History & Filters
    this.runCounter = 0;
    this.activeRunBlock = null;
    this.activeRunStartTime = null;
    this.activeMsgFilter = 'all';
    this.totalMsgCounts = { all: 0, error: 0, warning: 0, info: 0 };

    this.initEvents();
  }

  initEvents() {
    // Nav tabs (Data View, Profiler, Interactive Charts, Messages)
    document.querySelectorAll('.results-tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.results-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        tab.classList.add('active');
        const tabId = tab.dataset.tab;
        this.currentTab = tabId;
        const targetPane = document.getElementById(`tab-${tabId}`);
        if (targetPane) targetPane.classList.add('active');

        if (tabId === 'profile-view' && this.currentNodeId) {
          this.loadProfiling(this.currentNodeId, this.currentPort);
        } else if (tabId === 'chart-view' && this.currentNodeId) {
          this.initChartTab(this.currentNodeId, this.currentPort);
        }
      });
    });

    // Pagination
    document.getElementById('btn-page-prev').addEventListener('click', () => {
      if (this.currentPage > 1) {
        this.currentPage--;
        this.loadData(this.currentNodeId, this.currentPort);
      }
    });

    document.getElementById('btn-page-next').addEventListener('click', () => {
      this.currentPage++;
      this.loadData(this.currentNodeId, this.currentPort);
    });

    // Search filter in grid
    let searchTimeout = null;
    this.searchInput.addEventListener('input', (e) => {
      clearTimeout(searchTimeout);
      searchTimeout = setTimeout(() => {
        this.searchQuery = e.target.value;
        this.currentPage = 1;
        this.loadData(this.currentNodeId, this.currentPort);
      }, 250);
    });

    // Toggle histograms button
    const toggleHistBtn = document.getElementById('btn-toggle-histograms');
    if (toggleHistBtn) {
      toggleHistBtn.classList.toggle('active', this.showHistograms);
      toggleHistBtn.addEventListener('click', () => {
        this.showHistograms = !this.showHistograms;
        localStorage.setItem('dataflow_show_histograms', this.showHistograms);
        toggleHistBtn.classList.toggle('active', this.showHistograms);
        if (this.gridWrapper) {
          this.gridWrapper.classList.toggle('hide-histograms', !this.showHistograms);
        }
        const checkHist = document.getElementById('check-view-histograms');
        if (checkHist) checkHist.textContent = this.showHistograms ? '✓' : '';
      });
    }

    // Toggle collapse
    document.getElementById('btn-toggle-results').addEventListener('click', () => {
      this.panel.classList.toggle('collapsed');
    });

    // Export dropdown
    const exportBtn = document.getElementById('btn-export-dropdown');
    const exportMenu = document.getElementById('export-menu');
    exportBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      exportMenu.classList.toggle('show');
    });

    window.addEventListener('click', () => {
      exportMenu.classList.remove('show');
    });

    document.getElementById('btn-export-csv').addEventListener('click', () => {
      if (this.currentNodeId) {
        const node = window.appCanvas ? window.appCanvas.nodes.find(n => n.id === this.currentNodeId) : null;
        const nodeName = node ? (node.name || node.type) : this.currentNodeId;
        const filename = `${nodeName.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}_export.csv`;
        let url = `/api/export/${this.currentNodeId}?port=${this.currentPort}&format=csv&filename=${encodeURIComponent(filename)}`;
        if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
        if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
        window.location.href = url;
      }
    });

    document.getElementById('btn-export-excel').addEventListener('click', () => {
      if (this.currentNodeId) {
        const node = window.appCanvas ? window.appCanvas.nodes.find(n => n.id === this.currentNodeId) : null;
        const nodeName = node ? (node.name || node.type) : this.currentNodeId;
        const filename = `${nodeName.toLowerCase().replace(/[^a-z0-9_-]/g, '_')}_export.xlsx`;
        let url = `/api/export/${this.currentNodeId}?port=${this.currentPort}&format=excel&filename=${encodeURIComponent(filename)}`;
        if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
        if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
        window.location.href = url;
      }
    });

    // Copy table or selected cells to clipboard
    const copyBtn = document.getElementById('btn-copy-table');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        if (this.selectedCells.size > 0) {
          this.copySelectedCells(false);
        } else {
          this.copyEntireTable();
        }
      });
    }

    // Chart builder controls
    if (this.chartTypeSelect) {
      this.chartTypeSelect.addEventListener('change', () => {
        this.updateChartControlsVisibility();
        this.loadChartData();
      });
    }
    if (this.chartXSelect) {
      this.chartXSelect.addEventListener('change', () => this.loadChartData());
    }
    if (this.chartYSelect) {
      this.chartYSelect.addEventListener('change', () => this.loadChartData());
    }
    if (this.chartAggSelect) {
      this.chartAggSelect.addEventListener('change', () => this.loadChartData());
    }

    // Chart export buttons
    const btnPng = document.getElementById('btn-chart-export-png');
    if (btnPng) btnPng.addEventListener('click', () => this.exportChartPNG());

    const btnSvg = document.getElementById('btn-chart-export-svg');
    if (btnSvg) btnSvg.addEventListener('click', () => this.exportChartSVG());

    const btnCopy = document.getElementById('btn-chart-copy-clipboard');
    if (btnCopy) btnCopy.addEventListener('click', () => this.copyChartToClipboard());

    const btnCsv = document.getElementById('btn-chart-export-csv');
    if (btnCsv) btnCsv.addEventListener('click', () => this.exportChartCSV());

    // Toggle column explorer popover
    const toggleColsBtn = document.getElementById('btn-toggle-columns');
    if (toggleColsBtn) {
      toggleColsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.toggleColumnExplorer(toggleColsBtn);
      });
    }

    // Messages toolbar filters & actions
    document.querySelectorAll('.messages-filter-group [data-msg-filter]').forEach(btn => {
      btn.addEventListener('click', () => {
        this.filterMessages(btn.dataset.msgFilter);
      });
    });

    const btnClearMsg = document.getElementById('btn-clear-messages');
    if (btnClearMsg) {
      btnClearMsg.addEventListener('click', () => this.clearMessagesLog());
    }

    const btnCopyMsg = document.getElementById('btn-copy-messages');
    if (btnCopyMsg) {
      btnCopyMsg.addEventListener('click', () => this.copyMessagesLog());
    }

    // Dismiss popovers & context menu on outside click or scroll
    document.addEventListener('click', (e) => {
      if (this.activeQuickfilterPopover && !this.activeQuickfilterPopover.contains(e.target)) {
        this.closeQuickfilterPopover();
      }
      if (this.activeColumnExplorer && !this.activeColumnExplorer.contains(e.target) && (!toggleColsBtn || !toggleColsBtn.contains(e.target))) {
        this.closeColumnExplorer();
      }
      this.closeContextMenu();
    });

    if (this.gridWrapper) {
      this.gridWrapper.addEventListener('scroll', () => this.closeContextMenu());
    }

    // Stop drag selection on mouseup anywhere
    document.addEventListener('mouseup', () => {
      this.isSelecting = false;
    });

    // Keyboard shortcuts: Ctrl+C for cell copy, Escape to clear, Ctrl+A to select all
    document.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      if (activeTag === 'input' || activeTag === 'textarea' || (document.activeElement && document.activeElement.isContentEditable)) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'c') {
        if (this.selectedCells.size > 0) {
          const sel = window.getSelection();
          if (!sel || sel.isCollapsed || !this.gridWrapper.contains(sel.anchorNode)) {
            e.preventDefault();
            this.copySelectedCells(e.shiftKey);
          }
        }
      } else if (e.key === 'Escape') {
        if (this.selectedCells.size > 0) {
          this.clearCellSelection();
        }
        this.closeContextMenu();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
        if (this.gridWrapper && (this.gridWrapper.matches(':hover') || this.selectedCells.size > 0)) {
          e.preventDefault();
          this.selectAllCells();
        }
      }
    });
  }

  clear() {
    this.currentNodeId = null;
    this.currentPort = 'O';
    this.currentPage = 1;
    this.searchQuery = '';
    if (this.searchInput) this.searchInput.value = '';
    if (this.nodeBadge) this.nodeBadge.textContent = 'No tool selected';
    if (this.portTabsContainer) this.portTabsContainer.innerHTML = '';
    if (this.recordCountText) this.recordCountText.textContent = '0 records';
    if (this.paginationText) this.paginationText.textContent = 'Page 1 of 1';
    if (this.gridWrapper) this.gridWrapper.innerHTML = `<div class="results-empty-msg">Run workflow to view records.</div>`;
    if (this.profilerContainer) this.profilerContainer.innerHTML = `<div class="results-empty-msg">Select a tool to view profiling.</div>`;
    if (this.chartViewport) this.chartViewport.innerHTML = `<div class="results-empty-msg">Select a tool to render interactive charts.</div>`;
    if (this.partialBanner) {
      this.partialBanner.style.display = 'none';
      this.partialBanner.innerHTML = '';
    }
    this.closeColumnExplorer();
    this.clearCellSelection();
    this.closeContextMenu();
    const colsBtnLabel = document.getElementById('columns-btn-label');
    if (colsBtnLabel) colsBtnLabel.textContent = 'Columns';
    this.lastRenderedData = null;
    this.lastChartData = null;
    this.closeQuickfilterPopover();
  }

  setPageSize(newSize) {
    const parsed = parseInt(newSize, 10);
    if (!parsed || parsed <= 0) return;
    this.pageSize = parsed;
    localStorage.setItem('dataflow_page_size', this.pageSize);
    this.currentPage = 1;
    if (this.currentNodeId) {
      this.loadData(this.currentNodeId, this.currentPort);
    }
  }

  showNodeResults(node, port = null) {
    this.currentNodeId = node ? node.id : null;
    this.currentPage = 1;
    this.searchQuery = '';
    if (this.searchInput) this.searchInput.value = '';

    if (!node) {
      this.clear();
      return;
    }

    const meta = window.appCanvas.toolRegistry[node.type] || { outputs: ['O'] };
    const outputs = meta.outputs || ['O'];

    // Select default port
    this.currentPort = port || outputs[0];

    // Render port switcher tabs if tool has multiple outputs (like Filter or Join)
    this.renderPortTabs(outputs);

    if (node && node.type === 'browse') {
      this.nodeBadge.innerHTML = `<span class="browse-inspector-badge" title="Browse Tool: Deep Dataset Profiling Active"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> Browse: Full Inspector</span> <span>${this.escapeHtml(node.name || 'Browse')}</span>`;
    } else {
      this.nodeBadge.textContent = `${node.name}`;
    }

    // Load data & profiling
    this.loadData(this.currentNodeId, this.currentPort);
    if (this.currentTab === 'profile-view') {
      this.loadProfiling(this.currentNodeId, this.currentPort);
    } else if (this.currentTab === 'chart-view') {
      this.initChartTab(this.currentNodeId, this.currentPort);
    }
  }

  renderPortTabs(outputs) {
    this.portTabsContainer.innerHTML = '';
    if (outputs.length <= 1) return;

    outputs.forEach(p => {
      const btn = document.createElement('button');
      btn.className = `port-tab ${p === this.currentPort ? 'active' : ''}`;
      btn.textContent = this.getPortDisplayLabel(p);
      btn.addEventListener('click', () => {
        this.portTabsContainer.querySelectorAll('.port-tab').forEach(t => t.classList.remove('active'));
        btn.classList.add('active');
        this.currentPort = p;
        this.currentPage = 1;
        this.loadData(this.currentNodeId, this.currentPort);
        if (this.currentTab === 'profile-view') {
          this.loadProfiling(this.currentNodeId, this.currentPort);
        } else if (this.currentTab === 'chart-view') {
          this.initChartTab(this.currentNodeId, this.currentPort);
        }
      });
      this.portTabsContainer.appendChild(btn);
    });
  }

  getPortDisplayLabel(port) {
    switch (port) {
      case 'T': return 'True (T)';
      case 'F': return 'False (F)';
      case 'J': return 'Joined (J)';
      case 'L': return 'Left Unmatched (L)';
      case 'R': return 'Right Unmatched (R)';
      case 'U': return 'Unique (U)';
      case 'D': return 'Duplicates (D)';
      default: return `Output (${port})`;
    }
  }

  async safeFetchJson(url) {
    const res = await fetch(url);
    const contentType = res.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
      const text = await res.text().catch(() => '');
      throw new Error(`Server returned HTTP ${res.status}: ${text.slice(0, 100) || 'Non-JSON response'}`);
    }
    return await res.json();
  }

  async loadData(nodeId, port) {
    if (!nodeId) return;

    this.gridWrapper.innerHTML = `<div class="results-empty-msg">Loading data...</div>`;

    try {
      let url = `/api/node-data/${nodeId}?port=${port}&page=${this.currentPage}&page_size=${this.pageSize}&search=${encodeURIComponent(this.searchQuery)}&sample_mode=${encodeURIComponent(this.sampleMode)}`;
      if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
      if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
      const data = await this.safeFetchJson(url);

      if (!data.available) {
        this.gridWrapper.innerHTML = `<div class="results-empty-msg">${data.message || 'No records cached for this output port. Run workflow first.'}</div>`;
        this.recordCountText.textContent = '0 records';
        this.paginationText.textContent = 'Page 1 of 1';
        if (this.partialBanner) this.partialBanner.style.display = 'none';
        return;
      }

      this.renderGrid(data);
      if (this.currentTab === 'chart-view') {
        this.updateChartColumns();
      }
    } catch (err) {
      this.gridWrapper.innerHTML = `<div class="results-empty-msg" style="color: var(--color-error)">Error loading data: ${err.message}</div>`;
      if (this.partialBanner) this.partialBanner.style.display = 'none';
    }
  }

  renderGrid(data) {
    this.lastRenderedData = data;
    this.closeQuickfilterPopover();
    const { columns, records, pagination, is_partial, is_wide_table, memory_formatted } = data;
    const total = pagination.total_records;

    const selNode = (window.appCanvas && this.currentNodeId) ? window.appCanvas.nodes.find(n => n.id === this.currentNodeId) : null;
    const isBrowse = selNode && selNode.type === 'browse';
    const isJoinNode = selNode && selNode.type === 'join';
    const isMultiJoin = selNode && (selNode.type === 'join_multiple' || selNode.type === 'multi_join');

    // Update node badge if browse
    if (isBrowse) {
      this.nodeBadge.innerHTML = `<span class="browse-inspector-badge" title="Browse Tool: Deep Dataset Profiling Active"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg> Browse: Full Inspector</span> <span>${this.escapeHtml(selNode.name || 'Browse')}</span>`;
    } else {
      this.nodeBadge.textContent = selNode ? (selNode.name || selNode.type) : 'No tool selected';
    }

    // Filter visible columns based on hiddenColumns
    const visibleColumns = columns.filter(c => !this.hiddenColumns.has(c.name));
    const activeColumns = visibleColumns.length > 0 ? visibleColumns : columns; // Fallback if all hidden
    this.activeColumns = activeColumns;
    this.clearCellSelection();

    // Update toolbar record count and column count
    const memInfo = memory_formatted ? ` | ~${memory_formatted}` : '';
    this.recordCountText.textContent = `${total.toLocaleString()} records | ${activeColumns.length} of ${columns.length} columns${memInfo}`;

    if (this.sampleMode === 'random') {
      this.paginationText.textContent = `Random Sample (${records.length} records)`;
    } else if (this.sampleMode === 'head') {
      this.paginationText.textContent = `First ${records.length} records`;
    } else {
      this.paginationText.textContent = `Page ${pagination.page} of ${pagination.total_pages}`;
    }

    const colsBtnLabel = document.getElementById('columns-btn-label');
    if (colsBtnLabel) {
      colsBtnLabel.textContent = `Columns (${activeColumns.length}/${columns.length})`;
    }

    // Render Alteryx-style Partial Results & Sample Mode Banner
    this.renderPartialBanner(data, isBrowse);

    if (records.length === 0) {
      this.gridWrapper.innerHTML = `<div class="results-empty-msg">No records match the current view.</div>`;
      return;
    }

    const startRow = (pagination.page - 1) * pagination.page_size;

    let html = `
      <table class="data-table">
        <thead>
          <tr>
            <th class="th-select-all" style="width: 40px; text-align: right; cursor: pointer;" title="Click to select all cells">#</th>
            ${activeColumns.map((c, colIdx) => {
              const q = c.quality || { ok_pct: 100, null_pct: 0, blank_pct: 0, ok_count: 0, null_count: 0, blank_count: 0 };
              const hist = c.histogram || [];
              const maxHistCount = hist.length > 0 ? Math.max(...hist.map(b => b.count), 1) : 1;

              let joinThClass = '';
              let joinThTitle = '';
              let inputPillHtml = '';

              if (isMultiJoin) {
                let inputIdx = 1;
                if (c.source !== undefined && c.source !== null) {
                  inputIdx = parseInt(c.source) || 1;
                } else if (data.column_sources && data.column_sources[c.name] !== undefined) {
                  inputIdx = parseInt(data.column_sources[c.name]) || 1;
                } else {
                  const selectFields = (selNode.config && selNode.config.select_fields) || [];
                  const matchSf = selectFields.find(sf => (sf.rename || sf.field || sf.original) === c.name || (sf.field || sf.original) === c.name);
                  if (matchSf && matchSf.source) {
                    inputIdx = parseInt(matchSf.source) || 1;
                  } else {
                    const m = c.name.match(/^(?:Input|#)(\d+)_/i);
                    if (m) inputIdx = parseInt(m[1]) || 1;
                  }
                }
                const colorIdx = ((inputIdx - 1) % 6) + 1;
                joinThClass = `join-th-input-${colorIdx}`;
                joinThTitle = `Source: Input #${inputIdx} Table`;
                inputPillHtml = `<span class="th-input-source-pill source-input-${colorIdx}" title="Origin: Table #${inputIdx}">#${inputIdx}</span>`;
              } else if (isJoinNode) {
                let src = 'L';
                if (this.currentPort === 'R') {
                  src = 'R';
                } else if (this.currentPort === 'L') {
                  src = 'L';
                } else {
                  const selectFields = (selNode.config && (selNode.config.select_fields || selNode.config.output_fields)) || [];
                  const matchSf = selectFields.find(sf => (sf.rename || sf.field || sf.original) === c.name || (sf.field || sf.original) === c.name);
                  if (matchSf && matchSf.source) {
                    src = matchSf.source;
                  } else if (c.name.startsWith('Right_')) {
                    src = 'R';
                  }
                }
                joinThClass = src === 'R' ? 'join-th-r' : 'join-th-l';
                joinThTitle = `Source: ${src === 'R' ? 'Right Table (R)' : 'Left Table (L)'}`;
              }

              return `<th class="${joinThClass}" data-col-idx="${colIdx}" data-col-name="${this.escapeHtml(c.name)}" ${joinThTitle ? `title="${joinThTitle}"` : ''}>
                <div class="col-quality-bar" title="OK: ${q.ok_pct}% (${q.ok_count || 0}) | Null: ${q.null_pct}% (${q.null_count || 0}) | Empty: ${q.blank_pct}% (${q.blank_count || 0})">
                  <div class="quality-seg seg-ok" data-col="${this.escapeHtml(c.name)}" data-seg="ok" style="width: ${q.ok_pct}%" title="Valid / OK: ${q.ok_pct}% (${q.ok_count || 0})"></div>
                  <div class="quality-seg seg-null" data-col="${this.escapeHtml(c.name)}" data-seg="null" style="width: ${q.null_pct}%" title="Null: ${q.null_pct}% (${q.null_count || 0})"></div>
                  <div class="quality-seg seg-empty" data-col="${this.escapeHtml(c.name)}" data-seg="empty" style="width: ${q.blank_pct}%" title="Empty / Blank: ${q.blank_pct}% (${q.blank_count || 0})"></div>
                </div>
                <div class="th-content">
                  <span class="th-name" title="${this.escapeHtml(c.name)} (Click to select column)">${inputPillHtml}${this.escapeHtml(c.name)}</span>
                  <span class="th-dtype">${this.formatAlteryxTypeBadge(c.dtype)}</span>
                </div>
                ${hist.length > 0 ? `
                  <div class="col-hist-sparkline" title="Distribution for ${this.escapeHtml(c.name)}">
                    ${hist.map((b, bIdx) => {
                      const hPct = Math.max(14, Math.round((b.count / maxHistCount) * 100));
                      const label = this.escapeHtml(b.label || String(b.value || ''));
                      return `<div class="col-hist-bar" data-col="${this.escapeHtml(c.name)}" data-bin-idx="${bIdx}" style="height: ${hPct}%;" title="${label}: ${b.count} (${b.percent}%)"></div>`;
                    }).join('')}
                  </div>
                ` : ''}
              </th>`;
            }).join('')}
          </tr>
        </thead>
        <tbody>
    `;

    records.forEach((row, i) => {
      const rowNum = this.sampleMode === 'page' ? (startRow + i + 1) : (i + 1);
      html += `<tr><td class="row-num" data-row-idx="${i}" title="Click to select row">${rowNum}</td>`;
      activeColumns.forEach((c, cIdx) => {
        const val = row[c.name];
        if (val === null || val === undefined) {
          html += `<td class="cell-null" data-row-idx="${i}" data-col-idx="${cIdx}" data-col="${this.escapeAttr(c.name)}">null</td>`;
        } else {
          const strVal = String(val);
          if (strVal.length > 200) {
            const truncated = strVal.slice(0, 200) + '…';
            html += `<td class="cell-truncated" data-row-idx="${i}" data-col-idx="${cIdx}" data-full="${this.escapeAttr(strVal)}" data-col="${this.escapeAttr(c.name)}" data-row="${rowNum}" title="${this.escapeAttr(strVal.slice(0, 500))} (Double-click to expand)">${this.escapeHtml(truncated)}</td>`;
          } else {
            html += `<td data-row-idx="${i}" data-col-idx="${cIdx}" data-col="${this.escapeAttr(c.name)}">${this.escapeHtml(strVal)}</td>`;
          }
        }
      });
      html += `</tr>`;
    });

    html += `</tbody></table>`;
    this.gridWrapper.innerHTML = html;
    this.gridWrapper.classList.toggle('hide-histograms', !this.showHistograms);

    const toggleHistBtn = document.getElementById('btn-toggle-histograms');
    if (toggleHistBtn) {
      toggleHistBtn.classList.toggle('active', this.showHistograms);
    }

    // Attach listeners for quality bar, histogram sparkline bars, and truncated cells
    this.attachGridListeners(activeColumns);
  }

  renderPartialBanner(data, isBrowse) {
    if (!this.partialBanner) return;
    const { pagination, records, memory_formatted, is_wide_table, columns } = data;
    const total = pagination.total_records || 0;
    const rendered = records.length;
    const isPartial = total > rendered;

    if (!isPartial && !is_wide_table && !isBrowse) {
      this.partialBanner.style.display = 'none';
      this.partialBanner.innerHTML = '';
      return;
    }

    this.partialBanner.style.display = 'flex';
    const memStr = memory_formatted ? ` (~${memory_formatted})` : '';
    const wideBadge = is_wide_table ? `<span class="partial-banner-badge wide-table" title="Table has ${columns.length} columns. Use Columns button to hide fields and optimize layout.">Wide Table (${columns.length} cols)</span>` : '';
    const browseBadge = isBrowse ? `<span class="partial-banner-badge" style="background:rgba(139,92,246,0.15);color:#c4b5fd;">Browse Tool</span>` : '';

    let statusText = '';
    if (this.sampleMode === 'random') {
      statusText = `<strong>Random Sample:</strong> Displaying ${rendered} randomly sampled records of ${total.toLocaleString()}${memStr}. Full dataset processed by engine.`;
    } else if (this.sampleMode === 'head') {
      statusText = `<strong>First N Records:</strong> Displaying first ${rendered} records of ${total.toLocaleString()}${memStr}.`;
    } else if (isPartial) {
      statusText = `<strong>Partial results displayed:</strong> Showing ${rendered} records of ${total.toLocaleString()}${memStr}. Use pagination or Browse tool for full inspection.`;
    } else {
      statusText = `Complete dataset view: ${total.toLocaleString()} records${memStr}.`;
    }

    this.partialBanner.innerHTML = `
      <div class="partial-banner-left">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <span>${statusText}</span>
        ${wideBadge}
        ${browseBadge}
      </div>
      <div class="partial-banner-right">
        <span class="sample-mode-label">Mode:</span>
        <div class="btn-group-sm">
          <button class="btn ${this.sampleMode === 'page' ? 'active' : ''}" data-sample-mode="page" title="Sequential pagination (standard)">Pages</button>
          <button class="btn ${this.sampleMode === 'random' ? 'active' : ''}" data-sample-mode="random" title="Random representative sample of rows">Random</button>
          <button class="btn ${this.sampleMode === 'head' ? 'active' : ''}" data-sample-mode="head" title="First N rows">First N</button>
        </div>
        ${!isBrowse ? `<button class="btn-browse-tip" id="btn-banner-browse-tip" title="Switch to Profiler tab for full column statistics">📊 Profile</button>` : ''}
      </div>
    `;

    // Bind mode buttons
    this.partialBanner.querySelectorAll('[data-sample-mode]').forEach(b => {
      b.addEventListener('click', (e) => {
        const mode = e.currentTarget.dataset.sampleMode;
        if (mode !== this.sampleMode) {
          this.setSampleMode(mode);
        }
      });
    });

    const profilerTipBtn = this.partialBanner.querySelector('#btn-banner-browse-tip');
    if (profilerTipBtn) {
      profilerTipBtn.addEventListener('click', () => {
        const profilerTab = document.querySelector('.results-tab[data-tab="profile-view"]');
        if (profilerTab) profilerTab.click();
      });
    }
  }

  setSampleMode(mode) {
    this.sampleMode = mode;
    this.currentPage = 1;
    if (this.currentNodeId) {
      this.loadData(this.currentNodeId, this.currentPort);
    }
  }

  attachGridListeners(activeColumns) {
    // Quality bar segments
    this.gridWrapper.querySelectorAll('.quality-seg').forEach(seg => {
      seg.addEventListener('click', (e) => {
        e.stopPropagation();
        const colName = seg.dataset.col;
        const segType = seg.dataset.seg;
        this.openQualityQuickfilter(colName, segType, e.clientX, e.clientY);
      });
    });

    // Histogram sparkline bars
    this.gridWrapper.querySelectorAll('.col-hist-bar').forEach(bar => {
      bar.addEventListener('click', (e) => {
        e.stopPropagation();
        const colName = bar.dataset.col;
        const binIdx = parseInt(bar.dataset.binIdx, 10);
        const colMeta = activeColumns.find(c => c.name === colName);
        const bin = colMeta && colMeta.histogram ? colMeta.histogram[binIdx] : null;
        if (bin) {
          this.openHistogramQuickfilter(colName, bin, e.clientX, e.clientY);
        }
      });
    });

    // Truncated cell double-click to view complete text
    this.gridWrapper.querySelectorAll('td.cell-truncated').forEach(td => {
      td.addEventListener('dblclick', (e) => {
        e.stopPropagation();
        const full = td.dataset.full;
        const colName = td.dataset.col || 'Cell';
        const rowNum = td.dataset.row || '1';
        this.showCellContentModal(full, colName, rowNum);
      });
    });

    // Cell Selection & Drag Range
    this.gridWrapper.querySelectorAll('td[data-col-idx]').forEach(td => {
      const r = parseInt(td.dataset.rowIdx, 10);
      const c = parseInt(td.dataset.colIdx, 10);

      td.addEventListener('mousedown', (e) => {
        if (e.button === 2) {
          // Right-click: preserve selection if clicking inside already-selected cell
          const key = `${r}:${c}`;
          if (!this.selectedCells.has(key)) {
            this.clearCellSelection();
            this.selectionAnchor = { r, c };
            this.selectCellRange(r, c, r, c);
          }
          return;
        }

        if (e.button !== 0) return;

        if (e.shiftKey && this.selectionAnchor) {
          e.preventDefault();
          this.selectCellRange(this.selectionAnchor.r, this.selectionAnchor.c, r, c);
        } else if (e.ctrlKey || e.metaKey) {
          e.preventDefault();
          this.selectionAnchor = { r, c };
          this.toggleCellSelection(r, c);
        } else {
          this.isSelecting = true;
          this.selectionAnchor = { r, c };
          this.selectCellRange(r, c, r, c);
        }
      });

      td.addEventListener('mouseenter', () => {
        if (this.isSelecting && this.selectionAnchor) {
          window.getSelection()?.removeAllRanges();
          this.selectCellRange(this.selectionAnchor.r, this.selectionAnchor.c, r, c);
        }
      });

      td.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.openContextMenu(e.clientX, e.clientY, r, c, td);
      });
    });

    // Row selection on row number click
    this.gridWrapper.querySelectorAll('td.row-num[data-row-idx]').forEach(td => {
      td.addEventListener('click', (e) => {
        e.stopPropagation();
        const r = parseInt(td.dataset.rowIdx, 10);
        this.selectRow(r);
      });
    });

    // Column selection on column header click
    this.gridWrapper.querySelectorAll('th[data-col-idx]').forEach(th => {
      th.addEventListener('click', (e) => {
        if (e.target.closest('.col-quality-bar') || e.target.closest('.col-hist-sparkline')) {
          return;
        }
        e.stopPropagation();
        const c = parseInt(th.dataset.colIdx, 10);
        this.selectColumn(c);
      });
    });

    // Select all on table top-left corner '#' click
    const thSelectAll = this.gridWrapper.querySelector('th.th-select-all');
    if (thSelectAll) {
      thSelectAll.addEventListener('click', (e) => {
        e.stopPropagation();
        this.selectAllCells();
      });
    }
  }

  clearCellSelection() {
    this.selectedCells.clear();
    this.selectionAnchor = null;
    this.isSelecting = false;
    if (this.gridWrapper) {
      this.gridWrapper.querySelectorAll('.cell-selected, .cell-focus').forEach(el => {
        el.classList.remove('cell-selected', 'cell-focus');
      });
    }
    this.updateCopyButtonLabel();
  }

  selectCellRange(r1, c1, r2, c2, addToExisting = false) {
    if (!this.lastRenderedData || !this.lastRenderedData.records) return;
    const records = this.lastRenderedData.records;
    const maxRow = records.length - 1;
    const maxCol = (this.activeColumns && this.activeColumns.length > 0) ? this.activeColumns.length - 1 : 0;

    const minR = Math.max(0, Math.min(r1, r2));
    const maxR = Math.min(maxRow, Math.max(r1, r2));
    const minC = Math.max(0, Math.min(c1, c2));
    const maxC = Math.min(maxCol, Math.max(c1, c2));

    if (!addToExisting) {
      this.selectedCells.clear();
      this.gridWrapper.querySelectorAll('.cell-selected, .cell-focus').forEach(el => {
        el.classList.remove('cell-selected', 'cell-focus');
      });
    }

    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        this.selectedCells.add(`${r}:${c}`);
        const td = this.gridWrapper.querySelector(`td[data-row-idx="${r}"][data-col-idx="${c}"]`);
        if (td) td.classList.add('cell-selected');
      }
    }

    if (this.selectionAnchor) {
      const anchorTd = this.gridWrapper.querySelector(`td[data-row-idx="${this.selectionAnchor.r}"][data-col-idx="${this.selectionAnchor.c}"]`);
      if (anchorTd) anchorTd.classList.add('cell-focus');
    }

    this.updateCopyButtonLabel();
  }

  toggleCellSelection(r, c) {
    const key = `${r}:${c}`;
    const td = this.gridWrapper.querySelector(`td[data-row-idx="${r}"][data-col-idx="${c}"]`);
    if (this.selectedCells.has(key)) {
      this.selectedCells.delete(key);
      if (td) td.classList.remove('cell-selected', 'cell-focus');
    } else {
      this.selectedCells.add(key);
      if (td) td.classList.add('cell-selected');
    }
    this.updateCopyButtonLabel();
  }

  selectRow(rowIdx) {
    if (!this.lastRenderedData || !this.lastRenderedData.records) return;
    const colCount = (this.activeColumns && this.activeColumns.length > 0) ? this.activeColumns.length : 1;
    this.selectionAnchor = { r: rowIdx, c: 0 };
    this.selectCellRange(rowIdx, 0, rowIdx, colCount - 1);
  }

  selectColumn(colIdx) {
    if (!this.lastRenderedData || !this.lastRenderedData.records) return;
    this.selectionAnchor = { r: 0, c: colIdx };
    this.selectCellRange(0, colIdx, this.lastRenderedData.records.length - 1, colIdx);
  }

  selectAllCells() {
    if (!this.lastRenderedData || !this.lastRenderedData.records || this.lastRenderedData.records.length === 0) return;
    const colCount = (this.activeColumns && this.activeColumns.length > 0) ? this.activeColumns.length : 1;
    this.selectionAnchor = { r: 0, c: 0 };
    this.selectCellRange(0, 0, this.lastRenderedData.records.length - 1, colCount - 1);
  }

  updateCopyButtonLabel() {
    const copyBtn = document.getElementById('btn-copy-table');
    if (!copyBtn) return;
    const labelSpan = copyBtn.querySelector('span');
    const count = this.selectedCells.size;

    if (count === 0) {
      if (labelSpan) labelSpan.textContent = 'Copy';
      copyBtn.title = 'Copy current table data to clipboard as TSV';
    } else if (count === 1) {
      if (labelSpan) labelSpan.textContent = 'Copy Cell';
      copyBtn.title = 'Copy selected cell to clipboard';
    } else {
      if (labelSpan) labelSpan.textContent = `Copy (${count})`;
      copyBtn.title = `Copy ${count} selected cells to clipboard as TSV`;
    }
  }

  formatTsvCell(val) {
    if (val === null || val === undefined) return '';
    const s = String(val);
    if (s.includes('\t') || s.includes('\n') || s.includes('"')) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  }

  copySelectedCells(withHeaders = false) {
    if (this.selectedCells.size === 0) {
      this.copyEntireTable();
      return;
    }
    if (!this.lastRenderedData || !this.lastRenderedData.records) return;

    const records = this.lastRenderedData.records;
    const activeCols = this.activeColumns && this.activeColumns.length > 0 ? this.activeColumns : (this.lastRenderedData.columns || []);

    let minR = Infinity, maxR = -Infinity;
    let minC = Infinity, maxC = -Infinity;

    for (const key of this.selectedCells) {
      const [rStr, cStr] = key.split(':');
      const r = parseInt(rStr, 10);
      const c = parseInt(cStr, 10);
      if (r < minR) minR = r;
      if (r > maxR) maxR = r;
      if (c < minC) minC = c;
      if (c > maxC) maxC = c;
    }

    const rows = [];

    if (withHeaders) {
      const headerRow = [];
      for (let c = minC; c <= maxC; c++) {
        const col = activeCols[c];
        headerRow.push(col ? this.formatTsvCell(col.name) : '');
      }
      rows.push(headerRow.join('\t'));
    }

    for (let r = minR; r <= maxR; r++) {
      const rowVals = [];
      const rec = records[r] || {};
      for (let c = minC; c <= maxC; c++) {
        if (this.selectedCells.has(`${r}:${c}`)) {
          const col = activeCols[c];
          const val = col ? rec[col.name] : '';
          rowVals.push(this.formatTsvCell(val));
        } else {
          rowVals.push('');
        }
      }
      rows.push(rowVals.join('\t'));
    }

    const tsv = rows.join('\n');
    navigator.clipboard.writeText(tsv).then(() => {
      const cellCount = this.selectedCells.size;
      const msg = cellCount === 1 
        ? 'Cell copied to clipboard.' 
        : `${cellCount} cells copied to clipboard as TSV.`;
      if (window.showToast) {
        window.showToast('success', 'Copied', msg);
      }
    }).catch(err => {
      console.error('Clipboard copy failed:', err);
      if (window.showToast) {
        window.showToast('error', 'Copy Failed', 'Could not copy to clipboard.');
      }
    });
  }

  copyEntireTable() {
    if (!this.lastRenderedData || !this.lastRenderedData.records) return;
    const records = this.lastRenderedData.records;
    const activeCols = this.activeColumns && this.activeColumns.length > 0 ? this.activeColumns : (this.lastRenderedData.columns || []);

    if (records.length === 0) {
      if (window.showToast) window.showToast('info', 'Copy', 'No records to copy.');
      return;
    }

    const header = activeCols.map(c => this.formatTsvCell(c.name)).join('\t');
    const rows = records.map(r => activeCols.map(c => this.formatTsvCell(r[c.name])).join('\t'));
    const tsv = [header, ...rows].join('\n');

    navigator.clipboard.writeText(tsv).then(() => {
      if (window.showToast) {
        window.showToast('success', 'Copied', `Copied table (${records.length} rows) to clipboard.`);
      }
    }).catch(err => {
      console.error('Clipboard copy failed:', err);
      if (window.showToast) {
        window.showToast('error', 'Copy Failed', 'Could not copy to clipboard.');
      }
    });
  }

  openContextMenu(x, y, r, c, targetTd) {
    this.closeContextMenu();

    const key = `${r}:${c}`;
    if (!this.selectedCells.has(key)) {
      this.clearCellSelection();
      this.selectionAnchor = { r, c };
      this.selectCellRange(r, c, r, c);
    }

    const menu = document.createElement('div');
    menu.className = 'grid-context-menu';

    const isTruncated = targetTd && targetTd.classList.contains('cell-truncated');
    const fullText = isTruncated ? targetTd.dataset.full : (targetTd ? targetTd.textContent : '');
    const colName = targetTd ? (targetTd.dataset.col || '') : '';
    const rowNum = targetTd ? (targetTd.dataset.row || String(r + 1)) : String(r + 1);

    menu.innerHTML = `
      <button class="grid-context-menu-item" id="ctx-copy">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
        <span>Copy</span>
        <span class="menu-shortcut">Ctrl+C</span>
      </button>
      <button class="grid-context-menu-item" id="ctx-copy-headers">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
        <span>Copy with Headers</span>
        <span class="menu-shortcut">Ctrl+Shift+C</span>
      </button>
      <div class="grid-context-menu-divider"></div>
      <button class="grid-context-menu-item" id="ctx-select-row">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline></svg>
        <span>Select Row</span>
      </button>
      <button class="grid-context-menu-item" id="ctx-select-col">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><polyline points="5 12 12 19 19 12"></polyline></svg>
        <span>Select Column</span>
      </button>
      <button class="grid-context-menu-item" id="ctx-select-all">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect></svg>
        <span>Select All</span>
        <span class="menu-shortcut">Ctrl+A</span>
      </button>
      ${isTruncated ? `
        <div class="grid-context-menu-divider"></div>
        <button class="grid-context-menu-item" id="ctx-view-full">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <span>View Complete Text...</span>
        </button>
      ` : ''}
    `;

    document.body.appendChild(menu);
    this.activeContextMenu = menu;

    const menuWidth = 210;
    const menuHeight = isTruncated ? 210 : 175;
    let posX = x;
    let posY = y;
    if (posX + menuWidth > window.innerWidth) posX = window.innerWidth - menuWidth - 8;
    if (posY + menuHeight > window.innerHeight) posY = window.innerHeight - menuHeight - 8;
    menu.style.left = `${Math.max(8, posX)}px`;
    menu.style.top = `${Math.max(8, posY)}px`;

    menu.querySelector('#ctx-copy')?.addEventListener('click', () => {
      this.copySelectedCells(false);
      this.closeContextMenu();
    });

    menu.querySelector('#ctx-copy-headers')?.addEventListener('click', () => {
      this.copySelectedCells(true);
      this.closeContextMenu();
    });

    menu.querySelector('#ctx-select-row')?.addEventListener('click', () => {
      this.selectRow(r);
      this.closeContextMenu();
    });

    menu.querySelector('#ctx-select-col')?.addEventListener('click', () => {
      this.selectColumn(c);
      this.closeContextMenu();
    });

    menu.querySelector('#ctx-select-all')?.addEventListener('click', () => {
      this.selectAllCells();
      this.closeContextMenu();
    });

    menu.querySelector('#ctx-view-full')?.addEventListener('click', () => {
      this.closeContextMenu();
      this.showCellContentModal(fullText, colName, rowNum);
    });
  }

  closeContextMenu() {
    if (this.activeContextMenu) {
      this.activeContextMenu.remove();
      this.activeContextMenu = null;
    }
  }

  toggleColumnExplorer(triggerBtn) {
    if (this.activeColumnExplorer) {
      this.closeColumnExplorer();
      return;
    }
    if (!this.lastRenderedData || !this.lastRenderedData.columns) return;

    const columns = this.lastRenderedData.columns;
    const popover = document.createElement('div');
    popover.className = 'column-explorer-popover';

    popover.innerHTML = `
      <div class="col-explorer-header">
        <input type="text" class="col-explorer-search" placeholder="Search columns..." autocomplete="off">
      </div>
      <div class="col-explorer-actions">
        <span>${columns.length} columns</span>
        <div>
          <button id="btn-col-select-all">Select All</button>
          <span>·</span>
          <button id="btn-col-deselect-all">Clear</button>
        </div>
      </div>
      <div class="col-explorer-list">
        ${columns.map(c => {
          const isChecked = !this.hiddenColumns.has(c.name);
          return `
            <label class="col-explorer-item" data-col="${this.escapeAttr(c.name)}">
              <input type="checkbox" data-col="${this.escapeAttr(c.name)}" ${isChecked ? 'checked' : ''}>
              <span class="col-name" title="${this.escapeAttr(c.name)}">${this.escapeHtml(c.name)}</span>
              <span class="col-type-tag">${this.escapeHtml(c.dtype || 'str')}</span>
            </label>
          `;
        }).join('')}
      </div>
    `;

    triggerBtn.parentElement.style.position = 'relative';
    triggerBtn.parentElement.appendChild(popover);
    this.activeColumnExplorer = popover;

    // Search filter
    const searchInput = popover.querySelector('.col-explorer-search');
    setTimeout(() => searchInput.focus(), 50);
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase().trim();
      popover.querySelectorAll('.col-explorer-item').forEach(item => {
        const col = item.dataset.col.toLowerCase();
        item.style.display = col.includes(q) ? 'flex' : 'none';
      });
    });

    // Select all
    popover.querySelector('#btn-col-select-all').addEventListener('click', () => {
      this.hiddenColumns.clear();
      popover.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
      this.renderGrid(this.lastRenderedData);
    });

    // Deselect all (keep at least 1 column)
    popover.querySelector('#btn-col-deselect-all').addEventListener('click', () => {
      columns.forEach((c, idx) => {
        if (idx > 0) this.hiddenColumns.add(c.name);
      });
      popover.querySelectorAll('input[type="checkbox"]').forEach((cb, idx) => {
        cb.checked = idx === 0;
      });
      this.renderGrid(this.lastRenderedData);
    });

    // Individual checkboxes
    popover.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      cb.addEventListener('change', (e) => {
        const colName = e.target.dataset.col;
        if (e.target.checked) {
          this.hiddenColumns.delete(colName);
        } else {
          if (this.hiddenColumns.size < columns.length - 1) {
            this.hiddenColumns.add(colName);
          } else {
            e.target.checked = true;
          }
        }
        this.renderGrid(this.lastRenderedData);
      });
    });
  }

  closeColumnExplorer() {
    if (this.activeColumnExplorer) {
      this.activeColumnExplorer.remove();
      this.activeColumnExplorer = null;
    }
  }

  showCellContentModal(fullText, colName, rowNum) {
    if (this.activeCellModal) {
      this.activeCellModal.remove();
      this.activeCellModal = null;
    }

    const backdrop = document.createElement('div');
    backdrop.className = 'cell-expand-modal-backdrop';

    backdrop.innerHTML = `
      <div class="cell-expand-modal">
        <div class="cell-expand-header">
          <span>Row #${rowNum} · Field: <strong>${this.escapeHtml(colName)}</strong> (${fullText.length.toLocaleString()} characters)</span>
          <button id="btn-close-cell-modal" class="modal-close-btn" style="background:none;border:none;cursor:pointer;color:var(--text-muted);font-size:16px;">✕</button>
        </div>
        <div class="cell-expand-body">${this.escapeHtml(fullText)}</div>
        <div class="cell-expand-footer">
          <button id="btn-copy-cell-content" class="btn btn-secondary btn-sm">Copy Content</button>
          <button id="btn-dismiss-cell-modal" class="btn btn-primary btn-sm">Close</button>
        </div>
      </div>
    `;

    document.body.appendChild(backdrop);
    this.activeCellModal = backdrop;

    const close = () => {
      backdrop.remove();
      this.activeCellModal = null;
    };

    backdrop.querySelector('#btn-close-cell-modal').addEventListener('click', close);
    backdrop.querySelector('#btn-dismiss-cell-modal').addEventListener('click', close);
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) close();
    });

    backdrop.querySelector('#btn-copy-cell-content').addEventListener('click', () => {
      navigator.clipboard.writeText(fullText).then(() => {
        if (window.showToast) window.showToast('success', 'Copied', 'Cell content copied to clipboard.');
      });
    });
  }

  escapeAttr(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  openQualityQuickfilter(colName, segType, clientX, clientY) {
    this.closeQuickfilterPopover();

    const popover = document.createElement('div');
    popover.className = 'grid-quickfilter-popover';
    popover.style.left = `${Math.min(window.innerWidth - 210, clientX)}px`;
    popover.style.top = `${Math.min(window.innerHeight - 140, clientY + 8)}px`;

    const label = segType === 'null' ? 'Null Values' : (segType === 'empty' ? 'Empty Values' : 'Valid (OK) Values');

    popover.innerHTML = `
      <div class="popover-title">${this.escapeHtml(colName)}: ${label}</div>
      <button id="btn-qf-grid">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <span>Filter Grid View</span>
      </button>
      <button id="btn-qf-canvas">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
        <span>Add Filter Tool to Canvas</span>
      </button>
    `;

    popover.querySelector('#btn-qf-grid').addEventListener('click', (e) => {
      e.stopPropagation();
      this.closeQuickfilterPopover();
      if (segType === 'null') {
        this.searchInput.value = 'null';
      } else if (segType === 'empty') {
        this.searchInput.value = ' ';
      } else {
        this.searchInput.value = '';
      }
      this.searchQuery = this.searchInput.value;
      this.currentPage = 1;
      this.loadData(this.currentNodeId, this.currentPort);
    });

    popover.querySelector('#btn-qf-canvas').addEventListener('click', (e) => {
      e.stopPropagation();
      this.closeQuickfilterPopover();
      this.addFilterNodeToCanvas(colName, segType);
    });

    document.body.appendChild(popover);
    this.activeQuickfilterPopover = popover;
  }

  openHistogramQuickfilter(colName, bin, clientX, clientY) {
    this.closeQuickfilterPopover();

    const popover = document.createElement('div');
    popover.className = 'grid-quickfilter-popover';
    popover.style.left = `${Math.min(window.innerWidth - 210, clientX)}px`;
    popover.style.top = `${Math.min(window.innerHeight - 140, clientY + 8)}px`;

    popover.innerHTML = `
      <div class="popover-title">${this.escapeHtml(colName)}: ${this.escapeHtml(bin.label)}</div>
      <button id="btn-qf-grid">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
        <span>Filter Grid View</span>
      </button>
      <button id="btn-qf-canvas">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
        <span>Add Filter Tool to Canvas</span>
      </button>
    `;

    popover.querySelector('#btn-qf-grid').addEventListener('click', (e) => {
      e.stopPropagation();
      this.closeQuickfilterPopover();
      const filterTerm = bin.value !== undefined ? String(bin.value) : String(bin.start);
      this.searchInput.value = filterTerm;
      this.searchQuery = filterTerm;
      this.currentPage = 1;
      this.loadData(this.currentNodeId, this.currentPort);
    });

    popover.querySelector('#btn-qf-canvas').addEventListener('click', (e) => {
      e.stopPropagation();
      this.closeQuickfilterPopover();
      this.addHistogramFilterNodeToCanvas(colName, bin);
    });

    document.body.appendChild(popover);
    this.activeQuickfilterPopover = popover;
  }

  closeQuickfilterPopover() {
    if (this.activeQuickfilterPopover) {
      this.activeQuickfilterPopover.remove();
      this.activeQuickfilterPopover = null;
    }
  }

  addFilterNodeToCanvas(colName, segType) {
    if (!window.appCanvas || !this.currentNodeId) return;
    const srcNode = window.appCanvas.nodes.find(n => n.id === this.currentNodeId);
    const x = srcNode ? srcNode.x + 160 : 350;
    const y = srcNode ? srcNode.y : 220;

    let expr = '';
    if (segType === 'null') {
      expr = `[${colName}] is null`;
    } else if (segType === 'empty') {
      expr = `[${colName}] == ""`;
    } else {
      expr = `[${colName}] is not null`;
    }

    const newNode = window.appCanvas.addNode('filter', x, y, `Filter_${colName}`, {
      expression: expr,
      column: colName,
      operator: segType === 'null' ? 'is_null' : (segType === 'empty' ? '==' : 'is_not_null'),
      value: ''
    });

    if (srcNode && newNode) {
      window.appCanvas.addConnection(srcNode.id, this.currentPort, newNode.id, 'I');
    }
    if (window.showToast) {
      window.showToast('success', 'Filter Tool Added', `Added Filter tool for '${colName}' on canvas.`);
    }
  }

  addHistogramFilterNodeToCanvas(colName, bin) {
    if (!window.appCanvas || !this.currentNodeId) return;
    const srcNode = window.appCanvas.nodes.find(n => n.id === this.currentNodeId);
    const x = srcNode ? srcNode.x + 160 : 350;
    const y = srcNode ? srcNode.y : 220;

    let expr = '';
    let config = { column: colName };
    if (bin.value !== undefined) {
      expr = `[${colName}] == "${bin.value}"`;
      config.operator = '==';
      config.value = String(bin.value);
    } else if (bin.start !== undefined && bin.end !== undefined) {
      expr = `[${colName}] >= ${bin.start} and [${colName}] <= ${bin.end}`;
      config.operator = 'between';
      config.min = bin.start;
      config.max = bin.end;
    }
    config.expression = expr;

    const newNode = window.appCanvas.addNode('filter', x, y, `Filter_${colName}`, config);
    if (srcNode && newNode) {
      window.appCanvas.addConnection(srcNode.id, this.currentPort, newNode.id, 'I');
    }
    if (window.showToast) {
      window.showToast('success', 'Filter Tool Added', `Added Filter tool for '${bin.label}' on canvas.`);
    }
  }

  async loadProfiling(nodeId, port) {
    if (!nodeId) return;

    this.profilerContainer.innerHTML = `<div class="results-empty-msg">Computing column distributions and metrics...</div>`;

    try {
      let url = `/api/node-profile/${nodeId}?port=${port}`;
      if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
      if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
      const data = await this.safeFetchJson(url);

      if (!data.available || !data.columns || data.columns.length === 0) {
        this.profilerContainer.innerHTML = `<div class="results-empty-msg">${data.message || 'No data available to profile.'}</div>`;
        return;
      }

      this.renderProfilingCards(data);
    } catch (err) {
      this.profilerContainer.innerHTML = `<div class="results-empty-msg" style="color: var(--color-error)">Error profiling: ${err.message}</div>`;
    }
  }

  exportQualityReport() {
    if (!this.currentNodeId) return;
    const node = window.appCanvas ? window.appCanvas.nodes.find(n => n.id === this.currentNodeId) : null;
    const nodeName = node ? (node.name || node.type) : this.currentNodeId;
    let url = `/api/node-profile/${this.currentNodeId}/export-report?port=${this.currentPort}&title=${encodeURIComponent('Quality Report - ' + nodeName)}`;
    if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
    if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
    window.location.href = url;
  }

  renderProfilingCards(data) {
    const { total_rows, columns } = data;
    const totalCols = data.total_columns || (columns ? columns.length : 0);
    const healthScore = data.composite_health_score !== undefined ? data.composite_health_score : 100;
    const healthGrade = data.health_grade || 'A';
    const memFormatted = data.memory_formatted || '0 B';
    const missingPct = data.missing_cells_pct !== undefined ? data.missing_cells_pct : 0;
    const dupPct = data.duplicate_rows_pct !== undefined ? data.duplicate_rows_pct : 0;

    const gradeColorMap = {
      'A': '#22c55e',
      'B': '#3b82f6',
      'C': '#f59e0b',
      'D': '#f97316',
      'F': '#ef4444'
    };
    const gradeColor = gradeColorMap[healthGrade] || '#3b82f6';

    let html = `
      <div class="results-profiler-header" style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 12px 16px; background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 8px; margin-bottom: 4px;">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div class="browse-grade-circle" style="width: 44px; height: 44px; border-radius: 50%; border: 3px solid ${gradeColor}; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-shrink: 0; background: ${gradeColor}15;">
            <span style="font-size: 17px; font-weight: 800; color: ${gradeColor}; line-height: 1;">${healthGrade}</span>
            <span style="font-size: 8px; color: var(--text-muted); font-weight: 700;">GRADE</span>
          </div>
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 13px; font-weight: 700; color: var(--text-primary);">Dataset Health Score:</span>
              <span style="font-size: 13px; font-weight: 800; color: ${gradeColor};">${healthScore}%</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
              ${total_rows.toLocaleString()} records &bull; ${totalCols} columns &bull; ${memFormatted} &bull; Missing: ${missingPct}% &bull; Dups: ${dupPct}%
            </div>
          </div>
        </div>

        <div style="display: flex; align-items: center; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" id="btn-results-export-report" style="font-size: 11px; display: inline-flex; align-items: center; gap: 6px;">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
            <span>Download Audit Report</span>
          </button>
        </div>
      </div>
    `;

    columns.forEach(col => {
      const q = col.quality || {};
      const okP = q.ok_percent !== undefined ? q.ok_percent : (100 - (col.null_percent || 0));
      const wsP = q.whitespace_percent || 0;
      const outP = q.outlier_percent || 0;
      const nullP = q.null_percent !== undefined ? q.null_percent : (col.null_percent || 0);
      const hScore = col.health_score !== undefined ? col.health_score : 100;
      const hColor = hScore >= 90 ? '#22c55e' : (hScore >= 75 ? '#3b82f6' : (hScore >= 60 ? '#f59e0b' : '#ef4444'));

      // Distribution mini horizontal bar chart with data labels
      let sparklineHtml = '';
      if (col.histogram && col.histogram.length > 0) {
        const maxCnt = Math.max(...col.histogram.map(b => b.count || 0), 1);
        const previewBins = col.histogram.slice(0, 3);
        sparklineHtml = `
          <div class="browse-card-h-bars">
            ${previewBins.map(b => {
              const fillW = Math.max(3, Math.round(((b.count || 0) / maxCnt) * 100));
              const label = this.escapeHtml(b.label || String(b.value || ''));
              return `
                <div class="browse-h-bar-row">
                  <span class="browse-h-bar-lbl" title="${label}">${label}</span>
                  <div class="browse-h-bar-track">
                    <div class="browse-h-bar-fill" style="width: ${fillW}%;"></div>
                  </div>
                  <span class="browse-h-bar-val">
                    ${(b.count || 0).toLocaleString()} <span style="font-weight: 400; color: var(--text-muted);">(${b.percent}%)</span>
                  </span>
                </div>
              `;
            }).join('')}
            ${col.histogram.length > 3 ? `
              <div style="font-size: 9px; color: var(--text-muted); text-align: right; margin-top: 1px;">
                + ${col.histogram.length - 3} more in Deep Dive
              </div>
            ` : ''}
          </div>
        `;
      }

      html += `
        <div class="profile-card" data-col-name="${this.escapeHtml(col.name)}">
          <div class="profile-card-header">
            <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
              <span class="profile-card-name" title="${this.escapeHtml(col.name)}">${this.escapeHtml(col.name)}</span>
              ${this.formatAlteryxTypeBadge(col.dtype)}
              ${col.is_key_candidate ? `<span class="browse-badge-key" title="Candidate Primary Key: 100% unique, 0 nulls">🔑</span>` : ''}
            </div>
            <span style="font-size: 11px; font-weight: 700; color: ${hColor}; flex-shrink: 0;">${hScore}%</span>
          </div>

          <!-- Quad-Color Quality Ribbon -->
          <div class="browse-ribbon" title="OK: ${okP}% (${q.ok_count || 0}) | Whitespace: ${wsP}% (${q.whitespace_count || 0}) | Outliers: ${outP}% (${q.outlier_count || 0}) | Null: ${nullP}% (${q.null_count || 0})">
            <div class="browse-ribbon-seg seg-ok" style="width: ${okP}%;"></div>
            <div class="browse-ribbon-seg seg-ws" style="width: ${wsP}%;"></div>
            <div class="browse-ribbon-seg seg-out" style="width: ${outP}%;"></div>
            <div class="browse-ribbon-seg seg-null" style="width: ${nullP}%;"></div>
          </div>

          <div class="profile-stat-row">
            <span>Valid (OK)</span>
            <b>${(q.ok_count || (total_rows - (col.null_count || 0))).toLocaleString()} (${okP}%)</b>
          </div>
          ${wsP > 0 ? `
            <div class="profile-stat-row" style="color: #f59e0b;">
              <span>Whitespace / Blank</span>
              <b>${(q.whitespace_count || 0).toLocaleString()} (${wsP}%)</b>
            </div>
          ` : ''}
          ${outP > 0 ? `
            <div class="profile-stat-row" style="color: #ef4444;">
              <span>Outliers (IQR)</span>
              <b>${(q.outlier_count || 0).toLocaleString()} (${outP}%)</b>
            </div>
          ` : ''}
          <div class="profile-stat-row">
            <span>Null Records</span>
            <b>${(col.null_count || 0).toLocaleString()} (${nullP}%)</b>
          </div>
          <div class="profile-stat-row">
            <span>Unique Values</span>
            <b>${(col.unique_count || 0).toLocaleString()} (${col.unique_percent || 0}%)</b>
          </div>

          ${col.is_numeric && col.min !== undefined ? `
            <div style="border-top: 1px solid var(--border-subtle); margin-top: 6px; padding-top: 6px;">
              <div class="profile-stat-row"><span>Min / Max</span> <b>${col.min} / ${col.max}</b></div>
              <div class="profile-stat-row"><span>Mean / Median</span> <b>${col.mean} / ${col.median}</b></div>
              <div class="profile-stat-row"><span>Std Dev</span> <b>${col.std}</b></div>
            </div>
          ` : ''}

          ${col.string_stats ? `
            <div style="border-top: 1px solid var(--border-subtle); margin-top: 6px; padding-top: 6px;">
              <div class="profile-stat-row"><span>Length Range</span> <b>${col.string_stats.min_length}..${col.string_stats.max_length}</b></div>
              <div class="profile-stat-row"><span>Average Length</span> <b>${col.string_stats.avg_length}</b></div>
              ${col.string_stats.mixed_casing_detected ? `
                <div class="profile-stat-row" style="color: #f59e0b;"><span>Hygiene Alert</span> <b>Mixed Casing</b></div>
              ` : ''}
              ${col.string_stats.inferred_patterns?.length > 0 ? `
                <div class="profile-stat-row" style="color: #38bdf8;"><span>Pattern</span> <b>${col.string_stats.inferred_patterns[0].pattern}</b></div>
              ` : ''}
            </div>
          ` : ''}

          ${sparklineHtml}

          <div style="display: flex; gap: 4px; margin-top: 8px; border-top: 1px solid rgba(255,255,255,0.06); padding-top: 6px;">
            <button type="button" class="btn-action-remediate btn-card-deep-dive" data-col="${this.escapeHtml(col.name)}" style="flex: 1;">
              🔍 Deep Dive Inspector
            </button>
          </div>
        </div>
      `;
    });

    this.profilerContainer.innerHTML = html;

    // Bind report export
    const exportBtn = this.profilerContainer.querySelector('#btn-results-export-report');
    if (exportBtn) {
      exportBtn.addEventListener('click', () => this.exportQualityReport());
    }

    // Bind card deep dive buttons
    this.profilerContainer.querySelectorAll('.btn-card-deep-dive').forEach(btn => {
      btn.addEventListener('click', () => {
        const colName = btn.dataset.col;
        const colObj = columns.find(c => c.name === colName);
        if (colObj) this.openDeepDive(colObj);
      });
    });
  }

  openDeepDive(col) {
    const existingModal = document.getElementById('profiler-deepdive-modal');
    if (existingModal) existingModal.remove();

    const q = col.quality || {};
    const okP = q.ok_percent !== undefined ? q.ok_percent : 100;
    const wsP = q.whitespace_percent || 0;
    const outP = q.outlier_percent || 0;
    const nullP = q.null_percent || 0;
    const hScore = col.health_score !== undefined ? col.health_score : 100;

    let boxPlotSvg = '';
    if (col.numeric_stats) {
      const ns = col.numeric_stats;
      const min = ns.min !== null ? ns.min : 0;
      const max = ns.max !== null ? ns.max : 1;
      const q1 = ns.q1 !== null ? ns.q1 : min;
      const med = ns.median !== null ? ns.median : (min + max) / 2;
      const q3 = ns.q3 !== null ? ns.q3 : max;
      const lowF = ns.lower_fence !== null ? ns.lower_fence : min;
      const upF = ns.upper_fence !== null ? ns.upper_fence : max;

      const span = max - min || 1;
      const toX = (val) => 40 + Math.max(0, Math.min(460, ((val - min) / span) * 460));

      const xMin = toX(min);
      const xMax = toX(max);
      const xQ1 = toX(q1);
      const xMed = toX(med);
      const xQ3 = toX(q3);
      const xLowF = toX(Math.max(min, lowF));
      const xUpF = toX(Math.min(max, upF));

      boxPlotSvg = `
        <div style="margin: 16px 0; padding: 12px; background: var(--bg-main, #0f172a); border-radius: 6px; border: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; font-size: 11px; font-weight: 700; color: var(--text-muted); margin-bottom: 6px;">
            <span>Box-and-Whisker Distribution (Tukey IQR Fences)</span>
            <span style="color: #ef4444;">${ns.outlier_count || 0} Outliers Detected</span>
          </div>
          <svg viewBox="0 0 540 85" style="width: 100%; height: 85px;">
            <!-- Whisker line -->
            <line x1="${xLowF}" y1="40" x2="${xUpF}" y2="40" stroke="#64748b" stroke-width="2" />
            <!-- Whisker ends -->
            <line x1="${xLowF}" y1="26" x2="${xLowF}" y2="54" stroke="#64748b" stroke-width="2" />
            <line x1="${xUpF}" y1="26" x2="${xUpF}" y2="54" stroke="#64748b" stroke-width="2" />
            <!-- IQR Box -->
            <rect x="${xQ1}" y="20" width="${Math.max(2, xQ3 - xQ1)}" height="40" rx="3" fill="rgba(56, 189, 248, 0.25)" stroke="#38bdf8" stroke-width="2" />
            <!-- Median line -->
            <line x1="${xMed}" y1="20" x2="${xMed}" y2="60" stroke="#f59e0b" stroke-width="3" />
            <!-- Labels -->
            <text x="${xMin}" y="74" fill="#94a3b8" font-size="10" text-anchor="middle">Min: ${min}</text>
            <text x="${xMed}" y="14" fill="#f59e0b" font-size="10" font-weight="bold" text-anchor="middle">Median: ${med}</text>
            <text x="${xMax}" y="74" fill="#94a3b8" font-size="10" text-anchor="middle">Max: ${max}</text>
          </svg>
          <div style="display: flex; justify-content: space-between; font-size: 10px; color: var(--text-muted); margin-top: 4px;">
            <span>Lower Fence: <b>${lowF}</b></span>
            <span>Q1: <b>${q1}</b> &bull; IQR: <b>${ns.iqr}</b> &bull; Q3: <b>${q3}</b></span>
            <span>Upper Fence: <b>${upF}</b></span>
          </div>
        </div>
      `;
    }

    // Distribution Horizontal Bar Chart in deep dive with direct data point labels
    let histSvg = '';
    if (col.histogram && col.histogram.length > 0) {
      const maxCnt = Math.max(...col.histogram.map(b => b.count || 0), 1);
      histSvg = `
        <div style="margin: 16px 0; padding: 14px; background: var(--bg-main, #0f172a); border-radius: 6px; border: 1px solid var(--border-subtle);">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">
              Value Distribution (${col.histogram.length} Bins &bull; Horizontal Bar Chart)
            </div>
            <div style="font-size: 10px; color: var(--text-muted);">
              Data point values & percentages
            </div>
          </div>
          <div style="display: flex; flex-direction: column; gap: 7px;">
            ${col.histogram.map(b => {
              const count = b.count || 0;
              const pct = b.percent !== undefined ? b.percent : 0;
              const fillPct = Math.max(2, Math.round((count / maxCnt) * 100));
              const label = this.escapeHtml(b.label || String(b.value || ''));
              return `
                <div style="display: flex; align-items: center; gap: 10px; font-size: 11px;">
                  <div style="width: 125px; font-family: var(--font-mono); font-size: 10.5px; color: var(--text-secondary); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0;" title="${label}">
                    ${label}
                  </div>
                  <div style="flex: 1; height: 24px; background: rgba(255,255,255,0.05); border-radius: 4px; overflow: hidden; position: relative; border: 1px solid rgba(255,255,255,0.06); display: flex; align-items: center;">
                    <div style="height: 100%; width: ${fillPct}%; background: linear-gradient(90deg, #0284c7, #38bdf8); border-radius: 3px; transition: width 0.3s ease;"></div>
                    <span style="position: absolute; ${fillPct >= 28 ? 'left: 10px; color: #ffffff; text-shadow: 0 1px 2px rgba(0,0,0,0.8);' : `left: calc(${fillPct}% + 10px); color: var(--text-primary);`} font-size: 11px; font-weight: 700; font-family: var(--font-mono); pointer-events: none; white-space: nowrap;">
                      ${count.toLocaleString()} <span style="font-weight: 500; opacity: 0.85;">(${pct}%)</span>
                    </span>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    // Frequencies or Top Values
    let topValuesTable = '';
    const topVals = col.string_stats?.top_values || (col.top_values || []);
    if (topVals.length > 0) {
      topValuesTable = `
        <div style="margin: 16px 0;">
          <div style="font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px;">Top Value Frequencies</div>
          <div style="max-height: 160px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px;">
            <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
              <thead>
                <tr style="background: rgba(0,0,0,0.25); color: var(--text-muted); text-align: left;">
                  <th style="padding: 6px 10px;">Value</th>
                  <th style="padding: 6px 10px; text-align: right;">Count</th>
                  <th style="padding: 6px 10px; text-align: right;">Share</th>
                </tr>
              </thead>
              <tbody>
                ${topVals.map(tv => `
                  <tr style="border-top: 1px solid var(--border-subtle);">
                    <td style="padding: 5px 10px; font-family: var(--font-mono);">${this.escapeHtml(tv.value)}</td>
                    <td style="padding: 5px 10px; text-align: right; font-weight: 600;">${(tv.count || 0).toLocaleString()}</td>
                    <td style="padding: 5px 10px; text-align: right; color: var(--text-muted);">${tv.percent !== undefined ? tv.percent : ''}%</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    const modal = document.createElement('div');
    modal.id = 'profiler-deepdive-modal';
    modal.className = 'app-modal show';
    modal.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="modal-dialog" style="max-width: 620px; max-height: 90vh; display: flex; flex-direction: column; z-index: 2001;">
        <div class="modal-header" style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 16px; font-weight: 700;">${this.escapeHtml(col.name)}</span>
            ${this.formatAlteryxTypeBadge(col.dtype)}
            <span style="font-size: 11px; font-weight: 700; color: ${hScore >= 80 ? '#22c55e' : '#f59e0b'}; background: rgba(0,0,0,0.2); padding: 2px 6px; border-radius: 4px;">
              ${hScore}% Health
            </span>
          </div>
          <button type="button" class="btn-icon" id="btn-deepdive-close" style="border: none; background: transparent; color: var(--text-muted); cursor: pointer; font-size: 16px;">✕</button>
        </div>
        <div class="modal-body" style="overflow-y: auto; padding: 16px; flex: 1;">
          <!-- Quad-Color Quality Ribbon -->
          <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px;">
              <span>Data Quality Profile</span>
              <span>Valid: <b>${okP}%</b> &bull; Null: <b>${nullP}%</b></span>
            </div>
            <div class="browse-ribbon" style="height: 10px;" title="OK: ${okP}% | Whitespace: ${wsP}% | Outliers: ${outP}% | Null: ${nullP}%">
              <div class="browse-ribbon-seg seg-ok" style="width: ${okP}%;"></div>
              <div class="browse-ribbon-seg seg-ws" style="width: ${wsP}%;"></div>
              <div class="browse-ribbon-seg seg-out" style="width: ${outP}%;"></div>
              <div class="browse-ribbon-seg seg-null" style="width: ${nullP}%;"></div>
            </div>
          </div>

          ${boxPlotSvg}
          ${histSvg}
          ${topValuesTable}
        </div>
        <div class="modal-footer" style="padding: 12px 16px; border-top: 1px solid var(--border-subtle); display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; gap: 6px;">
            ${wsP > 0 ? `<button type="button" class="btn btn-secondary btn-sm" id="btn-deepdive-trim">✂️ Trim Spaces</button>` : ''}
            ${outP > 0 ? `<button type="button" class="btn btn-secondary btn-sm" id="btn-deepdive-filter-outliers">⚠️ Filter Outliers</button>` : ''}
            ${nullP > 0 ? `<button type="button" class="btn btn-secondary btn-sm" id="btn-deepdive-filter-nulls">🚫 Filter Nulls</button>` : ''}
          </div>
          <button type="button" class="btn btn-secondary btn-sm" id="btn-deepdive-dismiss">Close</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => modal.remove();
    modal.querySelector('#btn-deepdive-close')?.addEventListener('click', closeModal);
    modal.querySelector('#btn-deepdive-dismiss')?.addEventListener('click', closeModal);
    modal.querySelector('.modal-backdrop')?.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeModal();
    });

    const trimBtn = modal.querySelector('#btn-deepdive-trim');
    if (trimBtn) {
      trimBtn.addEventListener('click', () => {
        closeModal();
        if (window.appConfigPanel) {
          window.appConfigPanel.addRemediationNode(this.currentNodeId, 'clean', {
            columns: [col.name],
            trim_whitespace: true,
            remove_leading_trailing: true
          }, `Clean_${col.name}`);
        }
      });
    }

    const outBtn = modal.querySelector('#btn-deepdive-filter-outliers');
    if (outBtn && col.numeric_stats) {
      outBtn.addEventListener('click', () => {
        closeModal();
        const ns = col.numeric_stats;
        if (window.appConfigPanel) {
          window.appConfigPanel.addRemediationNode(this.currentNodeId, 'filter', {
            column: col.name,
            operator: 'between',
            min: ns.lower_fence,
            max: ns.upper_fence,
            expression: `[${col.name}] >= ${ns.lower_fence} and [${col.name}] <= ${ns.upper_fence}`
          }, `Filter_Outliers_${col.name}`);
        }
      });
    }

    const nullBtn = modal.querySelector('#btn-deepdive-filter-nulls');
    if (nullBtn) {
      nullBtn.addEventListener('click', () => {
        closeModal();
        if (window.appConfigPanel) {
          window.appConfigPanel.addRemediationNode(this.currentNodeId, 'filter', {
            column: col.name,
            operator: 'is_not_null',
            expression: `[${col.name}] is not null`
          }, `Filter_Valid_${col.name}`);
        }
      });
    }
  }

  // --------------------------------------------------------------------
  // Interactive Charting (Bar, Line, Scatter, Histogram, Donut)
  // --------------------------------------------------------------------
  initChartTab(nodeId, port) {
    if (!nodeId) return;
    this.updateChartColumns();
    this.updateChartControlsVisibility();
    this.loadChartData();
  }

  updateChartColumns() {
    if (!this.lastRenderedData || !this.lastRenderedData.columns) return;
    const cols = this.lastRenderedData.columns;

    const prevX = this.chartXSelect ? this.chartXSelect.value : null;
    const prevY = this.chartYSelect ? this.chartYSelect.value : null;

    if (this.chartXSelect) {
      this.chartXSelect.innerHTML = cols.map(c => `<option value="${this.escapeHtml(c.name)}">${this.escapeHtml(c.name)} (${c.dtype})</option>`).join('');
      if (prevX && cols.some(c => c.name === prevX)) {
        this.chartXSelect.value = prevX;
      }
    }

    if (this.chartYSelect) {
      let yOptions = `<option value="">(None - Count Records)</option>`;
      yOptions += cols.map(c => `<option value="${this.escapeHtml(c.name)}">${this.escapeHtml(c.name)} (${c.dtype})</option>`).join('');
      this.chartYSelect.innerHTML = yOptions;
      if (prevY && cols.some(c => c.name === prevY)) {
        this.chartYSelect.value = prevY;
      }
    }
  }

  updateChartControlsVisibility() {
    const type = this.chartTypeSelect ? this.chartTypeSelect.value : 'bar';
    const xGroup = document.getElementById('chart-x-group');
    const yGroup = document.getElementById('chart-y-group');
    const aggGroup = document.getElementById('chart-agg-group');

    if (!xGroup || !yGroup || !aggGroup) return;

    if (type === 'histogram') {
      xGroup.querySelector('label').textContent = 'Variable:';
      yGroup.style.display = 'none';
      aggGroup.style.display = 'none';
    } else if (type === 'scatter') {
      xGroup.querySelector('label').textContent = 'X Axis:';
      yGroup.querySelector('label').textContent = 'Y Axis:';
      yGroup.style.display = 'flex';
      aggGroup.style.display = 'none';
    } else if (type === 'donut') {
      xGroup.querySelector('label').textContent = 'Category:';
      yGroup.querySelector('label').textContent = 'Value (Optional):';
      yGroup.style.display = 'flex';
      aggGroup.style.display = 'flex';
    } else {
      // bar and line
      xGroup.querySelector('label').textContent = 'X Axis:';
      yGroup.querySelector('label').textContent = 'Value (Y):';
      yGroup.style.display = 'flex';
      aggGroup.style.display = 'flex';
    }
  }

  async loadChartData() {
    if (!this.currentNodeId) return;
    const type = this.chartTypeSelect ? this.chartTypeSelect.value : 'bar';
    const xCol = this.chartXSelect ? this.chartXSelect.value : '';
    const yCol = this.chartYSelect ? this.chartYSelect.value : '';
    const agg = this.chartAggSelect ? this.chartAggSelect.value : 'count';

    if (!xCol) {
      this.chartViewport.innerHTML = `<div class="results-empty-msg">Select a column to generate chart.</div>`;
      return;
    }

    this.chartViewport.innerHTML = `<div class="results-empty-msg">Rendering ${type} chart...</div>`;

    try {
      let url = `/api/node-chart-data/${this.currentNodeId}?port=${this.currentPort}&chart_type=${encodeURIComponent(type)}&x_col=${encodeURIComponent(xCol)}&y_col=${encodeURIComponent(yCol)}&agg_func=${encodeURIComponent(agg)}`;
      if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
      if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;

      const data = await this.safeFetchJson(url);
      if (!data.available) {
        this.chartViewport.innerHTML = `<div class="results-empty-msg" style="color: var(--color-warning);">${data.message || 'Unable to render chart.'}</div>`;
        return;
      }

      this.lastChartData = data;
      this.renderChartView(data);
    } catch (err) {
      this.chartViewport.innerHTML = `<div class="results-empty-msg" style="color: var(--color-error);">Chart error: ${err.message}</div>`;
    }
  }

  renderChartView(data) {
    this.chartViewport.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'chart-svg-wrap';

    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip';
    wrap.appendChild(tooltip);

    switch (data.chart_type) {
      case 'bar':
        this.renderBarChart(data, wrap, tooltip);
        break;
      case 'line':
        this.renderLineChart(data, wrap, tooltip);
        break;
      case 'scatter':
        this.renderScatterChart(data, wrap, tooltip);
        break;
      case 'histogram':
        this.renderHistogramChart(data, wrap, tooltip);
        break;
      case 'donut':
        this.renderDonutChart(data, wrap, tooltip);
        break;
      default:
        wrap.innerHTML = `<div class="results-empty-msg">Unsupported chart type: ${data.chart_type}</div>`;
    }

    this.chartViewport.appendChild(wrap);
  }

  renderBarChart(data, wrap, tooltip) {
    const items = data.items || [];
    if (items.length === 0) {
      wrap.innerHTML = `<div class="results-empty-msg">No data items to display in bar chart.</div>`;
      return;
    }

    const W = 880;
    const H = 450;
    const ml = 75, mr = 30, mt = 30, mb = 75;
    const pw = W - ml - mr;
    const ph = H - mt - mb;

    const maxVal = Math.max(...items.map(it => it.value), 1) * 1.15;
    const bandW = pw / items.length;
    const barW = Math.min(52, Math.max(6, bandW * 0.72));

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.className.baseVal = 'chart-svg';

    // Defs for gradient
    svg.innerHTML = `
      <defs>
        <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#38bdf8" />
          <stop offset="100%" stop-color="#0284c7" />
        </linearGradient>
      </defs>
    `;

    // Horizontal grid lines
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      const v = (maxVal / ticks) * i;
      const y = mt + ph - (v / maxVal) * ph;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', ml);
      line.setAttribute('x2', ml + pw);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('stroke', '#334155');
      line.setAttribute('stroke-dasharray', i === 0 ? 'none' : '3,3');
      line.setAttribute('stroke-width', i === 0 ? '1.5' : '1');
      svg.appendChild(line);

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', ml - 10);
      text.setAttribute('y', y + 4);
      text.setAttribute('text-anchor', 'end');
      text.setAttribute('fill', '#94a3b8');
      text.setAttribute('font-size', '10px');
      text.setAttribute('font-family', 'var(--font-mono)');
      text.textContent = this.formatNumber(v);
      svg.appendChild(text);
    }

    // Bars & X labels
    items.forEach((it, i) => {
      const bh = (it.value / maxVal) * ph;
      const bx = ml + i * bandW + (bandW - barW) / 2;
      const by = mt + ph - bh;

      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', bx);
      rect.setAttribute('y', by);
      rect.setAttribute('width', barW);
      rect.setAttribute('height', Math.max(2, bh));
      rect.setAttribute('rx', '3');
      rect.setAttribute('fill', 'url(#barGrad)');
      rect.style.cursor = 'pointer';
      rect.style.transition = 'opacity 0.15s ease';

      rect.addEventListener('mouseenter', (e) => {
        rect.setAttribute('fill', '#38bdf8');
        tooltip.style.display = 'block';
        tooltip.innerHTML = `<b>${this.escapeHtml(it.label)}</b>: ${it.value.toLocaleString()}`;
        this.positionTooltip(tooltip, e, wrap);
      });
      rect.addEventListener('mousemove', (e) => {
        this.positionTooltip(tooltip, e, wrap);
      });
      rect.addEventListener('mouseleave', () => {
        rect.setAttribute('fill', 'url(#barGrad)');
        tooltip.style.display = 'none';
      });

      svg.appendChild(rect);

      // Data point label above bar
      if (bh >= 14 || items.length <= 15) {
        const valLbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        valLbl.setAttribute('x', bx + barW / 2);
        valLbl.setAttribute('y', by - 5);
        valLbl.setAttribute('text-anchor', 'middle');
        valLbl.setAttribute('fill', '#f8fafc');
        valLbl.setAttribute('font-size', '10px');
        valLbl.setAttribute('font-weight', '600');
        valLbl.setAttribute('font-family', 'var(--font-mono)');
        valLbl.textContent = this.formatNumber(it.value);
        svg.appendChild(valLbl);
      }

      // Label
      const lx = bx + barW / 2;
      const ly = mt + ph + 16;
      const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      lbl.setAttribute('x', lx);
      lbl.setAttribute('y', ly);
      lbl.setAttribute('text-anchor', items.length > 8 ? 'end' : 'middle');
      lbl.setAttribute('fill', '#94a3b8');
      lbl.setAttribute('font-size', '10px');
      if (items.length > 8) {
        lbl.setAttribute('transform', `rotate(-35, ${lx}, ${ly})`);
      }
      lbl.textContent = it.label.length > 14 ? it.label.slice(0, 12) + '...' : it.label;
      svg.appendChild(lbl);
    });

    // Y Axis Title
    const yTitle = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    yTitle.setAttribute('x', -(mt + ph / 2));
    yTitle.setAttribute('y', 20);
    yTitle.setAttribute('transform', 'rotate(-90)');
    yTitle.setAttribute('text-anchor', 'middle');
    yTitle.setAttribute('fill', '#cbd5e1');
    yTitle.setAttribute('font-size', '11px');
    yTitle.setAttribute('font-weight', '600');
    yTitle.textContent = data.y_label || 'Value';
    svg.appendChild(yTitle);

    wrap.appendChild(svg);
  }

  renderLineChart(data, wrap, tooltip) {
    const points = data.points || [];
    if (points.length === 0) {
      wrap.innerHTML = `<div class="results-empty-msg">No data points to display in line chart.</div>`;
      return;
    }

    const W = 880;
    const H = 450;
    const ml = 75, mr = 30, mt = 30, mb = 75;
    const pw = W - ml - mr;
    const ph = H - mt - mb;

    const yVals = points.map(p => p.y);
    let minVal = Math.min(...yVals);
    let maxVal = Math.max(...yVals);
    if (minVal === maxVal) { minVal *= 0.9; maxVal *= 1.1; }
    if (minVal > 0) minVal = 0; // Baseline zero
    const valRange = maxVal - minVal || 1;

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.className.baseVal = 'chart-svg';

    svg.innerHTML = `
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0284c7" stop-opacity="0.3" />
          <stop offset="100%" stop-color="#0284c7" stop-opacity="0.0" />
        </linearGradient>
      </defs>
    `;

    // Horizontal grid lines
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      const v = minVal + (valRange / ticks) * i;
      const y = mt + ph - ((v - minVal) / valRange) * ph;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', ml);
      line.setAttribute('x2', ml + pw);
      line.setAttribute('y1', y);
      line.setAttribute('y2', y);
      line.setAttribute('stroke', '#334155');
      line.setAttribute('stroke-dasharray', i === 0 ? 'none' : '3,3');
      line.setAttribute('stroke-width', i === 0 ? '1.5' : '1');
      svg.appendChild(line);

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', ml - 10);
      text.setAttribute('y', y + 4);
      text.setAttribute('text-anchor', 'end');
      text.setAttribute('fill', '#94a3b8');
      text.setAttribute('font-size', '10px');
      text.setAttribute('font-family', 'var(--font-mono)');
      text.textContent = this.formatNumber(v);
      svg.appendChild(text);
    }

    const stepX = pw / Math.max(1, points.length - 1);
    const coords = points.map((p, i) => {
      const x = ml + i * stepX;
      const y = mt + ph - ((p.y - minVal) / valRange) * ph;
      return { x, y, raw: p };
    });

    // Area path
    let areaD = `M ${coords[0].x} ${mt + ph} L ${coords[0].x} ${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
      areaD += ` L ${coords[i].x} ${coords[i].y}`;
    }
    areaD += ` L ${coords[coords.length - 1].x} ${mt + ph} Z`;

    const areaPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    areaPath.setAttribute('d', areaD);
    areaPath.setAttribute('fill', 'url(#areaGrad)');
    svg.appendChild(areaPath);

    // Line path
    let lineD = `M ${coords[0].x} ${coords[0].y}`;
    for (let i = 1; i < coords.length; i++) {
      lineD += ` L ${coords[i].x} ${coords[i].y}`;
    }
    const linePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    linePath.setAttribute('d', lineD);
    linePath.setAttribute('fill', 'none');
    linePath.setAttribute('stroke', '#0284c7');
    linePath.setAttribute('stroke-width', '2.5');
    svg.appendChild(linePath);

    // Circles & X Ticks
    const showEvery = Math.max(1, Math.ceil(coords.length / 12));
    coords.forEach((c, i) => {
      const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      dot.setAttribute('cx', c.x);
      dot.setAttribute('cy', c.y);
      dot.setAttribute('r', '4');
      dot.setAttribute('fill', '#38bdf8');
      dot.setAttribute('stroke', '#0f172a');
      dot.setAttribute('stroke-width', '1.5');
      dot.style.cursor = 'pointer';

      dot.addEventListener('mouseenter', (e) => {
        dot.setAttribute('r', '6.5');
        dot.setAttribute('fill', '#ffffff');
        tooltip.style.display = 'block';
        tooltip.innerHTML = `<b>${this.escapeHtml(c.raw.x)}</b>: ${c.raw.y.toLocaleString()}`;
        this.positionTooltip(tooltip, e, wrap);
      });
      dot.addEventListener('mousemove', (e) => {
        this.positionTooltip(tooltip, e, wrap);
      });
      dot.addEventListener('mouseleave', () => {
        dot.setAttribute('r', '4');
        dot.setAttribute('fill', '#38bdf8');
        tooltip.style.display = 'none';
      });

      svg.appendChild(dot);

      if (i % showEvery === 0 || i === coords.length - 1) {
        const ly = mt + ph + 16;
        const lbl = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        lbl.setAttribute('x', c.x);
        lbl.setAttribute('y', ly);
        lbl.setAttribute('text-anchor', 'end');
        lbl.setAttribute('fill', '#94a3b8');
        lbl.setAttribute('font-size', '10px');
        lbl.setAttribute('transform', `rotate(-35, ${c.x}, ${ly})`);
        const str = String(c.raw.x);
        lbl.textContent = str.length > 12 ? str.slice(0, 10) + '...' : str;
        svg.appendChild(lbl);
      }
    });

    wrap.appendChild(svg);
  }

  renderScatterChart(data, wrap, tooltip) {
    const points = data.points || [];
    if (points.length === 0) {
      wrap.innerHTML = `<div class="results-empty-msg">No valid numeric pairs to display in scatter plot.</div>`;
      return;
    }

    const W = 880;
    const H = 450;
    const ml = 75, mr = 30, mt = 30, mb = 60;
    const pw = W - ml - mr;
    const ph = H - mt - mb;

    const xMin = data.x_min !== undefined ? data.x_min : 0;
    const xMax = data.x_max !== undefined ? data.x_max : 1;
    const yMin = data.y_min !== undefined ? data.y_min : 0;
    const yMax = data.y_max !== undefined ? data.y_max : 1;

    const xRange = xMax - xMin || 1;
    const yRange = yMax - yMin || 1;

    // Stat badge
    const badge = document.createElement('div');
    badge.className = 'chart-stat-badge';
    const corrStr = data.correlation !== null && data.correlation !== undefined ? `Pearson r = ${data.correlation}` : 'r = N/A';
    const sampleStr = data.sampled ? ' (Sampled 3k pts)' : ` (${points.length} pts)`;
    badge.textContent = `${corrStr}${sampleStr}`;
    wrap.appendChild(badge);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.className.baseVal = 'chart-svg';

    // Horizontal and vertical gridlines
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      // Y lines
      const yVal = yMin + (yRange / ticks) * i;
      const y = mt + ph - ((yVal - yMin) / yRange) * ph;
      const yLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      yLine.setAttribute('x1', ml);
      yLine.setAttribute('x2', ml + pw);
      yLine.setAttribute('y1', y);
      yLine.setAttribute('y2', y);
      yLine.setAttribute('stroke', '#334155');
      yLine.setAttribute('stroke-dasharray', '3,3');
      svg.appendChild(yLine);

      const yText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      yText.setAttribute('x', ml - 10);
      yText.setAttribute('y', y + 4);
      yText.setAttribute('text-anchor', 'end');
      yText.setAttribute('fill', '#94a3b8');
      yText.setAttribute('font-size', '10px');
      yText.textContent = this.formatNumber(yVal);
      svg.appendChild(yText);

      // X lines
      const xVal = xMin + (xRange / ticks) * i;
      const x = ml + ((xVal - xMin) / xRange) * pw;
      const xLine = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      xLine.setAttribute('x1', x);
      xLine.setAttribute('x2', x);
      xLine.setAttribute('y1', mt);
      xLine.setAttribute('y2', mt + ph);
      xLine.setAttribute('stroke', '#334155');
      xLine.setAttribute('stroke-dasharray', '3,3');
      svg.appendChild(xLine);

      const xText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      xText.setAttribute('x', x);
      xText.setAttribute('y', mt + ph + 18);
      xText.setAttribute('text-anchor', 'middle');
      xText.setAttribute('fill', '#94a3b8');
      xText.setAttribute('font-size', '10px');
      xText.textContent = this.formatNumber(xVal);
      svg.appendChild(xText);
    }

    // Points
    points.forEach(p => {
      const cx = ml + ((p.x - xMin) / xRange) * pw;
      const cy = mt + ph - ((p.y - yMin) / yRange) * ph;

      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', cx);
      circle.setAttribute('cy', cy);
      circle.setAttribute('r', '3.5');
      circle.setAttribute('fill', '#38bdf8');
      circle.setAttribute('fill-opacity', '0.65');
      circle.style.cursor = 'crosshair';

      circle.addEventListener('mouseenter', (e) => {
        circle.setAttribute('r', '6');
        circle.setAttribute('fill', '#ffffff');
        circle.setAttribute('fill-opacity', '1');
        tooltip.style.display = 'block';
        tooltip.innerHTML = `<b>X:</b> ${p.x}<br><b>Y:</b> ${p.y}`;
        this.positionTooltip(tooltip, e, wrap);
      });
      circle.addEventListener('mousemove', (e) => {
        this.positionTooltip(tooltip, e, wrap);
      });
      circle.addEventListener('mouseleave', () => {
        circle.setAttribute('r', '3.5');
        circle.setAttribute('fill', '#38bdf8');
        circle.setAttribute('fill-opacity', '0.65');
        tooltip.style.display = 'none';
      });

      svg.appendChild(circle);
    });

    wrap.appendChild(svg);
  }

  renderHistogramChart(data, wrap, tooltip) {
    const series = data.series || [];
    if (series.length === 0) {
      wrap.innerHTML = `<div class="results-empty-msg">No distribution series to display.</div>`;
      return;
    }

    const W = 900;
    const rowH = 36;
    const ml = 165, mr = 135, mt = 35, mb = 45;
    const H = Math.max(420, series.length * rowH + mt + mb);
    const pw = W - ml - mr;
    const ph = H - mt - mb;

    const maxCnt = Math.max(...series.map(s => s.count), 1) * 1.15;
    const bandH = ph / series.length;
    const barH = Math.min(24, Math.max(10, bandH * 0.72));

    // Stat badge
    const badge = document.createElement('div');
    badge.className = 'chart-stat-badge';
    badge.textContent = `Mean: ${data.mean} | Median: ${data.median} | Min: ${data.min} | Max: ${data.max}`;
    wrap.appendChild(badge);

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.className.baseVal = 'chart-svg';

    svg.innerHTML = `
      <defs>
        <linearGradient id="histHBarGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stop-color="#0284c7" />
          <stop offset="100%" stop-color="#38bdf8" />
        </linearGradient>
      </defs>
    `;

    // Vertical grid lines for X axis (record counts)
    const ticks = 5;
    for (let i = 0; i <= ticks; i++) {
      const v = (maxCnt / ticks) * i;
      const x = ml + (v / maxCnt) * pw;
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', x);
      line.setAttribute('x2', x);
      line.setAttribute('y1', mt);
      line.setAttribute('y2', mt + ph);
      line.setAttribute('stroke', '#334155');
      line.setAttribute('stroke-dasharray', i === 0 ? 'none' : '3,3');
      line.setAttribute('stroke-width', i === 0 ? '1.5' : '1');
      svg.appendChild(line);

      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', x);
      text.setAttribute('y', mt + ph + 16);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', '#94a3b8');
      text.setAttribute('font-size', '10px');
      text.setAttribute('font-family', 'var(--font-mono)');
      text.textContent = this.formatNumber(v);
      svg.appendChild(text);
    }

    // Horizontal bars & labels
    series.forEach((s, i) => {
      const bw = Math.max(2, (s.count / maxCnt) * pw);
      const by = mt + i * bandH + (bandH - barH) / 2;

      // Y-axis label on left
      const yLabel = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      yLabel.setAttribute('x', ml - 10);
      yLabel.setAttribute('y', by + barH / 2 + 4);
      yLabel.setAttribute('text-anchor', 'end');
      yLabel.setAttribute('fill', '#94a3b8');
      yLabel.setAttribute('font-size', '11px');
      yLabel.setAttribute('font-family', 'var(--font-mono)');
      yLabel.textContent = `[${s.bin_start}, ${s.bin_end})`;
      svg.appendChild(yLabel);

      // Bar
      const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      rect.setAttribute('x', ml);
      rect.setAttribute('y', by);
      rect.setAttribute('width', bw);
      rect.setAttribute('height', barH);
      rect.setAttribute('rx', '3');
      rect.setAttribute('fill', 'url(#histHBarGrad)');
      rect.style.cursor = 'pointer';
      rect.style.transition = 'opacity 0.15s ease';

      rect.addEventListener('mouseenter', (e) => {
        rect.setAttribute('fill', '#38bdf8');
        tooltip.style.display = 'block';
        tooltip.innerHTML = `<b>Bin:</b> [${s.bin_start}, ${s.bin_end})<br><b>Records:</b> ${s.count.toLocaleString()} (${s.percent}%)`;
        this.positionTooltip(tooltip, e, wrap);
      });
      rect.addEventListener('mousemove', (e) => {
        this.positionTooltip(tooltip, e, wrap);
      });
      rect.addEventListener('mouseleave', () => {
        rect.setAttribute('fill', 'url(#histHBarGrad)');
        tooltip.style.display = 'none';
      });

      svg.appendChild(rect);

      // Data point label directly on or next to the bar
      const isWide = bw >= 80;
      const valText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      valText.setAttribute('x', isWide ? ml + 10 : ml + bw + 8);
      valText.setAttribute('y', by + barH / 2 + 4);
      valText.setAttribute('fill', isWide ? '#ffffff' : '#f8fafc');
      valText.setAttribute('font-size', '11px');
      valText.setAttribute('font-weight', '700');
      valText.setAttribute('font-family', 'var(--font-mono)');
      valText.textContent = `${s.count.toLocaleString()} (${s.percent}%)`;
      svg.appendChild(valText);
    });

    wrap.appendChild(svg);
  }

  renderDonutChart(data, wrap, tooltip) {
    const items = data.items || [];
    if (items.length === 0) {
      wrap.innerHTML = `<div class="results-empty-msg">No categories to display in donut chart.</div>`;
      return;
    }

    const W = 880;
    const H = 400;
    const cx = 440;
    const cy = 200;
    const R = 150;
    const r = 88;

    const total = items.reduce((acc, it) => acc + it.value, 0);
    const colors = ['#0284c7', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1', '#84cc16'];

    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.className.baseVal = 'chart-svg';

    let curAngle = -Math.PI / 2;

    items.forEach((it, idx) => {
      const sliceAngle = total > 0 ? (it.value / total) * Math.PI * 2 : 0;
      const nextAngle = curAngle + sliceAngle;
      const color = colors[idx % colors.length];

      const x1 = cx + R * Math.cos(curAngle);
      const y1 = cy + R * Math.sin(curAngle);
      const x2 = cx + R * Math.cos(nextAngle);
      const y2 = cy + R * Math.sin(nextAngle);

      const x3 = cx + r * Math.cos(nextAngle);
      const y3 = cy + r * Math.sin(nextAngle);
      const x4 = cx + r * Math.cos(curAngle);
      const y4 = cy + r * Math.sin(curAngle);

      const largeArc = sliceAngle > Math.PI ? 1 : 0;

      const pathD = `M ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${r} ${r} 0 ${largeArc} 0 ${x4} ${y4} Z`;

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', pathD);
      path.setAttribute('fill', color);
      path.setAttribute('stroke', '#0f172a');
      path.setAttribute('stroke-width', '1.5');
      path.style.cursor = 'pointer';
      path.style.transition = 'transform 0.15s ease, filter 0.15s ease';

      const pct = total > 0 ? ((it.value / total) * 100).toFixed(1) : 0;

      path.addEventListener('mouseenter', (e) => {
        path.style.filter = 'brightness(1.25)';
        tooltip.style.display = 'block';
        tooltip.innerHTML = `<b>${this.escapeHtml(it.label)}</b>: ${it.value.toLocaleString()} (${pct}%)`;
        this.positionTooltip(tooltip, e, wrap);
      });
      path.addEventListener('mousemove', (e) => {
        this.positionTooltip(tooltip, e, wrap);
      });
      path.addEventListener('mouseleave', () => {
        path.style.filter = 'none';
        tooltip.style.display = 'none';
      });

      svg.appendChild(path);
      curAngle = nextAngle;
    });

    // Center total text
    const totalText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    totalText.setAttribute('x', cx);
    totalText.setAttribute('y', cy - 4);
    totalText.setAttribute('text-anchor', 'middle');
    totalText.setAttribute('fill', '#f8fafc');
    totalText.setAttribute('font-size', '20px');
    totalText.setAttribute('font-weight', '700');
    totalText.textContent = this.formatNumber(total);
    svg.appendChild(totalText);

    const subText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    subText.setAttribute('x', cx);
    subText.setAttribute('y', cy + 18);
    subText.setAttribute('text-anchor', 'middle');
    subText.setAttribute('fill', '#94a3b8');
    subText.setAttribute('font-size', '11px');
    subText.textContent = 'Total Records';
    svg.appendChild(subText);

    wrap.appendChild(svg);

    // Legend
    const legend = document.createElement('div');
    legend.className = 'chart-legend';
    items.slice(0, 10).forEach((it, idx) => {
      const pct = total > 0 ? ((it.value / total) * 100).toFixed(1) : 0;
      const itemEl = document.createElement('div');
      itemEl.className = 'chart-legend-item';
      itemEl.innerHTML = `
        <span class="chart-legend-color" style="background: ${colors[idx % colors.length]}"></span>
        <span>${this.escapeHtml(it.label)} (${pct}%)</span>
      `;
      legend.appendChild(itemEl);
    });
    wrap.appendChild(legend);
  }

  positionTooltip(tooltip, e, container) {
    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  formatNumber(val) {
    if (val === null || val === undefined) return '';
    const num = Number(val);
    if (isNaN(num)) return String(val);
    if (Math.abs(num) >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (Math.abs(num) >= 1e3) return (num / 1e3).toFixed(1) + 'k';
    return Number.isInteger(num) ? num.toString() : num.toFixed(1);
  }

  // --------------------------------------------------------------------
  // Chart Exports (PNG, SVG, Clipboard, CSV)
  // --------------------------------------------------------------------
  exportChartPNG() {
    const svgEl = this.chartViewport.querySelector('svg');
    if (!svgEl) {
      if (window.showToast) window.showToast('warning', 'Export Chart', 'No chart available to export.');
      return;
    }

    const svgXml = new XMLSerializer().serializeToString(svgEl);
    const canvas = document.createElement('canvas');
    canvas.width = 1600;
    canvas.height = 900;
    const ctx = canvas.getContext('2d');

    // Fill background
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const img = new Image();
    const svgBlob = new Blob([svgXml], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      const a = document.createElement('a');
      a.download = `dataflow_chart_${Date.now()}.png`;
      a.href = canvas.toDataURL('image/png');
      a.click();
      if (window.showToast) window.showToast('success', 'Chart Exported', 'Downloaded chart as PNG image.');
    };
    img.src = url;
  }

  exportChartSVG() {
    const svgEl = this.chartViewport.querySelector('svg');
    if (!svgEl) {
      if (window.showToast) window.showToast('warning', 'Export Chart', 'No chart available to export.');
      return;
    }
    const svgXml = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([svgXml], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.download = `dataflow_chart_${Date.now()}.svg`;
    a.href = url;
    a.click();
    URL.revokeObjectURL(url);
    if (window.showToast) window.showToast('success', 'Chart Exported', 'Downloaded chart as scalable SVG.');
  }

  copyChartToClipboard() {
    const svgEl = this.chartViewport.querySelector('svg');
    if (!svgEl) {
      if (window.showToast) window.showToast('warning', 'Copy Chart', 'No chart available to copy.');
      return;
    }

    const svgXml = new XMLSerializer().serializeToString(svgEl);
    const canvas = document.createElement('canvas');
    canvas.width = 1600;
    canvas.height = 900;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#0f172a';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const img = new Image();
    const svgBlob = new Blob([svgXml], { type: 'image/svg+xml;charset=utf-8' });
    const url = URL.createObjectURL(svgBlob);

    img.onload = () => {
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      URL.revokeObjectURL(url);
      canvas.toBlob(blob => {
        if (!blob) return;
        navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]).then(() => {
          if (window.showToast) window.showToast('success', 'Chart Copied', 'Chart image copied to clipboard.');
        }).catch(err => {
          if (window.showToast) window.showToast('error', 'Copy Failed', err.message);
        });
      });
    };
    img.src = url;
  }

  exportChartCSV() {
    if (!this.lastChartData) {
      if (window.showToast) window.showToast('warning', 'Export CSV', 'No chart data available to export.');
      return;
    }

    let csvContent = '';
    const d = this.lastChartData;

    if (d.items) {
      csvContent = 'Category,Value\n' + d.items.map(it => `"${String(it.label).replace(/"/g, '""')}",${it.value}`).join('\n');
    } else if (d.points) {
      csvContent = 'X,Y\n' + d.points.map(p => `"${String(p.x).replace(/"/g, '""')}",${p.y}`).join('\n');
    } else if (d.series) {
      csvContent = 'Bin Start,Bin End,Count,Percent\n' + d.series.map(s => `${s.bin_start},${s.bin_end},${s.count},${s.percent}`).join('\n');
    }

    if (!csvContent) {
      if (window.showToast) window.showToast('info', 'Export CSV', 'No tabular series to export.');
      return;
    }

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.download = `chart_data_${d.chart_type}_${Date.now()}.csv`;
    a.href = url;
    a.click();
    URL.revokeObjectURL(url);
    if (window.showToast) window.showToast('success', 'CSV Exported', 'Downloaded chart aggregated data as CSV.');
  }

  switchToTab(tabName) {
    document.querySelectorAll('.results-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

    const tabBtn = document.querySelector(`.results-tab[data-tab="${tabName}"]`);
    if (tabBtn) tabBtn.classList.add('active');
    const targetPane = document.getElementById(`tab-${tabName}`);
    if (targetPane) targetPane.classList.add('active');
    this.currentTab = tabName;

    if (tabName === 'chart-view' && this.currentNodeId) {
      this.initChartTab(this.currentNodeId, this.currentPort);
    }
  }

  startRun(runId = null) {
    this.runCounter++;
    this.activeRunStartTime = Date.now();

    if (!this.messagesLog) return this.runCounter;

    // Remove any placeholder empty message
    const emptyMsg = this.messagesLog.querySelector('.results-empty-msg');
    if (emptyMsg) emptyMsg.remove();

    // Create a new run block
    const runBlock = document.createElement('div');
    runBlock.className = 'run-block is-running';
    runBlock.id = `run-block-${this.runCounter}`;
    if (runId) runBlock.dataset.runId = runId;

    const startTimeStr = new Date().toLocaleTimeString();

    runBlock.innerHTML = `
      <div class="run-header run-header-running">
        <div class="run-header-left">
          <span class="spinner-sm"></span>
          <span class="run-badge run-badge-running">● Run #${this.runCounter} In Progress</span>
          <span class="run-meta">${startTimeStr}</span>
        </div>
        <div class="run-header-right">
          <button class="btn btn-ghost btn-xs btn-copy-single-run" title="Copy this run's log" style="font-size: 10px; padding: 2px 6px;">Copy</button>
        </div>
      </div>
      <div class="run-diagnostic-area"></div>
      <div class="run-entries"></div>
    `;

    // Bind copy single run button
    const copySingleBtn = runBlock.querySelector('.btn-copy-single-run');
    if (copySingleBtn) {
      const curRun = this.runCounter;
      copySingleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        this.copySingleRunLog(runBlock, curRun);
      });
    }

    this.messagesLog.appendChild(runBlock);
    this.activeRunBlock = runBlock;
    this.messagesLog.scrollTop = this.messagesLog.scrollHeight;

    return this.runCounter;
  }

  appendLog(logEntry) {
    if (!this.activeRunBlock) {
      this.startRun();
    }

    const rawLvl = (logEntry.level || 'info').toLowerCase();
    let lvl = 'info';
    if (rawLvl.includes('error') || rawLvl === 'err' || rawLvl === 'fatal') lvl = 'error';
    else if (rawLvl.includes('warn')) lvl = 'warning';
    else if (rawLvl.includes('success')) lvl = 'success';

    const entryEl = document.createElement('div');
    entryEl.className = `log-entry log-${lvl}`;
    entryEl.dataset.level = lvl;

    const timeStr = logEntry.time || new Date().toLocaleTimeString();
    entryEl.innerHTML = `
      <span class="log-time">${timeStr}</span>
      <span class="log-msg">${this.escapeHtml(logEntry.message || '')}</span>
    `;

    if (this.activeMsgFilter !== 'all' && this.activeMsgFilter !== lvl && !(this.activeMsgFilter === 'info' && lvl === 'success')) {
      entryEl.style.display = 'none';
    }

    const entriesContainer = this.activeRunBlock.querySelector('.run-entries');
    if (entriesContainer) {
      entriesContainer.appendChild(entryEl);
    }

    // Update counts
    this.totalMsgCounts.all++;
    if (lvl === 'error') this.totalMsgCounts.error++;
    else if (lvl === 'warning') this.totalMsgCounts.warning++;
    else this.totalMsgCounts.info++;

    this.updateMessageCountsDisplay();

    if (this.messagesLog) {
      this.messagesLog.scrollTop = this.messagesLog.scrollHeight;
    }
  }

  finalizeRun(result = {}) {
    if (!this.activeRunBlock) return;

    const runBlock = this.activeRunBlock;
    runBlock.classList.remove('is-running');

    const durationMs = result.total_duration_ms !== undefined 
      ? Math.round(result.total_duration_ms) 
      : (this.activeRunStartTime ? Math.round(Date.now() - this.activeRunStartTime) : 0);

    const isSuccess = Boolean(result.success);
    const isCancelled = Boolean(result.cancelled);
    const nodeCount = Object.keys(result.node_results || {}).length;

    const header = runBlock.querySelector('.run-header');
    const headerLeft = runBlock.querySelector('.run-header-left');

    if (header && headerLeft) {
      if (isCancelled) {
        header.className = 'run-header run-header-cancelled';
        headerLeft.innerHTML = `
          <span class="run-badge run-badge-cancelled">⏹ Run #${this.runCounter} Cancelled</span>
          <span class="run-meta">${durationMs}ms</span>
        `;
      } else if (isSuccess) {
        header.className = 'run-header run-header-success';
        const toolStr = nodeCount > 0 ? ` · ${nodeCount} tools executed` : '';
        headerLeft.innerHTML = `
          <span class="run-badge run-badge-success">✓ Run #${this.runCounter} Succeeded</span>
          <span class="run-meta">${durationMs}ms${toolStr}</span>
        `;
      } else {
        header.className = 'run-header run-header-error';
        headerLeft.innerHTML = `
          <span class="run-badge run-badge-error">✗ Run #${this.runCounter} Failed</span>
          <span class="run-meta">${durationMs}ms</span>
        `;
      }
    }

    // Render Diagnostic Banner inside this run block if diagnostic is present
    const diagArea = runBlock.querySelector('.run-diagnostic-area');
    if (diagArea && result.diagnostic) {
      const diag = result.diagnostic;
      const code = diag.error_code || 'ERROR';
      const title = this.escapeHtml(diag.title || 'Execution Error');
      const message = this.escapeHtml(diag.message || '');
      const suggestion = this.escapeHtml(diag.suggestion || '');
      const targetNodeId = diag.node_id;

      diagArea.innerHTML = `
        <div class="diagnostic-banner" style="margin: 8px 12px 4px 12px;">
          <div class="diagnostic-header">
            <div class="diagnostic-title-area">
              <span class="diagnostic-badge">${code}</span>
              <span class="diagnostic-title">${title}</span>
            </div>
            ${targetNodeId ? `
              <button class="btn btn-secondary btn-sm btn-jump-node" data-node="${targetNodeId}" style="font-size: 11px;">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 16 16 12 12 8"></polyline><line x1="8" y1="12" x2="16" y2="12"></line></svg>
                <span>Jump to Tool</span>
              </button>
            ` : ''}
          </div>
          <div class="diagnostic-body">${message}</div>
          ${suggestion ? `
            <div class="diagnostic-suggestion">
              <span class="diagnostic-suggestion-icon">&#9888;</span>
              <div><b>Suggested Fix:</b> ${suggestion}</div>
            </div>
          ` : ''}
        </div>
      `;

      const jumpBtn = diagArea.querySelector('.btn-jump-node');
      if (jumpBtn) {
        jumpBtn.addEventListener('click', () => {
          const nodeId = jumpBtn.dataset.node;
          if (window.appCanvas) {
            window.appCanvas.highlightErrorNode(nodeId);
          }
        });
      }
    }

    // Append any final completion log from result if not already streamed
    if (result.logs && Array.isArray(result.logs)) {
      const existingMsgs = new Set(Array.from(runBlock.querySelectorAll('.log-msg')).map(el => el.textContent.trim()));
      result.logs.forEach(l => {
        const msg = (l.message || '').trim();
        if (msg && !existingMsgs.has(msg)) {
          this.appendLog(l);
          existingMsgs.add(msg);
        }
      });
    }

    this.activeRunBlock = null;
    this.activeRunStartTime = null;
  }

  updateMessagesLog(logs = [], diagnostic = null) {
    // Backwards compatibility handler for non-streaming execution fallback
    this.startRun();
    logs.forEach(l => this.appendLog(l));
    this.finalizeRun({
      success: !diagnostic,
      diagnostic: diagnostic,
      logs: logs
    });
  }

  clearMessagesLog() {
    this.runCounter = 0;
    this.activeRunBlock = null;
    this.activeRunStartTime = null;
    this.totalMsgCounts = { all: 0, error: 0, warning: 0, info: 0 };
    this.updateMessageCountsDisplay();

    if (this.messagesLog) {
      this.messagesLog.innerHTML = `<div class="results-empty-msg">DataFlow ready. Build your pipeline and press 'Run Workflow'.</div>`;
    }
  }

  copyMessagesLog() {
    if (!this.messagesLog) return;
    const textLines = [];
    this.messagesLog.querySelectorAll('.run-block').forEach(rb => {
      const header = rb.querySelector('.run-header');
      if (header) {
        textLines.push(`=== ${header.innerText.replace(/\s+/g, ' ').trim()} ===`);
      }
      const diag = rb.querySelector('.diagnostic-banner');
      if (diag) {
        textLines.push(`[ERROR] ${diag.innerText.replace(/\s+/g, ' ').trim()}`);
      }
      rb.querySelectorAll('.log-entry').forEach(entry => {
        const time = entry.querySelector('.log-time')?.innerText || '';
        const lvl = (entry.dataset.level || 'info').toUpperCase();
        const msg = entry.querySelector('.log-msg')?.innerText || '';
        textLines.push(`${time} [${lvl}] ${msg}`);
      });
      textLines.push('');
    });

    const fullText = textLines.join('\n').trim();
    if (!fullText) {
      if (window.showToast) window.showToast('info', 'Log is Empty', 'No messages to copy.');
      return;
    }

    navigator.clipboard.writeText(fullText).then(() => {
      if (window.showToast) window.showToast('success', 'Copied', 'Messages log copied to clipboard.');
    }).catch(err => {
      console.error('Clipboard copy failed:', err);
    });
  }

  copySingleRunLog(runBlock, runNum) {
    const textLines = [];
    const header = runBlock.querySelector('.run-header');
    if (header) textLines.push(`=== ${header.innerText.replace(/\s+/g, ' ').trim()} ===`);
    const diag = runBlock.querySelector('.diagnostic-banner');
    if (diag) textLines.push(`[ERROR] ${diag.innerText.replace(/\s+/g, ' ').trim()}`);
    runBlock.querySelectorAll('.log-entry').forEach(entry => {
      const time = entry.querySelector('.log-time')?.innerText || '';
      const lvl = (entry.dataset.level || 'info').toUpperCase();
      const msg = entry.querySelector('.log-msg')?.innerText || '';
      textLines.push(`${time} [${lvl}] ${msg}`);
    });

    const text = textLines.join('\n').trim();
    navigator.clipboard.writeText(text).then(() => {
      if (window.showToast) window.showToast('success', 'Copied', `Run #${runNum} log copied to clipboard.`);
    });
  }

  filterMessages(filterLevel) {
    this.activeMsgFilter = filterLevel;
    document.querySelectorAll('.messages-filter-group [data-msg-filter]').forEach(b => {
      b.classList.toggle('active', b.dataset.msgFilter === filterLevel);
    });

    if (!this.messagesLog) return;
    this.messagesLog.querySelectorAll('.log-entry').forEach(entry => {
      const lvl = entry.dataset.level || 'info';
      if (filterLevel === 'all') {
        entry.style.display = 'flex';
      } else if (filterLevel === 'info') {
        entry.style.display = (lvl === 'info' || lvl === 'success') ? 'flex' : 'none';
      } else {
        entry.style.display = (lvl === filterLevel) ? 'flex' : 'none';
      }
    });
  }

  updateMessageCountsDisplay() {
    const elAll = document.getElementById('msg-filter-count-all');
    if (elAll) elAll.textContent = this.totalMsgCounts.all;
    const elErr = document.getElementById('msg-filter-count-error');
    if (elErr) elErr.textContent = this.totalMsgCounts.error;
    const elWarn = document.getElementById('msg-filter-count-warning');
    if (elWarn) elWarn.textContent = this.totalMsgCounts.warning;
    const elInfo = document.getElementById('msg-filter-count-info');
    if (elInfo) elInfo.textContent = this.totalMsgCounts.info;

    if (this.messagesCountPill) {
      this.messagesCountPill.textContent = this.totalMsgCounts.all;
    }
  }

  formatAlteryxTypeBadge(rawType) {
    if (!rawType || rawType === 'object' || rawType === 'string') {
      return `<span class="type-badge type-string" title="String: Text and character data">String</span>`;
    }
    const t = String(rawType).trim();
    if (t === 'Int64' || t === 'Int32' || t === 'Int16' || t === 'Byte' || t.startsWith('int') || t === 'integer') {
      return `<span class="type-badge type-numeric" title="${t}: Integer numbers">${t === 'integer' ? 'Int64' : t}</span>`;
    }
    if (t === 'Double' || t === 'Float' || t.startsWith('float') || t === 'FixedDecimal') {
      return `<span class="type-badge type-numeric" title="${t}: Decimal floating-point numbers">${t}</span>`;
    }
    if (t === 'Date') {
      return `<span class="type-badge type-date" title="Date: Calendar date (YYYY-MM-DD)">Date</span>`;
    }
    if (t === 'DateTime' || t.startsWith('datetime')) {
      return `<span class="type-badge type-date" title="DateTime: Date and time">DateTime</span>`;
    }
    if (t === 'Time' || t.startsWith('timedelta')) {
      return `<span class="type-badge type-date" title="Time: Time duration (HH:MM:SS)">Time</span>`;
    }
    if (t === 'Bool' || t === 'boolean' || t.startsWith('bool')) {
      return `<span class="type-badge type-bool" title="Bool: True / False boolean">Bool</span>`;
    }
    return `<span class="type-badge type-string" title="${this.escapeHtml(t)}: Text data">${this.escapeHtml(t)}</span>`;
  }

  escapeHtml(str) {
    return String(str || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
}
