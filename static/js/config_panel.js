/**
 * Dynamic Configuration Panel.
 * Generates tailored configuration forms for each tool type and synchronizes node parameters.
 */

class ConfigPanel {
  constructor(canvas) {
    this.canvas = canvas;
    this.currentNode = null;
    this.sampleDatasets = [];

    this.titleEl = document.getElementById('config-tool-title');
    this.iconEl = document.getElementById('config-tool-icon');
    this.categoryEl = document.getElementById('config-tool-category');
    this.contentEl = document.getElementById('config-content');
  }

  setSampleDatasets(datasets) {
    this.sampleDatasets = datasets;
  }

  render(node) {
    this.currentNode = node;

    if (!node) {
      this.titleEl.textContent = 'Configuration';
      this.iconEl.innerHTML = '';
      this.categoryEl.textContent = '';
      this.categoryEl.style.backgroundColor = 'transparent';
      this.contentEl.innerHTML = `
        <div class="empty-state">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="12" cy="12" r="3"></circle>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
          </svg>
          <p>Select a tool on the canvas to configure its settings.</p>
        </div>
      `;
      return;
    }

    const meta = this.canvas.toolRegistry[node.type] || {
      name: node.type,
      category: 'general',
      color: '#38bdf8'
    };

    this.titleEl.textContent = node.name;
    this.iconEl.style.backgroundColor = `${meta.color}25`;
    this.iconEl.style.color = meta.color;
    this.iconEl.innerHTML = window.appPalette ? window.appPalette.getToolSvg(meta.icon) : '';

    this.categoryEl.textContent = meta.category;
    this.categoryEl.style.backgroundColor = `${meta.color}30`;
    this.categoryEl.style.color = meta.color;

    // Upstream columns for smart dropdowns
    const upstreamCols = this.getUpstreamColumns(node.id);

    this.contentEl.innerHTML = '';
    const container = document.createElement('div');

    // General Node Name rename field (if not a container or comment)
    if (node.type !== 'tool_container' && node.type !== 'comment') {
      const nameGroup = document.createElement('div');
      nameGroup.className = 'form-group';
      nameGroup.innerHTML = `
        <label>Tool Label</label>
        <input type="text" class="form-control" id="cfg-node-label" value="${node.name}">
      `;
      container.appendChild(nameGroup);

      nameGroup.querySelector('#cfg-node-label').addEventListener('input', (e) => {
        this.canvas.updateNodeLabel(node.id, e.target.value);
      });
    }

    // Tool-specific fields
    const toolBody = document.createElement('div');
    toolBody.className = 'tool-config-body';

    switch (node.type) {
      case 'tool_container':
        this.renderContainerConfig(toolBody, node);
        break;
      case 'comment':
        this.renderCommentConfig(toolBody, node);
        break;
      case 'input_data':
        this.renderInputDataConfig(toolBody, node);
        break;
      case 'output_data':
        this.renderOutputDataConfig(toolBody, node);
        break;
      case 'browse':
        this.renderBrowseStudio(toolBody, node);
        break;
      case 'select':
        this.renderSelectConfig(toolBody, node, upstreamCols);
        break;
      case 'auto_field':
        this.renderAutoFieldConfig(toolBody, node, upstreamCols);
        break;
      case 'filter':
        this.renderFilterConfig(toolBody, node, upstreamCols);
        break;
      case 'formula':
        this.renderFormulaConfig(toolBody, node, upstreamCols);
        break;
      case 'multi_row_formula':
        this.renderMultiRowFormulaConfig(toolBody, node, upstreamCols);
        break;
      case 'multi_field_formula':
        this.renderMultiFieldFormulaConfig(toolBody, node, upstreamCols);
        break;
      case 'sort':
        this.renderSortConfig(toolBody, node, upstreamCols);
        break;
      case 'clean':
        this.renderCleanConfig(toolBody, node, upstreamCols);
        break;
      case 'unique':
        this.renderUniqueConfig(toolBody, node, upstreamCols);
        break;
      case 'summarize':
        this.renderSummarizeConfig(toolBody, node, upstreamCols);
        break;
      case 'join':
        this.renderJoinConfig(toolBody, node);
        break;
      case 'join_multiple':
      case 'multi_join':
        this.renderJoinMultipleConfig(toolBody, node);
        break;
      case 'union':
        this.renderUnionConfig(toolBody, node);
        break;
      case 'text_input':
        this.renderTextInputConfig(toolBody, node);
        break;
      case 'sample':
        this.renderSampleConfig(toolBody, node, upstreamCols);
        break;
      case 'record_id':
        this.renderRecordIDConfig(toolBody, node, upstreamCols);
        break;
      case 'find_replace':
        this.renderFindReplaceConfig(toolBody, node);
        break;
      case 'transpose':
        this.renderTransposeConfig(toolBody, node, upstreamCols);
        break;
      case 'crosstab':
        this.renderCrossTabConfig(toolBody, node, upstreamCols);
        break;
      case 'text_to_columns':
        this.renderTextToColumnsConfig(toolBody, node, upstreamCols);
        break;
      case 'append_fields':
        this.renderAppendFieldsConfig(toolBody, node);
        break;
      case 'date_time':
        this.renderDateTimeConfig(toolBody, node, upstreamCols);
        break;
      case 'llm_process':
        this.renderLLMProcessConfig(toolBody, node, upstreamCols);
        break;
      default:
        toolBody.innerHTML = `<p class="form-hint">No configuration options for this tool.</p>`;
    }

    container.appendChild(toolBody);
    this.contentEl.appendChild(container);
  }

  getUpstreamColumns(nodeId, inputHandle = 'I') {
    // Look for connection into this node
    const conn = this.canvas.connections.find(c => c.target === nodeId && (!c.targetHandle || c.targetHandle === inputHandle));
    if (!conn) return [];

    const srcNode = this.canvas.nodes.find(n => n.id === conn.source);
    if (!srcNode) return [];

    // Check if we have columns stored in executor data cache via window.appExecutorResults
    if (window.appLastResult && window.appLastResult.node_results) {
      const srcRes = window.appLastResult.node_results[srcNode.id];
      if (srcRes && srcRes.columns && srcRes.columns[conn.sourceHandle || 'O']) {
        return srcRes.columns[conn.sourceHandle || 'O'];
      }
    }

    return [];
  }

  getUpstreamColumnMeta(nodeId, inputHandle = 'I') {
    const conn = this.canvas.connections.find(c => c.target === nodeId && (!c.targetHandle || c.targetHandle === inputHandle));
    if (!conn) return [];

    const srcNode = this.canvas.nodes.find(n => n.id === conn.source);
    if (!srcNode) return [];

    const port = conn.sourceHandle || 'O';
    if (window.appLastResult && window.appLastResult.node_results) {
      const srcRes = window.appLastResult.node_results[srcNode.id];
      if (srcRes) {
        if (srcRes.column_meta && srcRes.column_meta[port]) {
          return srcRes.column_meta[port];
        }
        if (srcRes.columns && srcRes.columns[port]) {
          return srcRes.columns[port].map(c => {
            const low = c.toLowerCase();
            let inferred = 'unknown';
            if (/date|time|timestamp|_dt\b/.test(low)) inferred = 'datetime';
            else if (/\b(id|num|qty|amount|price|cost|sales|revenue|rate|count|total|tax|disc|discount|margin|profit|weight|score)\b|_id$/.test(low)) inferred = 'numeric';
            return { name: c, type: inferred };
          });
        }
      }
    }
    return [];
  }

  getMultiUpstreamInputs(nodeId) {
    if (!this.canvas || !this.canvas.connections) return [];
    const conns = this.canvas.connections.filter(c => c.target === nodeId);
    return conns.map((conn, idx) => {
      const srcNode = this.canvas.nodes ? this.canvas.nodes.find(n => n.id === conn.source) : null;
      let columns = [];
      let columnMeta = [];
      const port = conn.sourceHandle || 'O';
      if (srcNode && window.appLastResult && window.appLastResult.node_results) {
        const srcRes = window.appLastResult.node_results[srcNode.id];
        if (srcRes) {
          if (srcRes.columns && srcRes.columns[port]) {
            columns = srcRes.columns[port];
          }
          if (srcRes.column_meta && srcRes.column_meta[port]) {
            columnMeta = srcRes.column_meta[port];
          } else if (columns.length > 0) {
            columnMeta = columns.map(c => ({ name: c, type: 'unknown' }));
          }
        }
      }
      const label = srcNode ? (srcNode.label || srcNode.name || `${srcNode.type} (#${srcNode.id})`) : `Input #${idx + 1}`;
      return {
        index: idx + 1,
        conn,
        sourceNode: srcNode,
        columns,
        columnMeta,
        label
      };
    });
  }

  setupTableDragAndDrop(tbody, itemsArray, onReorder) {
    if (!tbody || !Array.isArray(itemsArray) || itemsArray.length <= 1) return;
    let draggedIdx = null;

    tbody.querySelectorAll('tr').forEach(tr => {
      tr.setAttribute('draggable', 'true');
      tr.classList.add('row-draggable');

      tr.addEventListener('dragstart', (e) => {
        const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'BUTTON') {
          e.preventDefault();
          return false;
        }

        const rawIdx = tr.dataset.idx !== undefined ? tr.dataset.idx : tr.dataset.sfIdx;
        draggedIdx = parseInt(rawIdx);
        if (isNaN(draggedIdx)) return;

        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', String(draggedIdx));
        tr.classList.add('row-dragging');
      });

      tr.addEventListener('dragover', (e) => {
        if (draggedIdx === null) return;
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        const rect = tr.getBoundingClientRect();
        const relY = e.clientY - rect.top;
        const isUpper = relY < rect.height / 2;

        tbody.querySelectorAll('tr').forEach(other => {
          if (other !== tr) {
            other.classList.remove('drop-target-above', 'drop-target-below');
          }
        });

        if (isUpper) {
          tr.classList.add('drop-target-above');
          tr.classList.remove('drop-target-below');
        } else {
          tr.classList.add('drop-target-below');
          tr.classList.remove('drop-target-above');
        }
      });

      tr.addEventListener('dragleave', (e) => {
        const rect = tr.getBoundingClientRect();
        if (e.clientY < rect.top || e.clientY >= rect.bottom || e.clientX < rect.left || e.clientX >= rect.right) {
          tr.classList.remove('drop-target-above', 'drop-target-below');
        }
      });

      tr.addEventListener('drop', (e) => {
        if (draggedIdx === null) return;
        e.preventDefault();

        const fromIdx = draggedIdx;
        const rawTarget = tr.dataset.idx !== undefined ? tr.dataset.idx : tr.dataset.sfIdx;
        const targetIdx = parseInt(rawTarget);

        const rect = tr.getBoundingClientRect();
        const relY = e.clientY - rect.top;
        const isUpper = relY < rect.height / 2;

        let insertIdx = targetIdx;
        if (!isUpper) {
          insertIdx++;
        }
        if (fromIdx < insertIdx) {
          insertIdx--;
        }

        tbody.querySelectorAll('tr').forEach(r => {
          r.classList.remove('row-dragging', 'drop-target-above', 'drop-target-below');
        });

        draggedIdx = null;

        if (fromIdx !== insertIdx && fromIdx >= 0 && fromIdx < itemsArray.length && insertIdx >= 0 && insertIdx < itemsArray.length) {
          const item = itemsArray.splice(fromIdx, 1)[0];
          itemsArray.splice(insertIdx, 0, item);
          if (typeof onReorder === 'function') {
            onReorder(itemsArray);
          }
        }
      });

      tr.addEventListener('dragend', () => {
        draggedIdx = null;
        tbody.querySelectorAll('tr').forEach(r => {
          r.classList.remove('row-dragging', 'drop-target-above', 'drop-target-below');
        });
      });
    });
  }

  // --------------------------------------------------------------------
  // 1. Input Data
  // --------------------------------------------------------------------
  renderInputDataConfig(container, node) {
    const cfg = node.config || {};
    const filePath = cfg.file_path || '';
    const hasWildcard = (str) => str && (str.includes('*') || str.includes('?'));
    const isWildcard = hasWildcard(filePath);
    const isExcel = cfg.file_type === 'excel' || (filePath && (filePath.endsWith('.xlsx') || filePath.endsWith('.xls') || filePath.endsWith('.xlsm') || filePath.endsWith('.xlsb')));

    container.innerHTML = `
      <div class="form-group">
        <label>Input Mode</label>
        <div class="file-mode-switch">
          <button type="button" class="file-mode-btn ${!isWildcard ? 'active' : ''}" id="btn-mode-single">Single File</button>
          <button type="button" class="file-mode-btn ${isWildcard ? 'active' : ''}" id="btn-mode-wildcard">Multi-File Pattern (* / ?)</button>
        </div>
      </div>

      <div class="form-group" id="cfg-sample-group" style="${isWildcard ? 'display: none;' : ''}">
        <label>Sample Dataset</label>
        <select class="form-control" id="cfg-file-select">
          <option value="">-- Choose Sample Dataset --</option>
          ${cfg.file_path && !this.sampleDatasets.some(d => d.name === cfg.file_path) ? `<option value="${cfg.file_path}" selected>${cfg.original_file_name || cfg.file_path} (Current File)</option>` : ''}
          ${this.sampleDatasets.map(d => `<option value="${d.name}" ${cfg.file_path === d.name ? 'selected' : ''}>${d.name} (${d.type.toUpperCase()}, ${d.size_kb} KB)</option>`).join('')}
        </select>
      </div>

      <div class="form-group">
        <label id="cfg-file-path-label">${isWildcard ? 'Multi-File Pattern (Glob)' : 'File Path'}</label>
        <div style="display: flex; gap: 6px;">
          <input type="text" class="form-control" id="cfg-file-path" value="${cfg.file_path || ''}" placeholder="${isWildcard ? 'e.g. data/sales_*.csv or orders_2024_??.xlsx' : 'e.g. sales_orders.csv or data/report.xlsx'}" style="flex: 1;">
          <button type="button" class="btn btn-secondary" id="btn-browse-in-file" style="white-space: nowrap; padding: 6px 12px;" title="Explore workspace files">📁 Browse...</button>
        </div>
        <div id="cfg-wildcard-badge" class="wildcard-match-badge ${isWildcard ? '' : 'hidden'}"></div>
        <div class="form-hint" id="cfg-file-hint">Use wildcards (* or ?) to automatically stack and union multiple files.</div>
      </div>

      <div class="form-group" id="cfg-upload-group" style="${isWildcard ? 'display: none;' : ''}">
        <label>Or Upload Local File (CSV / Excel / Parquet / JSON)</label>
        <input type="file" class="form-control" id="cfg-file-upload" accept=".csv,.xlsx,.xls,.xlsm,.xlsb,.tsv,.txt,.json,.parquet">
        <div id="cfg-upload-status" class="form-hint" style="margin-top: 4px;">
          ${cfg.file_path ? `<span style="color: var(--color-success); font-weight: 500;">✓ Connected to <b>${cfg.original_file_name || cfg.file_path}</b>${cfg.row_count ? ` (${cfg.row_count.toLocaleString()} rows)` : ''}${cfg.sheet_name ? ` &bull; Sheet: <b>${cfg.sheet_name}</b>` : ''}</span>` : ''}
        </div>
      </div>

      <div class="form-group" id="cfg-sheet-group" style="${isExcel ? '' : 'display: none;'}">
        <label style="display: flex; justify-content: space-between; align-items: center;">
          <span>Excel Sheet</span>
          <span id="cfg-sheet-refresh" style="font-size: 11px; cursor: pointer; color: var(--accent-primary, #0284c7);" title="Refresh available sheets">↻ Refresh</span>
        </label>
        <select class="form-control" id="cfg-sheet-name">
          <option value="0" ${(!cfg.sheet_name || cfg.sheet_name === 0 || cfg.sheet_name === '0') && !cfg.read_all_sheets ? 'selected' : ''}>First Sheet (Default)</option>
          <option value="__all__" ${(cfg.read_all_sheets || cfg.sheet_name === '*' || cfg.sheet_name === 'all') ? 'selected' : ''}>★ All Sheets (Union Together)</option>
          ${cfg.sheet_name && cfg.sheet_name !== 0 && cfg.sheet_name !== '0' && cfg.sheet_name !== '*' && cfg.sheet_name !== '__all__' ? `<option value="${cfg.sheet_name}" selected>${cfg.sheet_name}</option>` : ''}
        </select>
        <div class="form-hint" id="cfg-sheet-hint">Select a specific sheet or union all sheets into one table.</div>
      </div>

      <div class="form-group" id="cfg-csv-options" style="${isExcel ? 'display: none;' : ''}">
        <label>Delimiter</label>
        <select class="form-control" id="cfg-delimiter">
          <option value="," ${(!cfg.delimiter || cfg.delimiter === ',') ? 'selected' : ''}>Comma (,)</option>
          <option value=";" ${cfg.delimiter === ';' ? 'selected' : ''}>Semicolon (;)</option>
          <option value="\\t" ${cfg.delimiter === '\\t' || cfg.delimiter === '\t' ? 'selected' : ''}>Tab (\\t)</option>
          <option value="|" ${cfg.delimiter === '|' ? 'selected' : ''}>Pipe (|)</option>
        </select>
      </div>

      <div class="form-group" id="cfg-quote-group" style="${isExcel ? 'display: none;' : ''}">
        <label>Quote Character</label>
        <input type="text" class="form-control" id="cfg-quote-char" maxlength="1" value="${cfg.quote_char || '"'}">
      </div>

      <div class="form-group" id="cfg-escape-group" style="${isExcel ? 'display: none;' : ''}">
        <label>Escape Character</label>
        <input type="text" class="form-control" id="cfg-escape-char" maxlength="1" value="${cfg.escape_char || ''}" placeholder="None">
      </div>

      <div class="form-group" id="cfg-encoding-group" style="${isExcel ? 'display: none;' : ''}">
        <label>Encoding</label>
        <select class="form-control" id="cfg-encoding">
          <option value="utf-8" ${(!cfg.encoding || cfg.encoding === 'utf-8') ? 'selected' : ''}>UTF-8</option>
          <option value="utf-8-sig" ${cfg.encoding === 'utf-8-sig' ? 'selected' : ''}>UTF-8 with BOM</option>
          <option value="latin1" ${cfg.encoding === 'latin1' ? 'selected' : ''}>Latin-1 (ISO-8859-1)</option>
          <option value="cp1252" ${cfg.encoding === 'cp1252' ? 'selected' : ''}>Windows-1252</option>
          <option value="ascii" ${cfg.encoding === 'ascii' ? 'selected' : ''}>ASCII</option>
        </select>
      </div>

      <div class="form-group" id="cfg-bad-lines-group" style="${isExcel ? 'display: none;' : ''}">
        <label>Bad Lines Handling</label>
        <select class="form-control" id="cfg-bad-lines">
          <option value="error" ${(!cfg.on_bad_lines || cfg.on_bad_lines === 'error') ? 'selected' : ''}>Error (Fail Execution)</option>
          <option value="skip" ${cfg.on_bad_lines === 'skip' ? 'selected' : ''}>Skip Bad Lines</option>
          <option value="warn" ${cfg.on_bad_lines === 'warn' ? 'selected' : ''}>Warn & Skip Bad Lines</option>
        </select>
      </div>

      <div class="form-group">
        <label>Start Data Import at Row</label>
        <input type="number" class="form-control" id="cfg-start-row" min="1" value="${cfg.start_row || 1}">
      </div>

      <div class="form-group">
        <label>Limit Rows (Optional)</label>
        <input type="number" class="form-control" id="cfg-max-rows" placeholder="All rows" value="${cfg.max_rows || ''}">
      </div>

      <div class="form-group">
        <label class="form-check">
          <input type="checkbox" id="cfg-has-header" ${cfg.has_header !== false ? 'checked' : ''}>
          <span>First row contains headers</span>
        </label>
      </div>

      <div class="form-group">
        <label class="form-check">
          <input type="checkbox" id="cfg-trim-headers" ${cfg.trim_headers !== false ? 'checked' : ''}>
          <span>Trim whitespace from header field names</span>
        </label>
      </div>

      <div class="form-group">
        <label>Output File Name as Field</label>
        <select class="form-control" id="cfg-filename-field">
          <option value="none" ${(!cfg.output_file_name_mode || cfg.output_file_name_mode === 'none') && (!cfg.output_filename_field || cfg.output_filename_field === 'none') ? 'selected' : ''}>No (None)</option>
          <option value="filename_only" ${cfg.output_file_name_mode === 'filename_only' || cfg.output_filename_field === 'name_only' || cfg.output_filename_field === 'name' || cfg.output_filename_field === 'filename_only' ? 'selected' : ''}>File Name Only (FileName)</option>
          <option value="full_path" ${cfg.output_file_name_mode === 'full_path' || cfg.output_filename_field === 'full_path' || cfg.output_filename_field === 'path' ? 'selected' : ''}>Full Path (FilePath)</option>
          <option value="both" ${cfg.output_file_name_mode === 'both' || cfg.output_filename_field === 'both' ? 'selected' : ''}>Both (FileName & FilePath)</option>
        </select>
        <div class="form-hint">Appends source file origin to each record, matching Alteryx standard.</div>
      </div>
    `;

    // Helpers
    const toggleFileTypeUI = (targetPath) => {
      const isEx = targetPath && (targetPath.endsWith('.xlsx') || targetPath.endsWith('.xls') || targetPath.endsWith('.xlsm'));
      const isWc = hasWildcard(targetPath);
      container.querySelector('#cfg-sheet-group').style.display = isEx ? '' : 'none';
      container.querySelector('#cfg-csv-options').style.display = isEx ? 'none' : '';
      container.querySelector('#cfg-quote-group').style.display = isEx ? 'none' : '';
      container.querySelector('#cfg-escape-group').style.display = isEx ? 'none' : '';
      container.querySelector('#cfg-encoding-group').style.display = isEx ? 'none' : '';
      container.querySelector('#cfg-bad-lines-group').style.display = isEx ? 'none' : '';
      if (isEx) {
        fetchExcelSheets(targetPath);
      }
      updateWildcardPreview(targetPath);
    };

    let wildcardTimeout = null;
    const updateWildcardPreview = (pattern) => {
      clearTimeout(wildcardTimeout);
      const badge = container.querySelector('#cfg-wildcard-badge');
      if (!badge) return;
      if (!pattern || (!pattern.includes('*') && !pattern.includes('?'))) {
        badge.className = 'wildcard-match-badge hidden';
        badge.innerHTML = '';
        return;
      }
      badge.className = 'wildcard-match-badge empty';
      badge.innerHTML = '<span>🔍 Searching matching files...</span>';
      wildcardTimeout = setTimeout(async () => {
        try {
          const res = await fetch(`/api/wildcard-preview?pattern=${encodeURIComponent(pattern)}`);
          const json = await res.json();
          if (json.success) {
            if (json.count > 0) {
              badge.className = 'wildcard-match-badge matched';
              badge.innerHTML = `<span>✓ <b>${json.count}</b> matching file${json.count > 1 ? 's' : ''} found${json.files && json.files.length ? `: ${json.files.slice(0, 3).join(', ')}${json.has_more ? ' ...' : ''}` : ''}</span>`;
            } else {
              badge.className = 'wildcard-match-badge empty';
              badge.innerHTML = `<span>⚠ 0 files match pattern '<b>${pattern}</b>' in workspace</span>`;
            }
          }
        } catch (err) {
          badge.className = 'wildcard-match-badge hidden';
        }
      }, 250);
    };

    const fetchExcelSheets = async (targetPath) => {
      if (!targetPath || (!targetPath.endsWith('.xlsx') && !targetPath.endsWith('.xls') && !targetPath.endsWith('.xlsm'))) {
        return;
      }
      const sheetSelect = container.querySelector('#cfg-sheet-name');
      const sheetHint = container.querySelector('#cfg-sheet-hint');
      if (!sheetSelect) return;
      if (sheetHint) sheetHint.textContent = 'Loading sheets from workbook...';
      try {
        const res = await fetch(`/api/excel-sheets?file=${encodeURIComponent(targetPath)}`);
        const json = await res.json();
        if (json.success && Array.isArray(json.sheets) && json.sheets.length > 0) {
          const curSheet = node.config.sheet_name;
          const curAll = node.config.read_all_sheets;
          sheetSelect.innerHTML = `
            <option value="0" ${(!curSheet || curSheet === 0 || curSheet === '0') && !curAll ? 'selected' : ''}>First Sheet (Default: ${json.sheets[0]})</option>
            <option value="__all__" ${(curAll || curSheet === '*' || curSheet === 'all') ? 'selected' : ''}>★ All Sheets (Union Together)</option>
            ${json.sheets.map(s => `<option value="${s}" ${(!curAll && curSheet === s) ? 'selected' : ''}>Sheet: ${s}</option>`).join('')}
          `;
          if (sheetHint) sheetHint.innerHTML = `<span style="color: var(--color-success)">✓ Discovered ${json.sheets.length} sheet${json.sheets.length > 1 ? 's' : ''}</span>`;
        } else {
          if (sheetHint) sheetHint.textContent = 'Select a specific sheet or union all sheets.';
        }
      } catch (err) {
        if (sheetHint) sheetHint.textContent = 'Select a specific sheet or union all sheets.';
      }
    };

    // Mode switch logic
    const btnSingle = container.querySelector('#btn-mode-single');
    const btnWildcard = container.querySelector('#btn-mode-wildcard');
    const sampleGroup = container.querySelector('#cfg-sample-group');
    const uploadGroup = container.querySelector('#cfg-upload-group');
    const pathLabel = container.querySelector('#cfg-file-path-label');
    const filePathInput = container.querySelector('#cfg-file-path');

    btnSingle.addEventListener('click', () => {
      btnSingle.classList.add('active');
      btnWildcard.classList.remove('active');
      sampleGroup.style.display = '';
      uploadGroup.style.display = '';
      pathLabel.textContent = 'File Path';
      filePathInput.placeholder = 'e.g. sales_orders.csv or data/report.xlsx';
      if (filePathInput.value.includes('*') || filePathInput.value.includes('?')) {
        const cleaned = filePathInput.value.replace(/[\*\?]/g, '').replace(/__+/g, '_');
        filePathInput.value = cleaned;
        node.config.file_path = cleaned;
        toggleFileTypeUI(cleaned);
        this.canvas.onWorkflowChange();
      }
    });

    btnWildcard.addEventListener('click', () => {
      btnWildcard.classList.add('active');
      btnSingle.classList.remove('active');
      sampleGroup.style.display = 'none';
      uploadGroup.style.display = 'none';
      pathLabel.textContent = 'Multi-File Pattern (Glob)';
      filePathInput.placeholder = 'e.g. data/sales_*.csv or orders_2024_??.xlsx';
      if (!filePathInput.value.includes('*') && !filePathInput.value.includes('?')) {
        const cur = filePathInput.value.trim();
        if (cur) {
          const dotIdx = cur.lastIndexOf('.');
          if (dotIdx > 0) {
            filePathInput.value = cur.slice(0, dotIdx) + '_*' + cur.slice(dotIdx);
          } else {
            filePathInput.value = cur + '_*';
          }
          node.config.file_path = filePathInput.value;
          toggleFileTypeUI(filePathInput.value);
          this.canvas.onWorkflowChange();
        }
      }
    });

    // Inputs & listeners
    const fileSelect = container.querySelector('#cfg-file-select');
    fileSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      if (val) {
        node.config.file_path = val;
        filePathInput.value = val;
        node.config.file_type = (val.endsWith('.xlsx') || val.endsWith('.xls') || val.endsWith('.xlsm')) ? 'excel' : 'csv';
        toggleFileTypeUI(val);
        this.canvas.onWorkflowChange();
      }
    });

    filePathInput.addEventListener('input', (e) => {
      const val = e.target.value;
      node.config.file_path = val;
      const isEx = val.endsWith('.xlsx') || val.endsWith('.xls') || val.endsWith('.xlsm');
      node.config.file_type = isEx ? 'excel' : 'csv';
      const isWc = hasWildcard(val);
      btnWildcard.classList.toggle('active', isWc);
      btnSingle.classList.toggle('active', !isWc);
      sampleGroup.style.display = isWc ? 'none' : '';
      uploadGroup.style.display = isWc ? 'none' : '';
      pathLabel.textContent = isWc ? 'Multi-File Pattern (Glob)' : 'File Path';
      toggleFileTypeUI(val);
      this.canvas.onWorkflowChange();
    });

    const btnBrowseIn = container.querySelector('#btn-browse-in-file');
    if (btnBrowseIn) {
      btnBrowseIn.addEventListener('click', () => {
        if (window.fileExplorer) {
          window.fileExplorer.open({
            title: 'Select Input Data File or Workspace Path',
            mode: 'all',
            initialPath: node.config.file_path || '',
            onSelect: (selectedPath) => {
              node.config.file_path = selectedPath;
              filePathInput.value = selectedPath;
              node.config.file_type = (selectedPath.endsWith('.xlsx') || selectedPath.endsWith('.xls') || selectedPath.endsWith('.xlsm')) ? 'excel' : 'csv';
              toggleFileTypeUI(selectedPath);
              this.canvas.onWorkflowChange();
            }
          });
        }
      });
    }

    const fileUpload = container.querySelector('#cfg-file-upload');
    const uploadStatus = container.querySelector('#cfg-upload-status');

    fileUpload.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      uploadStatus.textContent = 'Uploading...';
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/api/upload', { method: 'POST', body: formData });
        const json = await res.json();
        if (json.success) {
          uploadStatus.innerHTML = `<span style="color: var(--color-success)">✓ Uploaded ${json.file_name} (${json.row_count} rows)</span>`;
          node.config.file_path = json.file_name;
          filePathInput.value = json.file_name;
          node.config.file_type = json.file_type;
          toggleFileTypeUI(json.file_name);
          this.canvas.onWorkflowChange();
        } else {
          uploadStatus.innerHTML = `<span style="color: var(--color-error)">Upload failed: ${json.error}</span>`;
        }
      } catch (err) {
        uploadStatus.innerHTML = `<span style="color: var(--color-error)">Upload error: ${err.message}</span>`;
      }
    });

    const sheetSelect = container.querySelector('#cfg-sheet-name');
    if (sheetSelect) {
      sheetSelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (val === '__all__') {
          node.config.read_all_sheets = true;
          node.config.sheet_name = '*';
        } else {
          node.config.read_all_sheets = false;
          node.config.sheet_name = val;
        }
        this.canvas.onWorkflowChange();
      });
    }

    const refreshSheetsBtn = container.querySelector('#cfg-sheet-refresh');
    if (refreshSheetsBtn) {
      refreshSheetsBtn.addEventListener('click', () => {
        fetchExcelSheets(node.config.file_path);
      });
    }

    container.querySelector('#cfg-has-header').addEventListener('change', (e) => {
      node.config.has_header = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-trim-headers').addEventListener('change', (e) => {
      node.config.trim_headers = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-delimiter').addEventListener('change', (e) => {
      node.config.delimiter = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-quote-char').addEventListener('input', (e) => {
      node.config.quote_char = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-escape-char').addEventListener('input', (e) => {
      node.config.escape_char = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-encoding').addEventListener('change', (e) => {
      node.config.encoding = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-bad-lines').addEventListener('change', (e) => {
      node.config.on_bad_lines = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-start-row').addEventListener('input', (e) => {
      node.config.start_row = parseInt(e.target.value) || 1;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-filename-field').addEventListener('change', (e) => {
      node.config.output_file_name_mode = e.target.value;
      node.config.output_filename_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-max-rows').addEventListener('input', (e) => {
      node.config.max_rows = e.target.value ? parseInt(e.target.value) : null;
      this.canvas.onWorkflowChange();
    });

    // Initial triggers
    if (isWildcard) {
      updateWildcardPreview(filePath);
    }
    if (isExcel) {
      fetchExcelSheets(filePath);
    }
  }

  // --------------------------------------------------------------------
  // 2. Output Data
  // --------------------------------------------------------------------
  renderOutputDataConfig(container, node) {
    const cfg = node.config || {};
    const upstreamCols = this.getUpstreamColumns(node.id);
    const lastResult = (window.appLastResult && window.appLastResult.node_results) ? window.appLastResult.node_results[node.id] : null;
    const writtenFiles = (lastResult && lastResult.written_files) ? lastResult.written_files : [];

    const formatBytes = (bytes) => {
      if (!bytes || bytes === 0) return '0 B';
      const k = 1024;
      const sizes = ['B', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    };

    let writtenFilesHtml = '';
    if (writtenFiles.length > 0) {
      writtenFilesHtml = `
        <div style="margin-bottom: 14px; padding: 12px; background: rgba(34, 197, 94, 0.08); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px;">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 12px; color: #22c55e;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>
              <span>Output Generated (${writtenFiles.length} file${writtenFiles.length > 1 ? 's' : ''})</span>
            </div>
            <button type="button" class="btn btn-secondary btn-open-written-folder" style="padding: 2px 8px; font-size: 11px; height: 24px; gap: 4px;" title="Open containing folder in Windows Explorer">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
              <span>Open Folder</span>
            </button>
          </div>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            ${writtenFiles.map((f, idx) => {
              const fname = (typeof f === 'object' && f.filename) ? f.filename : String(f).replace(/\\/g, '/').split('/').pop();
              const fpath = (typeof f === 'object' && f.path) ? f.path : (typeof f === 'string' ? f : fname);
              const recs = (typeof f === 'object' && f.records !== undefined) ? `${f.records.toLocaleString()} rows` : '';
              const size = (typeof f === 'object' && f.size_bytes !== undefined) ? formatBytes(f.size_bytes) : '';
              const metaText = [recs, size].filter(Boolean).join(' • ');

              return `
                <div style="display: flex; align-items: center; justify-content: space-between; padding: 6px 8px; background: var(--bg-card); border: 1px solid var(--border-subtle); border-radius: 6px; font-size: 11px;">
                  <div style="min-width: 0; flex: 1; margin-right: 8px;">
                    <div style="font-weight: 600; color: var(--text-main); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${fname}">
                      📄 ${fname}
                    </div>
                    ${metaText ? `<div style="font-size: 10px; color: var(--text-secondary); margin-top: 1px;">${metaText}</div>` : ''}
                  </div>
                  <div style="display: flex; gap: 4px; flex-shrink: 0;">
                    <button type="button" class="btn btn-secondary btn-reveal-file" data-filepath="${encodeURIComponent(fpath)}" style="padding: 2px 7px; font-size: 10px; height: 22px; gap: 3px;" title="Show and select this file in Windows Explorer">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
                      <span>Show</span>
                    </button>
                    <a href="/data/outputs/${fname}" download class="btn btn-secondary" style="padding: 2px 7px; font-size: 10px; height: 22px; text-decoration: none; color: var(--text-main); display: inline-flex; align-items: center; gap: 3px;" title="Download file to browser">
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                      <span>Get</span>
                    </a>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>
      `;
    }

    const currentFmt = cfg.format || 'csv';

    container.innerHTML = `
      ${writtenFilesHtml}
      <div class="form-group">
        <label>Export Format</label>
        <select class="form-control" id="cfg-out-format">
          <option value="csv" ${currentFmt === 'csv' ? 'selected' : ''}>CSV (.csv)</option>
          <option value="excel" ${currentFmt === 'excel' ? 'selected' : ''}>Excel (.xlsx)</option>
          <option value="tsv" ${currentFmt === 'tsv' ? 'selected' : ''}>Tab-Delimited TSV (.tsv)</option>
          <option value="json" ${currentFmt === 'json' ? 'selected' : ''}>JSON (.json)</option>
          <option value="parquet" ${currentFmt === 'parquet' ? 'selected' : ''}>Parquet (.parquet)</option>
        </select>
      </div>

      <div class="form-group">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <label style="margin-bottom: 0;">Output Folder / Directory Path</label>
          <button type="button" class="btn btn-secondary" id="btn-open-dir-explorer" style="padding: 2px 8px; font-size: 11px; height: 22px; gap: 4px;" title="Open this folder in Windows Explorer">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            <span>Open in Explorer</span>
          </button>
        </div>
        <div style="display: flex; gap: 6px;">
          <input type="text" class="form-control" id="cfg-out-dir" value="${cfg.output_dir || ''}" placeholder="e.g. data/outputs or C:\\Exports" style="flex: 1;">
          <button type="button" class="btn btn-secondary" id="btn-browse-out-dir" style="white-space: nowrap; padding: 6px 12px; gap: 4px;" title="Browse Folders with Windows Explorer">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
            <span>Browse...</span>
          </button>
        </div>
        <div class="form-hint">Destination directory on disk (leave blank to use default data/outputs).</div>
      </div>

      <div class="form-group">
        <label>Base File Name / Destination</label>
        <div style="display: flex; gap: 6px;">
          <input type="text" class="form-control" id="cfg-out-filename" value="${cfg.filename || 'export_result'}" placeholder="e.g. processed_orders" style="flex: 1;">
          <button type="button" class="btn btn-secondary" id="btn-browse-out-file" style="white-space: nowrap; padding: 6px 12px; gap: 4px;" title="Save As / Pick destination with Windows Explorer">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg>
            <span>Save As...</span>
          </button>
        </div>
      </div>

      <div class="form-group" id="cfg-out-sheet-group" style="${currentFmt === 'excel' ? '' : 'display: none;'}">
        <label>Excel Sheet Name</label>
        <input type="text" class="form-control" id="cfg-out-sheet-name" value="${cfg.sheet_name || 'Sheet1'}">
      </div>

      <div class="form-group" id="cfg-out-delimiter-group" style="${(currentFmt === 'csv' || currentFmt === 'tsv') ? '' : 'display: none;'}">
        <label>Delimiter</label>
        <select class="form-control" id="cfg-out-delimiter">
          <option value="," ${(!cfg.delimiter || cfg.delimiter === ',') ? 'selected' : ''}>Comma (,)</option>
          <option value=";" ${cfg.delimiter === ';' ? 'selected' : ''}>Semicolon (;)</option>
          <option value="\\t" ${cfg.delimiter === '\\t' || cfg.delimiter === '\t' ? 'selected' : ''}>Tab (\\t)</option>
          <option value="|" ${cfg.delimiter === '|' ? 'selected' : ''}>Pipe (|)</option>
        </select>
      </div>

      <div class="form-group">
        <label>Output / Write Mode</label>
        <select class="form-control" id="cfg-out-write-mode">
          <option value="overwrite" ${(!cfg.write_mode || cfg.write_mode === 'overwrite') ? 'selected' : ''}>Create New / Overwrite File</option>
          <option value="append" ${cfg.write_mode === 'append' ? 'selected' : ''}>Append Records to Existing File</option>
          <option value="create_new" ${cfg.write_mode === 'create_new' ? 'selected' : ''}>Create New (Fail if File Exists)</option>
        </select>
      </div>

      <div id="cfg-out-csv-text-options" style="${(currentFmt === 'csv' || currentFmt === 'tsv') ? '' : 'display: none;'}">
        <div class="form-group">
          <label>Quote Mode</label>
          <select class="form-control" id="cfg-out-quote-mode">
            <option value="minimal" ${(!cfg.quote_mode || cfg.quote_mode === 'minimal') ? 'selected' : ''}>Minimal Quotes (Only when needed)</option>
            <option value="all" ${cfg.quote_mode === 'all' ? 'selected' : ''}>Quote All Fields</option>
            <option value="none" ${cfg.quote_mode === 'none' ? 'selected' : ''}>Never Quote</option>
            <option value="nonnumeric" ${cfg.quote_mode === 'nonnumeric' ? 'selected' : ''}>Quote Non-Numeric Strings</option>
          </select>
        </div>

        <div class="form-group">
          <label>Encoding</label>
          <select class="form-control" id="cfg-out-encoding">
            <option value="utf-8" ${(!cfg.encoding || cfg.encoding === 'utf-8') ? 'selected' : ''}>UTF-8</option>
            <option value="utf-8-sig" ${cfg.encoding === 'utf-8-sig' ? 'selected' : ''}>UTF-8 with BOM (Alteryx/Excel Compat)</option>
            <option value="latin1" ${cfg.encoding === 'latin1' ? 'selected' : ''}>Latin-1 (ISO-8859-1)</option>
          </select>
        </div>

        <div class="form-group">
          <label>Line Endings</label>
          <select class="form-control" id="cfg-out-line-ending">
            <option value="crlf" ${(!cfg.line_ending || cfg.line_ending === 'crlf') ? 'selected' : ''}>Windows (CRLF - \\r\\n)</option>
            <option value="lf" ${cfg.line_ending === 'lf' ? 'selected' : ''}>Unix / Mac (LF - \\n)</option>
          </select>
        </div>
      </div>

      <div class="form-group">
        <label class="form-check">
          <input type="checkbox" id="cfg-take-filename" ${cfg.take_filename_from_field ? 'checked' : ''}>
          <span>Take File / Table Name from Field (Dynamic Partitioning)</span>
        </label>
      </div>

      <div id="cfg-dynamic-file-box" style="${cfg.take_filename_from_field ? '' : 'display: none;'} padding: 10px; background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: 6px; margin-bottom: 12px;">
        <div class="form-group">
          <label>Field Containing File Name</label>
          <select class="form-control" id="cfg-dyn-file-field">
            ${upstreamCols.length > 0 
              ? upstreamCols.map(c => `<option value="${c}" ${cfg.filename_field === c ? 'selected' : ''}>${c}</option>`).join('')
              : `<option value="${cfg.filename_field || ''}">${cfg.filename_field || 'Select field'}</option>`}
          </select>
        </div>

        <div class="form-group">
          <label>Action</label>
          <select class="form-control" id="cfg-dyn-file-action">
            <option value="change_entire" ${(!cfg.filename_action || cfg.filename_action === 'change_entire') ? 'selected' : ''}>Change Entire File Name</option>
            <option value="append_suffix" ${cfg.filename_action === 'append_suffix' ? 'selected' : ''}>Append Suffix to File Name</option>
            <option value="prepend_prefix" ${cfg.filename_action === 'prepend_prefix' ? 'selected' : ''}>Prepend Prefix to File Name</option>
          </select>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-check">
            <input type="checkbox" id="cfg-dyn-drop-field" ${cfg.drop_filename_field ? 'checked' : ''}>
            <span>Drop partitioning field from exported file</span>
          </label>
        </div>
      </div>

      <div class="form-group" style="margin-top: 16px; display: flex; flex-direction: column; gap: 8px;">
        <button id="btn-cfg-download" class="btn btn-primary" style="width: 100%; justify-content: center;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          <span>Download Output File</span>
        </button>
      </div>
    `;

    // Wire written files action buttons
    container.querySelectorAll('.btn-reveal-file').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const rawPath = decodeURIComponent(e.currentTarget.getAttribute('data-filepath') || '');
        if (!rawPath) return;
        fetch('/api/open-in-explorer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: rawPath })
        })
        .then(r => r.json())
        .then(data => {
          if (data.success && window.showToast) {
            window.showToast('success', 'Windows Explorer', `Revealed '${rawPath.split(/[\\/]/).pop()}' in Explorer.`);
          } else if (!data.success && window.showToast) {
            window.showToast('error', 'Explorer Error', data.error || 'Could not open in Windows Explorer.');
          }
        })
        .catch(err => {
          if (window.showToast) window.showToast('error', 'Explorer Error', err.message);
        });
      });
    });

    const btnOpenWrittenFolder = container.querySelector('.btn-open-written-folder');
    if (btnOpenWrittenFolder) {
      btnOpenWrittenFolder.addEventListener('click', () => {
        const dir = node.config.output_dir || 'data/outputs';
        fetch('/api/open-in-explorer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: dir })
        })
        .then(r => r.json())
        .then(data => {
          if (data.success && window.showToast) {
            window.showToast('success', 'Windows Explorer', 'Opened output directory in Windows Explorer.');
          } else if (!data.success && window.showToast) {
            window.showToast('error', 'Explorer Error', data.error || 'Could not open folder.');
          }
        })
        .catch(err => {
          if (window.showToast) window.showToast('error', 'Explorer Error', err.message);
        });
      });
    }

    const formatSelect = container.querySelector('#cfg-out-format');
    const sheetGroup = container.querySelector('#cfg-out-sheet-group');
    const delimGroup = container.querySelector('#cfg-out-delimiter-group');
    const csvTextOpts = container.querySelector('#cfg-out-csv-text-options');

    formatSelect.addEventListener('change', (e) => {
      const fmt = e.target.value;
      node.config.format = fmt;
      sheetGroup.style.display = (fmt === 'excel') ? '' : 'none';
      delimGroup.style.display = (fmt === 'csv' || fmt === 'tsv') ? '' : 'none';
      csvTextOpts.style.display = (fmt === 'csv' || fmt === 'tsv') ? '' : 'none';
      this.canvas.onWorkflowChange();
    });

    const delimSelect = container.querySelector('#cfg-out-delimiter');
    if (delimSelect) {
      delimSelect.addEventListener('change', (e) => {
        node.config.delimiter = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    const outDirInput = container.querySelector('#cfg-out-dir');
    if (outDirInput) {
      outDirInput.addEventListener('input', (e) => {
        node.config.output_dir = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    const btnOpenDirExplorer = container.querySelector('#btn-open-dir-explorer');
    if (btnOpenDirExplorer) {
      btnOpenDirExplorer.addEventListener('click', () => {
        const dir = (node.config.output_dir || '').trim() || 'data/outputs';
        fetch('/api/open-in-explorer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: dir })
        })
        .then(r => r.json())
        .then(data => {
          if (data.success && window.showToast) {
            window.showToast('success', 'Windows Explorer', `Opened folder '${dir}' in Explorer.`);
          } else if (!data.success && window.showToast) {
            window.showToast('warning', 'Folder Not Found', data.error || 'Folder could not be opened.');
          }
        })
        .catch(err => {
          if (window.showToast) window.showToast('error', 'Explorer Error', err.message);
        });
      });
    }

    const btnBrowseOutDir = container.querySelector('#btn-browse-out-dir');
    if (btnBrowseOutDir) {
      btnBrowseOutDir.addEventListener('click', async () => {
        try {
          const resp = await fetch('/api/dialog/pick-folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initial_dir: node.config.output_dir || '' })
          });
          const data = await resp.json();
          if (data && data.success && data.path) {
            node.config.output_dir = data.path;
            if (outDirInput) outDirInput.value = data.path;
            this.canvas.onWorkflowChange();
            if (window.showToast) window.showToast('success', 'Folder Selected', `Target directory set to '${data.path}'.`);
            return;
          } else if (data && data.cancelled) {
            return;
          }
        } catch (err) {
          console.warn('Native folder picker not available, falling back to web file explorer', err);
        }

        if (window.fileExplorer) {
          window.fileExplorer.open({
            title: 'Select Output Folder / Directory',
            mode: 'directory',
            initialPath: node.config.output_dir || '',
            onSelect: (selectedPath) => {
              node.config.output_dir = selectedPath;
              if (outDirInput) outDirInput.value = selectedPath;
              this.canvas.onWorkflowChange();
            }
          });
        }
      });
    }

    const filenameInput = container.querySelector('#cfg-out-filename');
    if (filenameInput) {
      filenameInput.addEventListener('input', (e) => {
        node.config.filename = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    const btnBrowseOutFile = container.querySelector('#btn-browse-out-file');
    if (btnBrowseOutFile) {
      btnBrowseOutFile.addEventListener('click', async () => {
        try {
          const currentFormat = node.config.format || 'csv';
          const resp = await fetch('/api/dialog/pick-output-path', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              format: currentFormat,
              default_name: node.config.filename || 'export_result',
              initial_dir: node.config.output_dir || ''
            })
          });
          const data = await resp.json();
          if (data && data.success && data.path) {
            if (data.filename) {
              node.config.filename = data.filename;
              if (filenameInput) filenameInput.value = data.filename;
            }
            if (data.directory) {
              node.config.output_dir = data.directory;
              if (outDirInput) outDirInput.value = data.directory;
            }
            if (data.detected_format && data.detected_format !== currentFormat) {
              node.config.format = data.detected_format;
              formatSelect.value = data.detected_format;
              sheetGroup.style.display = (data.detected_format === 'excel') ? '' : 'none';
              delimGroup.style.display = (data.detected_format === 'csv' || data.detected_format === 'tsv') ? '' : 'none';
              csvTextOpts.style.display = (data.detected_format === 'csv' || data.detected_format === 'tsv') ? '' : 'none';
            }
            this.canvas.onWorkflowChange();
            if (window.showToast) {
              window.showToast('success', 'Destination Set', `Output file set to '${data.full_filename}' in '${data.directory}'.`);
            }
            return;
          } else if (data && data.cancelled) {
            return;
          }
        } catch (err) {
          console.warn('Native Save As dialog not available, falling back to web file explorer', err);
        }

        if (window.fileExplorer) {
          window.fileExplorer.open({
            title: 'Select Output File / Destination',
            mode: 'all',
            initialPath: node.config.output_dir || '',
            defaultFilename: node.config.filename || 'export_result',
            onSelect: (selectedPath, meta) => {
              if (meta && meta.targetName) {
                node.config.filename = meta.targetName;
                if (filenameInput) filenameInput.value = meta.targetName;
              } else if (meta && meta.selectedItem && !meta.selectedItem.isFolder) {
                node.config.filename = meta.selectedItem.name;
                if (filenameInput) filenameInput.value = meta.selectedItem.name;
              } else {
                node.config.filename = selectedPath;
                if (filenameInput) filenameInput.value = selectedPath;
              }
              if (meta && meta.currentPath) {
                node.config.output_dir = meta.currentPath;
                if (outDirInput) outDirInput.value = meta.currentPath;
              }
              this.canvas.onWorkflowChange();
            }
          });
        }
      });
    }

    container.querySelector('#cfg-out-sheet-name').addEventListener('input', (e) => {
      node.config.sheet_name = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-out-write-mode').addEventListener('change', (e) => {
      node.config.write_mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-out-quote-mode').addEventListener('change', (e) => {
      node.config.quote_mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-out-encoding').addEventListener('change', (e) => {
      node.config.encoding = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-out-line-ending').addEventListener('change', (e) => {
      node.config.line_ending = e.target.value;
      this.canvas.onWorkflowChange();
    });

    const takeFileChk = container.querySelector('#cfg-take-filename');
    const dynBox = container.querySelector('#cfg-dynamic-file-box');
    takeFileChk.addEventListener('change', (e) => {
      node.config.take_filename_from_field = e.target.checked;
      dynBox.style.display = e.target.checked ? '' : 'none';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dyn-file-field').addEventListener('change', (e) => {
      node.config.filename_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dyn-file-action').addEventListener('change', (e) => {
      node.config.filename_action = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dyn-drop-field').addEventListener('change', (e) => {
      node.config.drop_filename_field = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-cfg-download').addEventListener('click', () => {
      const fmt = node.config.format || 'csv';
      const rawName = (node.config.filename || 'export_result').trim();
      const ext = fmt === 'excel' ? 'xlsx' : fmt;
      const fullFilename = rawName.includes('.') ? rawName : `${rawName}.${ext}`;
      const delim = encodeURIComponent(node.config.delimiter || ',');
      let url = `/api/export/${node.id}?port=O&format=${fmt}&filename=${encodeURIComponent(fullFilename)}&delimiter=${delim}`;
      if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
      if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
      window.location.href = url;
    });
  }

  // --------------------------------------------------------------------
  // Browse Tool - Data Profiling Studio
  // --------------------------------------------------------------------
  async renderBrowseStudio(container, node) {
    container.innerHTML = `
      <div class="browse-studio-loading" style="padding: 24px 16px; text-align: center;">
        <div class="spinner-small" style="margin: 12px auto; width: 28px; height: 28px; border: 3px solid rgba(16, 185, 129, 0.2); border-top-color: #10b981; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
        <p style="color: var(--text-muted); font-size: 12px;">Analyzing dataset & compiling profiling studio...</p>
      </div>
    `;

    try {
      let url = `/api/node-profile/${node.id}?port=O`;
      if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
      if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;

      const res = await fetch(url);
      const data = await res.json();

      if (!data || !data.available || !data.columns || data.columns.length === 0) {
        container.innerHTML = `
          <div class="browse-studio-empty" style="text-align: center; padding: 28px 16px;">
            <div style="width: 56px; height: 56px; margin: 0 auto 12px; border-radius: 12px; background: rgba(16, 185, 129, 0.15); display: flex; align-items: center; justify-content: center; color: #10b981;">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
              </svg>
            </div>
            <h4 style="font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px;">Browse Profiling Studio</h4>
            <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px; line-height: 1.4;">
              ${this.escapeHtml(data.message || 'Run the workflow to populate deep data quality diagnostics, distribution histograms, and outlier detection.')}
            </p>
            <button type="button" class="btn btn-primary" id="btn-browse-run-wf" style="font-size: 12px; padding: 7px 18px; margin: 0 auto; display: inline-flex; align-items: center; gap: 6px;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              <span>Run Workflow (Ctrl+R)</span>
            </button>
          </div>
        `;
        const runBtn = container.querySelector('#btn-browse-run-wf');
        if (runBtn) {
          runBtn.addEventListener('click', () => {
            const mainRunBtn = document.getElementById('btn-run');
            if (mainRunBtn) mainRunBtn.click();
          });
        }
        return;
      }

      this._renderBrowseStudioContent(container, node, data);
    } catch (err) {
      container.innerHTML = `
        <div class="browse-studio-error" style="padding: 16px; color: var(--color-error); font-size: 12px;">
          Error loading profile: ${this.escapeHtml(err.message)}
        </div>
      `;
    }
  }

  _renderBrowseStudioContent(container, node, data) {
    const totalRows = data.total_rows || 0;
    const totalCols = data.total_columns || 0;
    const healthScore = data.composite_health_score !== undefined ? data.composite_health_score : 100;
    const healthGrade = data.health_grade || 'A';
    const memFormatted = data.memory_formatted || '0 B';
    const missingPct = data.missing_cells_pct !== undefined ? data.missing_cells_pct : 0;
    const dupPct = data.duplicate_rows_pct !== undefined ? data.duplicate_rows_pct : 0;
    const keyCandidates = data.key_candidates || [];

    const gradeColorMap = {
      'A': '#22c55e',
      'B': '#3b82f6',
      'C': '#f59e0b',
      'D': '#f97316',
      'F': '#ef4444'
    };
    const gradeColor = gradeColorMap[healthGrade] || '#3b82f6';

    container.innerHTML = `
      <div class="browse-studio-root">
        <!-- Studio Header & Overall Health -->
        <div class="browse-health-banner" style="display: flex; align-items: center; gap: 12px; padding: 12px; background: var(--bg-surface-elevated, #1e293b); border-radius: 8px; border: 1px solid var(--border-subtle); margin-bottom: 12px;">
          <div class="browse-grade-circle" style="width: 46px; height: 46px; border-radius: 50%; border: 3px solid ${gradeColor}; display: flex; flex-direction: column; align-items: center; justify-content: center; flex-shrink: 0; background: ${gradeColor}15;">
            <span style="font-size: 18px; font-weight: 800; color: ${gradeColor}; line-height: 1;">${healthGrade}</span>
            <span style="font-size: 9px; color: var(--text-muted); font-weight: 600;">GRADE</span>
          </div>
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px;">
              <span style="font-size: 13px; font-weight: 700; color: var(--text-primary);">Dataset Health Score</span>
              <span style="font-size: 13px; font-weight: 700; color: ${gradeColor};">${healthScore}%</span>
            </div>
            <div style="font-size: 11px; color: var(--text-muted);">
              ${totalRows.toLocaleString()} rows &bull; ${totalCols} columns &bull; ${memFormatted}
            </div>
          </div>
        </div>

        <!-- Studio Tabs -->
        <div class="browse-studio-nav" style="display: flex; border-bottom: 1px solid var(--border-subtle); margin-bottom: 12px; gap: 4px;">
          <button type="button" class="browse-nav-tab active" data-tab="fields" style="padding: 6px 10px; font-size: 11px; font-weight: 600; border: none; background: transparent; color: var(--text-primary); border-bottom: 2px solid var(--color-primary); cursor: pointer;">Columns (${totalCols})</button>
          <button type="button" class="browse-nav-tab" data-tab="health" style="padding: 6px 10px; font-size: 11px; font-weight: 600; border: none; background: transparent; color: var(--text-muted); border-bottom: 2px solid transparent; cursor: pointer;">Health & KPIs</button>
          <button type="button" class="browse-nav-tab" data-tab="correlations" style="padding: 6px 10px; font-size: 11px; font-weight: 600; border: none; background: transparent; color: var(--text-muted); border-bottom: 2px solid transparent; cursor: pointer;">Correlations</button>
          <button type="button" class="browse-nav-tab" data-tab="report" style="padding: 6px 10px; font-size: 11px; font-weight: 600; border: none; background: transparent; color: var(--text-muted); border-bottom: 2px solid transparent; cursor: pointer;">Export Audit</button>
        </div>

        <!-- TAB 1: Fields Profile -->
        <div class="browse-pane active" id="pane-browse-fields">
          <div class="browse-fields-toolbar" style="margin-bottom: 10px; display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; gap: 6px;">
              <input type="text" class="form-control" id="browse-col-search" placeholder="Search columns..." style="font-size: 11px; padding: 4px 8px; flex: 1;">
              <select class="form-control" id="browse-col-sort" style="font-size: 11px; padding: 4px 8px; width: 130px;">
                <option value="health-asc">Health (Lowest)</option>
                <option value="health-desc">Health (Highest)</option>
                <option value="missing-desc">Missing % (High)</option>
                <option value="outliers-desc">Outliers % (High)</option>
                <option value="name-asc">Name (A-Z)</option>
              </select>
            </div>
            <div class="browse-filter-pills" style="display: flex; gap: 4px; overflow-x: auto; padding-bottom: 2px;">
              <button type="button" class="browse-filter-pill active" data-filter="all">All (${totalCols})</button>
              <button type="button" class="browse-filter-pill" data-filter="numeric">Numeric</button>
              <button type="button" class="browse-filter-pill" data-filter="string">String</button>
              <button type="button" class="browse-filter-pill" data-filter="issues" style="color: #f59e0b;">⚠️ Issues</button>
            </div>
          </div>

          <div class="browse-cards-list" id="browse-cards-list" style="display: flex; flex-direction: column; gap: 10px; max-height: calc(100vh - 360px); overflow-y: auto; padding-right: 2px;">
            <!-- Column cards populated by _initBrowseColumnsList -->
          </div>
        </div>

        <!-- TAB 2: Health & KPIs -->
        <div class="browse-pane" id="pane-browse-health" style="display: none;">
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 12px;">
            <div class="browse-kpi-box">
              <span class="browse-kpi-lbl">Missing Cells</span>
              <span class="browse-kpi-val" style="color: ${missingPct > 5 ? '#f59e0b' : 'inherit'};">${missingPct}%</span>
              <span class="browse-kpi-sub">${(data.missing_cells_count || 0).toLocaleString()} cells</span>
            </div>
            <div class="browse-kpi-box">
              <span class="browse-kpi-lbl">Duplicate Rows</span>
              <span class="browse-kpi-val" style="color: ${dupPct > 0 ? '#f59e0b' : 'inherit'};">${dupPct}%</span>
              <span class="browse-kpi-sub">${(data.duplicate_rows_count || 0).toLocaleString()} rows</span>
            </div>
          </div>

          <div class="browse-penalty-section" style="background: var(--bg-surface-elevated, #1e293b); padding: 10px; border-radius: 6px; border: 1px solid var(--border-subtle); margin-bottom: 12px;">
            <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); display: block; margin-bottom: 8px;">Health Penalty Breakdown</span>
            ${this._renderPenaltyBar('Completeness', data.health_penalties?.completeness || 0, 40)}
            ${this._renderPenaltyBar('Uniqueness', data.health_penalties?.uniqueness || 0, 20)}
            ${this._renderPenaltyBar('Conformance & Outliers', data.health_penalties?.conformance || 0, 20)}
            ${this._renderPenaltyBar('String Hygiene', data.health_penalties?.hygiene || 0, 20)}
          </div>

          ${data.duplicate_rows_count > 0 ? `
            <div style="margin-bottom: 12px; padding: 10px; background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 6px;">
              <div style="font-size: 12px; font-weight: 600; color: #f59e0b; margin-bottom: 4px;">Duplicates Detected</div>
              <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">Found ${(data.duplicate_rows_count || 0).toLocaleString()} duplicate rows in this dataset.</div>
              <button type="button" class="btn btn-secondary btn-sm" id="btn-browse-dedup" style="font-size: 11px;">
                ⚡ Add Unique Tool on Canvas
              </button>
            </div>
          ` : ''}

          <div style="background: var(--bg-surface-elevated, #1e293b); padding: 10px; border-radius: 6px; border: 1px solid var(--border-subtle);">
            <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); display: block; margin-bottom: 6px;">Primary Key Candidates</span>
            ${keyCandidates.length > 0 ? `
              <div style="display: flex; flex-wrap: wrap; gap: 4px;">
                ${keyCandidates.map(k => `<span class="browse-chip browse-chip-key">🔑 ${this.escapeHtml(k)} (100% Unique)</span>`).join('')}
              </div>
            ` : '<div style="font-size: 11px; color: var(--text-muted);">No single column meets 100% uniqueness with 0 nulls.</div>'}
          </div>
        </div>

        <!-- TAB 3: Correlations -->
        <div class="browse-pane" id="pane-browse-correlations" style="display: none;">
          ${data.correlations && data.correlations.top_correlations && data.correlations.top_correlations.length > 0 ? `
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
              Top Pearson correlation coefficients between numeric variables:
            </div>
            <div class="browse-corr-list" style="display: flex; flex-direction: column; gap: 6px;">
              ${data.correlations.top_correlations.map(cr => `
                <div class="browse-corr-item" style="display: flex; justify-content: space-between; align-items: center; padding: 6px 8px; background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 4px;">
                  <div style="min-width: 0; flex: 1;">
                    <span style="font-size: 11px; font-weight: 600;">${this.escapeHtml(cr.col1)}</span>
                    <span style="font-size: 10px; color: var(--text-muted);"> vs </span>
                    <span style="font-size: 11px; font-weight: 600;">${this.escapeHtml(cr.col2)}</span>
                  </div>
                  <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 12px; font-weight: 700; color: ${cr.r > 0 ? '#22c55e' : '#ef4444'};">
                      ${cr.r > 0 ? '▲ +' : '▼ '}${cr.r}
                    </span>
                    <button type="button" class="btn btn-secondary btn-sm btn-view-scatter" data-x="${this.escapeHtml(cr.col1)}" data-y="${this.escapeHtml(cr.col2)}" style="font-size: 10px; padding: 2px 6px;">
                      Scatter ↗
                    </button>
                  </div>
                </div>
              `).join('')}
            </div>
          ` : `
            <div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">
              Requires at least 2 numeric columns with data variance to calculate correlations.
            </div>
          `}
        </div>

        <!-- TAB 4: Export Audit Report -->
        <div class="browse-pane" id="pane-browse-report" style="display: none;">
          <div style="padding: 16px; background: var(--bg-surface-elevated, #1e293b); border-radius: 8px; border: 1px solid var(--border-subtle); text-align: center;">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" style="margin-bottom: 8px;">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
            </svg>
            <h5 style="font-size: 13px; font-weight: 700; margin-bottom: 4px;">Standalone HTML Quality Audit Report</h5>
            <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 14px; line-height: 1.4;">
              Download a complete, self-contained HTML report with executive KPI cards, 4-color quality ribbons, and correlation matrices for sharing.
            </p>
            <button type="button" class="btn btn-primary" id="btn-browse-download-report" style="font-size: 12px; padding: 7px 16px;">
              📥 Download HTML Quality Report
            </button>
          </div>
        </div>
      </div>
    `;

    // Tab switching in Studio
    const navTabs = container.querySelectorAll('.browse-nav-tab');
    const panes = container.querySelectorAll('.browse-pane');
    navTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        navTabs.forEach(t => {
          t.classList.remove('active');
          t.style.color = 'var(--text-muted)';
          t.style.borderBottomColor = 'transparent';
        });
        panes.forEach(p => p.style.display = 'none');

        tab.classList.add('active');
        tab.style.color = 'var(--text-primary)';
        tab.style.borderBottomColor = 'var(--color-primary)';
        const targetPane = container.querySelector(`#pane-browse-${tab.dataset.tab}`);
        if (targetPane) targetPane.style.display = 'block';
      });
    });

    // Dedup button on canvas
    const dedupBtn = container.querySelector('#btn-browse-dedup');
    if (dedupBtn) {
      dedupBtn.addEventListener('click', () => {
        this.addRemediationNode(node.id, 'unique', {}, `Unique_${node.name}`);
      });
    }

    // Download report button
    const downloadReportBtn = container.querySelector('#btn-browse-download-report');
    if (downloadReportBtn) {
      downloadReportBtn.addEventListener('click', () => {
        let url = `/api/node-profile/${node.id}/export-report?port=O&title=${encodeURIComponent('Data Quality Report - ' + node.name)}`;
        if (window.activeRunId) url += `&run_id=${encodeURIComponent(window.activeRunId)}`;
        if (window.clientSessionId) url += `&session_id=${encodeURIComponent(window.clientSessionId)}`;
        window.location.href = url;
      });
    }

    // View scatter plot buttons
    container.querySelectorAll('.btn-view-scatter').forEach(btn => {
      btn.addEventListener('click', () => {
        const xCol = btn.dataset.x;
        const yCol = btn.dataset.y;
        if (window.appResultsPanel) {
          window.appResultsPanel.switchToTab('chart-view');
          if (window.appResultsPanel.chartTypeSelect) {
            window.appResultsPanel.chartTypeSelect.value = 'scatter';
          }
          if (window.appResultsPanel.chartXSelect) {
            window.appResultsPanel.chartXSelect.value = xCol;
          }
          if (window.appResultsPanel.chartYSelect) {
            window.appResultsPanel.chartYSelect.value = yCol;
          }
          window.appResultsPanel.updateChartControlsVisibility();
          window.appResultsPanel.loadChartData();
        }
      });
    });

    // Render columns list with live filtering and sorting
    this._initBrowseColumnsList(container, node, data.columns || []);
  }

  _renderPenaltyBar(label, penalty, maxPenalty) {
    const pct = Math.min(100, Math.round((penalty / maxPenalty) * 100));
    const isHigh = pct > 25;
    return `
      <div style="margin-bottom: 6px;">
        <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 2px;">
          <span>${this.escapeHtml(label)}</span>
          <span style="color: ${isHigh ? '#f59e0b' : 'var(--text-muted)'}; font-weight: 600;">-${penalty} pts</span>
        </div>
        <div style="height: 4px; background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;">
          <div style="height: 100%; width: ${pct}%; background: ${isHigh ? '#f59e0b' : '#3b82f6'}; border-radius: 2px;"></div>
        </div>
      </div>
    `;
  }

  _initBrowseColumnsList(container, node, columns) {
    const listEl = container.querySelector('#browse-cards-list');
    const searchInput = container.querySelector('#browse-col-search');
    const sortSelect = container.querySelector('#browse-col-sort');
    const filterPills = container.querySelectorAll('.browse-filter-pill');

    let curFilter = 'all';
    let curSearch = '';
    let curSort = 'health-asc';

    const renderFiltered = () => {
      let filtered = columns.slice();

      // Search
      if (curSearch) {
        filtered = filtered.filter(c => c.name.toLowerCase().includes(curSearch));
      }

      // Category filter
      if (curFilter === 'numeric') {
        filtered = filtered.filter(c => c.category === 'numeric');
      } else if (curFilter === 'string') {
        filtered = filtered.filter(c => c.category === 'string' || c.raw_dtype === 'object');
      } else if (curFilter === 'issues') {
        filtered = filtered.filter(c => {
          const q = c.quality || {};
          return (c.health_score < 90) || (q.null_percent > 0) || (q.whitespace_percent > 0) || (q.outlier_percent > 0);
        });
      }

      // Sort
      if (curSort === 'health-asc') {
        filtered.sort((a, b) => a.health_score - b.health_score);
      } else if (curSort === 'health-desc') {
        filtered.sort((a, b) => b.health_score - a.health_score);
      } else if (curSort === 'missing-desc') {
        filtered.sort((a, b) => (b.quality?.null_percent || 0) - (a.quality?.null_percent || 0));
      } else if (curSort === 'outliers-desc') {
        filtered.sort((a, b) => (b.quality?.outlier_percent || 0) - (a.quality?.outlier_percent || 0));
      } else if (curSort === 'name-asc') {
        filtered.sort((a, b) => a.name.localeCompare(b.name));
      }

      if (filtered.length === 0) {
        listEl.innerHTML = `<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 11px;">No columns match current filter.</div>`;
        return;
      }

      listEl.innerHTML = filtered.map(c => this._renderBrowseColumnCardHtml(c)).join('');

      // Bind action buttons on cards
      this._bindBrowseCardActions(listEl, node, filtered);
    };

    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        curSearch = e.target.value.toLowerCase().trim();
        renderFiltered();
      });
    }

    if (sortSelect) {
      sortSelect.addEventListener('change', (e) => {
        curSort = e.target.value;
        renderFiltered();
      });
    }

    filterPills.forEach(pill => {
      pill.addEventListener('click', () => {
        filterPills.forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
        curFilter = pill.dataset.filter;
        renderFiltered();
      });
    });

    renderFiltered();
  }

  _renderBrowseColumnCardHtml(c) {
    const q = c.quality || {};
    const okP = q.ok_percent !== undefined ? q.ok_percent : 100;
    const wsP = q.whitespace_percent || 0;
    const outP = q.outlier_percent || 0;
    const nullP = q.null_percent || 0;
    const hScore = c.health_score !== undefined ? c.health_score : 100;

    const hColor = hScore >= 90 ? '#22c55e' : (hScore >= 75 ? '#3b82f6' : (hScore >= 60 ? '#f59e0b' : '#ef4444'));

    let typeBadgeHtml = `<span class="browse-type-badge">${this.escapeHtml(c.dtype || 'String')}</span>`;
    if (window.appResultsPanel && typeof window.appResultsPanel.formatAlteryxTypeBadge === 'function') {
      typeBadgeHtml = window.appResultsPanel.formatAlteryxTypeBadge(c.dtype);
    }

    // Distribution mini horizontal bar chart with data labels
    let sparklineHtml = '';
    if (c.histogram && c.histogram.length > 0) {
      const maxCnt = Math.max(...c.histogram.map(b => b.count || 0), 1);
      const previewBins = c.histogram.slice(0, 3);
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
          ${c.histogram.length > 3 ? `
            <div style="font-size: 9px; color: var(--text-muted); text-align: right; margin-top: 1px;">
              + ${c.histogram.length - 3} more in Deep Dive
            </div>
          ` : ''}
        </div>
      `;
    }

    // Specific stats chips
    let statsChips = '';
    if (c.numeric_stats) {
      const ns = c.numeric_stats;
      statsChips = `
        <div class="browse-chips-wrap">
          <span class="browse-stat-chip">Min: <b>${ns.min}</b></span>
          <span class="browse-stat-chip">Max: <b>${ns.max}</b></span>
          <span class="browse-stat-chip">Mean: <b>${ns.mean}</b></span>
          ${ns.outlier_count > 0 ? `<span class="browse-stat-chip chip-warn">⚠️ ${ns.outlier_count} Outliers (${ns.outlier_percent}%)</span>` : ''}
        </div>
      `;
    } else if (c.string_stats) {
      const ss = c.string_stats;
      statsChips = `
        <div class="browse-chips-wrap">
          <span class="browse-stat-chip">Len: <b>${ss.min_length}..${ss.max_length}</b> (Avg ${ss.avg_length})</span>
          ${ss.leading_whitespace_count > 0 ? `<span class="browse-stat-chip chip-warn">⚠️ ${ss.leading_whitespace_count} Leading Spaces</span>` : ''}
          ${ss.mixed_casing_detected ? `<span class="browse-stat-chip chip-warn" title="${ss.mixed_casing_examples?.join(', ')}">🔤 Mixed Casing</span>` : ''}
          ${ss.inferred_patterns?.length > 0 ? `<span class="browse-stat-chip chip-pattern">Pattern: <b>${ss.inferred_patterns[0].pattern}</b></span>` : ''}
        </div>
      `;
    }

    // 1-Click Action Buttons
    const actions = [];
    if (c.string_stats && (c.string_stats.leading_whitespace_count > 0 || c.string_stats.trailing_whitespace_count > 0 || wsP > 0)) {
      actions.push(`<button type="button" class="btn-action-remediate btn-trim-spaces" data-col="${this.escapeHtml(c.name)}">✂️ Trim Spaces</button>`);
    }
    if (c.numeric_stats && c.numeric_stats.outlier_count > 0) {
      actions.push(`<button type="button" class="btn-action-remediate btn-filter-outliers" data-col="${this.escapeHtml(c.name)}">⚠️ Filter Outliers</button>`);
    }
    if (nullP > 0) {
      actions.push(`<button type="button" class="btn-action-remediate btn-filter-nulls" data-col="${this.escapeHtml(c.name)}">🚫 Filter Nulls</button>`);
    }
    actions.push(`<button type="button" class="btn-action-remediate btn-deep-dive" data-col="${this.escapeHtml(c.name)}">🔍 Deep Dive</button>`);

    return `
      <div class="browse-card" data-col-name="${this.escapeHtml(c.name)}" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
            <span style="font-weight: 700; font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${this.escapeHtml(c.name)}">${this.escapeHtml(c.name)}</span>
            ${typeBadgeHtml}
            ${c.is_key_candidate ? `<span class="browse-badge-key" title="Candidate Primary Key: 100% unique, 0 nulls">🔑 Key</span>` : ''}
          </div>
          <span style="font-size: 11px; font-weight: 700; color: ${hColor};">${hScore}%</span>
        </div>

        <!-- 4-Color Quality Ribbon -->
        <div class="browse-ribbon" title="OK: ${okP}% (${q.ok_count || 0}) | Whitespace: ${wsP}% (${q.whitespace_count || 0}) | Outliers: ${outP}% (${q.outlier_count || 0}) | Null: ${nullP}% (${q.null_count || 0})">
          <div class="browse-ribbon-seg seg-ok" style="width: ${okP}%;"></div>
          <div class="browse-ribbon-seg seg-ws" style="width: ${wsP}%;"></div>
          <div class="browse-ribbon-seg seg-out" style="width: ${outP}%;"></div>
          <div class="browse-ribbon-seg seg-null" style="width: ${nullP}%;"></div>
        </div>

        ${statsChips}
        ${sparklineHtml}

        <div style="display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 6px;">
          ${actions.join('')}
        </div>
      </div>
    `;
  }

  _bindBrowseCardActions(container, node, columns) {
    // 1-Click Trim Spaces
    container.querySelectorAll('.btn-trim-spaces').forEach(btn => {
      btn.addEventListener('click', () => {
        const colName = btn.dataset.col;
        this.addRemediationNode(node.id, 'clean', {
          columns: [colName],
          trim_whitespace: true,
          remove_leading_trailing: true
        }, `Clean_${colName}`);
      });
    });

    // 1-Click Filter Outliers
    container.querySelectorAll('.btn-filter-outliers').forEach(btn => {
      btn.addEventListener('click', () => {
        const colName = btn.dataset.col;
        const colObj = columns.find(c => c.name === colName);
        if (colObj && colObj.numeric_stats) {
          const ns = colObj.numeric_stats;
          this.addRemediationNode(node.id, 'filter', {
            column: colName,
            operator: 'between',
            min: ns.lower_fence,
            max: ns.upper_fence,
            expression: `[${colName}] >= ${ns.lower_fence} and [${colName}] <= ${ns.upper_fence}`
          }, `Filter_Outliers_${colName}`);
        }
      });
    });

    // 1-Click Filter Nulls
    container.querySelectorAll('.btn-filter-nulls').forEach(btn => {
      btn.addEventListener('click', () => {
        const colName = btn.dataset.col;
        this.addRemediationNode(node.id, 'filter', {
          column: colName,
          operator: 'is_not_null',
          expression: `[${colName}] is not null`
        }, `Filter_Valid_${colName}`);
      });
    });

    // Deep Dive Drawer trigger
    container.querySelectorAll('.btn-deep-dive').forEach(btn => {
      btn.addEventListener('click', () => {
        const colName = btn.dataset.col;
        const colObj = columns.find(c => c.name === colName);
        if (colObj && window.appResultsPanel) {
          window.appResultsPanel.openDeepDive(colObj);
        }
      });
    });
  }

  addRemediationNode(srcNodeId, toolType, config, label) {
    if (!this.canvas) return;
    const srcNode = this.canvas.nodes.find(n => n.id === srcNodeId);
    const x = srcNode ? srcNode.x + 160 : 350;
    const y = srcNode ? srcNode.y + 40 : 220;

    const newNode = this.canvas.addNode(toolType, x, y, label || `${toolType}_remedy`, config);
    if (srcNode && newNode) {
      this.canvas.addConnection(srcNode.id, 'O', newNode.id, 'I');
    }
    if (window.showToast) {
      window.showToast('success', 'Remediation Tool Added', `Connected new ${toolType.toUpperCase()} tool to workflow.`);
    }
  }

  // --------------------------------------------------------------------
  // 3. Select Tool
  // --------------------------------------------------------------------
  renderSelectConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    let fields = cfg.fields || [];

    // If no fields configured yet, initialize from upstream columns
    if (fields.length === 0 && upstreamCols.length > 0) {
      fields = upstreamCols.map(c => ({ original: c, keep: true, rename: c, type: 'none' }));
      node.config.fields = fields;
    }

    const upstreamMeta = this.getUpstreamColumnMeta(node.id);
    const metaMap = {};
    if (Array.isArray(upstreamMeta)) {
      upstreamMeta.forEach(m => {
        if (m && m.name) {
          metaMap[m.name] = m.alteryx_type || m.dtype || (m.type === 'numeric' ? 'Int64' : (m.type === 'datetime' ? 'DateTime' : 'String'));
        }
      });
    }

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">
        Select columns to keep, rename, reorder, or cast to new data types:
      </div>

      <div class="cfg-toolbar">
        <button id="btn-select-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Select All</button>
        <button id="btn-deselect-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Deselect All</button>
        <button id="btn-invert-select" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Invert</button>
      </div>

      <div id="cfg-select-table-wrap" style="max-height: 380px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px;">
        <table style="width: 100%; font-size: 11px; border-collapse: collapse;">
          <thead>
            <tr style="background: var(--bg-main); color: var(--text-muted); text-align: left;">
              <th style="padding: 6px; width: 30px;">Keep</th>
              <th style="padding: 6px; width: 54px; text-align: center;">Order</th>
              <th style="padding: 6px;">Field</th>
              <th style="padding: 6px;">Rename</th>
              <th style="padding: 6px;">Type</th>
            </tr>
          </thead>
          <tbody id="cfg-select-tbody">
            ${fields.map((f, i) => `
              <tr style="border-top: 1px solid var(--border-subtle);" data-idx="${i}">
                <td style="padding: 6px; text-align: center;">
                  <input type="checkbox" class="field-keep" ${f.keep !== false ? 'checked' : ''}>
                </td>
                <td style="padding: 4px; text-align: center; white-space: nowrap;">
                  <span class="drag-grip" title="Click and drag to reorder">⋮⋮</span>
                  <button class="cfg-reorder-btn btn-row-up" data-idx="${i}" title="Move Up" ${i === 0 ? 'disabled style="opacity:0.3;"' : ''}>▲</button>
                  <button class="cfg-reorder-btn btn-row-down" data-idx="${i}" title="Move Down" ${i === fields.length - 1 ? 'disabled style="opacity:0.3;"' : ''}>▼</button>
                </td>
                <td style="padding: 6px; font-weight: 500;">
                  ${this.escapeHtml(f.original)}
                  ${metaMap[f.original] ? `<span class="type-badge type-${this.getTypeCategory(metaMap[f.original])}" style="margin-left: 4px; font-size: 8.5px; padding: 0 4px;">${this.escapeHtml(metaMap[f.original])}</span>` : ''}
                </td>
                <td style="padding: 4px;">
                  <input type="text" class="form-control field-rename" style="padding: 2px 6px; font-size: 11px;" value="${this.escapeHtml(f.rename || f.original)}">
                </td>
                <td style="padding: 4px;">
                  <select class="form-control field-type" style="padding: 2px 4px; font-size: 11px;">
                    <option value="none" ${(!f.type || f.type === 'none') ? 'selected' : ''}>Current</option>
                    <option value="string" ${f.type === 'string' || f.type === 'v_wstring' ? 'selected' : ''}>String (V_WString)</option>
                    <option value="int64" ${f.type === 'int64' || f.type === 'integer' ? 'selected' : ''}>Int64 (Integer)</option>
                    <option value="int32" ${f.type === 'int32' ? 'selected' : ''}>Int32</option>
                    <option value="int16" ${f.type === 'int16' ? 'selected' : ''}>Int16</option>
                    <option value="double" ${f.type === 'double' || f.type === 'float' ? 'selected' : ''}>Double (Float)</option>
                    <option value="date" ${f.type === 'date' ? 'selected' : ''}>Date</option>
                    <option value="datetime" ${f.type === 'datetime' ? 'selected' : ''}>DateTime</option>
                    <option value="time" ${f.type === 'time' ? 'selected' : ''}>Time</option>
                    <option value="bool" ${f.type === 'bool' || f.type === 'boolean' ? 'selected' : ''}>Bool</option>
                  </select>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>

      ${fields.length === 0 ? '<p class="form-hint" style="margin-top: 10px;">Connect an upstream tool and run the workflow to auto-populate columns.</p>' : ''}
    `;

    // Bulk buttons
    container.querySelector('#btn-select-all')?.addEventListener('click', () => {
      fields.forEach(f => f.keep = true);
      this.render(node);
      this.canvas.onWorkflowChange();
    });
    container.querySelector('#btn-deselect-all')?.addEventListener('click', () => {
      fields.forEach(f => f.keep = false);
      this.render(node);
      this.canvas.onWorkflowChange();
    });
    container.querySelector('#btn-invert-select')?.addEventListener('click', () => {
      fields.forEach(f => f.keep = !f.keep);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    const tbody = container.querySelector('#cfg-select-tbody');
    tbody.querySelectorAll('tr').forEach(tr => {
      const idx = parseInt(tr.dataset.idx);
      tr.querySelector('.field-keep').addEventListener('change', (e) => {
        fields[idx].keep = e.target.checked;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.field-rename').addEventListener('input', (e) => {
        fields[idx].rename = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.field-type').addEventListener('change', (e) => {
        fields[idx].type = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.btn-row-up')?.addEventListener('click', () => {
        if (idx > 0) {
          const temp = fields[idx];
          fields[idx] = fields[idx - 1];
          fields[idx - 1] = temp;
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
      tr.querySelector('.btn-row-down')?.addEventListener('click', () => {
        if (idx < fields.length - 1) {
          const temp = fields[idx];
          fields[idx] = fields[idx + 1];
          fields[idx + 1] = temp;
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
    });

    this.setupTableDragAndDrop(tbody, fields, (newFields) => {
      node.config.fields = newFields;
      this.render(node);
      this.canvas.onWorkflowChange();
    });
  }

  getTypeCategory(type) {
    const t = String(type || '').toLowerCase();
    if (t.includes('int') || t.includes('double') || t.includes('float') || t.includes('numeric') || t.includes('byte')) return 'numeric';
    if (t.includes('date') || t.includes('time')) return 'date';
    if (t.includes('bool')) return 'bool';
    return 'string';
  }

  // --------------------------------------------------------------------
  // 3b. Auto Field Tool
  // --------------------------------------------------------------------
  renderAutoFieldConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    let selectedCols = cfg.columns;
    if (!selectedCols || !Array.isArray(selectedCols)) {
      selectedCols = [...upstreamCols];
      node.config.columns = selectedCols;
    }

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.4;">
        Automatically inspects field data and sets each column to the most efficient, appropriate data type (converts string numbers to Int/Double, dates to Date, booleans to Bool).
      </div>

      <div class="form-group" style="margin-bottom: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <label style="font-weight: 600; font-size: 12px; margin: 0;">Select Fields to Auto-Configure:</label>
          <div style="display: flex; gap: 4px;">
            <button type="button" class="btn btn-xs btn-secondary" id="btn-autofield-all" style="padding: 2px 6px; font-size: 10px;">All</button>
            <button type="button" class="btn btn-xs btn-secondary" id="btn-autofield-none" style="padding: 2px 6px; font-size: 10px;">Clear</button>
          </div>
        </div>

        <div id="autofield-list" style="max-height: 280px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px 8px; background: var(--bg-main);">
          ${upstreamCols.length > 0 ? upstreamCols.map(col => `
            <label class="form-check" style="margin-bottom: 4px; font-size: 11.5px; display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" class="autofield-col-chk" value="${this.escapeHtml(col)}" ${selectedCols.includes(col) ? 'checked' : ''}>
              <span>${this.escapeHtml(col)}</span>
            </label>
          `).join('') : '<div class="form-hint" style="padding: 6px; text-align: center;">Connect input to view available fields.</div>'}
        </div>
      </div>

      <div style="padding: 8px 10px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 6px; font-size: 11px; color: var(--text-secondary);">
        <strong style="color: var(--color-primary);">Tip:</strong> Insert this tool directly after an Input Data tool to eliminate raw string/object types across your dataset.
      </div>
    `;

    const updateCols = () => {
      node.config.columns = Array.from(container.querySelectorAll('.autofield-col-chk:checked')).map(c => c.value);
      this.canvas.onWorkflowChange();
    };

    container.querySelectorAll('.autofield-col-chk').forEach(chk => {
      chk.addEventListener('change', updateCols);
    });

    container.querySelector('#btn-autofield-all')?.addEventListener('click', () => {
      container.querySelectorAll('.autofield-col-chk').forEach(c => c.checked = true);
      updateCols();
    });

    container.querySelector('#btn-autofield-none')?.addEventListener('click', () => {
      container.querySelectorAll('.autofield-col-chk').forEach(c => c.checked = false);
      updateCols();
    });
  }

  // --------------------------------------------------------------------
  // 4. Filter Tool (Alteryx Parity: Basic, Custom, Quick Query)
  // --------------------------------------------------------------------
  compileConditionsToExpression(conditions, logicalOp = 'AND') {
    if (!conditions || conditions.length === 0) return '';
    const parts = [];
    for (const c of conditions) {
      if (!c.column) continue;
      const col = `[${c.column}]`;
      const op = (c.operator || '==').toLowerCase();
      const val = (c.value !== undefined && c.value !== null) ? String(c.value).trim() : '';
      const valMax = (c.value_max !== undefined && c.value_max !== null) ? String(c.value_max).trim() : '';
      const ic = c.ignore_case !== false;
      const isNum = val !== '' && !isNaN(Number(val));
      const formattedVal = isNum ? val : `"${val.replace(/"/g, '\\"')}"`;

      if (op === '==') {
        parts.push(ic && !isNum ? `Lowercase(${col}) == "${val.toLowerCase()}"` : `${col} == ${formattedVal}`);
      } else if (op === '!=') {
        parts.push(ic && !isNum ? `Lowercase(${col}) != "${val.toLowerCase()}"` : `${col} != ${formattedVal}`);
      } else if (op === '>') {
        parts.push(`${col} > ${val || 0}`);
      } else if (op === '>=') {
        parts.push(`${col} >= ${val || 0}`);
      } else if (op === '<') {
        parts.push(`${col} < ${val || 0}`);
      } else if (op === '<=') {
        parts.push(`${col} <= ${val || 0}`);
      } else if (op === 'between') {
        parts.push(`Between(${col}, ${val || 0}, ${valMax || 0})`);
      } else if (op === 'contains') {
        parts.push(`Contains(${col}, "${val}", ${ic ? 1 : 0})`);
      } else if (op === 'not_contains') {
        parts.push(`NOT Contains(${col}, "${val}", ${ic ? 1 : 0})`);
      } else if (op === 'starts_with') {
        parts.push(`StartsWith(${col}, "${val}", ${ic ? 1 : 0})`);
      } else if (op === 'ends_with') {
        parts.push(`EndsWith(${col}, "${val}", ${ic ? 1 : 0})`);
      } else if (op === 'regex_match') {
        parts.push(`RegexMatch(${col}, "${val}")`);
      } else if (op === 'is_null') {
        parts.push(`IsNull(${col})`);
      } else if (op === 'not_null') {
        parts.push(`NotNull(${col})`);
      } else if (op === 'is_empty') {
        parts.push(`IsEmpty(${col})`);
      } else if (op === 'not_empty') {
        parts.push(`NotEmpty(${col})`);
      } else if (op === 'is_true') {
        parts.push(`(${col} == 1 OR ${col} == "true" OR ${col} == "True")`);
      } else if (op === 'is_false') {
        parts.push(`(${col} == 0 OR ${col} == "false" OR ${col} == "False")`);
      } else if (op === 'in') {
        const items = val.split(',').map(x => x.trim()).filter(Boolean);
        if (items.length > 0) {
          const checks = items.map(item => ic ? `Lowercase(${col}) == "${item.toLowerCase()}"` : `${col} == "${item}"`);
          parts.push(`(${checks.join(' OR ')})`);
        }
      } else if (op === 'not_in') {
        const items = val.split(',').map(x => x.trim()).filter(Boolean);
        if (items.length > 0) {
          const checks = items.map(item => ic ? `Lowercase(${col}) != "${item.toLowerCase()}"` : `${col} != "${item}"`);
          parts.push(`(${checks.join(' AND ')})`);
        }
      }
    }
    return parts.join(` ${logicalOp.toUpperCase()} `);
  }

  compileQueryToExpression(queryStr) {
    if (!queryStr || !queryStr.trim()) return '';
    const rawTokens = queryStr.trim().match(/("[^"]*"|\S+)/g) || [];
    const clauses = [];
    let currentOrGroup = [];

    const flushOrGroup = () => {
      if (currentOrGroup.length === 1) {
        clauses.push(currentOrGroup[0]);
      } else if (currentOrGroup.length > 1) {
        clauses.push(`(${currentOrGroup.join(' OR ')})`);
      }
      currentOrGroup = [];
    };

    for (let i = 0; i < rawTokens.length; i++) {
      const token = rawTokens[i];
      if (token.toUpperCase() === 'OR') {
        continue;
      }
      const isOrNext = (i + 1 < rawTokens.length && rawTokens[i + 1].toUpperCase() === 'OR') ||
                       (i > 0 && rawTokens[i - 1].toUpperCase() === 'OR');

      let clause = '';
      const compMatch = token.match(/^([A-Za-z0-9_]+)(>=|<=|>|<|!=)(.+)$/);
      if (compMatch) {
        const [, col, op, val] = compMatch;
        clause = `[${col}] ${op} ${val}`;
      } else if (token.includes(':')) {
        const parts = token.split(':');
        const col = parts[0];
        const val = parts.slice(1).join(':').replace(/^"|"$/g, '');
        if (val.includes('..')) {
          const [low, high] = val.split('..');
          clause = `Between([${col}], ${low}, ${high})`;
        } else if (val.includes(',')) {
          const items = val.split(',').map(x => x.trim()).filter(Boolean);
          clause = `(${items.map(it => `[${col}] == "${it}"`).join(' OR ')})`;
        } else {
          clause = `[${col}] == "${val}"`;
        }
      } else {
        const cleanWord = token.replace(/^"|"$/g, '');
        clause = `Contains([_All_Text_], "${cleanWord}")`;
      }

      if (clause) {
        if (isOrNext) {
          currentOrGroup.push(clause);
        } else {
          flushOrGroup();
          clauses.push(clause);
        }
      }
    }
    flushOrGroup();
    return clauses.join(' AND ');
  }

  renderFilterConfig(container, node, upstreamCols) {
    const cfg = node.config = node.config || {};
    const mode = cfg.mode || 'basic';
    const conditions = cfg.conditions = cfg.conditions || [];
    const catalog = this.getFormulaCatalog();

    // Determine upstream columns with type glyphs
    let colMeta = [];
    if (this.getUpstreamColumnMeta && node.id) {
      colMeta = this.getUpstreamColumnMeta(node.id);
    }
    if (!colMeta || colMeta.length === 0) {
      colMeta = (upstreamCols || []).map(c => {
        const low = c.toLowerCase();
        let inferred = 'unknown';
        if (/date|time|timestamp|_dt\b/.test(low)) inferred = 'datetime';
        else if (/\b(id|num|qty|amount|price|cost|sales|revenue|rate|count|total|tax|disc|discount|margin|profit|weight|score)\b|_id$/.test(low)) inferred = 'numeric';
        return { name: c, type: inferred };
      });
    }

    const getColIcon = (type) => {
      if (type === 'numeric') return '#';
      if (type === 'datetime' || type === 'date') return '📅';
      if (type === 'boolean') return '✓';
      return 'Aa';
    };

    const isNoValOp = (op) => ['is_null', 'not_null', 'is_empty', 'not_empty', 'is_true', 'is_false'].includes(op);
    const isTextOp = (op) => ['==', '!=', 'contains', 'not_contains', 'starts_with', 'ends_with', 'in', 'not_in', 'regex_match'].includes(op);

    container.innerHTML = `
      <!-- Mode Tabs (Tri-Mode Segmented Control) -->
      <div class="flt-mode-tabs" role="tablist">
        <button type="button" class="flt-mode-tab ${mode === 'basic' ? 'active' : ''}" data-mode="basic">
          <span>⚡</span> Basic Filter
        </button>
        <button type="button" class="flt-mode-tab ${mode === 'custom' ? 'active' : ''}" data-mode="custom">
          <span>🧮</span> Custom Expression
        </button>
        <button type="button" class="flt-mode-tab ${mode === 'query' ? 'active' : ''}" data-mode="query">
          <span>🔍</span> Quick Query
        </button>
      </div>

      <!-- 1. BASIC FILTER TAB -->
      <div id="cfg-filter-basic" style="${mode === 'basic' ? '' : 'display: none;'}">
        <div class="form-group" style="margin-bottom: 10px;">
          <label>Match Criteria</label>
          <select class="form-control" id="cfg-flt-logical">
            <option value="AND" ${cfg.logical_op === 'AND' ? 'selected' : ''}>Match ALL conditions (AND)</option>
            <option value="OR" ${cfg.logical_op === 'OR' ? 'selected' : ''}>Match ANY condition (OR)</option>
          </select>
        </div>

        <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; display: block;">Conditions (${conditions.length})</label>
        <div id="cfg-flt-conditions-list">
          ${conditions.length === 0 ? `
            <div style="padding: 12px; background: var(--bg-surface); border: 1px dashed var(--border-subtle); border-radius: 6px; text-align: center; color: var(--text-muted); font-size: 11px; margin-bottom: 8px;">
              No filter conditions defined. All records will pass to the <b>T</b> port.
            </div>
          ` : conditions.map((c, i) => {
            const op = (c.operator || '==').toLowerCase();
            const showNoVal = isNoValOp(op);
            const showBetween = op === 'between';
            const showCase = isTextOp(op);
            const ignoreCaseChecked = c.ignore_case !== false;

            return `
              <div class="flt-cond-row" data-idx="${i}">
                <div class="flt-cond-top-line">
                  <select class="form-control cond-col" style="flex: 2;">
                    ${colMeta.length > 0 
                      ? colMeta.map(col => `<option value="${col.name}" ${c.column === col.name ? 'selected' : ''}>${getColIcon(col.type)} ${col.name}</option>`).join('')
                      : `<option value="${c.column}">${c.column || 'Select column'}</option>`}
                  </select>
                  <select class="form-control cond-op" style="flex: 2;">
                    <optgroup label="Comparison & Ranges">
                      <option value="==" ${op === '==' ? 'selected' : ''}>= (Equals)</option>
                      <option value="!=" ${op === '!=' ? 'selected' : ''}>!= (Not equal)</option>
                      <option value=">" ${op === '>' ? 'selected' : ''}>&gt; (Greater than)</option>
                      <option value=">=" ${op === '>=' ? 'selected' : ''}>&gt;= (Greater or equal)</option>
                      <option value="<" ${op === '<' ? 'selected' : ''}>&lt; (Less than)</option>
                      <option value="<=" ${op === '<=' ? 'selected' : ''}>&lt;= (Less or equal)</option>
                      <option value="between" ${op === 'between' ? 'selected' : ''}>Between (Min &amp; Max)</option>
                    </optgroup>
                    <optgroup label="Text Matching">
                      <option value="contains" ${op === 'contains' ? 'selected' : ''}>Contains</option>
                      <option value="not_contains" ${op === 'not_contains' ? 'selected' : ''}>Does not contain</option>
                      <option value="starts_with" ${op === 'starts_with' ? 'selected' : ''}>Starts with</option>
                      <option value="ends_with" ${op === 'ends_with' ? 'selected' : ''}>Ends with</option>
                      <option value="in" ${op === 'in' ? 'selected' : ''}>In List (comma-separated)</option>
                      <option value="not_in" ${op === 'not_in' ? 'selected' : ''}>Not In List</option>
                      <option value="regex_match" ${op === 'regex_match' ? 'selected' : ''}>Regex Match</option>
                    </optgroup>
                    <optgroup label="Null &amp; Blank Checks">
                      <option value="is_null" ${op === 'is_null' ? 'selected' : ''}>Is Null</option>
                      <option value="not_null" ${op === 'not_null' ? 'selected' : ''}>Is Not Null</option>
                      <option value="is_empty" ${op === 'is_empty' ? 'selected' : ''}>Is Empty / Blank</option>
                      <option value="not_empty" ${op === 'not_empty' ? 'selected' : ''}>Is Not Empty</option>
                    </optgroup>
                    <optgroup label="Boolean">
                      <option value="is_true" ${op === 'is_true' ? 'selected' : ''}>Is True</option>
                      <option value="is_false" ${op === 'is_false' ? 'selected' : ''}>Is False</option>
                    </optgroup>
                  </select>
                  <div class="flt-val-container" style="flex: 2.2; display: flex; align-items: center;">
                    ${showNoVal ? `
                      <input type="text" class="form-control cond-val" value="" placeholder="(No value needed)" disabled style="opacity: 0.6;">
                    ` : showBetween ? `
                      <div class="flt-range-group">
                        <input type="text" class="form-control cond-val" value="${c.value || ''}" placeholder="Min">
                        <span class="flt-range-sep">to</span>
                        <input type="text" class="form-control cond-val-max" value="${c.value_max || ''}" placeholder="Max">
                      </div>
                    ` : op === 'in' || op === 'not_in' ? `
                      <input type="text" class="form-control cond-val" value="${c.value || ''}" placeholder="A, B, C...">
                    ` : `
                      <input type="text" class="form-control cond-val" value="${c.value || ''}" placeholder="Value">
                    `}
                  </div>
                  <button class="btn-icon btn-remove-cond" title="Remove Condition" style="color: var(--color-error);">&times;</button>
                </div>
                ${showCase ? `
                  <div class="flt-cond-bot-line">
                    <label class="flt-ignore-case-wrap">
                      <input type="checkbox" class="cond-ignore-case" ${ignoreCaseChecked ? 'checked' : ''}>
                      <span>Ignore Case</span>
                    </label>
                  </div>
                ` : ''}
              </div>
            `;
          }).join('')}
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
          <button id="btn-add-cond" class="btn btn-secondary btn-sm">
            + Add Condition
          </button>
          ${conditions.length > 0 ? `
            <button id="btn-convert-to-custom" class="flt-btn-convert" title="Convert conditions to an Alteryx formula expression">
              ✨ Convert to Custom Expression
            </button>
          ` : ''}
        </div>
      </div>

      <!-- 2. CUSTOM EXPRESSION TAB -->
      <div id="cfg-filter-custom" style="${mode === 'custom' ? '' : 'display: none;'}">
        <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 10px;">
          Write powerful Boolean expressions using Alteryx formula syntax, conditional operators, and functions.
        </div>

        <!-- Function Library & Reference Drawer -->
        <div class="formula-func-browser" style="margin-bottom: 10px;">
          <div class="formula-browser-toggle" id="btn-flt-toggle-funcs">
            <span>📘 Function Library &amp; Reference (${catalog.length} functions)</span>
            <span id="flt-funcs-arrow">▼</span>
          </div>
          <div class="formula-browser-content" id="flt-funcs-content">
            <input type="text" class="formula-browser-search" id="flt-func-search" placeholder="Search functions (e.g. contains, regex, between, null)..." />
            <div class="formula-cat-tabs" id="flt-cat-tabs">
              <button class="formula-cat-tab active" data-cat="All">All (${catalog.length})</button>
              <button class="formula-cat-tab" data-cat="String">String</button>
              <button class="formula-cat-tab" data-cat="Math">Math</button>
              <button class="formula-cat-tab" data-cat="DateTime">DateTime</button>
              <button class="formula-cat-tab" data-cat="Conditional">Conditional</button>
              <button class="formula-cat-tab" data-cat="Conversion">Conversion</button>
            </div>
            <div class="formula-func-list" id="flt-func-list"></div>
          </div>
        </div>

        <!-- Upstream Column Chips -->
        ${upstreamCols && upstreamCols.length > 0 ? `
          <div class="column-chips-wrapper" style="margin-bottom: 8px;">
            <div class="column-chips-label">Insert Column:</div>
            <div class="column-chips-container">
              ${colMeta.map(c => `<span class="column-chip flt-chip" data-col="${c.name}">+ [${c.name}]</span>`).join('')}
            </div>
          </div>
        ` : ''}

        <!-- Twin-layer Formula Code Editor -->
        <div class="form-group formula-editor-wrapper" style="margin-bottom: 6px;">
          <label style="display: flex; justify-content: space-between; align-items: center;">
            <span>Boolean Filter Expression</span>
            <span style="font-size: 10px; color: var(--text-secondary); font-weight: normal;">Type <code>[</code> for columns</span>
          </label>
          <div class="formula-editor-box">
            <pre class="formula-backdrop" aria-hidden="true"></pre>
            <textarea class="form-control form-expr formula-code-input" id="cfg-flt-expr" rows="4" placeholder="e.g. Contains([Region], 'East') AND [Sales] > 500" spellcheck="false" autocomplete="off" autocapitalize="off">${cfg.expression || ''}</textarea>
          </div>
          <div id="flt-valid-badge" class="formula-valid-badge"></div>
        </div>

        <!-- Quick Function Chips -->
        <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-bottom: 8px;">
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="Contains([col], 'text')" style="font-size: 10px; padding: 2px 6px;">Contains()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="StartsWith([col], 'prefix')" style="font-size: 10px; padding: 2px 6px;">StartsWith()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="EndsWith([col], 'suffix')" style="font-size: 10px; padding: 2px 6px;">EndsWith()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="Between([col], 100, 500)" style="font-size: 10px; padding: 2px 6px;">Between()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="NotNull([col])" style="font-size: 10px; padding: 2px 6px;">NotNull()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="NotEmpty([col])" style="font-size: 10px; padding: 2px 6px;">NotEmpty()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="RegexMatch([col], '^[A-Z]')" style="font-size: 10px; padding: 2px 6px;">RegexMatch()</button>
          <button class="btn btn-secondary btn-sm flt-quick-func" data-code="IIF([col] > 0, 1, 0)" style="font-size: 10px; padding: 2px 6px;">IIF()</button>
        </div>
      </div>

      <!-- 3. QUICK QUERY TAB -->
      <div id="cfg-filter-query" style="${mode === 'query' ? '' : 'display: none;'}">
        <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 10px;">
          Search-engine style query syntax for rapid filtering across columns or free text.
        </div>

        <div class="flt-query-box">
          <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; display: block;">Search Query</label>
          <div class="flt-query-input-wrap">
            <span class="flt-query-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            </span>
            <input type="text" class="form-control flt-query-input" id="cfg-flt-query" placeholder="e.g. Region:East Sales>500 Status:Active,Review" value="${cfg.query || ''}">
          </div>

          <div class="flt-query-preview" id="flt-query-preview-box">
            <div style="font-size: 10px; color: var(--text-muted); margin-bottom: 3px;">Compiled Formula Preview:</div>
            <code id="flt-query-preview-code">--</code>
          </div>

          <div style="display: flex; justify-content: flex-end; margin-top: 8px;">
            <button type="button" class="flt-btn-convert" id="btn-convert-query-to-custom" title="Push this compiled formula into the Custom Expression editor">
              ✨ Convert Query to Custom Expression
            </button>
          </div>
        </div>

        <!-- Syntax Guide & Clickable Chips -->
        <div class="flt-syntax-guide">
          <div style="font-size: 11px; font-weight: 600; color: var(--text-primary);">Quick Query Syntax Guide:</div>
          <div style="font-size: 10px; color: var(--text-muted); margin-top: 2px;">Click any example chip below to append to your search query:</div>
          <div class="flt-syntax-chips">
            <span class="flt-syntax-chip" data-example="Region:East"><b>Field:Val</b> (Region:East)</span>
            <span class="flt-syntax-chip" data-example="Sales>500"><b>Field&gt;Val</b> (Sales&gt;500)</span>
            <span class="flt-syntax-chip" data-example="Discount<=0.15"><b>Field&lt;=Val</b> (Discount&lt;=0.15)</span>
            <span class="flt-syntax-chip" data-example="Sales:100..500"><b>Field:Min..Max</b> (Sales:100..500)</span>
            <span class="flt-syntax-chip" data-example="Status:Active,Pending"><b>Field:A,B</b> (Status:Active,Pending)</span>
            <span class="flt-syntax-chip" data-example="Priority:High OR Urgent"><b>A OR B</b> (Priority:High OR Urgent)</span>
            <span class="flt-syntax-chip" data-example="Enterprise"><b>Keyword</b> (free text match)</span>
          </div>
        </div>
      </div>

      <!-- Outputs Partition Legend -->
      <div style="margin-top: 16px; padding: 10px; background: var(--bg-main); border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 11px;">
        <div style="font-weight: 700; color: var(--color-primary); margin-bottom: 4px;">Partition Outputs:</div>
        <div><b>T (True)</b>: Records that satisfy the filter condition (100% data retention)</div>
        <div><b>F (False)</b>: Records that do not satisfy the condition or evaluate to Null</div>
      </div>
    `;

    // -------------------------------------------------------------
    // Event Wiring
    // -------------------------------------------------------------

    // 1. Mode Tabs Switching
    const tabBtns = container.querySelectorAll('.flt-mode-tab');
    const tabBasic = container.querySelector('#cfg-filter-basic');
    const tabCustom = container.querySelector('#cfg-filter-custom');
    const tabQuery = container.querySelector('#cfg-filter-query');

    tabBtns.forEach(tab => {
      tab.addEventListener('click', () => {
        const selectedMode = tab.dataset.mode;
        node.config.mode = selectedMode;
        tabBtns.forEach(t => t.classList.toggle('active', t.dataset.mode === selectedMode));

        tabBasic.style.display = selectedMode === 'basic' ? '' : 'none';
        tabCustom.style.display = selectedMode === 'custom' ? '' : 'none';
        tabQuery.style.display = selectedMode === 'query' ? '' : 'none';

        if (selectedMode === 'custom' && syncCustomBackdrop) {
          syncCustomBackdrop();
          updateFltBadge();
        } else if (selectedMode === 'query' && updateQueryPreview) {
          updateQueryPreview();
        }

        this.canvas.onWorkflowChange();
      });
    });

    // 2. Basic Filter Logic
    const logicalSel = container.querySelector('#cfg-flt-logical');
    if (logicalSel) {
      logicalSel.addEventListener('change', (e) => {
        node.config.logical_op = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    const bindCondEvents = () => {
      container.querySelectorAll('.flt-cond-row').forEach(row => {
        const idx = parseInt(row.dataset.idx, 10);
        const cond = node.config.conditions[idx];
        if (!cond) return;

        const colEl = row.querySelector('.cond-col');
        const opEl = row.querySelector('.cond-op');
        const valEl = row.querySelector('.cond-val');
        const valMaxEl = row.querySelector('.cond-val-max');
        const ignoreCaseEl = row.querySelector('.cond-ignore-case');
        const removeBtn = row.querySelector('.btn-remove-cond');

        if (colEl) {
          colEl.addEventListener('change', (e) => {
            cond.column = e.target.value;
            this.canvas.onWorkflowChange();
          });
        }

        if (opEl) {
          opEl.addEventListener('change', (e) => {
            cond.operator = e.target.value;
            this.render(node);
            this.canvas.onWorkflowChange();
          });
        }

        if (valEl && !valEl.disabled) {
          valEl.addEventListener('input', (e) => {
            cond.value = e.target.value;
            this.canvas.onWorkflowChange();
          });
        }

        if (valMaxEl) {
          valMaxEl.addEventListener('input', (e) => {
            cond.value_max = e.target.value;
            this.canvas.onWorkflowChange();
          });
        }

        if (ignoreCaseEl) {
          ignoreCaseEl.addEventListener('change', (e) => {
            cond.ignore_case = e.target.checked;
            this.canvas.onWorkflowChange();
          });
        }

        if (removeBtn) {
          removeBtn.addEventListener('click', () => {
            node.config.conditions.splice(idx, 1);
            this.render(node);
            this.canvas.onWorkflowChange();
          });
        }
      });
    };
    bindCondEvents();

    const addCondBtn = container.querySelector('#btn-add-cond');
    if (addCondBtn) {
      addCondBtn.addEventListener('click', () => {
        const firstCol = (colMeta[0] && colMeta[0].name) || (upstreamCols && upstreamCols[0]) || '';
        node.config.conditions.push({
          column: firstCol,
          operator: '==',
          value: '',
          value_max: '',
          ignore_case: true
        });
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    }

    const convertToCustomBtn = container.querySelector('#btn-convert-to-custom');
    if (convertToCustomBtn) {
      convertToCustomBtn.addEventListener('click', () => {
        const compiled = this.compileConditionsToExpression(node.config.conditions, node.config.logical_op || 'AND');
        node.config.expression = compiled;
        node.config.mode = 'custom';
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    }

    // 3. Custom Expression Code Editor & Autocomplete
    const fltExpr = container.querySelector('#cfg-flt-expr');
    const fltBadge = container.querySelector('#flt-valid-badge');
    const editorBox = container.querySelector('#cfg-filter-custom .formula-editor-box');

    const updateFltBadge = () => {
      if (!fltBadge || !fltExpr) return;
      const status = this.validateFormulaExpression(fltExpr.value, upstreamCols);
      fltBadge.className = `formula-valid-badge ${status.type}`;
      fltBadge.textContent = status.msg;
      if (status.tooltip) fltBadge.setAttribute('title', status.tooltip);
    };

    let syncCustomBackdrop = null;
    if (editorBox && fltExpr) {
      syncCustomBackdrop = this.setupFormulaCodeEditor(editorBox, fltExpr, upstreamCols, () => {
        node.config.expression = fltExpr.value;
        updateFltBadge();
        this.canvas.onWorkflowChange();
      });

      this.setupFormulaAutocomplete(fltExpr, upstreamCols, () => {
        node.config.expression = fltExpr.value;
        if (syncCustomBackdrop) syncCustomBackdrop();
        updateFltBadge();
        this.canvas.onWorkflowChange();
      });

      updateFltBadge();
    }

    // Column chips insertion
    container.querySelectorAll('.flt-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const col = chip.dataset.col;
        if (fltExpr) {
          const start = fltExpr.selectionStart || fltExpr.value.length;
          const end = fltExpr.selectionEnd || fltExpr.value.length;
          const text = fltExpr.value;
          fltExpr.value = text.substring(0, start) + `[${col}]` + text.substring(end);
          fltExpr.focus();
          fltExpr.selectionStart = fltExpr.selectionEnd = start + col.length + 2;
          fltExpr.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    });

    // Quick function chips insertion
    container.querySelectorAll('.flt-quick-func').forEach(btn => {
      btn.addEventListener('click', () => {
        const code = btn.dataset.code;
        if (fltExpr) {
          const start = fltExpr.selectionStart || fltExpr.value.length;
          const end = fltExpr.selectionEnd || fltExpr.value.length;
          const text = fltExpr.value;
          fltExpr.value = text.substring(0, start) + code + text.substring(end);
          fltExpr.focus();
          const paren = code.indexOf('(');
          const newPos = start + (paren !== -1 ? paren + 1 : code.length);
          fltExpr.setSelectionRange(newPos, newPos);
          fltExpr.dispatchEvent(new Event('input', { bubbles: true }));
        }
      });
    });

    // Function Library Drawer in Custom Mode
    const fltBrowserToggle = container.querySelector('#btn-flt-toggle-funcs');
    const fltBrowserContent = container.querySelector('#flt-funcs-content');
    const fltBrowserArrow = container.querySelector('#flt-funcs-arrow');
    const fltFuncSearch = container.querySelector('#flt-func-search');
    const fltCatTabs = container.querySelectorAll('#flt-cat-tabs .formula-cat-tab');
    const fltFuncListContainer = container.querySelector('#flt-func-list');

    let fltCurrentCat = 'All';
    let fltSearchQuery = '';

    const renderFltFuncList = () => {
      if (!fltFuncListContainer) return;
      const filtered = catalog.filter(fn => {
        const matchesCat = (fltCurrentCat === 'All') || (fn.category.toLowerCase() === fltCurrentCat.toLowerCase());
        const matchesSearch = !fltSearchQuery || 
          fn.name.toLowerCase().includes(fltSearchQuery) || 
          fn.signature.toLowerCase().includes(fltSearchQuery) || 
          fn.doc.toLowerCase().includes(fltSearchQuery);
        return matchesCat && matchesSearch;
      });

      if (filtered.length === 0) {
        fltFuncListContainer.innerHTML = `<div style="font-size: 11px; color: var(--text-secondary); text-align: center; padding: 12px;">No matching functions found.</div>`;
        return;
      }

      fltFuncListContainer.innerHTML = filtered.map(fn => {
        const catClass = `cat-${fn.category.toLowerCase()}`;
        return `
          <div class="formula-func-card" data-template="${encodeURIComponent(fn.template)}" title="Double-click or click '+ Insert' to paste into expression">
            <div class="formula-func-head">
              <span class="formula-func-name">${fn.name}</span>
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="formula-ac-badge ${catClass}">${fn.category}</span>
                <button type="button" class="formula-func-insert-btn" title="Insert at cursor position">+ Insert</button>
              </div>
            </div>
            <div class="formula-func-sig">${fn.signature}</div>
            <div class="formula-func-doc">${fn.doc}</div>
            ${fn.example ? `<div class="formula-func-example"><span style="color: var(--text-muted); font-size: 9px;">Example:</span><code>${fn.example}</code></div>` : ''}
          </div>
        `;
      }).join('');

      fltFuncListContainer.querySelectorAll('.formula-func-card').forEach(card => {
        const insertAction = () => {
          const tmpl = decodeURIComponent(card.dataset.template);
          if (fltExpr) {
            const start = fltExpr.selectionStart || fltExpr.value.length;
            const end = fltExpr.selectionEnd || fltExpr.value.length;
            const text = fltExpr.value;
            fltExpr.value = text.substring(0, start) + tmpl + text.substring(end);
            fltExpr.focus();
            const paren = tmpl.indexOf('(');
            const newPos = start + (paren !== -1 ? paren + 1 : tmpl.length);
            fltExpr.setSelectionRange(newPos, newPos);
            fltExpr.dispatchEvent(new Event('input', { bubbles: true }));
          }
        };

        card.querySelector('.formula-func-insert-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          insertAction();
        });
        card.addEventListener('dblclick', insertAction);
      });
    };

    if (fltBrowserToggle && fltBrowserContent) {
      fltBrowserToggle.addEventListener('click', () => {
        const isOpen = fltBrowserContent.classList.toggle('open');
        fltBrowserArrow.textContent = isOpen ? '▲' : '▼';
        if (isOpen && fltFuncListContainer.children.length === 0) {
          renderFltFuncList();
        }
      });
    }

    if (fltFuncSearch) {
      fltFuncSearch.addEventListener('input', (e) => {
        fltSearchQuery = e.target.value.toLowerCase().trim();
        renderFltFuncList();
      });
    }

    fltCatTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        fltCatTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        fltCurrentCat = tab.dataset.cat;
        renderFltFuncList();
      });
    });

    // 4. Quick Query Logic
    const queryInput = container.querySelector('#cfg-flt-query');
    const queryPreviewCode = container.querySelector('#flt-query-preview-code');
    const updateQueryPreview = () => {
      if (!queryPreviewCode) return;
      const qVal = queryInput ? queryInput.value.trim() : '';
      if (!qVal) {
        queryPreviewCode.textContent = '(all records match)';
        return;
      }
      const compiled = this.compileQueryToExpression(qVal);
      queryPreviewCode.textContent = compiled || '(empty)';
    };
    updateQueryPreview();

    if (queryInput) {
      queryInput.addEventListener('input', (e) => {
        node.config.query = e.target.value;
        updateQueryPreview();
        this.canvas.onWorkflowChange();
      });
    }

    // Syntax Guide Chips
    container.querySelectorAll('.flt-syntax-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const ex = chip.dataset.example;
        if (queryInput) {
          const cur = queryInput.value.trim();
          queryInput.value = cur ? `${cur} ${ex}` : ex;
          node.config.query = queryInput.value;
          updateQueryPreview();
          queryInput.focus();
          this.canvas.onWorkflowChange();
        }
      });
    });

    // Convert Query to Custom Expression
    const btnConvertQuery = container.querySelector('#btn-convert-query-to-custom');
    if (btnConvertQuery) {
      btnConvertQuery.addEventListener('click', () => {
        const qVal = queryInput ? queryInput.value.trim() : '';
        const compiled = this.compileQueryToExpression(qVal);
        node.config.expression = compiled;
        node.config.mode = 'custom';
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    }
  }

  // --------------------------------------------------------------------
  // 5. Formula Tool & Expression Helpers
  // --------------------------------------------------------------------

  validateFormulaExpression(expr, upstreamCols) {
    const trimmed = (expr || '').trim();
    if (!trimmed) {
      return { valid: true, type: 'empty', msg: '', tooltip: 'Enter an expression to calculate a column.' };
    }

    // Bracket balancing
    let openBrackets = 0;
    for (let i = 0; i < trimmed.length; i++) {
      if (trimmed[i] === '[') openBrackets++;
      else if (trimmed[i] === ']') openBrackets--;
      if (openBrackets < 0) {
        return { valid: false, type: 'warning', msg: "⚠ Unmatched closing ']' bracket", tooltip: "Encountered a closing ']' before an opening '['." };
      }
    }
    if (openBrackets > 0) {
      return { valid: false, type: 'warning', msg: "⚠ Unclosed '[' bracket", tooltip: "Every '[' column reference must have a matching ']'." };
    }

    // Unclosed string literal quotes
    let inSingle = false;
    let inDouble = false;
    for (let i = 0; i < trimmed.length; i++) {
      const ch = trimmed[i];
      if (ch === "'" && !inDouble && (i === 0 || trimmed[i - 1] !== '\\')) {
        inSingle = !inSingle;
      } else if (ch === '"' && !inSingle && (i === 0 || trimmed[i - 1] !== '\\')) {
        inDouble = !inDouble;
      }
    }
    if (inSingle || inDouble) {
      return { valid: false, type: 'warning', msg: "⚠ Unclosed string quote", tooltip: "Ensure all string literals have matching opening and closing quotes." };
    }

    // Parentheses balancing
    let openParens = 0;
    for (let i = 0; i < trimmed.length; i++) {
      if (trimmed[i] === '(') openParens++;
      else if (trimmed[i] === ')') openParens--;
      if (openParens < 0) {
        return { valid: false, type: 'warning', msg: "⚠ Unmatched closing ')' parenthesis", tooltip: "Encountered a closing ')' before an opening '('." };
      }
    }
    if (openParens > 0) {
      return { valid: false, type: 'warning', msg: "⚠ Unclosed '(' parenthesis", tooltip: "Found unmatched opening '(' parenthesis without a closing ')'." };
    }

    // Conditional IF / ENDIF balancing
    const upper = trimmed.toUpperCase();
    const ifTokens = (upper.match(/\bIF\b/g) || []).length;
    const iifTokens = (upper.match(/\bIIF\b/g) || []).length;
    const standaloneIf = ifTokens - iifTokens;
    const endifTokens = (upper.match(/\bENDIF\b/g) || []).length;
    if (standaloneIf > 0 && endifTokens < standaloneIf) {
      return { valid: false, type: 'warning', msg: `⚠ Missing ENDIF (${standaloneIf} IF, ${endifTokens} ENDIF)`, tooltip: "Every standalone IF block in Alteryx expressions must conclude with ENDIF." };
    }

    // Column validation against upstreamCols
    const available = (upstreamCols && upstreamCols.length > 0)
      ? upstreamCols
      : (this.getUpstreamColumns && this.currentNode ? this.getUpstreamColumns(this.currentNode.id) : []);

    if (available && available.length > 0) {
      const bracketCols = [...trimmed.matchAll(/\[(.*?)\]/g)].map(m => m[1]);
      for (const col of bracketCols) {
        if (!available.some(c => c.toLowerCase() === col.toLowerCase())) {
          return { valid: false, type: 'error', msg: `⚠ Column '[${col}]' not found in upstream data`, tooltip: `The field '[${col}]' does not exist in incoming datasets. Check spelling or upstream node output.` };
        }
      }
    }

    return { valid: true, type: 'valid', msg: '✓ Valid expression & columns', tooltip: 'Formula syntax is balanced and all referenced fields are verified.' };
  }

  highlightFormulaSyntax(expr, upstreamCols) {
    if (!expr) return '<br>';

    const escape = (str) => String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    const tokenRegex = /(".*?"|'.*?'|\[.*?\]?|\b(?:IF|THEN|ELSEIF|ELSE|ENDIF|AND|OR|NOT)\b|\b(?:Contains|StartsWith|EndsWith|RegexMatch|Regex_Match|RegexCountMatches|Regex_CountMatches|RegexReplace|Regex_Replace|Left|Right|Substring|Uppercase|Lowercase|TitleCase|Trim|Length|Replace|Concat|DateTimeToday|DateTimeNow|DateTimeAdd|DateTimeDiff|DateTimeFormat|DateTimeYear|DateTimeMonth|DateTimeDay|Round|Abs|Ceil|Floor|Min|Max|Between|IIF|IsNull|NotNull|IsNotNull|IsEmpty|NotEmpty|IsNotEmpty|IsNumber|IsInteger|IsDate|Null|ToNumber|ToString)\b|\b\d+(?:\.\d+)?\b|==|!=|<=|>=|&&|\|\||[+\-*/%<>=!&|^~()]|[\s\S])/gi;

    let html = '';
    let match;

    while ((match = tokenRegex.exec(expr)) !== null) {
      const tok = match[0];
      const first = tok[0];

      if (first === '"' || first === "'") {
        html += `<span class="tok-string">${escape(tok)}</span>`;
      } else if (first === '[') {
        if (tok.endsWith(']')) {
          const colName = tok.slice(1, -1);
          if (upstreamCols && upstreamCols.length > 0 && !upstreamCols.some(c => c.toLowerCase() === colName.toLowerCase())) {
            html += `<span class="tok-unknown-col" title="Column not found in upstream data">${escape(tok)}</span>`;
          } else {
            html += `<span class="tok-col">${escape(tok)}</span>`;
          }
        } else {
          html += `<span class="tok-col tok-unclosed">${escape(tok)}</span>`;
        }
      } else if (/^(?:IF|THEN|ELSEIF|ELSE|ENDIF|AND|OR|NOT)$/i.test(tok)) {
        html += `<span class="tok-keyword">${escape(tok)}</span>`;
      } else if (/^(?:Contains|StartsWith|EndsWith|RegexMatch|Regex_Match|RegexCountMatches|Regex_CountMatches|RegexReplace|Regex_Replace|Left|Right|Substring|Uppercase|Lowercase|TitleCase|Trim|Length|Replace|Concat|DateTimeToday|DateTimeNow|DateTimeAdd|DateTimeDiff|DateTimeFormat|DateTimeYear|DateTimeMonth|DateTimeDay|Round|Abs|Ceil|Floor|Min|Max|Between|IIF|IsNull|NotNull|IsNotNull|IsEmpty|NotEmpty|IsNotEmpty|IsNumber|IsInteger|IsDate|Null|ToNumber|ToString)$/i.test(tok)) {
        html += `<span class="tok-func">${escape(tok)}</span>`;
      } else if (/^\d+(?:\.\d+)?$/.test(tok)) {
        html += `<span class="tok-num">${escape(tok)}</span>`;
      } else if (/^(?:==|!=|<=|>=|&&|\|\||[+\-*/%<>=!&|^~])$/.test(tok)) {
        html += `<span class="tok-op">${escape(tok)}</span>`;
      } else if (tok === '(' || tok === ')') {
        html += `<span class="tok-bracket">${escape(tok)}</span>`;
      } else {
        html += escape(tok);
      }
    }

    if (expr.endsWith('\n')) {
      html += '<br>&nbsp;';
    }

    return html;
  }

  setupFormulaCodeEditor(boxEl, textarea, upstreamCols, onValueChange) {
    let backdrop = boxEl.querySelector('.formula-backdrop');
    if (!backdrop) {
      backdrop = document.createElement('pre');
      backdrop.className = 'formula-backdrop';
      backdrop.setAttribute('aria-hidden', 'true');
      boxEl.insertBefore(backdrop, textarea);
    }

    const syncBackdrop = () => {
      const cols = (upstreamCols && upstreamCols.length > 0)
        ? upstreamCols
        : (this.getUpstreamColumns && this.currentNode ? this.getUpstreamColumns(this.currentNode.id) : []);
      backdrop.innerHTML = this.highlightFormulaSyntax(textarea.value, cols);
      backdrop.scrollTop = textarea.scrollTop;
      backdrop.scrollLeft = textarea.scrollLeft;
    };

    textarea.addEventListener('input', () => {
      syncBackdrop();
      if (onValueChange) onValueChange();
    });

    textarea.addEventListener('scroll', () => {
      backdrop.scrollTop = textarea.scrollTop;
      backdrop.scrollLeft = textarea.scrollLeft;
    });

    syncBackdrop();
    return syncBackdrop;
  }

  getFormulaCatalog() {
    return [
      // String
      { name: 'Contains', category: 'String', signature: 'Contains(str, target, [case_insensitive])', doc: 'Tests if target substring is found in string. Case-insensitive by default.', example: "Contains([Region], 'East')", template: "Contains([col], 'text')" },
      { name: 'StartsWith', category: 'String', signature: 'StartsWith(str, prefix, [case_insensitive])', doc: 'Tests if string begins with prefix. Case-insensitive by default.', example: "StartsWith([SKU], 'PROD')", template: "StartsWith([col], 'prefix')" },
      { name: 'EndsWith', category: 'String', signature: 'EndsWith(str, suffix, [case_insensitive])', doc: 'Tests if string concludes with suffix. Case-insensitive by default.', example: "EndsWith([Email], '.org')", template: "EndsWith([col], 'suffix')" },
      { name: 'RegexMatch', category: 'String', signature: 'RegexMatch(str, pattern)', doc: 'Tests whether string matches regular expression pattern.', example: "RegexMatch([Zip], '^\\d{5}$')", template: "RegexMatch([col], 'pattern')" },
      { name: 'RegexCountMatches', category: 'String', signature: 'RegexCountMatches(str, pattern)', doc: 'Counts the number of regex matches found in string.', example: "RegexCountMatches([Text], '\\b\\w+\\b')", template: "RegexCountMatches([col], 'pattern')" },
      { name: 'RegexReplace', category: 'String', signature: 'RegexReplace(str, pattern, replacement)', doc: 'Replaces all occurrences matching regex pattern with replacement string.', example: "RegexReplace([Phone], '\\D', '')", template: "RegexReplace([col], 'pattern', 'replacement')" },
      { name: 'Left', category: 'String', signature: 'Left(str, len)', doc: 'Returns the first len characters of string.', example: "Left([PostalCode], 3)", template: "Left([col], 3)" },
      { name: 'Right', category: 'String', signature: 'Right(str, len)', doc: 'Returns the last len characters of string.', example: "Right([AccountNo], 4)", template: "Right([col], 4)" },
      { name: 'Substring', category: 'String', signature: 'Substring(str, start, [len])', doc: 'Extracts a substring starting at 0-based index of specified length.', example: "Substring([SKU], 0, 5)", template: "Substring([col], 0, 5)" },
      { name: 'Uppercase', category: 'String', signature: 'Uppercase(str)', doc: 'Converts all characters in string to uppercase.', example: "Uppercase([CustomerName])", template: "Uppercase([col])" },
      { name: 'Lowercase', category: 'String', signature: 'Lowercase(str)', doc: 'Converts all characters in string to lowercase.', example: "Lowercase([Email])", template: "Lowercase([col])" },
      { name: 'TitleCase', category: 'String', signature: 'TitleCase(str)', doc: 'Capitalizes the first character of each word (proper case).', example: "TitleCase([City])", template: "TitleCase([col])" },
      { name: 'Trim', category: 'String', signature: 'Trim(str)', doc: 'Strips leading and trailing whitespace characters.', example: "Trim([Notes])", template: "Trim([col])" },
      { name: 'Length', category: 'String', signature: 'Length(str)', doc: 'Returns character length / count of string.', example: "Length([Description])", template: "Length([col])" },
      { name: 'Replace', category: 'String', signature: 'Replace(str, target, replacement)', doc: 'Replaces all occurrences of target with replacement string.', example: "Replace([Phone], '-', '')", template: "Replace([col], 'search', 'replace')" },
      { name: 'Concat', category: 'String', signature: 'Concat(str1, str2, ...)', doc: 'Concatenates two or more strings together.', example: "Concat([FirstName], ' ', [LastName])", template: "Concat([col1], ' ', [col2])" },

      // DateTime
      { name: 'DateTimeToday', category: 'DateTime', signature: 'DateTimeToday()', doc: 'Returns current date in YYYY-MM-DD format.', example: "DateTimeToday()", template: "DateTimeToday()" },
      { name: 'DateTimeNow', category: 'DateTime', signature: 'DateTimeNow()', doc: 'Returns current timestamp in YYYY-MM-DD HH:MM:SS format.', example: "DateTimeNow()", template: "DateTimeNow()" },
      { name: 'DateTimeAdd', category: 'DateTime', signature: "DateTimeAdd(dt, num, 'unit')", doc: "Adds or subtracts interval ('days', 'hours', 'minutes', 'seconds', 'months', 'years').", example: "DateTimeAdd([OrderDate], 7, 'days')", template: "DateTimeAdd([date_col], 7, 'days')" },
      { name: 'DateTimeDiff', category: 'DateTime', signature: "DateTimeDiff(dt1, dt2, 'unit')", doc: "Calculates difference (dt1 - dt2) in specified units.", example: "DateTimeDiff([ShipDate], [OrderDate], 'days')", template: "DateTimeDiff([date1], [date2], 'days')" },
      { name: 'DateTimeFormat', category: 'DateTime', signature: "DateTimeFormat(dt, '%Y-%m-%d')", doc: 'Formats date/time using standard strftime pattern string.', example: "DateTimeFormat([CreatedAt], '%b %d, %Y')", template: "DateTimeFormat([date_col], '%Y-%m-%d')" },
      { name: 'DateTimeYear', category: 'DateTime', signature: 'DateTimeYear(dt)', doc: 'Extracts 4-digit integer year from date/time.', example: "DateTimeYear([OrderDate])", template: "DateTimeYear([date_col])" },
      { name: 'DateTimeMonth', category: 'DateTime', signature: 'DateTimeMonth(dt)', doc: 'Extracts numeric month (1-12) from date/time.', example: "DateTimeMonth([OrderDate])", template: "DateTimeMonth([date_col])" },
      { name: 'DateTimeDay', category: 'DateTime', signature: 'DateTimeDay(dt)', doc: 'Extracts numeric day of month (1-31) from date/time.', example: "DateTimeDay([OrderDate])", template: "DateTimeDay([date_col])" },

      // Math
      { name: 'Round', category: 'Math', signature: 'Round(num, [decimals])', doc: 'Rounds number to specified decimal places (default 0).', example: "Round([Price] * 1.08, 2)", template: "Round([num_col], 2)" },
      { name: 'Abs', category: 'Math', signature: 'Abs(num)', doc: 'Returns absolute positive value of number.', example: "Abs([Variance])", template: "Abs([num_col])" },
      { name: 'Ceil', category: 'Math', signature: 'Ceil(num)', doc: 'Returns smallest integer greater than or equal to number.', example: "Ceil([FreightCost])", template: "Ceil([num_col])" },
      { name: 'Floor', category: 'Math', signature: 'Floor(num)', doc: 'Returns largest integer less than or equal to number.', example: "Floor([Rating])", template: "Floor([num_col])" },
      { name: 'Min', category: 'Math', signature: 'Min(a, b, ...)', doc: 'Returns the minimum value among arguments.', example: "Min([ScoreA], [ScoreB])", template: "Min([col1], [col2])" },
      { name: 'Max', category: 'Math', signature: 'Max(a, b, ...)', doc: 'Returns the maximum value among arguments.', example: "Max([DiscountRate], 0.05)", template: "Max([col1], [col2])" },
      { name: 'Between', category: 'Math', signature: 'Between(val, min, max)', doc: 'Tests if value is within inclusive range [min, max].', example: "Between([Sales], 100, 500)", template: "Between([col], min, max)" },

      // Conditional
      { name: 'IF', category: 'Conditional', signature: 'IF <condition> THEN <true> ELSE <false> ENDIF', doc: 'Alteryx multi-branch conditional block (supports ELSEIF).', example: "IF [Sales] > 1000 THEN 'Gold' ELSE 'Silver' ENDIF", template: "IF [col] > 0 THEN 'True' ELSE 'False' ENDIF" },
      { name: 'IIF', category: 'Conditional', signature: 'IIF(condition, true_val, false_val)', doc: 'Immediate inline if functional expression.', example: "IIF([Discount] > 0.2, 'High Discount', 'Standard')", template: "IIF([col] > 100, 'High', 'Standard')" },

      // Operators
      { name: '+ (Add / Concat)', category: 'Operators', signature: 'a + b', doc: 'Adds numeric values or concatenates text strings.', example: "[SubTotal] + [Tax]", template: " + " },
      { name: '- (Subtract)', category: 'Operators', signature: 'a - b', doc: 'Subtracts right numeric operand from left.', example: "[Revenue] - [Cost]", template: " - " },
      { name: '* (Multiply)', category: 'Operators', signature: 'a * b', doc: 'Multiplies two numeric operands.', example: "[Price] * [Quantity]", template: " * " },
      { name: '/ (Divide)', category: 'Operators', signature: 'a / b', doc: 'Divides left operand by right operand.', example: "[TotalSales] / [Units]", template: " / " },
      { name: '== (Equal)', category: 'Operators', signature: 'a == b', doc: 'Tests equality between two values.', example: "[Status] == 'Active'", template: " == " },
      { name: '!= (Not Equal)', category: 'Operators', signature: 'a != b', doc: 'Tests inequality between two values.', example: "[Region] != 'West'", template: " != " },
      { name: '> (Greater Than)', category: 'Operators', signature: 'a > b', doc: 'Tests if left value is strictly greater than right.', example: "[NetSales] > 500", template: " > " },
      { name: '< (Less Than)', category: 'Operators', signature: 'a < b', doc: 'Tests if left value is strictly less than right.', example: "[Discount] < 0.1", template: " < " },
      { name: '>= (Greater or Equal)', category: 'Operators', signature: 'a >= b', doc: 'Tests if left value is greater than or equal to right.', example: "[Age] >= 18", template: " >= " },
      { name: '<= (Less or Equal)', category: 'Operators', signature: 'a <= b', doc: 'Tests if left value is less than or equal to right.', example: "[Score] <= 50", template: " <= " },
      { name: 'AND (Logical AND)', category: 'Operators', signature: 'cond1 AND cond2', doc: 'Returns true only if both conditions are met.', example: "[Sales] > 100 AND [Margin] > 0.2", template: " AND " },
      { name: 'OR (Logical OR)', category: 'Operators', signature: 'cond1 OR cond2', doc: 'Returns true if either condition is met.', example: "[Tier] == 'VIP' OR [TotalSpend] > 5000", template: " OR " },
      { name: 'NOT (Logical NOT)', category: 'Operators', signature: 'NOT cond', doc: 'Inverts truth value of condition.', example: "NOT IsNull([Email])", template: "NOT " },

      // Conversion & Nulls
      { name: 'IsNull', category: 'Conversion', signature: 'IsNull(val)', doc: 'Returns true if value is null, missing, or NaN.', example: "IsNull([ShippingDate])", template: "IsNull([col])" },
      { name: 'NotNull', category: 'Conversion', signature: 'NotNull(val)', doc: 'Returns true if value is NOT null or missing.', example: "NotNull([Discount])", template: "NotNull([col])" },
      { name: 'IsEmpty', category: 'Conversion', signature: 'IsEmpty(str)', doc: 'Returns true if value is null or empty/whitespace string.', example: "IsEmpty([MiddleName])", template: "IsEmpty([col])" },
      { name: 'NotEmpty', category: 'Conversion', signature: 'NotEmpty(str)', doc: 'Returns true if string has non-whitespace characters.', example: "NotEmpty([Notes])", template: "NotEmpty([col])" },
      { name: 'IsNumber', category: 'Conversion', signature: 'IsNumber(val)', doc: 'Tests if value is numeric or can be parsed as a number.', example: "IsNumber([ZipCode])", template: "IsNumber([col])" },
      { name: 'IsInteger', category: 'Conversion', signature: 'IsInteger(val)', doc: 'Tests if value is an integer or whole number.', example: "IsInteger([Quantity])", template: "IsInteger([col])" },
      { name: 'IsDate', category: 'Conversion', signature: 'IsDate(val)', doc: 'Tests if value is a valid date or datetime.', example: "IsDate([OrderDate])", template: "IsDate([col])" },
      { name: 'Null', category: 'Conversion', signature: 'Null()', doc: 'Produces an explicit Null / NaN value.', example: "Null()", template: "Null()" },
      { name: 'ToNumber', category: 'Conversion', signature: 'ToNumber(val)', doc: 'Cleans currency symbols/commas and converts string to numeric.', example: "ToNumber([RawAmount])", template: "ToNumber([col])" },
      { name: 'ToString', category: 'Conversion', signature: 'ToString(val)', doc: 'Converts value or column to string representation.', example: "ToString([PostalCode])", template: "ToString([col])" }
    ];
  }

  setupFormulaAutocomplete(textarea, upstreamCols, onValueChange) {
    let dropdown = null;
    let activeIdx = 0;
    let currentSuggestions = [];
    let triggerType = null; // 'column' or 'function'
    let replaceStart = 0;
    let replaceEnd = 0;

    const catalog = this.getFormulaCatalog();

    const closeDropdown = () => {
      if (dropdown && dropdown.parentNode) {
        dropdown.parentNode.removeChild(dropdown);
      }
      dropdown = null;
      currentSuggestions = [];
      activeIdx = 0;
    };

    const selectItem = (item) => {
      const text = textarea.value;
      const before = text.slice(0, replaceStart);
      const after = text.slice(replaceEnd);
      let insertText = '';
      let cursorOffset = 0;

      if (triggerType === 'column') {
        insertText = `[${item.name}]`;
        cursorOffset = insertText.length;
      } else {
        insertText = item.template || `${item.name}()`;
        const parenIdx = insertText.indexOf('(');
        if (parenIdx !== -1) {
          cursorOffset = parenIdx + 1;
        } else {
          cursorOffset = insertText.length;
        }
      }

      textarea.value = before + insertText + after;
      const newPos = replaceStart + cursorOffset;
      textarea.setSelectionRange(newPos, newPos);
      textarea.focus();
      closeDropdown();
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      if (onValueChange) onValueChange();
    };

    const renderDropdown = (items, type) => {
      closeDropdown();
      if (!items || items.length === 0) return;

      currentSuggestions = items;
      triggerType = type;
      activeIdx = 0;

      dropdown = document.createElement('div');
      dropdown.className = 'formula-ac-dropdown';

      items.forEach((it, idx) => {
        const itemEl = document.createElement('div');
        itemEl.className = `formula-ac-item ${idx === 0 ? 'active' : ''}`;
        
        if (type === 'column') {
          let iconClass = 'col-icon';
          let iconText = '#';
          let badgeClass = 'cat-column';
          let typeLabel = it.type || 'Field';

          const t = (it.type || '').toLowerCase();
          if (/num|int|float|double|dec/.test(t)) {
            iconClass = 'col-num';
            iconText = '#';
            badgeClass = 'type-numeric';
            typeLabel = it.type === 'integer' ? 'Int64' : (it.type === 'float' ? 'Double' : 'Numeric');
          } else if (/str|text|char/.test(t)) {
            iconClass = 'col-str';
            iconText = 'Aa';
            badgeClass = 'type-string';
            typeLabel = 'String';
          } else if (/date|time/.test(t)) {
            iconClass = 'col-date';
            iconText = '📅';
            badgeClass = 'type-datetime';
            typeLabel = 'Date';
          } else if (/bool/.test(t)) {
            iconClass = 'col-bool';
            iconText = '✓';
            badgeClass = 'type-boolean';
            typeLabel = 'Bool';
          }

          itemEl.innerHTML = `
            <div class="formula-ac-left">
              <span class="formula-ac-icon ${iconClass}">${iconText}</span>
              <span class="formula-ac-label">[${it.name}]</span>
            </div>
            <span class="formula-ac-badge ${badgeClass}">${typeLabel}</span>
          `;
        } else {
          const catClass = `cat-${(it.category || 'conversion').toLowerCase()}`;
          itemEl.innerHTML = `
            <div class="formula-ac-left">
              <span class="formula-ac-icon func-icon">fx</span>
              <div>
                <span class="formula-ac-label">${it.name}</span>
                <div style="font-size: 10px; color: var(--text-secondary);">${it.signature}</div>
              </div>
            </div>
            <span class="formula-ac-badge ${catClass}">${it.category}</span>
          `;
        }

        itemEl.addEventListener('mousedown', (e) => {
          e.preventDefault();
          selectItem(it);
        });
        dropdown.appendChild(itemEl);
      });

      const wrapper = textarea.closest('.formula-editor-wrapper') || textarea.parentElement;
      const box = textarea.closest('.formula-editor-box') || textarea;
      if (wrapper) {
        wrapper.style.position = 'relative';
        dropdown.style.top = `${box.offsetTop + box.offsetHeight + 2}px`;
        dropdown.style.left = `${box.offsetLeft}px`;
        dropdown.style.width = `${Math.max(280, Math.min(380, box.offsetWidth || 340))}px`;
        wrapper.appendChild(dropdown);
      }
    };

    const checkAutocomplete = () => {
      const caret = textarea.selectionStart;
      const textBefore = textarea.value.slice(0, caret);

      // Check column trigger '['
      const colMatch = textBefore.match(/\[([^[\]\n]*)$/);
      if (colMatch) {
        const query = colMatch[1].toLowerCase().trim();
        replaceStart = caret - colMatch[1].length - 1;
        replaceEnd = caret;

        let colMeta = [];
        if (this.getUpstreamColumnMeta && this.currentNode) {
          colMeta = this.getUpstreamColumnMeta(this.currentNode.id);
        }
        if (!colMeta || colMeta.length === 0) {
          const cols = (upstreamCols && upstreamCols.length > 0)
            ? upstreamCols
            : (this.getUpstreamColumns && this.currentNode ? this.getUpstreamColumns(this.currentNode.id) : []);
          colMeta = (cols || []).map(c => ({ name: c, type: 'unknown' }));
        }

        const matches = colMeta.filter(c => c.name.toLowerCase().includes(query));
        if (matches.length > 0) {
          renderDropdown(matches.slice(0, 8), 'column');
          return;
        }
      }

      // Check function trigger (word of 2+ chars after start or operator/space)
      const funcMatch = textBefore.match(/(?:^|[\s,(=+\-*/%&|!><])([A-Za-z]{2,})$/);
      if (funcMatch) {
        const query = funcMatch[1].toLowerCase();
        replaceStart = caret - funcMatch[1].length;
        replaceEnd = caret;
        const matches = catalog.filter(f => 
          f.name.toLowerCase().includes(query)
        );
        if (matches.length > 0) {
          renderDropdown(matches.slice(0, 6), 'function');
          return;
        }
      }

      closeDropdown();
    };

    textarea.addEventListener('input', checkAutocomplete);
    textarea.addEventListener('click', checkAutocomplete);
    textarea.addEventListener('blur', () => {
      setTimeout(closeDropdown, 200);
    });

    textarea.addEventListener('keydown', (e) => {
      if (!dropdown || currentSuggestions.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = (activeIdx + 1) % currentSuggestions.length;
        updateActiveItem();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = (activeIdx - 1 + currentSuggestions.length) % currentSuggestions.length;
        updateActiveItem();
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        selectItem(currentSuggestions[activeIdx]);
      } else if (e.key === 'Escape') {
        e.preventDefault();
        closeDropdown();
      }
    });

    const updateActiveItem = () => {
      if (!dropdown) return;
      const items = dropdown.querySelectorAll('.formula-ac-item');
      items.forEach((el, idx) => {
        el.classList.toggle('active', idx === activeIdx);
        if (idx === activeIdx) {
          el.scrollIntoView({ block: 'nearest' });
        }
      });
    };
  }

  renderFormulaConfig(container, node, upstreamCols = []) {
    const cfg = node.config || {};
    const formulas = cfg.formulas || [];
    const catalog = this.getFormulaCatalog();

    const colMetas = this.getUpstreamColumnMeta(node.id) || [];
    const metaMap = {};
    colMetas.forEach(m => {
      if (m && m.name) metaMap[m.name] = (m.type || m.alteryx_type || 'string').toLowerCase();
    });

    const inferType = (colName) => {
      if (metaMap[colName]) {
        const t = metaMap[colName];
        if (t.includes('int')) return 'integer';
        if (t.includes('float') || t.includes('double') || t.includes('num')) return 'float';
        if (t.includes('date')) return 'date';
        if (t.includes('time')) return 'datetime';
        if (t.includes('bool')) return 'boolean';
        return 'string';
      }
      const low = (colName || '').toLowerCase();
      if (/date|time|timestamp|_dt\b/.test(low)) return 'datetime';
      if (/\b(id|num|qty|amount|price|cost|sales|revenue|rate|count|total|tax|disc|discount|margin|profit|score)\b|_id$/.test(low)) return 'float';
      return 'string';
    };

    const chipsHtml = upstreamCols && upstreamCols.length > 0 ? `
      <div class="column-chips-wrapper" style="margin-bottom: 10px;">
        <div class="column-chips-label">Available Columns (click or type <code>[</code>):</div>
        <div class="column-chips-container">
          ${upstreamCols.map(c => `<span class="column-chip" data-col="${c}">+ [${c}]</span>`).join('')}
        </div>
      </div>
    ` : '';

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 10px;">
        Compute new fields or update existing columns in-place using vectorized expressions, conditional logic, and functions.
      </div>

      <!-- Function Browser Collapsible -->
      <div class="formula-func-browser">
        <div class="formula-browser-toggle" id="btn-toggle-func-browser">
          <span>📘 Function Library &amp; Reference (${catalog.length} functions)</span>
          <span id="func-browser-arrow">▼</span>
        </div>
        <div class="formula-browser-content" id="func-browser-content">
          <input type="text" class="formula-browser-search" id="input-func-search" placeholder="Search functions (e.g. add, diff, trim, case)..." />
          <div class="formula-cat-tabs" id="func-cat-tabs">
            <button class="formula-cat-tab active" data-cat="All">All (${catalog.length})</button>
            <button class="formula-cat-tab" data-cat="String">String</button>
            <button class="formula-cat-tab" data-cat="DateTime">DateTime</button>
            <button class="formula-cat-tab" data-cat="Math">Math</button>
            <button class="formula-cat-tab" data-cat="Conditional">Conditional</button>
            <button class="formula-cat-tab" data-cat="Operators">Operators</button>
            <button class="formula-cat-tab" data-cat="Conversion">Conversion</button>
          </div>
          <div class="formula-func-list" id="func-list-container"></div>
        </div>
      </div>

      ${chipsHtml}

      <div id="cfg-formula-list">
        ${formulas.map((f, i) => {
          const isExisting = upstreamCols && upstreamCols.includes(f.output_field);
          return `
          <div class="formula-card" data-idx="${i}">
            <div class="formula-card-header">
              <div class="formula-card-title">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 7V4h16v3M9 20h6M12 4v16"/></svg>
                <span>Formula #${i + 1}</span>
                ${isExisting ? `<span style="font-size: 9px; padding: 1px 5px; border-radius: 3px; background: rgba(56, 189, 248, 0.15); color: #38bdf8; font-weight: 600; margin-left: 6px;">↻ Update Existing</span>` : `<span style="font-size: 9px; padding: 1px 5px; border-radius: 3px; background: rgba(34, 197, 94, 0.15); color: #22c55e; font-weight: 600; margin-left: 6px;">+ New Column</span>`}
              </div>
              <div class="formula-card-actions">
                <button class="formula-btn-tool btn-move-up" data-idx="${i}" title="Move Up" ${i === 0 ? 'disabled' : ''}>▲</button>
                <button class="formula-btn-tool btn-move-down" data-idx="${i}" title="Move Down" ${i === formulas.length - 1 ? 'disabled' : ''}>▼</button>
                <button class="formula-btn-tool btn-duplicate-formula" data-idx="${i}" title="Duplicate Formula">📋</button>
                <button class="formula-btn-tool btn-danger btn-remove-formula" data-idx="${i}" title="Delete Formula">&times;</button>
              </div>
            </div>

            <!-- Output Column Target Mode Selector -->
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
              <label style="font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 0;">Output Column Target</label>
              <div class="formula-out-mode-pills" style="display: flex; gap: 4px;">
                <button type="button" class="btn-formula-out-mode ${!isExisting ? 'active' : ''}" data-idx="${i}" data-mode="new" style="padding: 2px 7px; font-size: 10px; border-radius: 3px; border: 1px solid ${!isExisting ? 'var(--color-primary, #0284c7)' : 'var(--border-subtle)'}; background: ${!isExisting ? 'var(--color-primary, #0284c7)' : 'var(--bg-main)'}; color: ${!isExisting ? '#fff' : 'var(--text-primary)'}; cursor: pointer;">
                  + Add Column
                </button>
                <button type="button" class="btn-formula-out-mode ${isExisting ? 'active' : ''}" data-idx="${i}" data-mode="update" style="padding: 2px 7px; font-size: 10px; border-radius: 3px; border: 1px solid ${isExisting ? 'var(--color-primary, #0284c7)' : 'var(--border-subtle)'}; background: ${isExisting ? 'var(--color-primary, #0284c7)' : 'var(--bg-main)'}; color: ${isExisting ? '#fff' : 'var(--text-primary)'}; cursor: pointer;">
                  ↻ Update Existing
                </button>
              </div>
            </div>
            
            <div class="form-row" style="margin-bottom: 8px;">
              <div class="form-group form-col-target-wrap" style="flex: 2; margin-bottom: 0;">
                <div class="form-col-new-box" style="display: ${!isExisting ? 'block' : 'none'};">
                  <input type="text" class="form-control form-col-name" value="${!isExisting ? (f.output_field || '') : ''}" placeholder="e.g. TotalWithTax">
                </div>
                <div class="form-col-update-box" style="display: ${isExisting ? 'block' : 'none'};">
                  <select class="form-control form-col-existing-select">
                    ${upstreamCols.length > 0 
                      ? upstreamCols.map(col => `<option value="${this.escapeHtml(col)}" ${f.output_field === col ? 'selected' : ''}>${this.escapeHtml(col)} (${inferType(col)})</option>`).join('')
                      : `<option value="${this.escapeHtml(f.output_field || '')}">${this.escapeHtml(f.output_field || 'Select column')}</option>`}
                  </select>
                </div>
              </div>
              <div class="form-group" style="flex: 1.2; margin-bottom: 0;">
                <label>Data Type</label>
                <select class="form-control form-col-type">
                  <option value="string" ${f.type === 'string' ? 'selected' : ''}>String</option>
                  <option value="integer" ${f.type === 'integer' ? 'selected' : ''}>Int64</option>
                  <option value="float" ${f.type === 'float' ? 'selected' : ''}>Double / Float</option>
                  <option value="boolean" ${f.type === 'boolean' ? 'selected' : ''}>Bool</option>
                  <option value="datetime" ${f.type === 'datetime' ? 'selected' : ''}>DateTime</option>
                  <option value="date" ${f.type === 'date' ? 'selected' : ''}>Date</option>
                </select>
              </div>
            </div>

            <div class="form-group formula-editor-wrapper" style="margin-bottom: 4px;">
              <label style="display: flex; justify-content: space-between; align-items: center;">
                <span>Expression</span>
                <span style="font-size: 10px; color: var(--text-secondary); font-weight: normal;">Type <code>[</code> for columns</span>
              </label>
              <div class="formula-editor-box">
                <pre class="formula-backdrop" aria-hidden="true"></pre>
                <textarea class="form-control form-expr formula-code-input" rows="3" placeholder="e.g. [Price] * [Qty] * (1 - [Discount])" spellcheck="false" autocomplete="off" autocapitalize="off">${f.expression || ''}</textarea>
              </div>
              <div class="formula-valid-badge" data-badge-idx="${i}"></div>
            </div>

            <div style="display: flex; gap: 4px; flex-wrap: wrap; margin-top: 6px;">
              <button class="btn btn-secondary btn-sm chip-func" data-func="IF [col] > 0 THEN 1 ELSE 0 ENDIF" style="font-size: 10px; padding: 2px 6px;">IF...THEN...ELSE</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="IIF([col] > 0, 1, 0)" style="font-size: 10px; padding: 2px 6px;">IIF(,,)</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="Contains([col], 'search')" style="font-size: 10px; padding: 2px 6px;">Contains()</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="DateTimeAdd([date_col], 7, 'days')" style="font-size: 10px; padding: 2px 6px;">DateTimeAdd()</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="DateTimeDiff([d1], [d2], 'days')" style="font-size: 10px; padding: 2px 6px;">DateTimeDiff()</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="Round([col], 2)" style="font-size: 10px; padding: 2px 6px;">Round()</button>
              <button class="btn btn-secondary btn-sm chip-func" data-func="IsNull([col])" style="font-size: 10px; padding: 2px 6px;">IsNull()</button>
            </div>
          </div>
        `;
        }).join('')}
      </div>

      <button id="btn-add-formula" class="btn btn-secondary btn-sm" style="width: 100%; justify-content: center; margin-top: 4px;">
        + Add New Formula Column
      </button>

      <div class="form-hint" style="margin-top: 12px;">
        Tip: Choose <b>↻ Update Existing</b> to modify incoming fields directly, or <b>+ Add Column</b> to generate new fields. Type <code>[</code> inside any formula for column suggestions.
      </div>
    `;

    let lastFocusedTextarea = container.querySelector('.form-expr');

    // 1. Function Browser Interactive Filtering & Insertion
    const browserToggle = container.querySelector('#btn-toggle-func-browser');
    const browserContent = container.querySelector('#func-browser-content');
    const browserArrow = container.querySelector('#func-browser-arrow');
    const funcSearch = container.querySelector('#input-func-search');
    const catTabs = container.querySelectorAll('.formula-cat-tab');
    const funcListContainer = container.querySelector('#func-list-container');

    let currentCat = 'All';
    let searchQuery = '';

    const renderFuncList = () => {
      if (!funcListContainer) return;
      const filtered = catalog.filter(fn => {
        const matchesCat = (currentCat === 'All') || (fn.category.toLowerCase() === currentCat.toLowerCase());
        const matchesSearch = !searchQuery || 
          fn.name.toLowerCase().includes(searchQuery) || 
          fn.signature.toLowerCase().includes(searchQuery) || 
          fn.doc.toLowerCase().includes(searchQuery);
        return matchesCat && matchesSearch;
      });

      if (filtered.length === 0) {
        funcListContainer.innerHTML = '<div style="font-size: 11px; color: var(--text-muted); padding: 10px; text-align: center;">No matching functions found</div>';
        return;
      }

      funcListContainer.innerHTML = filtered.map(fn => `
        <div class="formula-func-item" data-sig="${fn.signature}">
          <div class="formula-func-name">${fn.name} <span class="formula-func-cat">${fn.category}</span></div>
          <div class="formula-func-sig">${fn.signature}</div>
          <div class="formula-func-doc">${fn.doc}</div>
        </div>
      `).join('');

      funcListContainer.querySelectorAll('.formula-func-item').forEach(item => {
        item.addEventListener('click', () => {
          const sig = item.dataset.sig;
          if (lastFocusedTextarea) {
            const start = lastFocusedTextarea.selectionStart || lastFocusedTextarea.value.length;
            const end = lastFocusedTextarea.selectionEnd || lastFocusedTextarea.value.length;
            const text = lastFocusedTextarea.value;
            lastFocusedTextarea.value = text.substring(0, start) + sig + text.substring(end);
            lastFocusedTextarea.focus();
            const paren = sig.indexOf('(');
            const newPos = start + (paren !== -1 ? paren + 1 : sig.length);
            lastFocusedTextarea.setSelectionRange(newPos, newPos);
            lastFocusedTextarea.dispatchEvent(new Event('input'));
          }
        });
      });
    };

    if (browserToggle && browserContent) {
      browserToggle.addEventListener('click', () => {
        const isOpen = browserContent.classList.toggle('open');
        browserArrow.textContent = isOpen ? '▲' : '▼';
        if (isOpen && funcListContainer.children.length === 0) {
          renderFuncList();
        }
      });
    }

    if (funcSearch) {
      funcSearch.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase().trim();
        renderFuncList();
      });
    }

    catTabs.forEach(tab => {
      tab.addEventListener('click', () => {
        catTabs.forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentCat = tab.dataset.cat;
        renderFuncList();
      });
    });

    // 2. Setup Formula Cards & Live Validation & Code Editor
    container.querySelectorAll('.formula-card').forEach(card => {
      const idx = parseInt(card.dataset.idx);
      const boxEl = card.querySelector('.formula-editor-box');
      const exprEl = card.querySelector('.form-expr');
      const badgeEl = card.querySelector(`.formula-valid-badge[data-badge-idx="${idx}"]`);
      const nameInput = card.querySelector('.form-col-name');
      const existingSelect = card.querySelector('.form-col-existing-select');
      const typeSelect = card.querySelector('.form-col-type');
      const newBox = card.querySelector('.form-col-new-box');
      const updateBox = card.querySelector('.form-col-update-box');

      const updateCardValidation = () => {
        if (!exprEl || !badgeEl) return;
        const status = this.validateFormulaExpression(exprEl.value, upstreamCols);
        badgeEl.className = `formula-valid-badge ${status.type}`;
        badgeEl.textContent = status.msg;
        badgeEl.title = status.tooltip || status.msg;
      };

      // Twin-layer Code Editor setup
      const syncBackdrop = this.setupFormulaCodeEditor(boxEl, exprEl, upstreamCols);

      exprEl.addEventListener('focus', () => {
        lastFocusedTextarea = exprEl;
      });

      // Mode switch buttons (+ Add Column vs ↻ Update Existing)
      card.querySelectorAll('.btn-formula-out-mode').forEach(btn => {
        btn.addEventListener('click', () => {
          const mode = btn.dataset.mode;
          card.querySelectorAll('.btn-formula-out-mode').forEach(b => {
            b.style.background = 'var(--bg-main)';
            b.style.borderColor = 'var(--border-subtle)';
            b.style.color = 'var(--text-primary)';
          });
          btn.style.background = 'var(--color-primary, #0284c7)';
          btn.style.borderColor = 'var(--color-primary, #0284c7)';
          btn.style.color = '#fff';

          if (mode === 'update') {
            newBox.style.display = 'none';
            updateBox.style.display = 'block';
            if (existingSelect && upstreamCols.length > 0) {
              const selCol = existingSelect.value || upstreamCols[0];
              node.config.formulas[idx].output_field = selCol;
              const inf = inferType(selCol);
              typeSelect.value = inf;
              node.config.formulas[idx].type = inf;
            }
          } else {
            updateBox.style.display = 'none';
            newBox.style.display = 'block';
            node.config.formulas[idx].output_field = nameInput.value || `NewField_${idx + 1}`;
          }
          this.render(node);
          this.canvas.onWorkflowChange();
        });
      });

      if (nameInput) {
        nameInput.addEventListener('input', (e) => {
          node.config.formulas[idx].output_field = e.target.value;
          this.canvas.onWorkflowChange();
        });
      }

      if (existingSelect) {
        existingSelect.addEventListener('change', (e) => {
          const col = e.target.value;
          node.config.formulas[idx].output_field = col;
          const inf = inferType(col);
          typeSelect.value = inf;
          node.config.formulas[idx].type = inf;
          this.render(node);
          this.canvas.onWorkflowChange();
        });
      }

      if (typeSelect) {
        typeSelect.addEventListener('change', (e) => {
          node.config.formulas[idx].type = e.target.value;
          this.canvas.onWorkflowChange();
        });
      }

      exprEl.addEventListener('input', (e) => {
        node.config.formulas[idx].expression = e.target.value;
        syncBackdrop();
        updateCardValidation();
        this.canvas.onWorkflowChange();
      });

      // Attach Autocomplete Popover
      this.setupFormulaAutocomplete(exprEl, upstreamCols, () => {
        node.config.formulas[idx].expression = exprEl.value;
        syncBackdrop();
        updateCardValidation();
        this.canvas.onWorkflowChange();
      });

      // Initial validation display
      updateCardValidation();

      // Card Header Actions: Reorder, Duplicate, Delete
      const btnUp = card.querySelector('.btn-move-up');
      if (btnUp) {
        btnUp.addEventListener('click', () => {
          if (idx > 0) {
            const temp = node.config.formulas[idx];
            node.config.formulas[idx] = node.config.formulas[idx - 1];
            node.config.formulas[idx - 1] = temp;
            this.render(node);
            this.canvas.onWorkflowChange();
          }
        });
      }

      const btnDown = card.querySelector('.btn-move-down');
      if (btnDown) {
        btnDown.addEventListener('click', () => {
          if (idx < node.config.formulas.length - 1) {
            const temp = node.config.formulas[idx];
            node.config.formulas[idx] = node.config.formulas[idx + 1];
            node.config.formulas[idx + 1] = temp;
            this.render(node);
            this.canvas.onWorkflowChange();
          }
        });
      }

      const btnDup = card.querySelector('.btn-duplicate-formula');
      if (btnDup) {
        btnDup.addEventListener('click', () => {
          const current = node.config.formulas[idx];
          const cloned = {
            output_field: `${current.output_field || 'Field'}_copy`,
            expression: current.expression || '',
            type: current.type || 'string'
          };
          node.config.formulas.splice(idx + 1, 0, cloned);
          this.render(node);
          this.canvas.onWorkflowChange();
        });
      }

      card.querySelector('.btn-remove-formula').addEventListener('click', () => {
        node.config.formulas.splice(idx, 1);
        this.render(node);
        this.canvas.onWorkflowChange();
      });

      // Quick helper chips
      card.querySelectorAll('.chip-func').forEach(chip => {
        chip.addEventListener('click', () => {
          const fnText = chip.dataset.func;
          const start = exprEl.selectionStart || exprEl.value.length;
          const end = exprEl.selectionEnd || exprEl.value.length;
          const text = exprEl.value;
          exprEl.value = text.substring(0, start) + fnText + text.substring(end);
          exprEl.focus();
          const paren = fnText.indexOf('(');
          const newPos = start + (paren !== -1 ? paren + 1 : fnText.length);
          exprEl.setSelectionRange(newPos, newPos);
        });
      });
    });



    // 3. Global Column Chips Insertion
    container.querySelectorAll('.column-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const col = chip.dataset.col;
        const target = lastFocusedTextarea || container.querySelector('.form-expr');
        if (target) {
          const start = target.selectionStart || target.value.length;
          const end = target.selectionEnd || target.value.length;
          const text = target.value;
          target.value = text.substring(0, start) + `[${col}]` + text.substring(end);
          target.focus();
          target.selectionStart = target.selectionEnd = start + col.length + 2;
          target.dispatchEvent(new Event('input'));
        }
      });
    });

    // 4. Add New Formula Card
    container.querySelector('#btn-add-formula').addEventListener('click', () => {
      if (!node.config.formulas) node.config.formulas = [];
      node.config.formulas.push({
        output_field: `NewField_${node.config.formulas.length + 1}`,
        expression: '',
        type: 'string'
      });
      this.render(node);
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 5b. Multi-Row Formula Tool (Superior & Intuitive)
  // --------------------------------------------------------------------
  renderMultiRowFormulaConfig(container, node, upstreamCols = []) {
    if (!node.config) node.config = {};
    const cfg = node.config;
    if (cfg.is_new_field === undefined) cfg.is_new_field = true;
    if (!cfg.output_field) cfg.output_field = 'NewField';
    if (!cfg.output_type) cfg.output_type = 'float';
    if (!cfg.values_for_rows_not_exist) cfg.values_for_rows_not_exist = 'null';
    if (!Array.isArray(cfg.group_by_fields)) cfg.group_by_fields = [];
    if (cfg.expression === undefined) cfg.expression = '';

    let activeRowOffset = -1;
    const firstCol = upstreamCols[0] || 'Field1';
    const firstNumCol = upstreamCols.find(c => /amount|revenue|price|qty|quantity|score|count|total|cost|val/i.test(c)) || firstCol;

    container.innerHTML = `
      <div class="mrf-panel">
        <div class="tool-desc-hint" style="margin-bottom: 12px; font-size: 11px; color: var(--text-secondary);">
          Perform recursive row calculations, running totals, lead/lag comparisons, and window aggregations across rows.
        </div>

        <div class="form-group" style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label style="font-weight: 600; font-size: 11px; color: var(--text-primary); margin-bottom: 0;">⚡ 1-Click Smart Presets</label>
            <span style="font-size: 10px; color: var(--text-muted);">Auto-configures formula &amp; boundary</span>
          </div>
          <select class="form-control" id="mrf-preset-select" style="border: 1px solid var(--color-primary, #0284c7);">
            <option value="">-- Choose a Smart Preset --</option>
            <option value="running_total">🏃 Running Total (Cumulative Sum)</option>
            <option value="row_id">🔢 Sequential Row ID per Group</option>
            <option value="fill_down">⬇️ Fill Down (Forward Fill Nulls)</option>
            <option value="lag_diff">📉 Difference from Previous Row (Lag 1)</option>
            <option value="pct_growth">📈 Percentage Growth Rate (%)</option>
            <option value="lead_val">⏭️ Lead Value (Next Row)</option>
            <option value="moving_avg">📊 3-Period Centered Moving Average</option>
          </select>
        </div>

        <div class="mrf-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 8px; display: block;">
            Target Output Field
          </label>
          <div style="display: flex; gap: 16px; margin-bottom: 8px;">
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;">
              <input type="radio" name="mrf-field-mode" value="new" ${cfg.is_new_field ? 'checked' : ''}>
              <span>Create New Field</span>
            </label>
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;">
              <input type="radio" name="mrf-field-mode" value="update" ${!cfg.is_new_field ? 'checked' : ''}>
              <span>Update Existing Field</span>
            </label>
          </div>

          <div id="mrf-new-field-row" style="display: ${cfg.is_new_field ? 'flex' : 'none'}; gap: 8px;">
            <div style="flex: 2;">
              <label style="font-size: 10px; color: var(--text-muted);">Field Name</label>
              <input type="text" class="form-control" id="mrf-output-field-input" value="${this.escapeHtml(cfg.output_field)}" placeholder="e.g. CumulativeSum">
            </div>
            <div style="flex: 1.2;">
              <label style="font-size: 10px; color: var(--text-muted);">Data Type</label>
              <select class="form-control" id="mrf-output-type-select">
                <option value="float" ${cfg.output_type === 'float' ? 'selected' : ''}>Double / Float</option>
                <option value="integer" ${cfg.output_type === 'integer' ? 'selected' : ''}>Int64</option>
                <option value="string" ${cfg.output_type === 'string' ? 'selected' : ''}>String</option>
                <option value="boolean" ${cfg.output_type === 'boolean' ? 'selected' : ''}>Bool</option>
                <option value="datetime" ${cfg.output_type === 'datetime' ? 'selected' : ''}>DateTime</option>
              </select>
            </div>
          </div>

          <div id="mrf-existing-field-row" style="display: ${!cfg.is_new_field ? 'block' : 'none'};">
            <label style="font-size: 10px; color: var(--text-muted);">Select Existing Field to Overwrite</label>
            <select class="form-control" id="mrf-existing-field-select">
              ${upstreamCols.length > 0
                ? upstreamCols.map(c => `<option value="${this.escapeHtml(c)}" ${cfg.output_field === c ? 'selected' : ''}>${this.escapeHtml(c)}</option>`).join('')
                : `<option value="${this.escapeHtml(cfg.output_field)}">${this.escapeHtml(cfg.output_field)}</option>`}
            </select>
          </div>
        </div>

        <div class="mrf-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 6px; display: block;">
            Values for Rows that Don't Exist (Boundaries)
          </label>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            <label style="display: flex; align-items: flex-start; gap: 8px; font-size: 11px; cursor: pointer;">
              <input type="radio" name="mrf-boundary-mode" value="null" ${cfg.values_for_rows_not_exist === 'null' ? 'checked' : ''} style="margin-top: 2px;">
              <div>
                <b style="color: var(--text-primary);">NULL / Empty</b>
                <div style="font-size: 10px; color: var(--text-muted);">Missing edge rows evaluate to NULL (Standard Alteryx default)</div>
              </div>
            </label>
            <label style="display: flex; align-items: flex-start; gap: 8px; font-size: 11px; cursor: pointer;">
              <input type="radio" name="mrf-boundary-mode" value="0" ${cfg.values_for_rows_not_exist === '0' || cfg.values_for_rows_not_exist === 'zero_or_empty' ? 'checked' : ''} style="margin-top: 2px;">
              <div>
                <b style="color: var(--text-primary);">0 or Empty String</b>
                <div style="font-size: 10px; color: var(--text-muted);">Ideal for running totals and counters: 0 for numbers, "" for text</div>
              </div>
            </label>
            <label style="display: flex; align-items: flex-start; gap: 8px; font-size: 11px; cursor: pointer;">
              <input type="radio" name="mrf-boundary-mode" value="nearest" ${cfg.values_for_rows_not_exist === 'nearest' ? 'checked' : ''} style="margin-top: 2px;">
              <div>
                <b style="color: var(--text-primary);">Set to Value of Nearest Row</b>
                <div style="font-size: 10px; color: var(--text-muted);">Edge rows clamp to the first or last available record</div>
              </div>
            </label>
          </div>
        </div>

        <div class="mrf-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 0;">
              Group By (Restart Calculations per Group)
            </label>
            <button type="button" class="btn-xs" id="mrf-clear-groupby" style="background: transparent; border: none; color: var(--color-primary, #0284c7); cursor: pointer; font-size: 10px;">Clear All</button>
          </div>
          <div style="max-height: 110px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 4px; padding: 6px; background: var(--bg-main);">
            ${upstreamCols.length > 0 ? upstreamCols.map(c => `
              <label style="display: flex; align-items: center; gap: 6px; font-size: 11px; margin-bottom: 4px; cursor: pointer;">
                <input type="checkbox" class="mrf-grp-chk" value="${this.escapeHtml(c)}" ${cfg.group_by_fields.includes(c) ? 'checked' : ''}>
                <span>${this.escapeHtml(c)}</span>
              </label>
            `).join('') : '<div style="font-size: 10px; color: var(--text-muted);">No upstream columns detected</div>'}
          </div>
        </div>

        <div class="mrf-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 0;">
              Relative Row Navigator
            </label>
            <span style="font-size: 10px; color: var(--text-muted);">Select offset to inject column</span>
          </div>

          <div class="mrf-timeline-buttons" style="display: flex; gap: 4px; overflow-x: auto; padding-bottom: 6px; margin-bottom: 8px;">
            ${[-3, -2, -1, 0, 1, 2, 3].map(offset => {
              const label = offset === 0 ? 'Row 0 (Current)' : (offset < 0 ? `Row${offset}` : `Row+${offset}`);
              const isAct = offset === activeRowOffset;
              return `<button type="button" class="mrf-offset-btn ${isAct ? 'active' : ''}" data-offset="${offset}" style="padding: 3px 8px; font-size: 10px; border-radius: 4px; border: 1px solid ${isAct ? 'var(--color-primary, #0284c7)' : 'var(--border-subtle)'}; background: ${isAct ? 'var(--color-primary, #0284c7)' : 'var(--bg-main)'}; color: ${isAct ? '#fff' : 'var(--text-primary)'}; cursor: pointer; white-space: nowrap;">${label}</button>`;
            }).join('')}
          </div>

          <div style="font-size: 10px; color: var(--text-muted); margin-bottom: 4px;">Click chip to insert at cursor:</div>
          <div id="mrf-active-tokens-container" style="display: flex; flex-wrap: wrap; gap: 5px; max-height: 90px; overflow-y: auto;"></div>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label style="font-weight: 600; font-size: 11px; color: var(--text-primary); margin-bottom: 0;">Expression</label>
            <span id="mrf-expr-status" style="font-size: 10px; font-weight: 600; color: #22c55e;">✓ Vectorized</span>
          </div>
          <textarea class="form-control" id="mrf-expr-textarea" rows="4" style="font-family: var(--font-mono, monospace); font-size: 12px; line-height: 1.4; resize: vertical;" placeholder="e.g. [Row-1:RunningTotal] + [Sales]">${this.escapeHtml(cfg.expression)}</textarea>
        </div>
      </div>
    `;

    const exprEl = container.querySelector('#mrf-expr-textarea');
    const statusEl = container.querySelector('#mrf-expr-status');
    const tokensContainer = container.querySelector('#mrf-active-tokens-container');

    const updateStatus = () => {
      const val = exprEl.value;
      const targetCol = cfg.output_field || '';
      if (!val.trim()) {
        statusEl.textContent = 'Empty Expression';
        statusEl.style.color = 'var(--text-muted)';
        return;
      }
      const isRecursive = targetCol && (val.includes(`[Row-1:${targetCol}]`) || val.includes(`[Row+1:${targetCol}]`) || val.includes(`[${targetCol}]`));
      if (isRecursive) {
        statusEl.textContent = '⚡ Recursive Running Calculation';
        statusEl.style.color = '#38bdf8';
      } else {
        statusEl.textContent = '✓ Vectorized Window Calculation';
        statusEl.style.color = '#22c55e';
      }
    };

    const insertAtCursor = (text) => {
      const start = exprEl.selectionStart || exprEl.value.length;
      const end = exprEl.selectionEnd || exprEl.value.length;
      const current = exprEl.value;
      exprEl.value = current.substring(0, start) + text + current.substring(end);
      exprEl.focus();
      exprEl.selectionStart = exprEl.selectionEnd = start + text.length;
      cfg.expression = exprEl.value;
      updateStatus();
      this.canvas.onWorkflowChange();
    };

    const renderTokens = () => {
      tokensContainer.innerHTML = '';
      const prefix = activeRowOffset === 0 ? '' : (activeRowOffset < 0 ? `Row${activeRowOffset}:` : `Row+${activeRowOffset}:`);
      
      if (cfg.output_field) {
        const selfToken = prefix ? `[${prefix}${cfg.output_field}]` : `[${cfg.output_field}]`;
        const selfChip = document.createElement('span');
        selfChip.className = 'column-chip';
        selfChip.style.borderColor = 'var(--color-primary, #0284c7)';
        selfChip.style.color = 'var(--color-primary, #0284c7)';
        selfChip.style.fontWeight = '600';
        selfChip.textContent = `+ ${selfToken} (Self)`;
        selfChip.title = `Insert self-reference for running/cumulative logic`;
        selfChip.addEventListener('click', () => insertAtCursor(selfToken));
        tokensContainer.appendChild(selfChip);
      }

      upstreamCols.forEach(col => {
        const token = prefix ? `[${prefix}${col}]` : `[${col}]`;
        const chip = document.createElement('span');
        chip.className = 'column-chip';
        chip.textContent = `+ ${token}`;
        chip.addEventListener('click', () => insertAtCursor(token));
        tokensContainer.appendChild(chip);
      });
    };

    container.querySelectorAll('.mrf-offset-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        container.querySelectorAll('.mrf-offset-btn').forEach(b => {
          b.style.background = 'var(--bg-main)';
          b.style.borderColor = 'var(--border-subtle)';
          b.style.color = 'var(--text-primary)';
        });
        btn.style.background = 'var(--color-primary, #0284c7)';
        btn.style.borderColor = 'var(--color-primary, #0284c7)';
        btn.style.color = '#fff';
        activeRowOffset = parseInt(btn.dataset.offset, 10);
        renderTokens();
      });
    });

    container.querySelectorAll('input[name="mrf-field-mode"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        cfg.is_new_field = e.target.value === 'new';
        container.querySelector('#mrf-new-field-row').style.display = cfg.is_new_field ? 'flex' : 'none';
        container.querySelector('#mrf-existing-field-row').style.display = !cfg.is_new_field ? 'block' : 'none';
        if (!cfg.is_new_field && upstreamCols.length > 0) {
          cfg.output_field = container.querySelector('#mrf-existing-field-select').value;
        } else {
          cfg.output_field = container.querySelector('#mrf-output-field-input').value;
        }
        renderTokens();
        updateStatus();
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#mrf-output-field-input').addEventListener('input', (e) => {
      cfg.output_field = e.target.value;
      renderTokens();
      updateStatus();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mrf-output-type-select').addEventListener('change', (e) => {
      cfg.output_type = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mrf-existing-field-select').addEventListener('change', (e) => {
      cfg.output_field = e.target.value;
      renderTokens();
      updateStatus();
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('input[name="mrf-boundary-mode"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        cfg.values_for_rows_not_exist = e.target.value;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelectorAll('.mrf-grp-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.mrf-grp-chk:checked')).map(c => c.value);
        cfg.group_by_fields = checked;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#mrf-clear-groupby').addEventListener('click', () => {
      container.querySelectorAll('.mrf-grp-chk').forEach(c => c.checked = false);
      cfg.group_by_fields = [];
      this.canvas.onWorkflowChange();
    });

    exprEl.addEventListener('input', () => {
      cfg.expression = exprEl.value;
      updateStatus();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mrf-preset-select').addEventListener('change', (e) => {
      const p = e.target.value;
      if (!p) return;
      if (p === 'running_total') {
        cfg.is_new_field = true;
        cfg.output_field = 'RunningTotal';
        cfg.output_type = 'float';
        cfg.values_for_rows_not_exist = '0';
        cfg.expression = `[Row-1:RunningTotal] + [${firstNumCol}]`;
      } else if (p === 'row_id') {
        cfg.is_new_field = true;
        cfg.output_field = 'RowID';
        cfg.output_type = 'integer';
        cfg.values_for_rows_not_exist = '0';
        cfg.expression = `[Row-1:RowID] + 1`;
      } else if (p === 'fill_down') {
        cfg.is_new_field = false;
        cfg.output_field = firstCol;
        cfg.values_for_rows_not_exist = 'null';
        cfg.expression = `IFNULL([${firstCol}], [Row-1:${firstCol}])`;
      } else if (p === 'lag_diff') {
        cfg.is_new_field = true;
        cfg.output_field = `Diff_${firstNumCol}`;
        cfg.output_type = 'float';
        cfg.values_for_rows_not_exist = 'null';
        cfg.expression = `[${firstNumCol}] - [Row-1:${firstNumCol}]`;
      } else if (p === 'pct_growth') {
        cfg.is_new_field = true;
        cfg.output_field = `PctGrowth_${firstNumCol}`;
        cfg.output_type = 'float';
        cfg.values_for_rows_not_exist = 'null';
        cfg.expression = `ROUND(([${firstNumCol}] - [Row-1:${firstNumCol}]) / [Row-1:${firstNumCol}] * 100.0, 2)`;
      } else if (p === 'lead_val') {
        cfg.is_new_field = true;
        cfg.output_field = `Next_${firstNumCol}`;
        cfg.output_type = 'float';
        cfg.values_for_rows_not_exist = 'null';
        cfg.expression = `[Row+1:${firstNumCol}]`;
      } else if (p === 'moving_avg') {
        cfg.is_new_field = true;
        cfg.output_field = `MovingAvg3_${firstNumCol}`;
        cfg.output_type = 'float';
        cfg.values_for_rows_not_exist = 'nearest';
        cfg.expression = `([Row-1:${firstNumCol}] + [${firstNumCol}] + [Row+1:${firstNumCol}]) / 3.0`;
      }
      this.renderMultiRowFormulaConfig(container, node, upstreamCols);
      this.canvas.onWorkflowChange();
    });

    renderTokens();
    updateStatus();
  }

  // --------------------------------------------------------------------
  // 5c. Multi-Field Formula Tool (Superior & Intuitive)
  // --------------------------------------------------------------------
  renderMultiFieldFormulaConfig(container, node, upstreamCols = []) {
    if (!node.config) node.config = {};
    const cfg = node.config;
    if (!Array.isArray(cfg.selected_fields)) {
      cfg.selected_fields = cfg.fields && Array.isArray(cfg.fields) ? cfg.fields : [];
    }
    if (!cfg.field_type_filter) cfg.field_type_filter = 'all';
    if (!cfg.output_mode) cfg.output_mode = 'update';
    if (cfg.output_prefix === undefined) cfg.output_prefix = '';
    if (cfg.output_suffix === undefined) cfg.output_suffix = '';
    if (!cfg.output_type) cfg.output_type = 'none';
    if (cfg.expression === undefined) cfg.expression = '';

    let colSearch = '';
    let curTypeFilter = cfg.field_type_filter || 'all';

    const colMetas = this.getUpstreamColumnMeta(node.id) || [];
    const metaMap = {};
    colMetas.forEach(m => {
      if (m && m.name) metaMap[m.name] = (m.type || m.alteryx_type || 'unknown').toLowerCase();
    });

    const inferType = (colName) => {
      if (metaMap[colName]) return metaMap[colName];
      const low = colName.toLowerCase();
      if (/date|time|timestamp|_dt\b/.test(low)) return 'datetime';
      if (/\b(id|num|qty|amount|price|cost|sales|revenue|rate|count|total|tax|disc|discount|margin|profit|score)\b|_id$/.test(low)) return 'numeric';
      return 'text';
    };

    container.innerHTML = `
      <div class="mff-panel">
        <div class="tool-desc-hint" style="margin-bottom: 12px; font-size: 11px; color: var(--text-secondary);">
          Execute batch formulas across multiple columns simultaneously using dynamic <code>[_CurrentField_]</code> references.
        </div>

        <div class="form-group" style="margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label style="font-weight: 600; font-size: 11px; color: var(--text-primary); margin-bottom: 0;">⚡ 1-Click Transformation Presets</label>
            <span style="font-size: 10px; color: var(--text-muted);">Quick-fill expression</span>
          </div>
          <select class="form-control" id="mff-preset-select" style="border: 1px solid var(--color-primary, #0284c7);">
            <option value="">-- Choose a Batch Preset --</option>
            <option value="trim">✂️ Trim Whitespace: TRIM([_CurrentField_])</option>
            <option value="upper">🔠 Convert to UPPERCASE: UPPER([_CurrentField_])</option>
            <option value="lower">🔡 Convert to lowercase: LOWER([_CurrentField_])</option>
            <option value="fill_zero">🚫 Fill Nulls with 0: IFNULL([_CurrentField_], 0)</option>
            <option value="fill_empty">🧼 Fill Nulls with "": IFNULL([_CurrentField_], '')</option>
            <option value="round_2">🎯 Round to 2 Decimals: ROUND([_CurrentField_], 2)</option>
            <option value="abs">📏 Absolute Values: ABS([_CurrentField_])</option>
            <option value="scale_100">⚖️ Scale by 100: [_CurrentField_] * 100.0</option>
          </select>
        </div>

        <div class="mff-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 0;">
              Fields to Process
            </label>
            <span id="mff-selection-count" style="font-size: 10px; color: var(--color-primary, #0284c7); font-weight: 600;">
              (${cfg.selected_fields.length} selected)
            </span>
          </div>

          <div class="mff-filter-pills" style="display: flex; gap: 4px; margin-bottom: 8px;">
            ${['all', 'numeric', 'text', 'datetime', 'boolean'].map(cat => `
              <button type="button" class="mff-type-pill ${curTypeFilter === cat ? 'active' : ''}" data-type="${cat}" style="padding: 2px 7px; font-size: 10px; border-radius: 3px; border: 1px solid ${curTypeFilter === cat ? 'var(--color-primary, #0284c7)' : 'var(--border-subtle)'}; background: ${curTypeFilter === cat ? 'var(--color-primary, #0284c7)' : 'var(--bg-main)'}; color: ${curTypeFilter === cat ? '#fff' : 'var(--text-primary)'}; cursor: pointer;">
                ${cat.charAt(0).toUpperCase() + cat.slice(1)}
              </button>
            `).join('')}
          </div>

          <div style="display: flex; gap: 6px; margin-bottom: 8px;">
            <input type="text" class="form-control" id="mff-search-input" placeholder="Filter columns..." style="font-size: 11px; padding: 3px 6px; flex: 1;">
            <button type="button" class="btn-xs" id="mff-btn-select-all" style="padding: 2px 6px; font-size: 10px; background: var(--bg-hover); border: 1px solid var(--border-subtle); border-radius: 3px; cursor: pointer; color: var(--text-primary);">All</button>
            <button type="button" class="btn-xs" id="mff-btn-deselect-all" style="padding: 2px 6px; font-size: 10px; background: var(--bg-hover); border: 1px solid var(--border-subtle); border-radius: 3px; cursor: pointer; color: var(--text-primary);">None</button>
            <button type="button" class="btn-xs" id="mff-btn-invert" style="padding: 2px 6px; font-size: 10px; background: var(--bg-hover); border: 1px solid var(--border-subtle); border-radius: 3px; cursor: pointer; color: var(--text-primary);">Invert</button>
          </div>

          <div id="mff-cols-list-container" style="max-height: 140px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 4px; padding: 6px; background: var(--bg-main);"></div>
        </div>

        <div class="mff-section-card" style="background: var(--bg-surface-elevated, #1e293b); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 10px; margin-bottom: 12px;">
          <label style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 8px; display: block;">
            Output Options &amp; Renaming
          </label>
          <div style="display: flex; gap: 16px; margin-bottom: 8px;">
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;">
              <input type="radio" name="mff-out-mode" value="update" ${cfg.output_mode === 'update' ? 'checked' : ''}>
              <span>Update Existing Fields</span>
            </label>
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer;">
              <input type="radio" name="mff-out-mode" value="create_new" ${cfg.output_mode === 'create_new' ? 'checked' : ''}>
              <span>Create New Fields</span>
            </label>
          </div>

          <div id="mff-create-fields-config" style="display: ${cfg.output_mode === 'create_new' ? 'block' : 'none'};">
            <div style="display: flex; gap: 8px; margin-bottom: 8px;">
              <div style="flex: 1;">
                <label style="font-size: 10px; color: var(--text-muted);">Prefix</label>
                <input type="text" class="form-control" id="mff-prefix-input" value="${this.escapeHtml(cfg.output_prefix)}" placeholder="e.g. New_">
              </div>
              <div style="flex: 1;">
                <label style="font-size: 10px; color: var(--text-muted);">Suffix</label>
                <input type="text" class="form-control" id="mff-suffix-input" value="${this.escapeHtml(cfg.output_suffix)}" placeholder="e.g. _Cleaned">
              </div>
              <div style="flex: 1.2;">
                <label style="font-size: 10px; color: var(--text-muted);">Change Output Type</label>
                <select class="form-control" id="mff-out-type-select">
                  <option value="none" ${cfg.output_type === 'none' ? 'selected' : ''}>Keep Original</option>
                  <option value="float" ${cfg.output_type === 'float' ? 'selected' : ''}>Double / Float</option>
                  <option value="integer" ${cfg.output_type === 'integer' ? 'selected' : ''}>Int64</option>
                  <option value="string" ${cfg.output_type === 'string' ? 'selected' : ''}>String</option>
                  <option value="boolean" ${cfg.output_type === 'boolean' ? 'selected' : ''}>Bool</option>
                  <option value="datetime" ${cfg.output_type === 'datetime' ? 'selected' : ''}>DateTime</option>
                </select>
              </div>
            </div>

            <div style="background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: 4px; padding: 6px;">
              <div style="font-size: 10px; font-weight: 600; color: var(--text-muted); margin-bottom: 4px; display: flex; justify-content: space-between;">
                <span>Live Renaming Preview:</span>
                <span id="mff-preview-summary" style="color: var(--color-primary, #0284c7);"></span>
              </div>
              <div id="mff-name-preview-container" style="max-height: 80px; overflow-y: auto; font-family: var(--font-mono, monospace); font-size: 11px;"></div>
            </div>
          </div>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <label style="font-weight: 600; font-size: 11px; color: var(--text-primary); margin-bottom: 0;">Formula Expression</label>
            <span style="font-size: 10px; color: var(--text-muted);">Evaluated for each selected field</span>
          </div>

          <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;">
            <span class="column-chip" id="mff-token-field" style="border-color: var(--color-primary, #0284c7); color: var(--color-primary, #0284c7); font-weight: 600;">
              + [_CurrentField_]
            </span>
            <span class="column-chip" id="mff-token-name" style="border-color: #a855f7; color: #a855f7; font-weight: 600;">
              + [_CurrentFieldName_]
            </span>
            ${upstreamCols.slice(0, 5).map(c => `
              <span class="column-chip mff-col-chip" data-col="${this.escapeHtml(c)}">+ [${this.escapeHtml(c)}]</span>
            `).join('')}
          </div>

          <textarea class="form-control" id="mff-expr-textarea" rows="4" style="font-family: var(--font-mono, monospace); font-size: 12px; line-height: 1.4; resize: vertical;" placeholder="e.g. TRIM([_CurrentField_])">${this.escapeHtml(cfg.expression)}</textarea>
        </div>
      </div>
    `;

    const colsListEl = container.querySelector('#mff-cols-list-container');
    const previewContainer = container.querySelector('#mff-name-preview-container');
    const countEl = container.querySelector('#mff-selection-count');
    const exprEl = container.querySelector('#mff-expr-textarea');

    const updatePreview = () => {
      if (cfg.output_mode !== 'create_new') return;
      if (!previewContainer) return;
      previewContainer.innerHTML = '';
      const selected = cfg.selected_fields || [];
      if (selected.length === 0) {
        previewContainer.innerHTML = '<span style="color: var(--text-muted);">No fields selected</span>';
        return;
      }
      selected.forEach(c => {
        const outName = `${cfg.output_prefix || ''}${c}${cfg.output_suffix || ''}`;
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.gap = '6px';
        row.style.marginBottom = '2px';
        row.innerHTML = `<span style="color: var(--text-muted);">${this.escapeHtml(c)}</span> <span style="color: var(--color-primary, #0284c7); font-weight: bold;">➔</span> <b style="color: var(--text-primary);">${this.escapeHtml(outName)}</b>`;
        previewContainer.appendChild(row);
      });
    };

    const renderColumnCheckboxes = () => {
      colsListEl.innerHTML = '';
      const visibleCols = upstreamCols.filter(c => {
        const matchesSearch = !colSearch || c.toLowerCase().includes(colSearch);
        if (!matchesSearch) return false;
        if (curTypeFilter === 'all') return true;
        const t = inferType(c);
        if (curTypeFilter === 'numeric') return t.includes('num') || t.includes('int') || t.includes('float') || t.includes('double') || t.includes('dec');
        if (curTypeFilter === 'text') return t.includes('text') || t.includes('str') || t === 'unknown';
        if (curTypeFilter === 'datetime') return t.includes('date') || t.includes('time');
        if (curTypeFilter === 'boolean') return t.includes('bool');
        return true;
      });

      if (visibleCols.length === 0) {
        colsListEl.innerHTML = '<div style="font-size: 10px; color: var(--text-muted); padding: 4px;">No columns match filter</div>';
        return;
      }

      visibleCols.forEach(c => {
        const t = inferType(c);
        const isChecked = cfg.selected_fields.includes(c);
        const row = document.createElement('label');
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.justifyContent = 'space-between';
        row.style.fontSize = '11px';
        row.style.marginBottom = '4px';
        row.style.cursor = 'pointer';

        row.innerHTML = `
          <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
            <input type="checkbox" class="mff-col-chk" value="${this.escapeHtml(c)}" ${isChecked ? 'checked' : ''}>
            <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(c)}</span>
          </div>
          <span style="font-size: 9px; padding: 1px 4px; border-radius: 3px; background: var(--bg-hover); color: var(--text-muted); text-transform: uppercase;">${t.slice(0, 4)}</span>
        `;

        row.querySelector('.mff-col-chk').addEventListener('change', (e) => {
          if (e.target.checked) {
            if (!cfg.selected_fields.includes(c)) cfg.selected_fields.push(c);
          } else {
            cfg.selected_fields = cfg.selected_fields.filter(x => x !== c);
          }
          countEl.textContent = `(${cfg.selected_fields.length} selected)`;
          updatePreview();
          this.canvas.onWorkflowChange();
        });

        colsListEl.appendChild(row);
      });
    };

    const insertAtCursor = (text) => {
      const start = exprEl.selectionStart || exprEl.value.length;
      const end = exprEl.selectionEnd || exprEl.value.length;
      const current = exprEl.value;
      exprEl.value = current.substring(0, start) + text + current.substring(end);
      exprEl.focus();
      exprEl.selectionStart = exprEl.selectionEnd = start + text.length;
      cfg.expression = exprEl.value;
      this.canvas.onWorkflowChange();
    };

    container.querySelectorAll('.mff-type-pill').forEach(pill => {
      pill.addEventListener('click', () => {
        container.querySelectorAll('.mff-type-pill').forEach(p => {
          p.style.background = 'var(--bg-main)';
          p.style.borderColor = 'var(--border-subtle)';
          p.style.color = 'var(--text-primary)';
        });
        pill.style.background = 'var(--color-primary, #0284c7)';
        pill.style.borderColor = 'var(--color-primary, #0284c7)';
        pill.style.color = '#fff';
        curTypeFilter = pill.dataset.type;
        cfg.field_type_filter = curTypeFilter;
        renderColumnCheckboxes();
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#mff-search-input').addEventListener('input', (e) => {
      colSearch = e.target.value.toLowerCase().trim();
      renderColumnCheckboxes();
    });

    container.querySelector('#mff-btn-select-all').addEventListener('click', () => {
      const allCheckboxes = container.querySelectorAll('.mff-col-chk');
      allCheckboxes.forEach(chk => {
        chk.checked = true;
        if (!cfg.selected_fields.includes(chk.value)) cfg.selected_fields.push(chk.value);
      });
      countEl.textContent = `(${cfg.selected_fields.length} selected)`;
      updatePreview();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-btn-deselect-all').addEventListener('click', () => {
      container.querySelectorAll('.mff-col-chk').forEach(chk => chk.checked = false);
      cfg.selected_fields = [];
      countEl.textContent = `(0 selected)`;
      updatePreview();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-btn-invert').addEventListener('click', () => {
      container.querySelectorAll('.mff-col-chk').forEach(chk => {
        chk.checked = !chk.checked;
        if (chk.checked) {
          if (!cfg.selected_fields.includes(chk.value)) cfg.selected_fields.push(chk.value);
        } else {
          cfg.selected_fields = cfg.selected_fields.filter(x => x !== chk.value);
        }
      });
      countEl.textContent = `(${cfg.selected_fields.length} selected)`;
      updatePreview();
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('input[name="mff-out-mode"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        cfg.output_mode = e.target.value;
        container.querySelector('#mff-create-fields-config').style.display = cfg.output_mode === 'create_new' ? 'block' : 'none';
        updatePreview();
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#mff-prefix-input').addEventListener('input', (e) => {
      cfg.output_prefix = e.target.value;
      updatePreview();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-suffix-input').addEventListener('input', (e) => {
      cfg.output_suffix = e.target.value;
      updatePreview();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-out-type-select').addEventListener('change', (e) => {
      cfg.output_type = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-token-field').addEventListener('click', () => {
      insertAtCursor('[_CurrentField_]');
    });

    container.querySelector('#mff-token-name').addEventListener('click', () => {
      insertAtCursor('[_CurrentFieldName_]');
    });

    container.querySelectorAll('.mff-col-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        insertAtCursor(`[${chip.dataset.col}]`);
      });
    });

    exprEl.addEventListener('input', () => {
      cfg.expression = exprEl.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#mff-preset-select').addEventListener('change', (e) => {
      const p = e.target.value;
      if (!p) return;
      if (p === 'trim') {
        cfg.expression = 'TRIM([_CurrentField_])';
      } else if (p === 'upper') {
        cfg.expression = 'UPPER([_CurrentField_])';
      } else if (p === 'lower') {
        cfg.expression = 'LOWER([_CurrentField_])';
      } else if (p === 'fill_zero') {
        cfg.expression = 'IFNULL([_CurrentField_], 0)';
      } else if (p === 'fill_empty') {
        cfg.expression = "IFNULL([_CurrentField_], '')";
      } else if (p === 'round_2') {
        cfg.expression = 'ROUND([_CurrentField_], 2)';
      } else if (p === 'abs') {
        cfg.expression = 'ABS([_CurrentField_])';
      } else if (p === 'scale_100') {
        cfg.expression = '[_CurrentField_] * 100.0';
      }
      exprEl.value = cfg.expression;
      this.canvas.onWorkflowChange();
    });

    renderColumnCheckboxes();
    updatePreview();
  }

  // --------------------------------------------------------------------
  // 6. Sort Tool
  // --------------------------------------------------------------------
  renderSortConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const sortBy = cfg.sort_by || [];

    container.innerHTML = `
      <label style="font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 8px; display: block;">
        Sorting Rules (Evaluated in order):
      </label>

      <div id="cfg-sort-rules-list">
        ${sortBy.map((s, i) => `
          <div class="form-row sort-rule-row" data-idx="${i}" style="margin-bottom: 8px;">
            <select class="form-control sort-col" style="flex: 2;">
              ${upstreamCols.length > 0 
                ? upstreamCols.map(col => `<option value="${col}" ${s.column === col ? 'selected' : ''}>${col}</option>`).join('')
                : `<option value="${s.column}">${s.column || 'Select column'}</option>`}
            </select>
            <select class="form-control sort-asc" style="flex: 1.5;">
              <option value="true" ${s.ascending !== false ? 'selected' : ''}>Ascending (A-Z, 0-9)</option>
              <option value="false" ${s.ascending === false ? 'selected' : ''}>Descending (Z-A, 9-0)</option>
            </select>
            <button class="btn-icon btn-remove-sort" style="color: var(--color-error);">&times;</button>
          </div>
        `).join('')}
      </div>

      <button id="btn-add-sort" class="btn btn-secondary btn-sm" style="margin-top: 6px;">
        + Add Sort Column
      </button>

      <div class="form-group" style="margin-top: 14px;">
        <label class="form-check">
          <input type="checkbox" id="cfg-sort-case" ${cfg.case_sensitive ? 'checked' : ''}>
          <span>Use Case-Sensitive Sorting</span>
        </label>
      </div>
    `;

    container.querySelectorAll('.sort-rule-row').forEach(row => {
      const idx = parseInt(row.dataset.idx);
      row.querySelector('.sort-col').addEventListener('change', (e) => {
        node.config.sort_by[idx].column = e.target.value;
        this.canvas.onWorkflowChange();
      });
      row.querySelector('.sort-asc').addEventListener('change', (e) => {
        node.config.sort_by[idx].ascending = (e.target.value === 'true');
        this.canvas.onWorkflowChange();
      });
      row.querySelector('.btn-remove-sort').addEventListener('click', () => {
        node.config.sort_by.splice(idx, 1);
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#btn-add-sort').addEventListener('click', () => {
      if (!node.config.sort_by) node.config.sort_by = [];
      node.config.sort_by.push({
        column: upstreamCols[0] || '',
        ascending: true
      });
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-sort-case').addEventListener('change', (e) => {
      node.config.case_sensitive = e.target.checked;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 7. Clean Tool
  // --------------------------------------------------------------------
  renderCleanConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    if (!cfg.columns && upstreamCols && upstreamCols.length > 0) {
      cfg.columns = [...upstreamCols];
    }
    const selectedCols = Array.isArray(cfg.columns) ? cfg.columns : (upstreamCols || []);

    // Get column metadata with type detection
    const colMeta = this.getUpstreamColumnMeta(node.id) || [];
    const fieldsList = (upstreamCols && upstreamCols.length > 0)
      ? upstreamCols.map(c => {
          const meta = colMeta.find(m => m.name === c);
          const type = meta ? meta.type : 'string';
          return { name: c, type };
        })
      : (Array.isArray(cfg.columns) ? cfg.columns.map(c => ({ name: c, type: 'string' })) : []);

    const selectedCount = selectedCols.filter(c => fieldsList.some(f => f.name === c)).length;

    container.innerHTML = `
      <div class="cfg-section-title">
        <span>Select Fields to Cleanse</span>
        <span class="badge" id="clean-selected-badge" style="margin-left: auto; font-size: 10px; font-weight: normal; color: var(--text-muted);">
          ${selectedCount} of ${fieldsList.length}
        </span>
      </div>

      <div class="cfg-card" style="padding: 8px;">
        <div style="display: flex; gap: 6px; margin-bottom: 8px;">
          <input type="text" class="form-control form-control-sm" id="clean-search-input" placeholder="Search fields..." style="flex: 1; font-size: 11px;">
        </div>
        <div class="cfg-toolbar" style="margin-bottom: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" id="clean-btn-all" style="padding: 2px 8px; font-size: 10px;">All</button>
          <button type="button" class="btn btn-secondary btn-sm" id="clean-btn-str" style="padding: 2px 8px; font-size: 10px;">Strings</button>
          <button type="button" class="btn btn-secondary btn-sm" id="clean-btn-num" style="padding: 2px 8px; font-size: 10px;">Numeric</button>
          <button type="button" class="btn btn-secondary btn-sm" id="clean-btn-none" style="padding: 2px 8px; font-size: 10px;">None</button>
        </div>

        <div id="clean-fields-list" class="clean-fields-box" style="max-height: 160px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 4px; padding: 4px; background: var(--bg-surface);">
          ${fieldsList.length > 0 ? fieldsList.map(f => {
            const isChecked = selectedCols.includes(f.name);
            const typeClass = f.type === 'numeric' ? 'sum-type-num' : (f.type === 'datetime' ? 'sum-type-date' : 'sum-type-str');
            return `
              <label class="clean-field-row form-check" data-field="${f.name}" data-type="${f.type}" style="display: flex; align-items: center; gap: 6px; padding: 4px 6px; margin-bottom: 2px; border-radius: 4px; cursor: pointer; font-size: 11px;">
                <input type="checkbox" class="clean-col-chk" value="${f.name}" ${isChecked ? 'checked' : ''} style="margin: 0;">
                <span class="clean-field-label" style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${f.name}</span>
                <span class="sum-type-badge ${typeClass}">${f.type}</span>
              </label>
            `;
          }).join('') : `
            <div style="padding: 10px; font-size: 11px; color: var(--text-muted); text-align: center;">
              Connect an input tool to view available fields. All incoming fields will be cleansed by default.
            </div>
          `}
        </div>
      </div>

      <div class="cfg-section-title">Replace Null Data</div>
      <div class="cfg-card">
        <label class="form-check" style="margin-bottom: 8px;">
          <input type="checkbox" id="cfg-clean-rep-null-str" ${cfg.replace_nulls_string ? 'checked' : ''}>
          <span>Replace with Blanks (String fields)</span>
        </label>
        <label class="form-check" style="margin-bottom: 8px;">
          <input type="checkbox" id="cfg-clean-rep-null-num" ${cfg.replace_nulls_numeric ? 'checked' : ''}>
          <span>Replace with 0 (Numeric fields)</span>
        </label>
        
        <details style="margin-top: 6px; font-size: 11px;" ${cfg.null_strategy && cfg.null_strategy !== 'none' ? 'open' : ''}>
          <summary style="color: var(--text-muted); cursor: pointer; user-select: none; font-size: 10.5px;">Advanced Null Options</summary>
          <div style="margin-top: 8px; padding: 8px; background: rgba(0, 0, 0, 0.15); border-radius: 4px; border: 1px solid var(--border-subtle);">
            <div class="form-group" style="margin-bottom: 6px;">
              <label style="font-size: 10.5px; color: var(--text-secondary); margin-bottom: 4px;">Custom Strategy</label>
              <select class="form-control form-control-sm" id="cfg-clean-null-strat">
                <option value="none" ${(!cfg.null_strategy || cfg.null_strategy === 'none') ? 'selected' : ''}>None (Alteryx default)</option>
                <option value="replace_value" ${cfg.null_strategy === 'replace_value' ? 'selected' : ''}>Replace with custom value</option>
                <option value="mean" ${cfg.null_strategy === 'mean' ? 'selected' : ''}>Mean (numeric fields)</option>
                <option value="median" ${cfg.null_strategy === 'median' ? 'selected' : ''}>Median (numeric fields)</option>
                <option value="drop_rows" ${cfg.null_strategy === 'drop_rows' ? 'selected' : ''}>Drop rows with nulls in selected fields</option>
              </select>
            </div>
            <div class="form-group" id="cfg-clean-null-rep-val-group" style="margin-bottom: 0; display: ${cfg.null_strategy === 'replace_value' ? 'block' : 'none'};">
              <label style="font-size: 10.5px; color: var(--text-secondary); margin-bottom: 4px;">Replacement Value</label>
              <input type="text" class="form-control form-control-sm" id="cfg-clean-null-rep-val" value="${cfg.null_replacement || ''}" placeholder="e.g. N/A">
            </div>
          </div>
        </details>
      </div>

      <div class="cfg-section-title">Remove Unwanted Characters</div>
      <div class="cfg-card">
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-trim" ${cfg.trim_whitespace !== false ? 'checked' : ''}>
          <span>Leading and Trailing Whitespace</span>
        </label>
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-tabs-lb" ${cfg.remove_tabs_linebreaks ? 'checked' : ''}>
          <span>Tabs, Line Breaks, and Duplicate Whitespace</span>
        </label>
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-all-ws" ${cfg.remove_all_ws ? 'checked' : ''}>
          <span>All Whitespace</span>
        </label>
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-letters" ${cfg.remove_letters ? 'checked' : ''}>
          <span>Letters</span>
        </label>
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-numbers" ${cfg.remove_numbers ? 'checked' : ''}>
          <span>Numbers</span>
        </label>
        <label class="form-check" style="margin-bottom: 8px;">
          <input type="checkbox" id="cfg-clean-punct" ${cfg.remove_punctuation ? 'checked' : ''}>
          <span>Punctuation</span>
        </label>

        <div class="form-group" style="margin-top: 8px; margin-bottom: 0;">
          <label style="font-size: 11px; color: var(--text-secondary); margin-bottom: 4px;">Custom characters / symbols to strip:</label>
          <input type="text" class="form-control form-control-sm" id="cfg-clean-custom-chars" placeholder="e.g. $€£%#@" value="${cfg.remove_custom_chars || cfg.custom_chars || ''}">
        </div>
      </div>

      <div class="cfg-section-title">Modify Case</div>
      <div class="cfg-card">
        <select class="form-control" id="cfg-clean-case">
          <option value="none" ${(!cfg.case_transformation || cfg.case_transformation === 'none') && (!cfg.case_mode || cfg.case_mode === 'none') ? 'selected' : ''}>Don't Modify Case</option>
          <option value="upper" ${cfg.case_transformation === 'upper' || cfg.case_mode === 'upper' ? 'selected' : ''}>UPPERCASE</option>
          <option value="lower" ${cfg.case_transformation === 'lower' || cfg.case_mode === 'lower' ? 'selected' : ''}>lowercase</option>
          <option value="title" ${cfg.case_transformation === 'title' || cfg.case_mode === 'title' ? 'selected' : ''}>Title Case</option>
        </select>
      </div>

      <div class="cfg-section-title">Row & Column Hygiene</div>
      <div class="cfg-card">
        <label class="form-check" style="margin-bottom: 6px;">
          <input type="checkbox" id="cfg-clean-empty-rows" ${cfg.remove_empty_rows ? 'checked' : ''}>
          <span>Remove completely empty rows</span>
        </label>
        <label class="form-check">
          <input type="checkbox" id="cfg-clean-empty-cols" ${cfg.remove_empty_cols ? 'checked' : ''}>
          <span>Remove completely empty columns</span>
        </label>
      </div>
    `;

    // Event handlers
    const updateSelectedCount = () => {
      const allChecked = Array.from(container.querySelectorAll('.clean-col-chk:checked')).map(c => c.value);
      node.config.columns = allChecked;
      const badge = container.querySelector('#clean-selected-badge');
      if (badge) {
        badge.textContent = `${allChecked.length} of ${fieldsList.length}`;
      }
      this.canvas.onWorkflowChange();
    };

    container.querySelectorAll('.clean-col-chk').forEach(chk => {
      chk.addEventListener('change', updateSelectedCount);
    });

    // Search filter
    const searchInput = container.querySelector('#clean-search-input');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        container.querySelectorAll('.clean-field-row').forEach(row => {
          const name = (row.getAttribute('data-field') || '').toLowerCase();
          row.style.display = (!query || name.includes(query)) ? 'flex' : 'none';
        });
      });
    }

    // Quick select buttons
    container.querySelector('#clean-btn-all')?.addEventListener('click', () => {
      container.querySelectorAll('.clean-col-chk').forEach(c => c.checked = true);
      updateSelectedCount();
    });

    container.querySelector('#clean-btn-none')?.addEventListener('click', () => {
      container.querySelectorAll('.clean-col-chk').forEach(c => c.checked = false);
      updateSelectedCount();
    });

    container.querySelector('#clean-btn-str')?.addEventListener('click', () => {
      container.querySelectorAll('.clean-field-row').forEach(row => {
        const type = row.getAttribute('data-type');
        const chk = row.querySelector('.clean-col-chk');
        if (chk) chk.checked = (type === 'string' || type === 'unknown');
      });
      updateSelectedCount();
    });

    container.querySelector('#clean-btn-num')?.addEventListener('click', () => {
      container.querySelectorAll('.clean-field-row').forEach(row => {
        const type = row.getAttribute('data-type');
        const chk = row.querySelector('.clean-col-chk');
        if (chk) chk.checked = (type === 'numeric');
      });
      updateSelectedCount();
    });

    // Checkboxes & inputs
    container.querySelector('#cfg-clean-rep-null-str')?.addEventListener('change', (e) => {
      node.config.replace_nulls_string = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-rep-null-num')?.addEventListener('change', (e) => {
      node.config.replace_nulls_numeric = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-null-strat')?.addEventListener('change', (e) => {
      node.config.null_strategy = e.target.value;
      const repValGroup = container.querySelector('#cfg-clean-null-rep-val-group');
      if (repValGroup) {
        repValGroup.style.display = e.target.value === 'replace_value' ? 'block' : 'none';
      }
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-null-rep-val')?.addEventListener('input', (e) => {
      node.config.null_replacement = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-trim')?.addEventListener('change', (e) => {
      node.config.trim_whitespace = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-tabs-lb')?.addEventListener('change', (e) => {
      node.config.remove_tabs_linebreaks = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-all-ws')?.addEventListener('change', (e) => {
      node.config.remove_all_ws = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-letters')?.addEventListener('change', (e) => {
      node.config.remove_letters = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-numbers')?.addEventListener('change', (e) => {
      node.config.remove_numbers = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-punct')?.addEventListener('change', (e) => {
      node.config.remove_punctuation = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-custom-chars')?.addEventListener('input', (e) => {
      node.config.remove_custom_chars = e.target.value;
      node.config.custom_chars = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-case')?.addEventListener('change', (e) => {
      node.config.case_transformation = e.target.value;
      node.config.case_mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-empty-rows')?.addEventListener('change', (e) => {
      node.config.remove_empty_rows = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-clean-empty-cols')?.addEventListener('change', (e) => {
      node.config.remove_empty_cols = e.target.checked;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 8. Unique Tool
  // --------------------------------------------------------------------
  renderUniqueConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const selectedCols = cfg.columns || [];

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">
        Choose unique key fields to identify duplicate rows:
      </div>

      <div class="cfg-toolbar" style="display: flex; gap: 6px; margin-bottom: 8px;">
        <button id="btn-unique-select-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Select All</button>
        <button id="btn-unique-deselect-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Deselect All</button>
      </div>

      <div style="max-height: 250px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 8px; background: var(--bg-main);">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 6px;">
            <input type="checkbox" class="unique-col-chk" value="${col}" ${selectedCols.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>

      <div style="margin-top: 16px; padding: 10px; background: var(--bg-main); border-radius: 6px; border: 1px solid var(--border-subtle); font-size: 11px;">
        <div style="font-weight: 700; color: var(--color-primary); margin-bottom: 4px;">Outputs:</div>
        <div><b>U (Unique)</b>: First unique occurrence of each record</div>
        <div><b>D (Duplicate)</b>: All duplicate records</div>
      </div>
    `;

    container.querySelector('#btn-unique-select-all')?.addEventListener('click', () => {
      node.config.columns = [...upstreamCols];
      container.querySelectorAll('.unique-col-chk').forEach(chk => { chk.checked = true; });
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-unique-deselect-all')?.addEventListener('click', () => {
      node.config.columns = [];
      container.querySelectorAll('.unique-col-chk').forEach(chk => { chk.checked = false; });
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.unique-col-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.unique-col-chk:checked')).map(c => c.value);
        node.config.columns = checked;
        this.canvas.onWorkflowChange();
      });
    });
  }

  getSummarizeDefaultName(field, action, extra = {}) {
    if (!field) return action || 'Summary';
    const a = (action || '').toLowerCase();
    if (a === 'groupby') return field;
    if (a === 'count') return `Count_${field}`;
    if (a === 'countdistinct') return `Distinct_${field}`;
    if (a === 'countdistinctnonnull' || a === 'count_distinct_non_null') return `DistinctNonNull_${field}`;
    if (a === 'countnull' || a === 'count_null') return `Nulls_${field}`;
    if (a === 'countnonnull' || a === 'count_non_null') return `NonNulls_${field}`;
    if (a === 'countblank' || a === 'count_blank') return `Blank_${field}`;
    if (a === 'countnonblank' || a === 'count_non_blank') return `NonBlank_${field}`;
    if (a === 'sum') return `Sum_${field}`;
    if (a === 'mean' || a === 'average' || a === 'avg') return `Avg_${field}`;
    if (a === 'min') return `Min_${field}`;
    if (a === 'max') return `Max_${field}`;
    if (a === 'median') return `Median_${field}`;
    if (a === 'mode') return `Mode_${field}`;
    if (a === 'product') return `Product_${field}`;
    if (a === 'percentile') {
      const p = extra && extra.percentile !== undefined ? String(extra.percentile).replace('.0', '') : '50';
      return `Percentile_${p}_${field}`;
    }
    if (a === 'stddev' || a === 'std') return `StdDev_${field}`;
    if (a === 'variance' || a === 'var') return `Var_${field}`;
    if (a === 'first') return `First_${field}`;
    if (a === 'last') return `Last_${field}`;
    if (a === 'longest') return `Longest_${field}`;
    if (a === 'shortest') return `Shortest_${field}`;
    if (a === 'concat' || a === 'concatenate') return `Concat_${field}`;
    if (a === 'concatdistinct' || a === 'concatenate_distinct') return `ConcatDistinct_${field}`;
    if (a === 'npv') return `NPV_${field}`;
    if (a === 'xnpv') return `XNPV_${field}`;
    if (a === 'irr') return `IRR_${field}`;
    if (a === 'xirr') return `XIRR_${field}`;
    if (a === 'mirr') return `MIRR_${field}`;
    return `${action}_${field}`;
  }

  // --------------------------------------------------------------------
  // 9. Summarize Tool (Faithful Alteryx Designer Parity)
  // --------------------------------------------------------------------
  renderSummarizeConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    if (!cfg.actions) cfg.actions = [];
    const actions = cfg.actions;

    // Upstream column metadata
    const colMeta = this.getUpstreamColumnMeta(node.id);
    const colMetaMap = {};
    colMeta.forEach(m => { colMetaMap[m.name] = m.type; });

    // Effective list of columns to show
    const availableCols = upstreamCols.length > 0 
      ? upstreamCols 
      : Array.from(new Set(actions.map(a => a.field).filter(Boolean)));

    // Categorized action definition for the Add Action menu & dropdowns
    const actionGroups = [
      {
        category: 'Group By',
        actions: [
          { value: 'GroupBy', label: 'GroupBy (Key)' }
        ]
      },
      {
        category: 'Numeric',
        actions: [
          { value: 'Sum', label: 'Sum' },
          { value: 'Average', label: 'Average / Mean' },
          { value: 'Min', label: 'Min' },
          { value: 'Max', label: 'Max' },
          { value: 'Median', label: 'Median' },
          { value: 'Mode', label: 'Mode' },
          { value: 'Product', label: 'Product' },
          { value: 'Percentile', label: 'Percentile' },
          { value: 'StdDev', label: 'Standard Deviation' },
          { value: 'Variance', label: 'Variance' }
        ]
      },
      {
        category: 'String',
        actions: [
          { value: 'Concat', label: 'Concatenate' },
          { value: 'ConcatDistinct', label: 'Concatenate Distinct' },
          { value: 'First', label: 'First' },
          { value: 'Last', label: 'Last' },
          { value: 'Longest', label: 'Longest' },
          { value: 'Shortest', label: 'Shortest' },
          { value: 'CountBlank', label: 'Count Blank' },
          { value: 'CountNonBlank', label: 'Count Non-Blank' },
          { value: 'Mode', label: 'Mode (Alphabetical)' }
        ]
      },
      {
        category: 'Count',
        actions: [
          { value: 'Count', label: 'Count Records' },
          { value: 'CountDistinct', label: 'Count Distinct' },
          { value: 'CountDistinctNonNull', label: 'Count Distinct Non-Null' },
          { value: 'CountNull', label: 'Count Null' },
          { value: 'CountNonNull', label: 'Count Non-Null' }
        ]
      },
      {
        category: 'Finance',
        actions: [
          { value: 'NPV', label: 'Net Present Value (NPV)' },
          { value: 'XNPV', label: 'NPV w/ Dates (XNPV)' },
          { value: 'IRR', label: 'Internal Rate of Return (IRR)' },
          { value: 'XIRR', label: 'IRR w/ Dates (XIRR)' },
          { value: 'MIRR', label: 'Modified IRR (MIRR)' }
        ]
      }
    ];

    // Count duplicate output names
    const nameCounts = {};
    actions.forEach(a => {
      const name = a.output_name || this.getSummarizeDefaultName(a.field, a.action, a);
      nameCounts[name] = (nameCounts[name] || 0) + 1;
    });

    // Helper to test if action is numeric
    const isNumericOp = (op) => {
      const o = (op || '').toLowerCase();
      return ['sum', 'average', 'mean', 'avg', 'min', 'max', 'median', 'mode', 'product', 'percentile', 'stddev', 'std', 'variance', 'var'].includes(o);
    };

    container.innerHTML = `
      <div class="sum-container">
        <!-- TOP SECTION: Available Fields -->
        <div class="sum-fields-section">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
            <label style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-secondary); letter-spacing: 0.5px; margin: 0;">
              1. Fields (${availableCols.length})
            </label>
            <div style="display: flex; gap: 4px;">
              <button type="button" class="btn btn-secondary btn-sm sum-pill-btn" data-filter="all" style="padding: 1px 6px; font-size: 10px;">All</button>
              <button type="button" class="btn btn-secondary btn-sm sum-pill-btn" data-filter="none" style="padding: 1px 6px; font-size: 10px;">None</button>
              <button type="button" class="btn btn-secondary btn-sm sum-pill-btn" data-filter="numeric" style="padding: 1px 6px; font-size: 10px;"># Num</button>
              <button type="button" class="btn btn-secondary btn-sm sum-pill-btn" data-filter="string" style="padding: 1px 6px; font-size: 10px;">Aa Str</button>
            </div>
          </div>

          <input type="text" id="sum-field-search" class="form-control" placeholder="Search fields..." style="padding: 3px 8px; font-size: 11px; margin-bottom: 6px;">

          <div class="sum-fields-box" id="sum-fields-list">
            ${availableCols.length > 0 ? availableCols.map(col => {
              const type = colMetaMap[col] || 'unknown';
              let badgeClass = 'sum-type-other';
              let badgeLabel = '?';
              if (type === 'numeric') {
                badgeClass = 'sum-type-num';
                badgeLabel = '# Num';
              } else if (type === 'string') {
                badgeClass = 'sum-type-str';
                badgeLabel = 'Aa Str';
              } else if (type === 'datetime') {
                badgeClass = 'sum-type-date';
                badgeLabel = '📅 Date';
              }
              return `
                <div class="sum-field-row" data-col="${col}" data-type="${type}">
                  <input type="checkbox" class="sum-col-chk" value="${col}">
                  <span style="font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${col}</span>
                  <span class="sum-type-badge ${badgeClass}">${badgeLabel}</span>
                </div>
              `;
            }).join('') : `
              <div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 11px;">
                Connect an upstream tool and run to view input fields.
              </div>
            `}
          </div>
        </div>

        <!-- ACTION BAR: Add Action Dropdown -->
        <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
          <div class="sum-actions-dropdown-wrap">
            <button type="button" class="btn btn-primary btn-sm" id="btn-sum-menu-toggle" style="display: flex; align-items: center; gap: 6px;">
              <span>+ Add Action</span>
              <span style="font-size: 9px;">▼</span>
            </button>
            <div class="sum-menu" id="sum-action-menu">
              ${actionGroups.map(grp => `
                <div class="sum-menu-group">${grp.category}</div>
                ${grp.actions.map(act => `
                  <div class="sum-menu-item" data-action="${act.value}">
                    <span>${act.label}</span>
                  </div>
                `).join('')}
              `).join('')}
            </div>
          </div>

          <div style="font-size: 11px; color: var(--text-muted);">
            ${actions.length} ${actions.length === 1 ? 'operation' : 'operations'} configured
          </div>
        </div>

        <!-- BOTTOM SECTION: Actions List with Reorder & Properties -->
        <div>
          <label style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-secondary); letter-spacing: 0.5px; margin-bottom: 6px; display: block;">
            2. Actions & Output Columns (Reorder controls output order)
          </label>

          <div id="sum-actions-container">
            ${actions.length === 0 ? `
              <div style="padding: 16px; border: 1px dashed var(--border-subtle); border-radius: 6px; text-align: center; color: var(--text-muted); font-size: 11px;">
                Select field(s) above and click <b>+ Add Action</b> to add aggregation operations.
              </div>
            ` : actions.map((a, i) => {
              const currentAction = a.action || 'GroupBy';
              const effectiveName = a.output_name || this.getSummarizeDefaultName(a.field, currentAction, a);
              const isDup = nameCounts[effectiveName] > 1;
              const isConcat = ['Concat', 'ConcatDistinct'].includes(currentAction);
              const isPct = currentAction === 'Percentile';
              const isNum = isNumericOp(currentAction);
              const isNpv = currentAction === 'NPV';
              const isXnpv = currentAction === 'XNPV';
              const isXirr = currentAction === 'XIRR';
              const isMirr = currentAction === 'MIRR';

              return `
                <div class="sum-act-card" data-idx="${i}">
                  <!-- Primary Action Row -->
                  <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 6px;">
                    <!-- Reorder Up/Down -->
                    <div style="display: flex; flex-direction: column; gap: 2px;">
                      <button type="button" class="cfg-reorder-btn btn-act-up" data-idx="${i}" title="Move Up" ${i === 0 ? 'disabled style="opacity:0.25; cursor:not-allowed;"' : ''} style="line-height:1; font-size:9px; padding:1px 3px;">▲</button>
                      <button type="button" class="cfg-reorder-btn btn-act-down" data-idx="${i}" title="Move Down" ${i === actions.length - 1 ? 'disabled style="opacity:0.25; cursor:not-allowed;"' : ''} style="line-height:1; font-size:9px; padding:1px 3px;">▼</button>
                    </div>

                    <!-- Field Select -->
                    <select class="form-control sum-field" style="flex: 2; font-size: 11px; padding: 3px 6px;">
                      ${availableCols.length > 0 
                        ? availableCols.map(col => `<option value="${col}" ${a.field === col ? 'selected' : ''}>${col}</option>`).join('')
                        : `<option value="${a.field}">${a.field || 'Select field'}</option>`}
                    </select>

                    <!-- Action Select with Optgroups -->
                    <select class="form-control sum-action" style="flex: 2.2; font-size: 11px; padding: 3px 6px;">
                      ${actionGroups.map(grp => `
                        <optgroup label="${grp.category}">
                          ${grp.actions.map(act => `
                            <option value="${act.value}" ${currentAction === act.value ? 'selected' : ''}>${act.label}</option>
                          `).join('')}
                        </optgroup>
                      `).join('')}
                    </select>

                    <!-- Delete Button -->
                    <button type="button" class="btn-icon btn-remove-sum" data-idx="${i}" title="Delete Action" style="color: var(--color-error); font-size: 14px; padding: 2px 5px;">&times;</button>
                  </div>

                  <!-- Output Column Name Row -->
                  <div style="display: flex; align-items: center; gap: 6px;">
                    <span style="font-size: 10px; color: var(--text-muted); width: 42px; text-align: right; flex-shrink: 0;">Output:</span>
                    <input type="text" class="form-control sum-outname" value="${a.output_name || ''}" placeholder="${effectiveName}" style="flex: 1; font-size: 11px; padding: 3px 6px;">
                  </div>

                  <!-- Duplicate Name Warning -->
                  ${isDup ? `
                    <div style="font-size: 10px; color: #f59e0b; margin-top: 4px; padding-left: 48px;">
                      ⚠️ Output name '${effectiveName}' is duplicated (auto-suffixed on run).
                    </div>
                  ` : ''}

                  <!-- Context-Sensitive Properties Drawer -->
                  ${(isConcat || isPct || isNum || isNpv || isXnpv || isXirr || isMirr) ? `
                    <div class="sum-props-drawer" style="margin-top: 6px; padding: 6px 8px; font-size: 11px;">
                      ${isConcat ? `
                        <div style="display: grid; grid-template-columns: 1fr 1.2fr 1fr; gap: 6px;">
                          <div>
                            <span style="font-size: 9px; color: var(--text-muted); display: block;">Start (Prefix):</span>
                            <input type="text" class="form-control sum-start" value="${a.start || ''}" placeholder="e.g. [" style="padding: 2px 4px; font-size: 10px;">
                          </div>
                          <div>
                            <span style="font-size: 9px; color: var(--text-muted); display: block;">Separator:</span>
                            <input type="text" class="form-control sum-sep" value="${a.separator !== undefined ? a.separator : ', '}" placeholder=", " style="padding: 2px 4px; font-size: 10px;">
                          </div>
                          <div>
                            <span style="font-size: 9px; color: var(--text-muted); display: block;">End (Suffix):</span>
                            <input type="text" class="form-control sum-end" value="${a.end || ''}" placeholder="e.g. ]" style="padding: 2px 4px; font-size: 10px;">
                          </div>
                        </div>
                      ` : ''}

                      ${isPct ? `
                        <div style="display: flex; align-items: center; gap: 8px;">
                          <span style="font-size: 10px; color: var(--text-muted);">Percentile (0-100):</span>
                          <input type="number" class="form-control sum-pct" min="0" max="100" step="0.1" value="${a.percentile !== undefined ? a.percentile : 50}" style="width: 70px; padding: 2px 4px; font-size: 10px;">
                          <span style="font-size: 10px; color: var(--text-muted);">%</span>
                        </div>
                      ` : ''}

                      ${isNum ? `
                        <div style="margin-top: ${isPct ? '4px' : '0'};">
                          <label class="form-check" style="margin: 0; font-size: 11px;">
                            <input type="checkbox" class="sum-ignore-zero" ${a.ignore_zeros ? 'checked' : ''}>
                            <span>Ignore 0's</span>
                          </label>
                        </div>
                      ` : ''}

                      ${isNpv ? `
                        <div style="display: flex; align-items: center; gap: 8px;">
                          <span style="font-size: 10px; color: var(--text-muted);">Discount Rate %:</span>
                          <input type="number" class="form-control sum-disc-rate" step="0.1" value="${a.discount_rate !== undefined ? a.discount_rate : 8.0}" style="width: 70px; padding: 2px 4px; font-size: 10px;">
                          <span style="font-size: 10px; color: var(--text-muted);">% per period</span>
                        </div>
                      ` : ''}

                      ${isXnpv ? `
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                          <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 10px; color: var(--text-muted); width: 85px;">Discount Rate:</span>
                            <input type="number" class="form-control sum-disc-rate" step="0.1" value="${a.discount_rate !== undefined ? a.discount_rate : 8.0}" style="width: 70px; padding: 2px 4px; font-size: 10px;">
                            <span style="font-size: 10px; color: var(--text-muted);">% annual</span>
                          </div>
                          <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 10px; color: var(--text-muted); width: 85px;">Date Field:</span>
                            <select class="form-control sum-date-field" style="flex: 1; padding: 2px 4px; font-size: 10px;">
                              <option value="">-- Choose Date Column --</option>
                              ${availableCols.map(col => `<option value="${col}" ${a.date_field === col ? 'selected' : ''}>${col}</option>`).join('')}
                            </select>
                          </div>
                        </div>
                      ` : ''}

                      ${isXirr ? `
                        <div style="display: flex; align-items: center; gap: 8px;">
                          <span style="font-size: 10px; color: var(--text-muted); width: 85px;">Date Field:</span>
                          <select class="form-control sum-date-field" style="flex: 1; padding: 2px 4px; font-size: 10px;">
                            <option value="">-- Choose Date Column --</option>
                            ${availableCols.map(col => `<option value="${col}" ${a.date_field === col ? 'selected' : ''}>${col}</option>`).join('')}
                          </select>
                        </div>
                      ` : ''}

                      ${isMirr ? `
                        <div style="display: flex; flex-direction: column; gap: 4px;">
                          <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 10px; color: var(--text-muted); width: 85px;">Finance Rate %:</span>
                            <input type="number" class="form-control sum-fin-rate" step="0.1" value="${a.finance_rate !== undefined ? a.finance_rate : 8.0}" style="width: 70px; padding: 2px 4px; font-size: 10px;">
                            <span style="font-size: 10px; color: var(--text-muted);">%</span>
                          </div>
                          <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 10px; color: var(--text-muted); width: 85px;">Reinvest Rate %:</span>
                            <input type="number" class="form-control sum-reinv-rate" step="0.1" value="${a.reinvest_rate !== undefined ? a.reinvest_rate : 8.0}" style="width: 70px; padding: 2px 4px; font-size: 10px;">
                            <span style="font-size: 10px; color: var(--text-muted);">%</span>
                          </div>
                        </div>
                      ` : ''}
                    </div>
                  ` : ''}
                </div>
              `;
            }).join('')}
          </div>
        </div>
      </div>
    `;

    // ------------------------------------------------------------------
    // Event Wiring
    // ------------------------------------------------------------------

    // 1. Field filter pills (All / None / Numeric / String)
    container.querySelectorAll('.sum-pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const f = btn.dataset.filter;
        const rows = container.querySelectorAll('.sum-field-row');
        rows.forEach(r => {
          const chk = r.querySelector('.sum-col-chk');
          const t = r.dataset.type;
          if (f === 'all') chk.checked = true;
          else if (f === 'none') chk.checked = false;
          else if (f === 'numeric') chk.checked = (t === 'numeric');
          else if (f === 'string') chk.checked = (t === 'string');
          r.classList.toggle('selected', chk.checked);
        });
      });
    });

    // 2. Field search box
    const searchInput = container.querySelector('#sum-field-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        container.querySelectorAll('.sum-field-row').forEach(r => {
          const name = (r.dataset.col || '').toLowerCase();
          r.style.display = name.includes(query) ? 'flex' : 'none';
        });
      });
    }

    // Row selection toggle on click
    container.querySelectorAll('.sum-field-row').forEach(row => {
      const chk = row.querySelector('.sum-col-chk');
      row.addEventListener('click', (e) => {
        if (e.target !== chk) {
          chk.checked = !chk.checked;
        }
        row.classList.toggle('selected', chk.checked);
      });
    });

    // 3. Dropdown Menu Toggle & Selection
    const menuToggleBtn = container.querySelector('#btn-sum-menu-toggle');
    const menuEl = container.querySelector('#sum-action-menu');

    if (menuToggleBtn && menuEl) {
      menuToggleBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        menuEl.classList.toggle('show');
      });

      const closeMenu = () => menuEl.classList.remove('show');
      document.addEventListener('click', closeMenu);

      menuEl.querySelectorAll('.sum-menu-item').forEach(item => {
        item.addEventListener('click', (e) => {
          e.stopPropagation();
          const chosenAction = item.dataset.action;
          closeMenu();

          // Get checked fields from the top list
          const checkedCols = Array.from(container.querySelectorAll('.sum-col-chk:checked')).map(c => c.value);
          const targetCols = checkedCols.length > 0 ? checkedCols : (availableCols.length > 0 ? [availableCols[0]] : ['']);

          targetCols.forEach(col => {
            const defaultName = this.getSummarizeDefaultName(col, chosenAction);
            const newAct = {
              field: col,
              action: chosenAction,
              output_name: defaultName
            };
            if (['Concat', 'ConcatDistinct'].includes(chosenAction)) {
              newAct.start = '';
              newAct.separator = ', ';
              newAct.end = '';
            } else if (chosenAction === 'Percentile') {
              newAct.percentile = 50;
            } else if (['NPV', 'XNPV'].includes(chosenAction)) {
              newAct.discount_rate = 8.0;
            } else if (chosenAction === 'MIRR') {
              newAct.finance_rate = 8.0;
              newAct.reinvest_rate = 8.0;
            }
            node.config.actions.push(newAct);
          });

          this.render(node);
          this.canvas.onWorkflowChange();
        });
      });
    }

    // 4. Reorder, Delete, and Parameter Edits on Actions List
    container.querySelectorAll('.sum-act-card').forEach(card => {
      const idx = parseInt(card.dataset.idx);
      const actionObj = node.config.actions[idx];

      // Reorder Up
      card.querySelector('.btn-act-up')?.addEventListener('click', () => {
        if (idx > 0) {
          const temp = node.config.actions[idx - 1];
          node.config.actions[idx - 1] = node.config.actions[idx];
          node.config.actions[idx] = temp;
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });

      // Reorder Down
      card.querySelector('.btn-act-down')?.addEventListener('click', () => {
        if (idx < node.config.actions.length - 1) {
          const temp = node.config.actions[idx + 1];
          node.config.actions[idx + 1] = node.config.actions[idx];
          node.config.actions[idx] = temp;
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });

      // Delete
      card.querySelector('.btn-remove-sum')?.addEventListener('click', () => {
        node.config.actions.splice(idx, 1);
        this.render(node);
        this.canvas.onWorkflowChange();
      });

      // Field Change
      const fieldSel = card.querySelector('.sum-field');
      const outNameInp = card.querySelector('.sum-outname');
      fieldSel?.addEventListener('change', (e) => {
        const oldField = actionObj.field;
        const currentAction = actionObj.action || 'GroupBy';
        const oldDefault = this.getSummarizeDefaultName(oldField, currentAction, actionObj);
        const currentCustom = actionObj.output_name;

        actionObj.field = e.target.value;
        if (!currentCustom || currentCustom === oldDefault || currentCustom === oldField) {
          const newDefault = this.getSummarizeDefaultName(e.target.value, currentAction, actionObj);
          actionObj.output_name = newDefault;
          if (outNameInp) outNameInp.value = newDefault;
        }
        this.render(node);
        this.canvas.onWorkflowChange();
      });

      // Action Change
      const actSel = card.querySelector('.sum-action');
      actSel?.addEventListener('change', (e) => {
        const oldAction = actionObj.action;
        const currentField = actionObj.field;
        const oldDefault = this.getSummarizeDefaultName(currentField, oldAction, actionObj);
        const currentCustom = actionObj.output_name;

        actionObj.action = e.target.value;
        if (!currentCustom || currentCustom === oldDefault || currentCustom === currentField) {
          const newDefault = this.getSummarizeDefaultName(currentField, e.target.value, actionObj);
          actionObj.output_name = newDefault;
          if (outNameInp) outNameInp.value = newDefault;
        }
        this.render(node);
        this.canvas.onWorkflowChange();
      });

      // Output Name Manual Edit
      outNameInp?.addEventListener('input', (e) => {
        actionObj.output_name = e.target.value;
        this.canvas.onWorkflowChange();
      });

      // Parameters
      card.querySelector('.sum-start')?.addEventListener('input', (e) => {
        actionObj.start = e.target.value;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-sep')?.addEventListener('input', (e) => {
        actionObj.separator = e.target.value;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-end')?.addEventListener('input', (e) => {
        actionObj.end = e.target.value;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-pct')?.addEventListener('input', (e) => {
        actionObj.percentile = parseFloat(e.target.value) || 50;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-ignore-zero')?.addEventListener('change', (e) => {
        actionObj.ignore_zeros = e.target.checked;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-disc-rate')?.addEventListener('input', (e) => {
        actionObj.discount_rate = parseFloat(e.target.value) || 8.0;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-date-field')?.addEventListener('change', (e) => {
        actionObj.date_field = e.target.value;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-fin-rate')?.addEventListener('input', (e) => {
        actionObj.finance_rate = parseFloat(e.target.value) || 8.0;
        this.canvas.onWorkflowChange();
      });
      card.querySelector('.sum-reinv-rate')?.addEventListener('input', (e) => {
        actionObj.reinvest_rate = parseFloat(e.target.value) || 8.0;
        this.canvas.onWorkflowChange();
      });
    });
  }

  // --------------------------------------------------------------------
  // --------------------------------------------------------------------
  // 10. Join Tool (Alteryx Parity)
  // --------------------------------------------------------------------
  renderJoinConfig(container, node) {
    const cfg = node.config || {};
    if (cfg.ignore_case === undefined) cfg.ignore_case = true;
    if (!cfg.join_keys) cfg.join_keys = [];

    const leftCols = this.getUpstreamColumns(node.id, 'L');
    const rightCols = this.getUpstreamColumns(node.id, 'R');
    const leftMeta = this.getUpstreamColumnMeta(node.id, 'L');
    const rightMeta = this.getUpstreamColumnMeta(node.id, 'R');

    const metaMap = {};
    if (Array.isArray(leftMeta)) {
      leftMeta.forEach(m => {
        if (m && m.name) metaMap[`L_${m.name}`] = m.alteryx_type || m.type || 'unknown';
      });
    }
    if (Array.isArray(rightMeta)) {
      rightMeta.forEach(m => {
        if (m && m.name) metaMap[`R_${m.name}`] = m.alteryx_type || m.type || 'unknown';
      });
    }

    // Auto-initialize join_keys if empty and columns are available
    if (cfg.join_keys.length === 0 && leftCols.length > 0 && rightCols.length > 0) {
      const rightLower = rightCols.map(c => c.toLowerCase());
      const initialMatches = [];
      leftCols.forEach(lc => {
        const rIdx = rightLower.indexOf(lc.toLowerCase());
        if (rIdx !== -1 && initialMatches.length === 0) {
          initialMatches.push({ left_key: lc, right_key: rightCols[rIdx] });
        }
      });
      if (initialMatches.length > 0) {
        cfg.join_keys = initialMatches;
      } else {
        cfg.join_keys = [{ left_key: leftCols[0], right_key: rightCols[0] }];
      }
    }

    // Synchronize embedded select_fields
    if (!cfg.select_fields) cfg.select_fields = [];
    const existingFieldMap = new Map();
    cfg.select_fields.forEach(sf => {
      if (sf && sf.field) existingFieldMap.set(sf.field, sf);
    });

    if (leftCols.length > 0 || rightCols.length > 0) {
      const newSelectFields = [];
      // 1. Left columns
      leftCols.forEach(c => {
        if (existingFieldMap.has(c)) {
          const prev = existingFieldMap.get(c);
          newSelectFields.push({
            field: c,
            source: 'L',
            original: c,
            selected: prev.selected !== false,
            rename: prev.rename !== undefined ? prev.rename : c,
            type: prev.type || 'none'
          });
        } else {
          newSelectFields.push({
            field: c,
            source: 'L',
            original: c,
            selected: true,
            rename: c,
            type: 'none'
          });
        }
      });

      // 2. Right columns (colliding names prefixed with Right_)
      rightCols.forEach(c => {
        const outName = leftCols.includes(c) ? `Right_${c}` : c;
        if (existingFieldMap.has(outName)) {
          const prev = existingFieldMap.get(outName);
          newSelectFields.push({
            field: outName,
            source: 'R',
            original: c,
            selected: prev.selected !== false,
            rename: prev.rename !== undefined ? prev.rename : outName,
            type: prev.type || 'none'
          });
        } else {
          // By default in Alteryx, duplicate join keys from Right are often deselected or kept prefixed
          newSelectFields.push({
            field: outName,
            source: 'R',
            original: c,
            selected: true,
            rename: outName,
            type: 'none'
          });
        }
      });

      // If user had customized reordering, preserve order of existing fields
      if (cfg.select_fields.length > 0) {
        const orderedFields = [];
        cfg.select_fields.forEach(prev => {
          const foundIdx = newSelectFields.findIndex(n => n.field === prev.field);
          if (foundIdx !== -1) {
            orderedFields.push(newSelectFields[foundIdx]);
            newSelectFields.splice(foundIdx, 1);
          }
        });
        // Append any newly discovered fields to the end
        cfg.select_fields = [...orderedFields, ...newSelectFields];
      } else {
        cfg.select_fields = newSelectFields;
      }
    }

    const getTypeIcon = (typeName) => {
      if (!typeName) return '';
      const t = typeName.toLowerCase();
      if (t.includes('int') || t.includes('double') || t.includes('float') || t.includes('num')) return '#';
      if (t.includes('date') || t.includes('time')) return '📅';
      if (t.includes('bool')) return '✓';
      return 'Aa';
    };

    container.innerHTML = `
      <!-- 1. Join Keys Section -->
      <div class="join-section-title">
        <span>Join Keys</span>
        <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">
          ${cfg.join_keys.length} key pair${cfg.join_keys.length !== 1 ? 's' : ''}
        </span>
      </div>

      <div class="join-keys-container">
        <div id="cfg-join-keys-list">
          ${cfg.join_keys.map((k, i) => `
            <div class="join-key-row" data-idx="${i}">
              <div style="flex: 1; min-width: 0;">
                <select class="form-control join-left-key" style="width: 100%; font-size: 11px;">
                  <option value="" ${!k.left_key ? 'selected' : ''}>-- Select Left Key --</option>
                  ${leftCols.length > 0
                    ? leftCols.map(c => `
                        <option value="${this.escapeHtml(c)}" ${k.left_key === c ? 'selected' : ''}>
                          ${getTypeIcon(metaMap[`L_${c}`])} ${this.escapeHtml(c)}
                        </option>
                      `).join('')
                    : `<option value="${this.escapeHtml(k.left_key || '')}" selected>${this.escapeHtml(k.left_key || 'Left Key')}</option>`}
                </select>
              </div>

              <span class="join-key-op">=</span>

              <div style="flex: 1; min-width: 0;">
                <select class="form-control join-right-key" style="width: 100%; font-size: 11px;">
                  <option value="" ${!k.right_key ? 'selected' : ''}>-- Select Right Key --</option>
                  ${rightCols.length > 0
                    ? rightCols.map(c => `
                        <option value="${this.escapeHtml(c)}" ${k.right_key === c ? 'selected' : ''}>
                          ${getTypeIcon(metaMap[`R_${c}`])} ${this.escapeHtml(c)}
                        </option>
                      `).join('')
                    : `<option value="${this.escapeHtml(k.right_key || '')}" selected>${this.escapeHtml(k.right_key || 'Right Key')}</option>`}
                </select>
              </div>

              <button class="btn-icon btn-remove-key" title="Remove Key Pair" style="color: var(--color-error); padding: 4px;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
              </button>
            </div>
          `).join('')}
        </div>

        <div style="display: flex; gap: 8px; margin-top: 10px; align-items: center; justify-content: space-between;">
          <div style="display: flex; gap: 6px;">
            <button id="btn-add-key" class="btn btn-secondary btn-sm" style="font-size: 11px; padding: 4px 8px;">
              + Add Key Pair
            </button>
            <button id="btn-automatch-keys" class="btn btn-secondary btn-sm" title="Pair columns with identical names" style="font-size: 11px; padding: 4px 8px;">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 3px;"><polyline points="20 6 9 17 4 12"></polyline></svg>
              Auto-Match Keys
            </button>
          </div>

          <label style="display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); cursor: pointer; user-select: none; margin: 0;">
            <input type="checkbox" id="cfg-join-ignore-case" ${cfg.ignore_case ? 'checked' : ''}>
            <span>Ignore Case & Trim</span>
          </label>
        </div>
      </div>

      <!-- 2. Embedded Select Tool Grid (Alteryx Parity) -->
      <div class="join-section-title" style="margin-top: 14px;">
        <span>Joined (J) Output Columns</span>
        <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">
          ${cfg.select_fields.filter(f => f.selected !== false).length} of ${cfg.select_fields.length} selected
        </span>
      </div>

      <div class="join-toolbar" style="gap: 4px; display: flex; flex-wrap: wrap;">
        <button id="btn-join-select-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Select All</button>
        <button id="btn-join-deselect-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 6px;">Deselect All</button>
        <button id="btn-join-select-all-left" class="btn btn-secondary btn-sm" title="Select all columns from Left table" style="font-size: 10px; padding: 2px 6px; border-left: 2px solid #22c55e;">+ All Left (L)</button>
        <button id="btn-join-deselect-all-left" class="btn btn-secondary btn-sm" title="Deselect all columns from Left table" style="font-size: 10px; padding: 2px 6px; border-left: 2px solid #22c55e;">- All Left (L)</button>
        <button id="btn-join-select-all-right" class="btn btn-secondary btn-sm" title="Select all columns from Right table" style="font-size: 10px; padding: 2px 6px; border-left: 2px solid #a855f7;">+ All Right (R)</button>
        <button id="btn-join-deselect-all-right" class="btn btn-secondary btn-sm" title="Deselect all columns from Right table" style="font-size: 10px; padding: 2px 6px; border-left: 2px solid #a855f7;">- All Right (R)</button>
        <button id="btn-join-deselect-right-keys" class="btn btn-secondary btn-sm" title="Uncheck duplicate Right join keys" style="font-size: 10px; padding: 2px 6px;">Deselect Right Keys</button>
        <button id="btn-join-reset-renames" class="btn btn-secondary btn-sm" title="Reset all custom column names" style="font-size: 10px; padding: 2px 6px;">Reset Names</button>
      </div>

      <div class="join-select-wrap">
        <table class="join-select-table">
          <thead>
            <tr>
              <th style="width: 32px; text-align: center;">Keep</th>
              <th style="width: 54px; text-align: center;">Order</th>
              <th style="width: 30px; text-align: center;">Src</th>
              <th>Field</th>
              <th>Rename</th>
              <th style="width: 110px;">Type Cast</th>
            </tr>
          </thead>
          <tbody id="cfg-join-select-tbody">
            ${cfg.select_fields.map((sf, i) => {
              const isRight = sf.source === 'R';
              const metaKey = isRight ? `R_${sf.original || sf.field.replace(/^Right_/, '')}` : `L_${sf.field}`;
              const typeDesc = metaMap[metaKey];
              return `
                <tr data-sf-idx="${i}">
                  <td style="text-align: center;">
                    <input type="checkbox" class="sf-keep" ${sf.selected !== false ? 'checked' : ''}>
                  </td>
                  <td style="text-align: center; white-space: nowrap;">
                    <span class="drag-grip" title="Click and drag to reorder">⋮⋮</span>
                    <button class="join-reorder-btn sf-move-up" data-idx="${i}" title="Move Up" ${i === 0 ? 'disabled' : ''}>▲</button>
                    <button class="join-reorder-btn sf-move-down" data-idx="${i}" title="Move Down" ${i === cfg.select_fields.length - 1 ? 'disabled' : ''}>▼</button>
                  </td>
                  <td style="text-align: center;">
                    <span class="join-source-pill source-${isRight ? 'r' : 'l'}">${isRight ? 'R' : 'L'}</span>
                  </td>
                  <td style="font-weight: 500; word-break: break-word;">
                    ${this.escapeHtml(sf.field)}
                    ${typeDesc ? `<span style="font-size: 9px; color: var(--text-muted); margin-left: 3px;">(${typeDesc})</span>` : ''}
                  </td>
                  <td>
                    <input type="text" class="form-control sf-rename" style="padding: 2px 6px; font-size: 11px; width: 100%;" value="${this.escapeHtml(sf.rename || sf.field)}">
                  </td>
                  <td>
                    <select class="form-control sf-type" style="padding: 2px 4px; font-size: 11px; width: 100%;">
                      <option value="none" ${(!sf.type || sf.type === 'none') ? 'selected' : ''}>Current</option>
                      <option value="string" ${sf.type === 'string' ? 'selected' : ''}>String</option>
                      <option value="int64" ${sf.type === 'int64' ? 'selected' : ''}>Int64</option>
                      <option value="int32" ${sf.type === 'int32' ? 'selected' : ''}>Int32</option>
                      <option value="double" ${sf.type === 'double' || sf.type === 'float' ? 'selected' : ''}>Double</option>
                      <option value="date" ${sf.type === 'date' ? 'selected' : ''}>Date</option>
                      <option value="datetime" ${sf.type === 'datetime' ? 'selected' : ''}>DateTime</option>
                      <option value="bool" ${sf.type === 'bool' ? 'selected' : ''}>Bool</option>
                    </select>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>

      ${cfg.select_fields.length === 0 ? `
        <div style="padding: 10px; font-size: 11px; color: var(--text-muted); text-align: center; border: 1px dashed var(--border-subtle); border-radius: 6px; margin-top: 6px;">
          Connect both Left (L) and Right (R) inputs to populate and customize joined columns.
        </div>
      ` : ''}

      <!-- 3. Tri-Stream Partition Legend -->
      <div class="join-stream-legend">
        <div style="font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 2px;">
          Output Stream Partitions
        </div>
        <div class="join-stream-item">
          <span class="join-port-tag port-j">J</span>
          <div><b>Joined</b>: Matched records combining Left & Right data, shaped by the select configuration above.</div>
        </div>
        <div class="join-stream-item">
          <span class="join-port-tag port-l">L</span>
          <div><b>Left Unjoined</b>: Records from Left input that found no matching Right key (original Left schema).</div>
        </div>
        <div class="join-stream-item">
          <span class="join-port-tag port-r">R</span>
          <div><b>Right Unjoined</b>: Records from Right input that found no matching Left key (original Right schema).</div>
        </div>
      </div>
    `;

    // Event Bindings: Join Keys
    container.querySelectorAll('.join-key-row').forEach(row => {
      const idx = parseInt(row.dataset.idx);
      row.querySelector('.join-left-key').addEventListener('change', (e) => {
        node.config.join_keys[idx].left_key = e.target.value;
        this.canvas.onWorkflowChange();
      });
      row.querySelector('.join-right-key').addEventListener('change', (e) => {
        node.config.join_keys[idx].right_key = e.target.value;
        this.canvas.onWorkflowChange();
      });
      row.querySelector('.btn-remove-key').addEventListener('click', () => {
        node.config.join_keys.splice(idx, 1);
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#cfg-join-ignore-case')?.addEventListener('change', (e) => {
      node.config.ignore_case = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-add-key')?.addEventListener('click', () => {
      if (!node.config.join_keys) node.config.join_keys = [];
      node.config.join_keys.push({
        left_key: leftCols[0] || '',
        right_key: rightCols[0] || ''
      });
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-automatch-keys')?.addEventListener('click', () => {
      if (!leftCols.length || !rightCols.length) {
        if (window.showToast) window.showToast('info', 'Auto-Match Keys', 'Connect both Left (L) and Right (R) inputs to auto-match columns.');
        return;
      }
      const matches = [];
      const rightLower = rightCols.map(c => c.toLowerCase());
      leftCols.forEach(lc => {
        const rIdx = rightLower.indexOf(lc.toLowerCase());
        if (rIdx !== -1) {
          matches.push({ left_key: lc, right_key: rightCols[rIdx] });
        }
      });
      if (matches.length > 0) {
        node.config.join_keys = matches;
        this.render(node);
        this.canvas.onWorkflowChange();
        if (window.showToast) window.showToast('success', 'Auto-Match Keys', `Matched ${matches.length} key pair(s) automatically!`);
      } else {
        if (window.showToast) window.showToast('warning', 'Auto-Match Keys', 'No matching column names found between Left and Right inputs.');
      }
    });

    // Event Bindings: Embedded Select Grid
    container.querySelectorAll('[data-sf-idx]').forEach(tr => {
      const idx = parseInt(tr.dataset.sfIdx);
      tr.querySelector('.sf-keep').addEventListener('change', (e) => {
        node.config.select_fields[idx].selected = e.target.checked;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-rename').addEventListener('input', (e) => {
        node.config.select_fields[idx].rename = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-type').addEventListener('change', (e) => {
        node.config.select_fields[idx].type = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-move-up')?.addEventListener('click', () => {
        if (idx > 0) {
          const item = node.config.select_fields.splice(idx, 1)[0];
          node.config.select_fields.splice(idx - 1, 0, item);
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
      tr.querySelector('.sf-move-down')?.addEventListener('click', () => {
        if (idx < node.config.select_fields.length - 1) {
          const item = node.config.select_fields.splice(idx, 1)[0];
          node.config.select_fields.splice(idx + 1, 0, item);
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
    });

    const joinTbody = container.querySelector('#cfg-join-select-tbody');
    this.setupTableDragAndDrop(joinTbody, node.config.select_fields, (newFields) => {
      node.config.select_fields = newFields;
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    // Bulk action toolbar bindings
    container.querySelector('#btn-join-select-all')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => f.selected = true);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-join-deselect-all')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => f.selected = false);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-join-select-all-left')?.addEventListener('click', () => {
      let count = 0;
      node.config.select_fields.forEach(f => {
        if (f.source === 'L') {
          f.selected = true;
          count++;
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Grid', `Selected all ${count} Left column(s).`);
    });

    container.querySelector('#btn-join-deselect-all-left')?.addEventListener('click', () => {
      let count = 0;
      node.config.select_fields.forEach(f => {
        if (f.source === 'L') {
          f.selected = false;
          count++;
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Grid', `Deselected all ${count} Left column(s).`);
    });

    container.querySelector('#btn-join-select-all-right')?.addEventListener('click', () => {
      let count = 0;
      node.config.select_fields.forEach(f => {
        if (f.source === 'R') {
          f.selected = true;
          count++;
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Grid', `Selected all ${count} Right column(s).`);
    });

    container.querySelector('#btn-join-deselect-all-right')?.addEventListener('click', () => {
      let count = 0;
      node.config.select_fields.forEach(f => {
        if (f.source === 'R') {
          f.selected = false;
          count++;
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Grid', `Deselected all ${count} Right column(s).`);
    });

    container.querySelector('#btn-join-deselect-right-keys')?.addEventListener('click', () => {
      const rightKeyNames = (node.config.join_keys || []).map(k => k.right_key).filter(Boolean);
      let deselectedCount = 0;
      node.config.select_fields.forEach(f => {
        if (f.source === 'R') {
          const orig = f.original || f.field.replace(/^Right_/, '');
          if (rightKeyNames.includes(orig) || f.field.startsWith('Right_')) {
            f.selected = false;
            deselectedCount++;
          }
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Grid', `Deselected ${deselectedCount} duplicate Right column(s).`);
    });

    container.querySelector('#btn-join-reset-renames')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => {
        f.rename = f.field;
      });
      this.render(node);
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 10b. Join Multiple Tool (Alteryx Parity)
  // --------------------------------------------------------------------
  renderJoinMultipleConfig(container, node) {
    const cfg = node.config || {};
    if (!cfg.join_mode) cfg.join_mode = 'specific_fields';
    if (cfg.join_all_only === undefined) cfg.join_all_only = false;
    if (cfg.ignore_case === undefined) cfg.ignore_case = true;
    if (!cfg.join_keys) cfg.join_keys = [];
    if (!cfg.select_fields) cfg.select_fields = [];

    const upstreamInputs = this.getMultiUpstreamInputs(node.id);
    const numInputs = upstreamInputs.length;

    // Build metaMap for fast type icon retrieval
    const metaMap = {};
    upstreamInputs.forEach(u => {
      if (Array.isArray(u.columnMeta)) {
        u.columnMeta.forEach(m => {
          if (m && m.name) metaMap[`${u.index}_${m.name}`] = m.alteryx_type || m.type || 'unknown';
        });
      }
    });

    // Auto-initialize join_keys if empty and multiple inputs have columns
    if (cfg.join_keys.length === 0 && numInputs >= 2) {
      const allHaveCols = upstreamInputs.every(u => u.columns && u.columns.length > 0);
      if (allHaveCols) {
        // Try to find matching column across all inputs (case-insensitive)
        const commonMatches = [];
        upstreamInputs[0].columns.forEach(c1 => {
          const c1Low = c1.toLowerCase();
          const matchRow = { '1': c1 };
          let matchFoundAll = true;
          for (let uIdx = 1; uIdx < numInputs; uIdx++) {
            const otherCols = upstreamInputs[uIdx].columns;
            const otherColsLow = otherCols.map(c => c.toLowerCase());
            const foundIdx = otherColsLow.indexOf(c1Low);
            if (foundIdx !== -1) {
              matchRow[String(uIdx + 1)] = otherCols[foundIdx];
            } else {
              matchFoundAll = false;
              break;
            }
          }
          if (matchFoundAll) {
            commonMatches.push(matchRow);
          }
        });

        if (commonMatches.length > 0) {
          cfg.join_keys = commonMatches;
        } else {
          // Fallback to first column from each input
          const fallbackRow = {};
          upstreamInputs.forEach(u => {
            fallbackRow[String(u.index)] = u.columns[0] || '';
          });
          cfg.join_keys = [fallbackRow];
        }
      }
    }

    // Synchronize embedded select_fields
    const existingFieldMap = new Map();
    cfg.select_fields.forEach(sf => {
      if (sf && sf.field) existingFieldMap.set(sf.field, sf);
    });

    const hasAnyCols = upstreamInputs.some(u => u.columns && u.columns.length > 0);
    if (hasAnyCols) {
      const newSelectFields = [];
      const seenColNames = new Set();

      upstreamInputs.forEach(u => {
        (u.columns || []).forEach(c => {
          let outName = c;
          if (seenColNames.has(c)) {
            outName = `Input${u.index}_${c}`;
          }
          seenColNames.add(outName);

          if (existingFieldMap.has(outName)) {
            const prev = existingFieldMap.get(outName);
            newSelectFields.push({
              field: outName,
              source: u.index,
              original: c,
              selected: prev.selected !== false,
              rename: prev.rename !== undefined ? prev.rename : outName,
              type: prev.type || 'none'
            });
          } else {
            newSelectFields.push({
              field: outName,
              source: u.index,
              original: c,
              selected: true,
              rename: outName,
              type: 'none'
            });
          }
        });
      });

      // Preserve existing ordering if customized
      if (cfg.select_fields.length > 0) {
        const ordered = [];
        cfg.select_fields.forEach(prev => {
          const foundIdx = newSelectFields.findIndex(n => n.field === prev.field);
          if (foundIdx !== -1) {
            ordered.push(newSelectFields[foundIdx]);
            newSelectFields.splice(foundIdx, 1);
          }
        });
        cfg.select_fields = [...ordered, ...newSelectFields];
      } else {
        cfg.select_fields = newSelectFields;
      }
    }

    const getTypeIcon = (typeName) => {
      if (!typeName) return '';
      const t = typeName.toLowerCase();
      if (t.includes('int') || t.includes('double') || t.includes('float') || t.includes('num')) return '#';
      if (t.includes('date') || t.includes('time')) return '📅';
      if (t.includes('bool')) return '✓';
      return 'Aa';
    };

    const selectedCount = cfg.select_fields.filter(f => f.selected !== false).length;
    const totalCount = cfg.select_fields.length;

    container.innerHTML = `
      <!-- Connected Streams Overview -->
      <div class="join-section-title" style="margin-bottom: 6px;">
        <span>Connected Streams (${numInputs})</span>
      </div>

      <div class="multi-join-stream-chips">
        ${numInputs > 0
          ? upstreamInputs.map(u => {
              const colorIdx = ((u.index - 1) % 6) + 1;
              return `
                <div class="multi-join-stream-chip">
                  <span class="chip-dot stream-${colorIdx}"></span>
                  <span><b>#${u.index}</b>: ${this.escapeHtml(u.label)}</span>
                  <span style="color: var(--text-muted); font-size: 10px;">(${u.columns.length} cols)</span>
                </div>
              `;
            }).join('')
          : `<div style="font-size: 11px; color: var(--text-muted); padding: 4px 0;">No streams connected yet.</div>`
        }
      </div>

      ${numInputs < 2 ? `
        <div style="padding: 10px 12px; font-size: 11px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 6px; margin-bottom: 12px; color: var(--text-secondary); line-height: 1.4;">
          ℹ <b>Connect 2 or more datasets</b> to the input port (<b>I</b>) to join multiple data streams simultaneously.
        </div>
      ` : ''}

      <!-- Join Mode Selection -->
      <div class="form-group" style="margin-bottom: 12px;">
        <label style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-secondary); margin-bottom: 6px; display: block;">
          Join Mode
        </label>
        <div style="display: flex; gap: 14px;">
          <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; user-select: none; margin: 0;">
            <input type="radio" name="multi-join-mode" value="specific_fields" ${cfg.join_mode === 'specific_fields' ? 'checked' : ''}>
            <span>Join by Specific Fields</span>
          </label>
          <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; user-select: none; margin: 0;">
            <input type="radio" name="multi-join-mode" value="record_position" ${cfg.join_mode === 'record_position' ? 'checked' : ''}>
            <span>Join by Record Position</span>
          </label>
        </div>
      </div>

      <!-- Output Record Filtering (Alteryx parity: join_all_only) -->
      <div style="margin-bottom: 14px; padding: 8px 10px; background: var(--bg-surface-elevated); border: 1px solid var(--border-subtle); border-radius: 6px;">
        <label style="display: flex; align-items: flex-start; gap: 8px; font-size: 11.5px; cursor: pointer; user-select: none; margin: 0; font-weight: 500;">
          <input type="checkbox" id="cfg-multi-join-all-only" ${cfg.join_all_only ? 'checked' : ''} style="margin-top: 2px;">
          <div>
            <div>Only output records that join from all inputs</div>
            <div style="font-size: 10.5px; color: var(--text-muted); font-weight: normal; margin-top: 2px;">
              When checked: Inner join across all inputs (matches in all streams).<br>
              When unchecked (default): Full outer join preserving all records with null padding.
            </div>
          </div>
        </label>
      </div>

      ${cfg.join_mode === 'specific_fields' ? `
        <!-- Join Keys Section -->
        <div class="join-section-title">
          <span>Join Keys</span>
          <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">
            ${cfg.join_keys.length} key row${cfg.join_keys.length !== 1 ? 's' : ''}
          </span>
        </div>

        <div class="join-keys-container" style="margin-bottom: 14px;">
          <div id="cfg-multi-join-keys-list" style="display: flex; flex-direction: column; gap: 8px;">
            ${cfg.join_keys.map((k, pairIdx) => `
              <div class="multi-join-key-row" data-pair-idx="${pairIdx}" style="display: flex; align-items: center; gap: 6px; background: var(--bg-surface-elevated); padding: 6px 8px; border-radius: 6px; border: 1px solid var(--border-subtle); overflow-x: auto;">
                ${upstreamInputs.map((u, inIdx) => {
                  const currentVal = (typeof k === 'object' && k !== null) ? (k[String(u.index)] || '') : '';
                  const colorIdx = ((u.index - 1) % 6) + 1;
                  return `
                    <div style="flex: 1; min-width: 130px;">
                      <div style="display: flex; align-items: center; gap: 4px; margin-bottom: 3px;">
                        <span class="chip-dot stream-${colorIdx}"></span>
                        <span style="font-size: 10px; font-weight: 600; color: var(--text-secondary);">#${u.index}</span>
                      </div>
                      <select class="form-control multi-join-key-select" data-pair-idx="${pairIdx}" data-in-idx="${u.index}" style="width: 100%; font-size: 11px; padding: 3px 6px;">
                        <option value="" ${!currentVal ? 'selected' : ''}>-- Select Field --</option>
                        ${u.columns.length > 0
                          ? u.columns.map(c => `
                              <option value="${this.escapeHtml(c)}" ${currentVal === c ? 'selected' : ''}>
                                ${getTypeIcon(metaMap[`${u.index}_${c}`])} ${this.escapeHtml(c)}
                              </option>
                            `).join('')
                          : `<option value="${this.escapeHtml(currentVal)}" selected>${this.escapeHtml(currentVal || `Field #${u.index}`)}</option>`
                        }
                      </select>
                    </div>
                    ${inIdx < upstreamInputs.length - 1 ? `<span style="font-weight: 700; color: var(--text-muted); font-size: 12px; margin-top: 14px;">=</span>` : ''}
                  `;
                }).join('')}

                <button class="btn-icon btn-remove-multi-key" data-pair-idx="${pairIdx}" title="Remove Key Row" style="color: var(--color-error); padding: 4px; margin-top: 14px; margin-left: 4px;">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
              </div>
            `).join('')}
          </div>

          <div style="display: flex; gap: 8px; margin-top: 10px; align-items: center; justify-content: space-between; flex-wrap: wrap;">
            <div style="display: flex; gap: 6px;">
              <button id="btn-add-multi-key" class="btn btn-secondary btn-sm" style="font-size: 11px; padding: 4px 8px;">
                + Add Key Pair
              </button>
              <button id="btn-automatch-multi-keys" class="btn btn-secondary btn-sm" title="Pair columns with identical names across all inputs" style="font-size: 11px; padding: 4px 8px;">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 3px;"><polyline points="20 6 9 17 4 12"></polyline></svg>
                Auto-Match Keys
              </button>
            </div>

            <label style="display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary); cursor: pointer; user-select: none; margin: 0;">
              <input type="checkbox" id="cfg-multi-join-ignore-case" ${cfg.ignore_case ? 'checked' : ''}>
              <span>Ignore Case & Trim</span>
            </label>
          </div>
        </div>
      ` : `
        <!-- Record Position Info Callout -->
        <div style="padding: 10px 12px; font-size: 11px; background: rgba(56, 189, 248, 0.06); border: 1px dashed rgba(56, 189, 248, 0.3); border-radius: 6px; margin-bottom: 14px; color: var(--text-secondary); line-height: 1.4;">
          📄 <b>Record Position Join Active</b>: Rows are paired strictly by index (row 1 to row 1, row 2 to row 2). No join keys are required.
        </div>
      `}

      <!-- Embedded Select Tool Grid (Alteryx Parity) -->
      <div class="join-section-title" style="margin-top: 14px;">
        <span>Joined (J) Output Columns</span>
        <span style="font-size: 10px; font-weight: 500; color: var(--text-muted);">
          ${selectedCount} of ${totalCount} selected
        </span>
      </div>

      <div class="join-toolbar">
        <button id="btn-multi-join-select-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 7px;">Select All</button>
        <button id="btn-multi-join-deselect-all" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 2px 7px;">Deselect All</button>
        <button id="btn-multi-join-deselect-dup-keys" class="btn btn-secondary btn-sm" title="Uncheck duplicate join keys from later inputs" style="font-size: 10px; padding: 2px 7px;">Deselect Duplicate Keys</button>
        <button id="btn-multi-join-reset-renames" class="btn btn-secondary btn-sm" title="Reset all custom column names" style="font-size: 10px; padding: 2px 7px;">Reset Names</button>
      </div>

      <div class="join-select-wrap">
        <table class="join-select-table">
          <thead>
            <tr>
              <th style="width: 32px; text-align: center;">Keep</th>
              <th style="width: 54px; text-align: center;">Order</th>
              <th style="width: 36px; text-align: center;">Src</th>
              <th>Field</th>
              <th>Rename</th>
              <th style="width: 110px;">Type Cast</th>
            </tr>
          </thead>
          <tbody id="cfg-multi-join-select-tbody">
            ${cfg.select_fields.map((sf, i) => {
              const srcIdx = sf.source || 1;
              const colorIdx = ((srcIdx - 1) % 6) + 1;
              const metaKey = `${srcIdx}_${sf.original || sf.field}`;
              const typeDesc = metaMap[metaKey];
              return `
                <tr data-sf-idx="${i}">
                  <td style="text-align: center;">
                    <input type="checkbox" class="sf-keep" ${sf.selected !== false ? 'checked' : ''}>
                  </td>
                  <td style="text-align: center; white-space: nowrap;">
                    <span class="drag-grip" title="Click and drag to reorder">⋮⋮</span>
                    <button class="join-reorder-btn sf-move-up" data-idx="${i}" title="Move Up" ${i === 0 ? 'disabled' : ''}>▲</button>
                    <button class="join-reorder-btn sf-move-down" data-idx="${i}" title="Move Down" ${i === cfg.select_fields.length - 1 ? 'disabled' : ''}>▼</button>
                  </td>
                  <td style="text-align: center;">
                    <span class="join-source-pill source-input-${colorIdx}">#${srcIdx}</span>
                  </td>
                  <td style="font-weight: 500; word-break: break-word;">
                    ${this.escapeHtml(sf.field)}
                    ${typeDesc ? `<span style="font-size: 9px; color: var(--text-muted); margin-left: 3px;">(${typeDesc})</span>` : ''}
                  </td>
                  <td>
                    <input type="text" class="form-control sf-rename" style="padding: 2px 6px; font-size: 11px; width: 100%;" value="${this.escapeHtml(sf.rename || sf.field)}">
                  </td>
                  <td>
                    <select class="form-control sf-type" style="padding: 2px 4px; font-size: 11px; width: 100%;">
                      <option value="none" ${(!sf.type || sf.type === 'none') ? 'selected' : ''}>Current</option>
                      <option value="string" ${sf.type === 'string' ? 'selected' : ''}>String</option>
                      <option value="int64" ${sf.type === 'int64' ? 'selected' : ''}>Int64</option>
                      <option value="int32" ${sf.type === 'int32' ? 'selected' : ''}>Int32</option>
                      <option value="double" ${sf.type === 'double' || sf.type === 'float' ? 'selected' : ''}>Double</option>
                      <option value="date" ${sf.type === 'date' ? 'selected' : ''}>Date</option>
                      <option value="datetime" ${sf.type === 'datetime' ? 'selected' : ''}>DateTime</option>
                      <option value="bool" ${sf.type === 'bool' ? 'selected' : ''}>Bool</option>
                    </select>
                  </td>
                </tr>
              `;
            }).join('')}
          </tbody>
        </table>
      </div>

      ${cfg.select_fields.length === 0 ? `
        <div style="padding: 10px; font-size: 11px; color: var(--text-muted); text-align: center; border: 1px dashed var(--border-subtle); border-radius: 6px; margin-top: 6px;">
          Connect 2 or more datasets to populate and customize joined columns.
        </div>
      ` : ''}

      <!-- Output Stream Partition Legend -->
      <div class="join-stream-legend">
        <div style="font-weight: 700; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 2px;">
          Output Stream
        </div>
        <div class="join-stream-item">
          <span class="join-port-tag port-j">J</span>
          <div><b>Joined</b>: Multi-way merged records across all connected inputs, customized by the select table above.</div>
        </div>
      </div>
    `;

    // Event Bindings: Join Mode
    container.querySelectorAll('input[name="multi-join-mode"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        node.config.join_mode = e.target.value;
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    });

    // Event Binding: Output Option (join_all_only)
    container.querySelector('#cfg-multi-join-all-only')?.addEventListener('change', (e) => {
      node.config.join_all_only = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    // Event Binding: Ignore Case
    container.querySelector('#cfg-multi-join-ignore-case')?.addEventListener('change', (e) => {
      node.config.ignore_case = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    // Event Bindings: Join Keys
    container.querySelectorAll('.multi-join-key-select').forEach(sel => {
      sel.addEventListener('change', (e) => {
        const pairIdx = parseInt(e.target.dataset.pairIdx);
        const inIdx = e.target.dataset.inIdx;
        if (!node.config.join_keys[pairIdx]) node.config.join_keys[pairIdx] = {};
        node.config.join_keys[pairIdx][String(inIdx)] = e.target.value;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelectorAll('.btn-remove-multi-key').forEach(btn => {
      btn.addEventListener('click', (e) => {
        const pairIdx = parseInt(btn.dataset.pairIdx);
        node.config.join_keys.splice(pairIdx, 1);
        this.render(node);
        this.canvas.onWorkflowChange();
      });
    });

    // Add Key Pair Button
    container.querySelector('#btn-add-multi-key')?.addEventListener('click', () => {
      if (!node.config.join_keys) node.config.join_keys = [];
      const newKey = {};
      upstreamInputs.forEach(u => {
        newKey[String(u.index)] = (u.columns && u.columns[0]) ? u.columns[0] : '';
      });
      node.config.join_keys.push(newKey);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    // Auto-Match Keys Button
    container.querySelector('#btn-automatch-multi-keys')?.addEventListener('click', () => {
      if (numInputs < 2) {
        if (window.showToast) window.showToast('info', 'Auto-Match Keys', 'Connect 2 or more inputs to auto-match columns.');
        return;
      }
      const allHaveCols = upstreamInputs.every(u => u.columns && u.columns.length > 0);
      if (!allHaveCols) {
        if (window.showToast) window.showToast('warning', 'Auto-Match Keys', 'Upstream inputs have not been executed yet. Run workflow to discover columns.');
        return;
      }

      const matches = [];
      const firstCols = upstreamInputs[0].columns;
      firstCols.forEach(c1 => {
        const c1Low = c1.toLowerCase();
        const matchRow = { '1': c1 };
        let allMatch = true;

        for (let uIdx = 1; uIdx < numInputs; uIdx++) {
          const uCols = upstreamInputs[uIdx].columns;
          const found = uCols.find(uc => uc.toLowerCase() === c1Low);
          if (found) {
            matchRow[String(uIdx + 1)] = found;
          } else {
            allMatch = false;
            break;
          }
        }

        if (allMatch) {
          matches.push(matchRow);
        }
      });

      if (matches.length > 0) {
        node.config.join_keys = matches;
        this.render(node);
        this.canvas.onWorkflowChange();
        if (window.showToast) window.showToast('success', 'Auto-Match Keys', `Matched ${matches.length} key row(s) across all ${numInputs} inputs!`);
      } else {
        if (window.showToast) window.showToast('warning', 'Auto-Match Keys', 'No matching column names found across all connected inputs.');
      }
    });

    // Event Bindings: Embedded Select Grid
    container.querySelectorAll('[data-sf-idx]').forEach(tr => {
      const idx = parseInt(tr.dataset.sfIdx);
      tr.querySelector('.sf-keep')?.addEventListener('change', (e) => {
        node.config.select_fields[idx].selected = e.target.checked;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-rename')?.addEventListener('input', (e) => {
        node.config.select_fields[idx].rename = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-type')?.addEventListener('change', (e) => {
        node.config.select_fields[idx].type = e.target.value;
        this.canvas.onWorkflowChange();
      });
      tr.querySelector('.sf-move-up')?.addEventListener('click', () => {
        if (idx > 0) {
          const item = node.config.select_fields.splice(idx, 1)[0];
          node.config.select_fields.splice(idx - 1, 0, item);
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
      tr.querySelector('.sf-move-down')?.addEventListener('click', () => {
        if (idx < node.config.select_fields.length - 1) {
          const item = node.config.select_fields.splice(idx, 1)[0];
          node.config.select_fields.splice(idx + 1, 0, item);
          this.render(node);
          this.canvas.onWorkflowChange();
        }
      });
    });

    const multiTbody = container.querySelector('#cfg-multi-join-select-tbody');
    this.setupTableDragAndDrop(multiTbody, node.config.select_fields, (newFields) => {
      node.config.select_fields = newFields;
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    // Select Toolbar Actions
    container.querySelector('#btn-multi-join-select-all')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => f.selected = true);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-multi-join-deselect-all')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => f.selected = false);
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-multi-join-deselect-dup-keys')?.addEventListener('click', () => {
      const keyNamesToDeselect = new Set();
      (node.config.join_keys || []).forEach(k => {
        if (typeof k === 'object' && k !== null) {
          for (let inIdx = 2; inIdx <= numInputs; inIdx++) {
            const keyCol = k[String(inIdx)];
            if (keyCol) {
              keyNamesToDeselect.add(keyCol);
              keyNamesToDeselect.add(`Input${inIdx}_${keyCol}`);
            }
          }
        }
      });

      let deselectedCount = 0;
      node.config.select_fields.forEach(f => {
        if (f.source && f.source > 1) {
          if (keyNamesToDeselect.has(f.field) || keyNamesToDeselect.has(f.original)) {
            f.selected = false;
            deselectedCount++;
          }
        }
      });
      this.render(node);
      this.canvas.onWorkflowChange();
      if (window.showToast) window.showToast('info', 'Join Multiple Grid', `Deselected ${deselectedCount} duplicate key column(s) from later inputs.`);
    });

    container.querySelector('#btn-multi-join-reset-renames')?.addEventListener('click', () => {
      node.config.select_fields.forEach(f => {
        f.rename = f.field;
      });
      this.render(node);
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 11. Union Tool
  // --------------------------------------------------------------------
  renderUnionConfig(container, node) {
    const cfg = node.config || {};
    container.innerHTML = `
      <div class="form-group">
        <label>Union Mode</label>
        <select class="form-control" id="cfg-union-mode">
          <option value="by_name" ${cfg.mode === 'by_name' ? 'selected' : ''}>Auto Config by Tag / Column Name</option>
          <option value="by_position" ${cfg.mode === 'by_position' ? 'selected' : ''}>Auto Config by Column Position</option>
        </select>
      </div>

      <div class="form-group">
        <label>When Fields Differ</label>
        <select class="form-control" id="cfg-union-nonmatching">
          <option value="all" ${(!cfg.non_matching || cfg.non_matching === 'all') ? 'selected' : ''}>Output all fields (Allow subsets with nulls)</option>
          <option value="common_only" ${cfg.non_matching === 'common_only' ? 'selected' : ''}>Output only common fields (Intersect)</option>
          <option value="error" ${cfg.non_matching === 'error' ? 'selected' : ''}>Error - Halt processing if fields differ</option>
        </select>
        <div class="form-hint" style="margin-top: 8px;">Connect 2 or more tools into the input port to stack records vertically.</div>
      </div>
    `;

    container.querySelector('#cfg-union-mode').addEventListener('change', (e) => {
      node.config.mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-union-nonmatching').addEventListener('change', (e) => {
      node.config.non_matching = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 12. Text Input Tool
  // --------------------------------------------------------------------
  renderTextInputConfig(container, node) {
    const cfg = node.config || {};
    let columns = cfg.columns || ['Field_1', 'Field_2'];
    let data = cfg.data || [['Sample 1', '100'], ['Sample 2', '200']];
    let mode = cfg.entry_mode || 'grid'; // 'grid' or 'paste'

    node.config.columns = columns;
    node.config.data = data;
    node.config.entry_mode = mode;

    container.innerHTML = `
      <div class="form-group">
        <label>Input Mode</label>
        <div class="form-row">
          <label class="form-check">
            <input type="radio" name="cfg-ti-mode" value="grid" ${mode === 'grid' ? 'checked' : ''}>
            <span>Spreadsheet Grid</span>
          </label>
          <label class="form-check" style="margin-left: 14px;">
            <input type="radio" name="cfg-ti-mode" value="paste" ${mode === 'paste' ? 'checked' : ''}>
            <span>Paste TSV / CSV</span>
          </label>
        </div>
      </div>

      <div id="cfg-ti-grid-box" style="${mode === 'grid' ? '' : 'display: none;'}">
        <div class="cfg-toolbar">
          <button id="btn-ti-add-col" class="btn btn-secondary btn-sm">+ Column</button>
          <button id="btn-ti-add-row" class="btn btn-secondary btn-sm">+ Row</button>
          <button id="btn-ti-clear" class="btn btn-secondary btn-sm" style="color: var(--color-error);">Clear</button>
        </div>

        <div style="max-height: 280px; overflow: auto; border: 1px solid var(--border-subtle); border-radius: 4px;">
          <table class="text-input-grid" id="cfg-ti-table">
            <thead>
              <tr>
                ${columns.map((col, cIdx) => `
                  <th>
                    <input type="text" class="ti-col-header" data-cidx="${cIdx}" value="${col}">
                  </th>
                `).join('')}
              </tr>
            </thead>
            <tbody>
              ${data.map((row, rIdx) => `
                <tr>
                  ${columns.map((_, cIdx) => `
                    <td>
                      <input type="text" class="ti-cell" data-ridx="${rIdx}" data-cidx="${cIdx}" value="${row[cIdx] !== undefined ? row[cIdx] : ''}">
                    </td>
                  `).join('')}
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>

      <div id="cfg-ti-paste-box" style="${mode === 'paste' ? '' : 'display: none;'}">
        <div class="form-group">
          <label>Delimiter</label>
          <select class="form-control" id="cfg-ti-delimiter">
            <option value="\\t" ${cfg.delimiter === '\\t' ? 'selected' : ''}>Tab (Excel Copy-Paste)</option>
            <option value="," ${cfg.delimiter === ',' ? 'selected' : ''}>Comma (,)</option>
            <option value=";" ${cfg.delimiter === ';' ? 'selected' : ''}>Semicolon (;)</option>
            <option value="|" ${cfg.delimiter === '|' ? 'selected' : ''}>Pipe (|)</option>
          </select>
        </div>
        <div class="form-group">
          <label>Raw Text (Paste directly from Excel or CSV)</label>
          <textarea class="form-control" id="cfg-ti-raw" rows="8" placeholder="Paste data here...">${cfg.raw_text || ''}</textarea>
        </div>
      </div>
    `;

    container.querySelectorAll('input[name="cfg-ti-mode"]').forEach(r => {
      r.addEventListener('change', (e) => {
        node.config.entry_mode = e.target.value;
        container.querySelector('#cfg-ti-grid-box').style.display = e.target.value === 'grid' ? '' : 'none';
        container.querySelector('#cfg-ti-paste-box').style.display = e.target.value === 'paste' ? '' : 'none';
        this.canvas.onWorkflowChange();
      });
    });

    const bindGridEvents = () => {
      container.querySelectorAll('.ti-col-header').forEach(inp => {
        inp.addEventListener('input', (e) => {
          const cIdx = parseInt(e.target.dataset.cidx);
          columns[cIdx] = e.target.value;
          this.canvas.onWorkflowChange();
        });
      });
      container.querySelectorAll('.ti-cell').forEach(inp => {
        inp.addEventListener('input', (e) => {
          const rIdx = parseInt(e.target.dataset.ridx);
          const cIdx = parseInt(e.target.dataset.cidx);
          if (!data[rIdx]) data[rIdx] = [];
          data[rIdx][cIdx] = e.target.value;
          this.canvas.onWorkflowChange();
        });
      });
    };
    bindGridEvents();

    container.querySelector('#btn-ti-add-col')?.addEventListener('click', () => {
      columns.push(`Field_${columns.length + 1}`);
      data.forEach(r => r.push(''));
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-ti-add-row')?.addEventListener('click', () => {
      data.push(new Array(columns.length).fill(''));
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#btn-ti-clear')?.addEventListener('click', () => {
      columns = ['Field_1'];
      data = [['']];
      node.config.columns = columns;
      node.config.data = data;
      this.render(node);
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ti-raw')?.addEventListener('input', (e) => {
      node.config.raw_text = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ti-delimiter')?.addEventListener('change', (e) => {
      node.config.delimiter = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 13. Sample Tool
  // --------------------------------------------------------------------
  renderSampleConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const sampleType = cfg.sample_type || 'first_n';
    const nRecords = cfg.n_records !== undefined ? cfg.n_records : 100;
    const percent = cfg.percent !== undefined ? cfg.percent : 10;
    const groupBy = cfg.group_by || [];

    container.innerHTML = `
      <div class="form-group">
        <label>Sample Type</label>
        <select class="form-control" id="cfg-sample-type">
          <option value="first_n" ${sampleType === 'first_n' ? 'selected' : ''}>First N records</option>
          <option value="last_n" ${sampleType === 'last_n' ? 'selected' : ''}>Last N records</option>
          <option value="skip_first_n" ${sampleType === 'skip_first_n' ? 'selected' : ''}>Skip First N records</option>
          <option value="sample_1_in_n" ${sampleType === 'sample_1_in_n' ? 'selected' : ''}>1 of every N records</option>
          <option value="random_1_in_n" ${sampleType === 'random_1_in_n' ? 'selected' : ''}>1 in N random chance</option>
          <option value="first_n_percent" ${sampleType === 'first_n_percent' ? 'selected' : ''}>First N% of records</option>
        </select>
      </div>

      <div class="form-group" id="cfg-sample-n-grp" style="${sampleType === 'first_n_percent' ? 'display:none;' : ''}">
        <label>N Records</label>
        <input type="number" class="form-control" id="cfg-sample-n" min="1" value="${nRecords}">
      </div>

      <div class="form-group" id="cfg-sample-pct-grp" style="${sampleType === 'first_n_percent' ? '' : 'display:none;'}">
        <label>Percent of Records (%)</label>
        <input type="number" class="form-control" id="cfg-sample-pct" min="0.1" max="100" step="0.5" value="${percent}">
      </div>

      <div class="cfg-section-title">Group By (Optional)</div>
      <div style="max-height: 180px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 8px; background: var(--bg-main);">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 6px;">
            <input type="checkbox" class="sample-grp-chk" value="${col}" ${groupBy.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>
      <div class="form-hint" style="margin-top: 6px;">If Group By columns are selected, sampling applies independently to each group.</div>
    `;

    container.querySelector('#cfg-sample-type').addEventListener('change', (e) => {
      node.config.sample_type = e.target.value;
      container.querySelector('#cfg-sample-n-grp').style.display = e.target.value === 'first_n_percent' ? 'none' : '';
      container.querySelector('#cfg-sample-pct-grp').style.display = e.target.value === 'first_n_percent' ? '' : 'none';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-sample-n').addEventListener('input', (e) => {
      node.config.n_records = parseInt(e.target.value) || 100;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-sample-pct').addEventListener('input', (e) => {
      node.config.percent = parseFloat(e.target.value) || 10.0;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.sample-grp-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.sample-grp-chk:checked')).map(c => c.value);
        node.config.group_by = checked;
        this.canvas.onWorkflowChange();
      });
    });
  }

  // --------------------------------------------------------------------
  // 14. Record ID Tool
  // --------------------------------------------------------------------
  renderRecordIDConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const colName = cfg.column_name || 'RecordID';
    const startVal = cfg.start_value !== undefined ? cfg.start_value : 1;
    const position = cfg.position || 'first';
    const groupBy = cfg.group_by || [];

    container.innerHTML = `
      <div class="form-group">
        <label>Record ID Column Name</label>
        <input type="text" class="form-control" id="cfg-recid-name" value="${colName}" placeholder="e.g. RecordID">
      </div>

      <div class="form-group">
        <label>Starting Value</label>
        <input type="number" class="form-control" id="cfg-recid-start" value="${startVal}">
      </div>

      <div class="form-group">
        <label>Position</label>
        <select class="form-control" id="cfg-recid-pos">
          <option value="first" ${position === 'first' ? 'selected' : ''}>First Column</option>
          <option value="last" ${position === 'last' ? 'selected' : ''}>Last Column</option>
        </select>
      </div>

      <div class="cfg-section-title">Group By (Optional)</div>
      <div style="max-height: 180px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 8px; background: var(--bg-main);">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 6px;">
            <input type="checkbox" class="recid-grp-chk" value="${col}" ${groupBy.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>
      <div class="form-hint" style="margin-top: 6px;">If Group By columns are selected, Record ID restarts from the starting value for each distinct group.</div>
    `;

    container.querySelector('#cfg-recid-name').addEventListener('input', (e) => {
      node.config.column_name = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-recid-start').addEventListener('input', (e) => {
      node.config.start_value = parseInt(e.target.value) || 1;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-recid-pos').addEventListener('change', (e) => {
      node.config.position = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.recid-grp-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.recid-grp-chk:checked')).map(c => c.value);
        node.config.group_by = checked;
        this.canvas.onWorkflowChange();
      });
    });
  }

  // --------------------------------------------------------------------
  // 15. Find Replace Tool
  // --------------------------------------------------------------------
  renderFindReplaceConfig(container, node) {
    const cfg = node.config || {};
    const fCols = this.getUpstreamColumns(node.id, 'F');
    const rCols = this.getUpstreamColumns(node.id, 'R');

    const searchMode = cfg.search_mode || 'entire_field';
    const action = cfg.action || 'replace';
    const appendFields = cfg.append_fields || [];

    container.innerHTML = `
      <div class="cfg-section-title">Find</div>
      <div class="cfg-card">
        <div class="form-group">
          <label>Find in Field (From 'F' Input)</label>
          <select class="form-control" id="cfg-fr-find-field">
            ${fCols.length > 0 
              ? fCols.map(c => `<option value="${c}" ${cfg.find_field === c ? 'selected' : ''}>${c}</option>`).join('')
              : `<option value="${cfg.find_field || ''}">${cfg.find_field || 'Select field'}</option>`}
          </select>
        </div>

        <div class="form-group">
          <label>Find Value (From 'R' Input)</label>
          <select class="form-control" id="cfg-fr-find-val">
            ${rCols.length > 0 
              ? rCols.map(c => `<option value="${c}" ${cfg.find_value_field === c ? 'selected' : ''}>${c}</option>`).join('')
              : `<option value="${cfg.find_value_field || ''}">${cfg.find_value_field || 'Select field'}</option>`}
          </select>
        </div>

        <div class="form-group">
          <label>Search Mode</label>
          <select class="form-control" id="cfg-fr-mode">
            <option value="entire_field" ${searchMode === 'entire_field' ? 'selected' : ''}>Match Entire Field</option>
            <option value="any_part" ${searchMode === 'any_part' ? 'selected' : ''}>Match Any Part of Field</option>
            <option value="beginning" ${searchMode === 'beginning' ? 'selected' : ''}>Match Beginning of Field</option>
          </select>
        </div>

        <div class="form-group" style="margin-bottom: 0;">
          <label class="form-check" style="margin-bottom: 6px;">
            <input type="checkbox" id="cfg-fr-case" ${cfg.case_sensitive ? 'checked' : ''}>
            <span>Case Sensitive Search</span>
          </label>
          <label class="form-check">
            <input type="checkbox" id="cfg-fr-whole" ${cfg.whole_word ? 'checked' : ''}>
            <span>Match Whole Word Only</span>
          </label>
        </div>
      </div>

      <div class="cfg-section-title">Action</div>
      <div class="cfg-card">
        <div class="form-group">
          <div class="form-row">
            <label class="form-check">
              <input type="radio" name="cfg-fr-act" value="replace" ${action === 'replace' ? 'checked' : ''}>
              <span>Replace Text</span>
            </label>
            <label class="form-check" style="margin-left: 14px;">
              <input type="radio" name="cfg-fr-act" value="append" ${action === 'append' ? 'checked' : ''}>
              <span>Append Field(s)</span>
            </label>
          </div>
        </div>

        <div id="cfg-fr-replace-box" style="${action === 'replace' ? '' : 'display: none;'}">
          <div class="form-group" style="margin-bottom: 0;">
            <label>Replace With Field (From 'R' Input)</label>
            <select class="form-control" id="cfg-fr-rep-field">
              ${rCols.length > 0 
                ? rCols.map(c => `<option value="${c}" ${cfg.replace_with_field === c ? 'selected' : ''}>${c}</option>`).join('')
                : `<option value="${cfg.replace_with_field || ''}">${cfg.replace_with_field || 'Select field'}</option>`}
            </select>
          </div>
        </div>

        <div id="cfg-fr-append-box" style="${action === 'append' ? '' : 'display: none;'}">
          <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; display: block;">
            Select Fields to Append (From 'R' Input):
          </label>
          <div style="max-height: 150px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 4px; padding: 6px; background: var(--bg-surface);">
            ${rCols.length > 0 ? rCols.map(col => `
              <label class="form-check" style="margin-bottom: 4px;">
                <input type="checkbox" class="fr-append-chk" value="${col}" ${appendFields.includes(col) ? 'checked' : ''}>
                <span>${col}</span>
              </label>
            `).join('') : '<span class="form-hint">Connect Replace (R) input to see columns.</span>'}
          </div>
        </div>
      </div>
    `;

    container.querySelector('#cfg-fr-find-field').addEventListener('change', (e) => {
      node.config.find_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-fr-find-val').addEventListener('change', (e) => {
      node.config.find_value_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-fr-mode').addEventListener('change', (e) => {
      node.config.search_mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-fr-case').addEventListener('change', (e) => {
      node.config.case_sensitive = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-fr-whole').addEventListener('change', (e) => {
      node.config.whole_word = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('input[name="cfg-fr-act"]').forEach(r => {
      r.addEventListener('change', (e) => {
        node.config.action = e.target.value;
        container.querySelector('#cfg-fr-replace-box').style.display = e.target.value === 'replace' ? '' : 'none';
        container.querySelector('#cfg-fr-append-box').style.display = e.target.value === 'append' ? '' : 'none';
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#cfg-fr-rep-field')?.addEventListener('change', (e) => {
      node.config.replace_with_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.fr-append-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.fr-append-chk:checked')).map(c => c.value);
        node.config.append_fields = checked;
        this.canvas.onWorkflowChange();
      });
    });
  }

  // --------------------------------------------------------------------
  // 16. Transpose Tool
  // --------------------------------------------------------------------
  renderTransposeConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const keyCols = cfg.key_columns || [];
    const dataCols = cfg.data_columns || [];
    const nameCol = cfg.name_column || 'Name';
    const valueCol = cfg.value_column || 'Value';

    container.innerHTML = `
      <div class="cfg-section-title">Key Columns (Identifiers to Keep)</div>
      <div style="max-height: 150px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px; background: var(--bg-main); margin-bottom: 12px;">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 4px;">
            <input type="checkbox" class="transpose-key-chk" value="${col}" ${keyCols.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>

      <div class="cfg-section-title">Data Columns (Pivot Into Rows)</div>
      <div style="max-height: 150px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px; background: var(--bg-main); margin-bottom: 12px;">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 4px;">
            <input type="checkbox" class="transpose-data-chk" value="${col}" ${dataCols.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>

      <div class="form-row">
        <div class="form-group" style="flex: 1;">
          <label>Name Column Header</label>
          <input type="text" class="form-control" id="cfg-trans-name" value="${nameCol}">
        </div>
        <div class="form-group" style="flex: 1;">
          <label>Value Column Header</label>
          <input type="text" class="form-control" id="cfg-trans-val" value="${valueCol}">
        </div>
      </div>
    `;

    container.querySelectorAll('.transpose-key-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.transpose-key-chk:checked')).map(c => c.value);
        node.config.key_columns = checked;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelectorAll('.transpose-data-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.transpose-data-chk:checked')).map(c => c.value);
        node.config.data_columns = checked;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#cfg-trans-name').addEventListener('input', (e) => {
      node.config.name_column = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-trans-val').addEventListener('input', (e) => {
      node.config.value_column = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 17. Cross Tab Tool
  // --------------------------------------------------------------------
  renderCrossTabConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const groupBy = cfg.group_by || [];
    const headerField = cfg.header_field || (upstreamCols[1] || '');
    const valueField = cfg.value_field || (upstreamCols[2] || '');
    const aggFunc = cfg.agg_func || 'sum';
    const separator = cfg.separator || ', ';

    container.innerHTML = `
      <div class="cfg-section-title">1. Group By (Row Identifiers)</div>
      <div style="max-height: 140px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px; background: var(--bg-main); margin-bottom: 10px;">
        ${upstreamCols.length > 0 ? upstreamCols.map(col => `
          <label class="form-check" style="margin-bottom: 4px;">
            <input type="checkbox" class="crosstab-grp-chk" value="${col}" ${groupBy.includes(col) ? 'checked' : ''}>
            <span>${col}</span>
          </label>
        `).join('') : '<span class="form-hint">Connect input to see column list.</span>'}
      </div>

      <div class="form-group">
        <label>2. Change Column Headers (Unique values become headers)</label>
        <select class="form-control" id="cfg-ct-header">
          ${upstreamCols.length > 0 
            ? upstreamCols.map(c => `<option value="${c}" ${headerField === c ? 'selected' : ''}>${c}</option>`).join('')
            : `<option value="${headerField}">${headerField || 'Select header column'}</option>`}
        </select>
      </div>

      <div class="form-group">
        <label>3. Values for New Columns (Data to aggregate)</label>
        <select class="form-control" id="cfg-ct-val">
          ${upstreamCols.length > 0 
            ? upstreamCols.map(c => `<option value="${c}" ${valueField === c ? 'selected' : ''}>${c}</option>`).join('')
            : `<option value="${valueField}">${valueField || 'Select value column'}</option>`}
        </select>
      </div>

      <div class="form-group">
        <label>4. Method for Aggregating Values</label>
        <select class="form-control" id="cfg-ct-agg">
          <option value="sum" ${aggFunc === 'sum' ? 'selected' : ''}>Sum</option>
          <option value="mean" ${aggFunc === 'mean' ? 'selected' : ''}>Average / Mean</option>
          <option value="count" ${aggFunc === 'count' ? 'selected' : ''}>Count</option>
          <option value="first" ${aggFunc === 'first' ? 'selected' : ''}>First</option>
          <option value="last" ${aggFunc === 'last' ? 'selected' : ''}>Last</option>
          <option value="concat" ${aggFunc === 'concat' ? 'selected' : ''}>Concatenate Strings</option>
        </select>
      </div>

      <div class="form-group" id="cfg-ct-sep-grp" style="${aggFunc === 'concat' ? '' : 'display:none;'}">
        <label>Separator for Concatenation</label>
        <input type="text" class="form-control" id="cfg-ct-sep" value="${separator}">
      </div>
    `;

    container.querySelectorAll('.crosstab-grp-chk').forEach(chk => {
      chk.addEventListener('change', () => {
        const checked = Array.from(container.querySelectorAll('.crosstab-grp-chk:checked')).map(c => c.value);
        node.config.group_by = checked;
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#cfg-ct-header').addEventListener('change', (e) => {
      node.config.header_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ct-val').addEventListener('change', (e) => {
      node.config.value_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ct-agg').addEventListener('change', (e) => {
      node.config.agg_func = e.target.value;
      container.querySelector('#cfg-ct-sep-grp').style.display = e.target.value === 'concat' ? '' : 'none';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ct-sep').addEventListener('input', (e) => {
      node.config.separator = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  renderTextToColumnsConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const column = cfg.column || (upstreamCols[0] || '');
    const delimiters = cfg.delimiters !== undefined ? cfg.delimiters : ',';
    const splitType = cfg.split_type || 'columns';
    const numColumns = cfg.num_columns || 2;
    const rootName = cfg.root_name || '';
    const extraCharacters = cfg.extra_characters || 'last';
    const ignoreQuotes = cfg.ignore_quotes !== false;
    const ignoreSingleQuotes = !!cfg.ignore_single_quotes;
    const ignoreParentheses = !!cfg.ignore_parentheses;
    const ignoreBrackets = !!cfg.ignore_brackets;
    const skipEmpty = !!cfg.skip_empty;

    container.innerHTML = `
      <div class="form-group">
        <label>1. Select Column to Split</label>
        <select class="form-control" id="cfg-ttc-col">
          ${upstreamCols.length > 0
            ? upstreamCols.map(c => `<option value="${c}" ${column === c ? 'selected' : ''}>${c}</option>`).join('')
            : `<option value="${column}">${column || 'Select column'}</option>`}
        </select>
      </div>

      <div class="form-group">
        <label>2. Delimiters</label>
        <input type="text" class="form-control" id="cfg-ttc-delims" value="${delimiters}" placeholder="e.g. , or \\t or \\s">
        <div class="form-hint">Each character acts as an individual delimiter. Supports \\t (tab), \\n (newline), \\s (space).</div>
      </div>

      <div class="form-group">
        <label>3. Split Options</label>
        <div style="display: flex; gap: 16px; margin-top: 4px;">
          <label class="form-radio">
            <input type="radio" name="ttc-split-type" value="columns" ${splitType === 'columns' ? 'checked' : ''}>
            <span>Split to columns</span>
          </label>
          <label class="form-radio">
            <input type="radio" name="ttc-split-type" value="rows" ${splitType === 'rows' ? 'checked' : ''}>
            <span>Split to rows</span>
          </label>
        </div>
      </div>

      <div id="cfg-ttc-columns-opts" style="${splitType === 'columns' ? '' : 'display: none;'}">
        <div class="form-group">
          <label>Number of Columns</label>
          <input type="number" class="form-control" id="cfg-ttc-num-cols" min="1" max="100" value="${numColumns}">
        </div>

        <div class="form-group">
          <label>Root Column Name (optional)</label>
          <input type="text" class="form-control" id="cfg-ttc-root" value="${rootName}" placeholder="Defaults to original column name">
          <div class="form-hint">Generated columns will be named &lt;Root&gt;1, &lt;Root&gt;2, etc.</div>
        </div>

        <div class="form-group">
          <label>Extra Characters Handling</label>
          <select class="form-control" id="cfg-ttc-extra">
            <option value="last" ${extraCharacters === 'last' ? 'selected' : ''}>Leave extra in last column</option>
            <option value="drop" ${extraCharacters === 'drop' ? 'selected' : ''}>Drop extra with warning</option>
            <option value="error" ${extraCharacters === 'error' ? 'selected' : ''}>Error (stop processing)</option>
          </select>
        </div>
      </div>

      <div class="cfg-section-title" style="margin-top: 14px;">Advanced Options</div>
      <div style="display: flex; flex-direction: column; gap: 6px; padding: 8px; background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: 6px;">
        <label class="form-check">
          <input type="checkbox" id="cfg-ttc-ignore-quotes" ${ignoreQuotes ? 'checked' : ''}>
          <span>Ignore delimiters in quotes ("...")</span>
        </label>
        <label class="form-check">
          <input type="checkbox" id="cfg-ttc-ignore-single-quotes" ${ignoreSingleQuotes ? 'checked' : ''}>
          <span>Ignore delimiters in single quotes ('...')</span>
        </label>
        <label class="form-check">
          <input type="checkbox" id="cfg-ttc-ignore-parens" ${ignoreParentheses ? 'checked' : ''}>
          <span>Ignore delimiters in parentheses (...)</span>
        </label>
        <label class="form-check">
          <input type="checkbox" id="cfg-ttc-ignore-brackets" ${ignoreBrackets ? 'checked' : ''}>
          <span>Ignore delimiters in brackets [...]</span>
        </label>
        <label class="form-check">
          <input type="checkbox" id="cfg-ttc-skip-empty" ${skipEmpty ? 'checked' : ''}>
          <span>Skip empty parts</span>
        </label>
      </div>
    `;

    container.querySelector('#cfg-ttc-col').addEventListener('change', (e) => {
      node.config.column = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ttc-delims').addEventListener('input', (e) => {
      node.config.delimiters = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('input[name="ttc-split-type"]').forEach(radio => {
      radio.addEventListener('change', (e) => {
        node.config.split_type = e.target.value;
        container.querySelector('#cfg-ttc-columns-opts').style.display = e.target.value === 'columns' ? '' : 'none';
        this.canvas.onWorkflowChange();
      });
    });

    const numColsInput = container.querySelector('#cfg-ttc-num-cols');
    if (numColsInput) {
      numColsInput.addEventListener('input', (e) => {
        node.config.num_columns = parseInt(e.target.value, 10) || 1;
        this.canvas.onWorkflowChange();
      });
    }

    const rootInput = container.querySelector('#cfg-ttc-root');
    if (rootInput) {
      rootInput.addEventListener('input', (e) => {
        node.config.root_name = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    const extraSelect = container.querySelector('#cfg-ttc-extra');
    if (extraSelect) {
      extraSelect.addEventListener('change', (e) => {
        node.config.extra_characters = e.target.value;
        this.canvas.onWorkflowChange();
      });
    }

    container.querySelector('#cfg-ttc-ignore-quotes').addEventListener('change', (e) => {
      node.config.ignore_quotes = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ttc-ignore-single-quotes').addEventListener('change', (e) => {
      node.config.ignore_single_quotes = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ttc-ignore-parens').addEventListener('change', (e) => {
      node.config.ignore_parentheses = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ttc-ignore-brackets').addEventListener('change', (e) => {
      node.config.ignore_brackets = e.target.checked;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-ttc-skip-empty').addEventListener('change', (e) => {
      node.config.skip_empty = e.target.checked;
      this.canvas.onWorkflowChange();
    });
  }

  renderAppendFieldsConfig(container, node) {
    const cfg = node.config || {};
    const cartesianMode = cfg.cartesian_mode || 'error_16';
    const sourcePrefix = cfg.source_prefix !== undefined ? cfg.source_prefix : 'Source_';
    let selectFields = cfg.select_fields || [];

    const targetCols = this.getUpstreamColumns(node.id, 'T');
    const sourceCols = this.getUpstreamColumns(node.id, 'S');

    // Auto-populate select_fields if empty and upstream columns exist
    if (selectFields.length === 0 && (targetCols.length > 0 || sourceCols.length > 0)) {
      targetCols.forEach(c => selectFields.push({ field: c, source: 'T', selected: true, rename: c }));
      sourceCols.forEach(c => {
        const outName = targetCols.includes(c) ? `${sourcePrefix}${c}` : c;
        selectFields.push({ field: outName, source: 'S', selected: true, rename: outName });
      });
      node.config.select_fields = selectFields;
    }

    container.innerHTML = `
      <div class="form-group">
        <label>Cartesian Safety Limit</label>
        <select class="form-control" id="cfg-af-mode">
          <option value="error_16" ${cartesianMode === 'error_16' ? 'selected' : ''}>Error if Source has &gt; 16 records (Safe Default)</option>
          <option value="warn_16" ${cartesianMode === 'warn_16' ? 'selected' : ''}>Warn if Source has &gt; 16 records</option>
          <option value="allow_all" ${cartesianMode === 'allow_all' ? 'selected' : ''}>Allow All Appends (Full Cartesian Join)</option>
        </select>
        <div class="form-hint">Protects against unintended record explosion when joining large datasets.</div>
      </div>

      <div class="form-group">
        <label>Source Column Collision Prefix</label>
        <input type="text" class="form-control" id="cfg-af-prefix" value="${sourcePrefix}" placeholder="e.g. Source_">
        <div class="form-hint">Prefix added to Source columns that share a name with Target columns.</div>
      </div>

      <div class="cfg-section-title" style="margin-top: 14px;">Select &amp; Rename Output Columns</div>
      ${selectFields.length > 0 ? `
        <div style="max-height: 220px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px;">
          <table style="width: 100%; font-size: 11px; border-collapse: collapse;">
            <thead>
              <tr style="background: var(--bg-main); color: var(--text-muted); text-align: left;">
                <th style="padding: 4px 6px; width: 30px;">Keep</th>
                <th style="padding: 4px 6px; width: 45px;">Stream</th>
                <th style="padding: 4px 6px;">Field</th>
                <th style="padding: 4px 6px;">Rename</th>
              </tr>
            </thead>
            <tbody>
              ${selectFields.map((sf, i) => `
                <tr style="border-top: 1px solid var(--border-subtle);" data-sf-idx="${i}">
                  <td style="padding: 4px; text-align: center;">
                    <input type="checkbox" class="af-keep" ${sf.selected !== false ? 'checked' : ''}>
                  </td>
                  <td style="padding: 4px 6px;">
                    <span style="font-weight: 700; color: ${sf.source === 'T' ? 'var(--color-primary)' : 'var(--cat-join)'};">
                      ${sf.source || 'T'}
                    </span>
                  </td>
                  <td style="padding: 4px 6px; font-family: var(--font-mono);">${sf.field}</td>
                  <td style="padding: 4px 6px;">
                    <input type="text" class="form-control form-control-sm af-rename" value="${sf.rename || sf.field}" style="font-size: 11px; padding: 2px 6px;">
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      ` : `
        <div style="padding: 10px; background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: 6px; font-size: 11px; color: var(--text-muted);">
          Connect Target ('T') and Source ('S') inputs to customize column schema.
        </div>
      `}
    `;

    container.querySelector('#cfg-af-mode').addEventListener('change', (e) => {
      node.config.cartesian_mode = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-af-prefix').addEventListener('input', (e) => {
      node.config.source_prefix = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.af-keep').forEach(chk => {
      chk.addEventListener('change', (e) => {
        const row = e.target.closest('tr');
        const idx = parseInt(row.dataset.sfIdx, 10);
        if (node.config.select_fields && node.config.select_fields[idx]) {
          node.config.select_fields[idx].selected = e.target.checked;
          this.canvas.onWorkflowChange();
        }
      });
    });

    container.querySelectorAll('.af-rename').forEach(inp => {
      inp.addEventListener('input', (e) => {
        const row = e.target.closest('tr');
        const idx = parseInt(row.dataset.sfIdx, 10);
        if (node.config.select_fields && node.config.select_fields[idx]) {
          node.config.select_fields[idx].rename = e.target.value.trim() || node.config.select_fields[idx].field;
          this.canvas.onWorkflowChange();
        }
      });
    });
  }

  renderDateTimeConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const column = cfg.column || (upstreamCols[0] || '');
    const conversionType = cfg.conversion_type || 'string_to_date';
    const formatTemplate = cfg.format_template || 'yyyy-MM-dd';
    const customFormat = cfg.custom_format || '';
    const outputColumn = cfg.output_column || '';

    container.innerHTML = `
      <div class="form-group">
        <label>1. Select Conversion Type</label>
        <select class="form-control" id="cfg-dt-conv">
          <option value="string_to_date" ${conversionType === 'string_to_date' ? 'selected' : ''}>String to Date/Time format (Parse)</option>
          <option value="date_to_string" ${conversionType === 'date_to_string' ? 'selected' : ''}>Date/Time format to string (Format)</option>
        </select>
      </div>

      <div class="form-group">
        <label>2. Select Column to Convert</label>
        <select class="form-control" id="cfg-dt-col">
          ${upstreamCols.length > 0
            ? upstreamCols.map(c => `<option value="${c}" ${column === c ? 'selected' : ''}>${c}</option>`).join('')
            : `<option value="${column}">${column || 'Select column'}</option>`}
        </select>
      </div>

      <div class="form-group">
        <label>3. Select the Format of the Incoming / Outgoing Date</label>
        <select class="form-control" id="cfg-dt-template">
          <option value="yyyy-MM-dd" ${formatTemplate === 'yyyy-MM-dd' ? 'selected' : ''}>yyyy-MM-dd (e.g. 2026-09-11)</option>
          <option value="yyyy-MM-dd HH:mm:ss" ${formatTemplate === 'yyyy-MM-dd HH:mm:ss' ? 'selected' : ''}>yyyy-MM-dd HH:mm:ss (e.g. 2026-09-11 14:30:00)</option>
          <option value="MM/dd/yyyy" ${formatTemplate === 'MM/dd/yyyy' ? 'selected' : ''}>MM/dd/yyyy (e.g. 09/11/2026)</option>
          <option value="dd/MM/yyyy" ${formatTemplate === 'dd/MM/yyyy' ? 'selected' : ''}>dd/MM/yyyy (e.g. 11/09/2026)</option>
          <option value="dd-Mon-yyyy" ${formatTemplate === 'dd-Mon-yyyy' ? 'selected' : ''}>dd-Mon-yyyy (e.g. 11-Sep-2026)</option>
          <option value="Month dd, yyyy" ${formatTemplate === 'Month dd, yyyy' ? 'selected' : ''}>Month dd, yyyy (e.g. September 11, 2026)</option>
          <option value="Mon dd, yy" ${formatTemplate === 'Mon dd, yy' ? 'selected' : ''}>Mon dd, yy (e.g. Sep 11, 26)</option>
          <option value="yyyyMMdd" ${formatTemplate === 'yyyyMMdd' ? 'selected' : ''}>yyyyMMdd (e.g. 20260911)</option>
          <option value="custom" ${formatTemplate === 'custom' ? 'selected' : ''}>Custom Format...</option>
        </select>
      </div>

      <div class="form-group" id="cfg-dt-custom-grp" style="${formatTemplate === 'custom' ? '' : 'display: none;'}">
        <label>Custom Date/Time Format</label>
        <input type="text" class="form-control" id="cfg-dt-custom" value="${customFormat}" placeholder="e.g. yyyy/MM/dd or %Y-%m-%d">
        <div class="form-hint">Supports Alteryx tokens (yyyy, MM, dd, HH, mm, ss) or Python strftime (%Y, %m, %d).</div>
      </div>

      <div class="form-group">
        <label>4. Output Column Name (optional)</label>
        <input type="text" class="form-control" id="cfg-dt-out" value="${outputColumn}" placeholder="Defaults to ${column ? column + '_DateTime' : 'DateTime_Out'}">
        <div class="form-hint">Leave blank to append <code>_DateTime</code> or <code>_String</code> to column name.</div>
      </div>
    `;

    container.querySelector('#cfg-dt-conv').addEventListener('change', (e) => {
      node.config.conversion_type = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dt-col').addEventListener('change', (e) => {
      node.config.column = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dt-template').addEventListener('change', (e) => {
      node.config.format_template = e.target.value;
      container.querySelector('#cfg-dt-custom-grp').style.display = e.target.value === 'custom' ? '' : 'none';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dt-custom').addEventListener('input', (e) => {
      node.config.custom_format = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-dt-out').addEventListener('input', (e) => {
      node.config.output_column = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 21. Tool Container (Full Alteryx Parity)
  // --------------------------------------------------------------------
  renderContainerConfig(container, node) {
    const targetC = this.canvas.containers ? this.canvas.containers.find(item => item.id === node.id) : null;
    const c = targetC || node.config || {};
    const count = (c.nodeIds || []).length;
    const themeColor = c.color || '#0284c7';
    const textColor = c.textColor || '#ffffff';
    const fillOpacity = c.fillOpacity !== undefined ? c.fillOpacity : (c.transparency !== undefined ? c.transparency : 12);
    const borderStyle = c.borderStyle || 'solid';
    const borderWidth = c.borderWidth || 2;
    const margin = c.margin !== undefined ? c.margin : 24;

    const colorPresets = [
      { hex: '#0284c7', name: 'Alteryx Blue' },
      { hex: '#16a34a', name: 'Emerald Green' },
      { hex: '#0d9488', name: 'Teal' },
      { hex: '#ea580c', name: 'Amber Orange' },
      { hex: '#dc2626', name: 'Crimson Red' },
      { hex: '#9333ea', name: 'Royal Purple' },
      { hex: '#475569', name: 'Slate Grey' },
      { hex: '#1e3a8a', name: 'Navy' }
    ];

    container.innerHTML = `
      <div class="form-group">
        <label>Container Title / Caption</label>
        <input type="text" class="form-control" id="cfg-container-title" value="${this.escapeHtml(c.title || 'Tool Container')}">
      </div>

      <div class="form-row" style="display:flex; gap:12px; margin-bottom:12px;">
        <div class="form-group" style="flex:1;">
          <label>Header Text Color</label>
          <select class="form-control" id="cfg-container-text-color">
            <option value="#ffffff" ${textColor === '#ffffff' ? 'selected' : ''}>White (#ffffff)</option>
            <option value="#1e293b" ${textColor === '#1e293b' ? 'selected' : ''}>Dark (#1e293b)</option>
            <option value="#fbbf24" ${textColor === '#fbbf24' ? 'selected' : ''}>Amber (#fbbf24)</option>
            <option value="#38bdf8" ${textColor === '#38bdf8' ? 'selected' : ''}>Cyan (#38bdf8)</option>
          </select>
        </div>
        <div class="form-group" style="flex:1;">
          <label>Custom Color</label>
          <div style="display:flex; align-items:center; gap:8px;">
            <input type="color" id="cfg-container-custom-color" value="${themeColor}" style="width:36px; height:32px; border:none; border-radius:4px; cursor:pointer; background:none; padding:0;">
            <span id="cfg-container-color-hex" style="font-size:11px; font-family:monospace; color:var(--text-muted);">${themeColor}</span>
          </div>
        </div>
      </div>

      <div class="form-group">
        <label>Theme Color Presets</label>
        <div class="color-presets" style="display:flex; gap:8px; flex-wrap:wrap; margin-top:4px;">
          ${colorPresets.map(p => `
            <div class="color-preset-swatch ${themeColor.toLowerCase() === p.hex.toLowerCase() ? 'active' : ''}" 
                 data-color="${p.hex}" 
                 title="${p.name}"
                 style="width:24px; height:24px; border-radius:50%; background:${p.hex}; cursor:pointer; border:2px solid ${themeColor.toLowerCase() === p.hex.toLowerCase() ? '#fff' : 'transparent'}; box-shadow:0 0 0 1px #888;"></div>
          `).join('')}
        </div>
      </div>

      <div class="form-group" style="margin-top:14px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <label style="margin-bottom:0;">Background Fill Opacity</label>
          <span id="cfg-container-opacity-val" style="font-size:11px; font-weight:600; color:var(--color-primary);">${fillOpacity}%</span>
        </div>
        <input type="range" class="form-range" id="cfg-container-opacity" min="0" max="100" step="5" value="${fillOpacity}" style="width:100%;">
      </div>

      <div class="form-row" style="display:flex; gap:12px; margin-top:12px; margin-bottom:12px;">
        <div class="form-group" style="flex:1;">
          <label>Border Style</label>
          <select class="form-control" id="cfg-container-border-style">
            <option value="solid" ${borderStyle === 'solid' ? 'selected' : ''}>Solid</option>
            <option value="dashed" ${borderStyle === 'dashed' ? 'selected' : ''}>Dashed</option>
            <option value="dotted" ${borderStyle === 'dotted' ? 'selected' : ''}>Dotted</option>
          </select>
        </div>
        <div class="form-group" style="flex:1;">
          <label>Border Width</label>
          <select class="form-control" id="cfg-container-border-width">
            <option value="1" ${borderWidth === 1 ? 'selected' : ''}>1px (Thin)</option>
            <option value="2" ${borderWidth === 2 ? 'selected' : ''}>2px (Standard)</option>
            <option value="3" ${borderWidth === 3 ? 'selected' : ''}>3px (Medium)</option>
            <option value="4" ${borderWidth === 4 ? 'selected' : ''}>4px (Thick)</option>
          </select>
        </div>
      </div>

      <div class="form-group" style="margin-top:14px; padding:12px; background:var(--bg-secondary); border-radius:6px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <label style="margin-bottom:0; font-weight:600;">Boundary & Margin</label>
          <button class="btn btn-secondary btn-xs" id="cfg-container-btn-autofit" ${count === 0 ? 'disabled' : ''} style="font-size:11px; display:inline-flex; align-items:center; gap:4px;">
            <span>📐 Auto-Fit Boundary</span>
          </button>
        </div>
        <div style="display:flex; gap:8px; align-items:center;">
          <span style="font-size:11px; color:var(--text-secondary); width:50px;">Padding:</span>
          <select class="form-control" id="cfg-container-margin" style="flex:1; height:28px; font-size:12px;">
            <option value="0" ${margin === 0 ? 'selected' : ''}>None (0px)</option>
            <option value="15" ${margin === 15 ? 'selected' : ''}>Small (15px)</option>
            <option value="24" ${margin === 24 ? 'selected' : ''}>Medium (24px)</option>
            <option value="40" ${margin === 40 ? 'selected' : ''}>Large (40px)</option>
          </select>
        </div>
      </div>

      <div class="form-group" style="margin-top:16px;">
        <label class="checkbox-label" style="display:flex; align-items:center; gap:8px; cursor:pointer;">
          <input type="checkbox" id="cfg-container-disabled" ${c.disabled ? 'checked' : ''}>
          <span><b>Disable Container</b> (Bypass enclosed tools during execution)</span>
        </label>
      </div>

      <div class="form-group">
        <label class="checkbox-label" style="display:flex; align-items:center; gap:8px; cursor:pointer;">
          <input type="checkbox" id="cfg-container-collapsed" ${c.collapsed ? 'checked' : ''}>
          <span><b>Collapse Container</b> (Hide enclosed tools to save space)</span>
        </label>
      </div>

      <div class="form-group" style="margin-top:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <label style="margin-bottom:0;">Enclosed Tools (${count})</label>
          <button class="btn btn-secondary btn-xs" id="cfg-container-btn-select-tools" ${count === 0 ? 'disabled' : ''} style="font-size:11px;">
            Select Tools
          </button>
        </div>
        <div style="font-size:12px; color:var(--text-secondary); background:var(--bg-secondary); padding:8px 12px; border-radius:6px; max-height:140px; overflow-y:auto;">
          ${count > 0
            ? c.nodeIds.map(nid => {
                const n = this.canvas.nodes ? this.canvas.nodes.find(item => item.id === nid) : null;
                const toolName = n ? n.name : nid;
                const toolType = n ? n.type : '';
                return `
                  <div class="enclosed-tool-item" data-node-id="${nid}" style="padding:3px 0; display:flex; align-items:center; justify-content:space-between; cursor:pointer;">
                    <span>&bull; <strong>${this.escapeHtml(toolName)}</strong></span>
                    <span style="font-size:10px; opacity:0.75; background:rgba(0,0,0,0.1); padding:1px 6px; border-radius:3px;">${toolType}</span>
                  </div>
                `;
              }).join('')
            : '<em>No tools currently inside boundary. Drag tools inside container to link them.</em>'
          }
        </div>
      </div>

      <div class="form-group" style="margin-top:20px; padding-top:14px; border-top:1px solid var(--border-subtle); display:flex; flex-direction:column; gap:8px;">
        <button class="btn btn-secondary btn-sm" id="cfg-container-btn-ungroup" style="width:100%; display:flex; justify-content:center; align-items:center; gap:6px;">
          <span>📦 Un-group (Remove Container, Keep Tools)</span>
        </button>
        <button class="btn btn-danger btn-sm" id="cfg-container-btn-delete-all" style="width:100%; display:flex; justify-content:center; align-items:center; gap:6px;">
          <span>🗑️ Delete Container & Enclosed Tools</span>
        </button>
      </div>
    `;

    // 1. Title
    container.querySelector('#cfg-container-title').addEventListener('input', (e) => {
      c.title = e.target.value;
      if (targetC) targetC.title = e.target.value;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });

    // 2. Text Color
    container.querySelector('#cfg-container-text-color').addEventListener('change', (e) => {
      c.textColor = e.target.value;
      if (targetC) targetC.textColor = e.target.value;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });

    // 3. Custom Color Picker
    const customColorInput = container.querySelector('#cfg-container-custom-color');
    const colorHexSpan = container.querySelector('#cfg-container-color-hex');
    customColorInput.addEventListener('input', (e) => {
      const hex = e.target.value;
      c.color = hex;
      if (targetC) targetC.color = hex;
      if (colorHexSpan) colorHexSpan.textContent = hex;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });
    customColorInput.addEventListener('change', () => {
      this.renderContainerConfig(container, node);
    });

    // 4. Color Swatches
    container.querySelectorAll('.color-preset-swatch').forEach(swatch => {
      swatch.addEventListener('click', () => {
        const hex = swatch.dataset.color;
        c.color = hex;
        if (targetC) targetC.color = hex;
        this.renderContainerConfig(container, node);
        this.canvas.renderContainerElement(targetC || c);
        this.canvas.onWorkflowChange();
      });
    });

    // 5. Opacity Slider
    const opacitySlider = container.querySelector('#cfg-container-opacity');
    const opacityValSpan = container.querySelector('#cfg-container-opacity-val');
    opacitySlider.addEventListener('input', (e) => {
      const val = parseInt(e.target.value, 10);
      c.fillOpacity = val;
      if (targetC) targetC.fillOpacity = val;
      if (opacityValSpan) opacityValSpan.textContent = `${val}%`;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });

    // 6. Border Style & Width
    container.querySelector('#cfg-container-border-style').addEventListener('change', (e) => {
      c.borderStyle = e.target.value;
      if (targetC) targetC.borderStyle = e.target.value;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });
    container.querySelector('#cfg-container-border-width').addEventListener('change', (e) => {
      const w = parseInt(e.target.value, 10);
      c.borderWidth = w;
      if (targetC) targetC.borderWidth = w;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.onWorkflowChange();
    });

    // 7. Margin Selector
    container.querySelector('#cfg-container-margin').addEventListener('change', (e) => {
      const m = parseInt(e.target.value, 10);
      c.margin = m;
      if (targetC) targetC.margin = m;
      this.canvas.onWorkflowChange();
    });

    // 8. Auto-Fit Button
    container.querySelector('#cfg-container-btn-autofit')?.addEventListener('click', () => {
      const currentMargin = parseInt(container.querySelector('#cfg-container-margin').value, 10) || 24;
      this.canvas.autoFitContainer(c.id, currentMargin);
      this.renderContainerConfig(container, node);
    });

    // 9. Select Enclosed Tools
    container.querySelector('#cfg-container-btn-select-tools')?.addEventListener('click', () => {
      this.canvas.selectEnclosedTools(c.id);
    });

    // Click on individual tool item to select on canvas
    container.querySelectorAll('.enclosed-tool-item').forEach(item => {
      item.addEventListener('click', () => {
        const nid = item.dataset.nodeId;
        if (nid) this.canvas.selectNode(nid);
      });
    });

    // 10. Checkboxes
    container.querySelector('#cfg-container-disabled').addEventListener('change', (e) => {
      if (targetC) targetC.disabled = e.target.checked;
      c.disabled = e.target.checked;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.applyContainerVisibility(targetC || c);
      this.canvas.renderWires();
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-container-collapsed').addEventListener('change', (e) => {
      if (targetC) targetC.collapsed = e.target.checked;
      c.collapsed = e.target.checked;
      this.canvas.renderContainerElement(targetC || c);
      this.canvas.applyContainerVisibility(targetC || c);
      this.canvas.renderWires();
      this.canvas.onWorkflowChange();
    });

    // 11. Deletion buttons
    container.querySelector('#cfg-container-btn-ungroup').addEventListener('click', () => {
      this.canvas.removeContainer(c.id, false);
      this.render(null);
      if (window.appHistory) window.appHistory.pushSnapshot('Un-group Container');
      if (window.showToast) window.showToast('info', 'Container Removed', 'Tools preserved on canvas.');
    });

    container.querySelector('#cfg-container-btn-delete-all').addEventListener('click', () => {
      if (count === 0 || confirm(`Delete container '${c.title || 'Tool Container'}' and all ${count} enclosed tool(s)?`)) {
        this.canvas.removeContainer(c.id, true);
        this.render(null);
        if (window.appHistory) window.appHistory.pushSnapshot('Delete Container and Tools');
        if (window.showToast) window.showToast('info', 'Container Deleted', `Deleted container and ${count} tool(s).`);
      }
    });
  }

  // --------------------------------------------------------------------
  // 22. Comment Note (Sticky Annotation)
  // --------------------------------------------------------------------
  renderCommentConfig(container, node) {
    const comm = node.config || (this.canvas.comments ? this.canvas.comments.find(item => item.id === node.id) : {}) || {};
    container.innerHTML = `
      <div class="form-group">
        <label>Documentation Note (Markdown Supported)</label>
        <textarea class="form-control" id="cfg-comment-text" rows="6" style="font-family:monospace; font-size:12px;">${this.escapeHtml(comm.text || '')}</textarea>
        <span class="form-hint" style="font-size:11px;">Supports # Headings, **bold**, *italic*, - lists, and \`code\`.</span>
      </div>
      <div class="form-group">
        <label>Note Color</label>
        <div class="color-presets" style="display:flex; gap:8px; margin-top:6px;">
          ${[
            { bg: '#fef08a', text: '#1e293b' },
            { bg: '#bae6fd', text: '#0f172a' },
            { bg: '#bbf7d0', text: '#064e3b' },
            { bg: '#fed7aa', text: '#431407' },
            { bg: '#e9d5ff', text: '#3b0764' },
            { bg: '#334155', text: '#f8fafc' }
          ].map(p => `
            <div class="color-preset-swatch ${comm.color === p.bg ? 'active' : ''}" data-bg="${p.bg}" data-text="${p.text}" style="width:24px; height:24px; border-radius:50%; background:${p.bg}; cursor:pointer; border:2px solid ${comm.color === p.bg ? '#fff' : 'transparent'}; box-shadow:0 0 0 1px #888;"></div>
          `).join('')}
        </div>
      </div>
      <div class="form-group">
        <label>Font Size</label>
        <select class="form-control" id="cfg-comment-font-size">
          ${[11, 12, 13, 14, 16, 18].map(sz => `
            <option value="${sz}" ${comm.fontSize === sz ? 'selected' : ''}>${sz}px</option>
          `).join('')}
        </select>
      </div>
    `;

    container.querySelector('#cfg-comment-text').addEventListener('input', (e) => {
      const targetComm = this.canvas.comments ? this.canvas.comments.find(item => item.id === comm.id) : null;
      if (targetComm) targetComm.text = e.target.value;
      comm.text = e.target.value;
      this.canvas.renderCommentElement(targetComm || comm);
      this.canvas.onWorkflowChange();
    });

    container.querySelectorAll('.color-preset-swatch').forEach(swatch => {
      swatch.addEventListener('click', () => {
        const bg = swatch.dataset.bg;
        const text = swatch.dataset.text;
        const targetComm = this.canvas.comments ? this.canvas.comments.find(item => item.id === comm.id) : null;
        if (targetComm) {
          targetComm.color = bg;
          targetComm.textColor = text;
        }
        comm.color = bg;
        comm.textColor = text;
        this.renderCommentConfig(container, node);
        this.canvas.renderCommentElement(targetComm || comm);
        this.canvas.onWorkflowChange();
      });
    });

    container.querySelector('#cfg-comment-font-size').addEventListener('change', (e) => {
      const sz = parseInt(e.target.value) || 13;
      const targetComm = this.canvas.comments ? this.canvas.comments.find(item => item.id === comm.id) : null;
      if (targetComm) targetComm.fontSize = sz;
      comm.fontSize = sz;
      this.canvas.renderCommentElement(targetComm || comm);
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 16. Transpose Tool (Unpivot)
  // --------------------------------------------------------------------
  renderTransposeConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const keyCols = cfg.key_columns || [];
    const dataCols = cfg.data_columns || [];
    const nameCol = cfg.name_column || 'Name';
    const valueCol = cfg.value_column || 'Value';
    const missingAction = cfg.missing_columns_action || 'ignore';

    const allCols = Array.from(new Set([...upstreamCols, ...keyCols, ...dataCols]));

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.4;">
        Pivot wide tables into narrow (tall) format by transforming multiple column headers into rows.
      </div>

      <!-- Key Columns Section -->
      <div class="form-group" style="margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <label style="font-weight: 600; font-size: 12px; margin: 0;">Key Columns (Keep as Dimensions)</label>
          <div style="display: flex; gap: 4px;">
            <button type="button" class="btn btn-xs btn-secondary" id="btn-transpose-key-all" style="padding: 2px 6px; font-size: 10px;">All</button>
            <button type="button" class="btn btn-xs btn-secondary" id="btn-transpose-key-none" style="padding: 2px 6px; font-size: 10px;">Clear</button>
          </div>
        </div>
        <div class="form-hint" style="margin-bottom: 6px; font-size: 10.5px;">Fields that remain as rows and duplicate for each transposed field.</div>
        <div id="transpose-key-list" style="max-height: 160px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px 8px; background: var(--bg-main);">
          ${allCols.length > 0 ? allCols.map(col => `
            <label class="form-check" style="margin-bottom: 4px; font-size: 11.5px; display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" class="transpose-key-chk" value="${this.escapeHtml(col)}" ${keyCols.includes(col) ? 'checked' : ''}>
              <span>${this.escapeHtml(col)}</span>
            </label>
          `).join('') : '<div class="form-hint" style="padding: 6px; text-align: center;">Connect input to view available fields.</div>'}
        </div>
      </div>

      <!-- Data Columns Section -->
      <div class="form-group" style="margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <label style="font-weight: 600; font-size: 12px; margin: 0;">Data Columns (Transpose to Rows)</label>
          <div style="display: flex; gap: 4px;">
            <button type="button" class="btn btn-xs btn-secondary" id="btn-transpose-data-all" style="padding: 2px 6px; font-size: 10px;">All</button>
            <button type="button" class="btn btn-xs btn-secondary" id="btn-transpose-data-none" style="padding: 2px 6px; font-size: 10px;">Clear</button>
          </div>
        </div>
        <div class="form-hint" style="margin-bottom: 6px; font-size: 10.5px;">Fields whose names become Name and cell values become Value. (If none selected, all non-key fields are transposed).</div>
        <div id="transpose-data-list" style="max-height: 160px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px 8px; background: var(--bg-main);">
          ${allCols.length > 0 ? allCols.map(col => `
            <label class="form-check" style="margin-bottom: 4px; font-size: 11.5px; display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" class="transpose-data-chk" value="${this.escapeHtml(col)}" ${dataCols.includes(col) ? 'checked' : ''}>
              <span>${this.escapeHtml(col)}</span>
            </label>
          `).join('') : '<div class="form-hint" style="padding: 6px; text-align: center;">Connect input to view available fields.</div>'}
        </div>
      </div>

      <!-- Output Column Names -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 14px;">
        <div class="form-group" style="margin-bottom: 0;">
          <label style="font-size: 11px; font-weight: 600;">Name Column</label>
          <input type="text" class="form-control form-control-sm" id="cfg-transpose-name-col" value="${this.escapeHtml(nameCol)}" placeholder="Name">
        </div>
        <div class="form-group" style="margin-bottom: 0;">
          <label style="font-size: 11px; font-weight: 600;">Value Column</label>
          <input type="text" class="form-control form-control-sm" id="cfg-transpose-value-col" value="${this.escapeHtml(valueCol)}" placeholder="Value">
        </div>
      </div>

      <!-- Missing Fields Action -->
      <div class="form-group" style="margin-bottom: 6px;">
        <label style="font-size: 11px; font-weight: 600;">Missing Columns Action</label>
        <select class="form-control form-control-sm" id="cfg-transpose-missing-action">
          <option value="ignore" ${missingAction === 'ignore' ? 'selected' : ''}>Ignore (Skip missing columns)</option>
          <option value="warn" ${missingAction === 'warn' ? 'selected' : ''}>Warn (Log warning and continue)</option>
          <option value="error" ${missingAction === 'error' ? 'selected' : ''}>Error (Halt execution if column missing)</option>
        </select>
      </div>
    `;

    // Event bindings for Transpose
    const updateKeyCols = () => {
      node.config.key_columns = Array.from(container.querySelectorAll('.transpose-key-chk:checked')).map(c => c.value);
      this.canvas.onWorkflowChange();
    };

    const updateDataCols = () => {
      node.config.data_columns = Array.from(container.querySelectorAll('.transpose-data-chk:checked')).map(c => c.value);
      this.canvas.onWorkflowChange();
    };

    container.querySelectorAll('.transpose-key-chk').forEach(chk => {
      chk.addEventListener('change', updateKeyCols);
    });

    container.querySelectorAll('.transpose-data-chk').forEach(chk => {
      chk.addEventListener('change', updateDataCols);
    });

    container.querySelector('#btn-transpose-key-all')?.addEventListener('click', () => {
      container.querySelectorAll('.transpose-key-chk').forEach(c => c.checked = true);
      updateKeyCols();
    });

    container.querySelector('#btn-transpose-key-none')?.addEventListener('click', () => {
      container.querySelectorAll('.transpose-key-chk').forEach(c => c.checked = false);
      updateKeyCols();
    });

    container.querySelector('#btn-transpose-data-all')?.addEventListener('click', () => {
      container.querySelectorAll('.transpose-data-chk').forEach(c => c.checked = true);
      updateDataCols();
    });

    container.querySelector('#btn-transpose-data-none')?.addEventListener('click', () => {
      container.querySelectorAll('.transpose-data-chk').forEach(c => c.checked = false);
      updateDataCols();
    });

    container.querySelector('#cfg-transpose-name-col')?.addEventListener('input', (e) => {
      node.config.name_column = e.target.value.trim() || 'Name';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-transpose-value-col')?.addEventListener('input', (e) => {
      node.config.value_column = e.target.value.trim() || 'Value';
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-transpose-missing-action')?.addEventListener('change', (e) => {
      node.config.missing_columns_action = e.target.value;
      this.canvas.onWorkflowChange();
    });
  }

  // --------------------------------------------------------------------
  // 17. Cross Tab Tool (Pivot)
  // --------------------------------------------------------------------
  renderCrossTabConfig(container, node, upstreamCols) {
    const cfg = node.config || {};
    const groupCols = cfg.group_by || [];
    const headerField = cfg.header_field || '';
    const valueField = cfg.value_field || '';
    let aggMethods = cfg.agg_methods || [];
    if (!aggMethods.length && cfg.agg_func) {
      aggMethods = Array.isArray(cfg.agg_func) ? cfg.agg_func : [cfg.agg_func];
    }
    if (!aggMethods.length) {
      aggMethods = ['sum'];
    }
    const cleanHeaders = cfg.clean_headers !== false;
    const separator = cfg.separator || ', ';

    const allCols = Array.from(new Set([...upstreamCols, ...groupCols, headerField, valueField].filter(Boolean)));

    container.innerHTML = `
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.4;">
        Pivot tall tables into wide summary matrices by transforming values from one column into multiple headers.
      </div>

      <!-- 1. Group Data By -->
      <div class="form-group" style="margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <label style="font-weight: 600; font-size: 12px; margin: 0;">1. Group data by these values:</label>
          <div style="display: flex; gap: 4px;">
            <button type="button" class="btn btn-xs btn-secondary" id="btn-crosstab-group-all" style="padding: 2px 6px; font-size: 10px;">All</button>
            <button type="button" class="btn btn-xs btn-secondary" id="btn-crosstab-group-none" style="padding: 2px 6px; font-size: 10px;">Clear</button>
          </div>
        </div>
        <div id="crosstab-group-list" style="max-height: 140px; overflow-y: auto; border: 1px solid var(--border-subtle); border-radius: 6px; padding: 6px 8px; background: var(--bg-main);">
          ${allCols.length > 0 ? allCols.map(col => `
            <label class="form-check" style="margin-bottom: 4px; font-size: 11.5px; display: flex; align-items: center; gap: 6px;">
              <input type="checkbox" class="crosstab-group-chk" value="${this.escapeHtml(col)}" ${groupCols.includes(col) ? 'checked' : ''}>
              <span>${this.escapeHtml(col)}</span>
            </label>
          `).join('') : '<div class="form-hint" style="padding: 6px; text-align: center;">Connect input to view available fields.</div>'}
        </div>
      </div>

      <!-- 2. New Column Headers -->
      <div class="form-group" style="margin-bottom: 12px;">
        <label style="font-weight: 600; font-size: 12px; margin-bottom: 4px;">2. New Column Headers (Categorical):</label>
        <select class="form-control form-control-sm" id="cfg-crosstab-header-field">
          <option value="">-- Select Header Field --</option>
          ${allCols.map(col => `
            <option value="${this.escapeHtml(col)}" ${headerField === col ? 'selected' : ''}>${this.escapeHtml(col)}</option>
          `).join('')}
        </select>
      </div>

      <!-- 3. Values for New Columns -->
      <div class="form-group" style="margin-bottom: 14px;">
        <label style="font-weight: 600; font-size: 12px; margin-bottom: 4px;">3. Values for New Columns (Metrics):</label>
        <select class="form-control form-control-sm" id="cfg-crosstab-value-field">
          <option value="">-- Select Value Field --</option>
          ${allCols.map(col => `
            <option value="${this.escapeHtml(col)}" ${valueField === col ? 'selected' : ''}>${this.escapeHtml(col)}</option>
          `).join('')}
        </select>
      </div>

      <!-- 4. Aggregation Methods -->
      <div class="form-group" style="margin-bottom: 14px;">
        <label style="font-weight: 600; font-size: 12px; margin-bottom: 6px;">4. Method for Aggregating Values (Multi-Select):</label>
        
        <div style="border: 1px solid var(--border-subtle); border-radius: 6px; padding: 8px 10px; background: var(--bg-main);">
          <div style="font-size: 10px; font-weight: 700; color: var(--color-primary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Calculations</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-bottom: 8px;">
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="sum" ${aggMethods.includes('sum') ? 'checked' : ''}>
              <span>Sum</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="avg" ${aggMethods.includes('avg') || aggMethods.includes('mean') ? 'checked' : ''}>
              <span>Average (Mean)</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="count" ${aggMethods.includes('count') ? 'checked' : ''}>
              <span>Count (All)</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="count_non_null" ${aggMethods.includes('count_non_null') || aggMethods.includes('count_without_nulls') ? 'checked' : ''}>
              <span>Count (Non-Null)</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="min" ${aggMethods.includes('min') ? 'checked' : ''}>
              <span>Min</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="max" ${aggMethods.includes('max') ? 'checked' : ''}>
              <span>Max</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="first" ${aggMethods.includes('first') ? 'checked' : ''}>
              <span>First</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="last" ${aggMethods.includes('last') ? 'checked' : ''}>
              <span>Last</span>
            </label>
          </div>

          <div style="font-size: 10px; font-weight: 700; color: var(--color-primary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Text / Strings</div>
          <div style="margin-bottom: 8px;">
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" id="cfg-crosstab-chk-concat" value="concat" ${aggMethods.includes('concat') ? 'checked' : ''}>
              <span>Concatenate</span>
            </label>
            <div id="cfg-crosstab-sep-group" style="margin-top: 4px; margin-left: 20px; display: ${aggMethods.includes('concat') ? 'flex' : 'none'}; align-items: center; gap: 6px;">
              <span style="font-size: 10.5px; color: var(--text-muted);">Separator:</span>
              <input type="text" class="form-control form-control-sm" id="cfg-crosstab-separator" value="${this.escapeHtml(separator)}" style="width: 70px; padding: 2px 6px; font-size: 11px;">
            </div>
          </div>

          <div style="font-size: 10px; font-weight: 700; color: var(--color-primary); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">Totals & Percentages</div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px;">
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="total_row" ${aggMethods.includes('total_row') ? 'checked' : ''}>
              <span>Total Row</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="total_col" ${aggMethods.includes('total_col') ? 'checked' : ''}>
              <span>Total Column</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="pct_row" ${aggMethods.includes('pct_row') ? 'checked' : ''}>
              <span>Percent Row</span>
            </label>
            <label class="form-check" style="font-size: 11px;">
              <input type="checkbox" class="crosstab-method-chk" value="pct_col" ${aggMethods.includes('pct_col') ? 'checked' : ''}>
              <span>Percent Column</span>
            </label>
          </div>
        </div>
      </div>

      <!-- 5. Options -->
      <div style="border-top: 1px solid var(--border-subtle); padding-top: 10px;">
        <label class="form-check" style="font-size: 11px;">
          <input type="checkbox" id="cfg-crosstab-clean-headers" ${cleanHeaders ? 'checked' : ''}>
          <span>Clean Column Headers (Alteryx Standard: replace special chars with _, prefix leading digits)</span>
        </label>
      </div>
    `;

    // Event bindings for CrossTab
    const updateGroupCols = () => {
      node.config.group_by = Array.from(container.querySelectorAll('.crosstab-group-chk:checked')).map(c => c.value);
      this.canvas.onWorkflowChange();
    };

    const updateMethods = () => {
      const selected = Array.from(container.querySelectorAll('.crosstab-method-chk:checked')).map(c => c.value);
      node.config.agg_methods = selected.length ? selected : ['sum'];
      // Also update legacy agg_func for backwards compatibility
      node.config.agg_func = node.config.agg_methods[0];
      this.canvas.onWorkflowChange();
    };

    container.querySelectorAll('.crosstab-group-chk').forEach(chk => {
      chk.addEventListener('change', updateGroupCols);
    });

    container.querySelectorAll('.crosstab-method-chk').forEach(chk => {
      chk.addEventListener('change', (e) => {
        if (e.target.value === 'concat') {
          const sepGroup = container.querySelector('#cfg-crosstab-sep-group');
          if (sepGroup) sepGroup.style.display = e.target.checked ? 'flex' : 'none';
        }
        updateMethods();
      });
    });

    container.querySelector('#btn-crosstab-group-all')?.addEventListener('click', () => {
      container.querySelectorAll('.crosstab-group-chk').forEach(c => c.checked = true);
      updateGroupCols();
    });

    container.querySelector('#btn-crosstab-group-none')?.addEventListener('click', () => {
      container.querySelectorAll('.crosstab-group-chk').forEach(c => c.checked = false);
      updateGroupCols();
    });

    container.querySelector('#cfg-crosstab-header-field')?.addEventListener('change', (e) => {
      node.config.header_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-crosstab-value-field')?.addEventListener('change', (e) => {
      node.config.value_field = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-crosstab-separator')?.addEventListener('input', (e) => {
      node.config.separator = e.target.value;
      this.canvas.onWorkflowChange();
    });

    container.querySelector('#cfg-crosstab-clean-headers')?.addEventListener('change', (e) => {
      node.config.clean_headers = e.target.checked;
      this.canvas.onWorkflowChange();
    });
  }

  renderLLMProcessConfig(container, node, upstreamCols) {
    // 1. Ensure sensible configuration defaults
    if (!node.config) node.config = {};
    const cfg = node.config;
    cfg.provider_type = cfg.provider_type || 'ollama';
    cfg.connection = cfg.connection || {};
    if (!cfg.connection.base_url) {
      if (cfg.provider_type === 'ollama') cfg.connection.base_url = 'http://localhost:11434';
      else if (cfg.provider_type === 'lm_studio') cfg.connection.base_url = 'http://localhost:1234/v1';
      else if (cfg.provider_type === 'openai') cfg.connection.base_url = 'https://api.openai.com/v1';
      else if (cfg.provider_type === 'gemini') cfg.connection.base_url = 'https://generativelanguage.googleapis.com';
    }
    cfg.connection.api_key = cfg.connection.api_key || '';
    cfg.model = cfg.model || (cfg.provider_type === 'ollama' ? 'llama3.2' : (cfg.provider_type === 'gemini' ? 'gemini-2.0-flash' : 'gpt-4o-mini'));
    cfg.temperature = cfg.temperature !== undefined ? cfg.temperature : 0.3;
    cfg.max_tokens = cfg.max_tokens !== undefined ? cfg.max_tokens : 512;
    cfg.top_p = cfg.top_p !== undefined ? cfg.top_p : 1.0;
    cfg.timeout_seconds = cfg.timeout_seconds !== undefined ? cfg.timeout_seconds : 30;

    cfg.system_prompt = cfg.system_prompt !== undefined ? cfg.system_prompt : 'You are an accurate, concise data processing assistant.';
    cfg.user_prompt_template = cfg.user_prompt_template !== undefined ? cfg.user_prompt_template : '';

    cfg.rag_context = cfg.rag_context || {};
    cfg.rag_context.enabled = !!cfg.rag_context.enabled;
    cfg.rag_context.source = cfg.rag_context.source || 'static';
    cfg.rag_context.text = cfg.rag_context.text || '';
    cfg.rag_context.column = cfg.rag_context.column || '';
    cfg.rag_context.file_path = cfg.rag_context.file_path || '';
    cfg.rag_context.placement = cfg.rag_context.placement || 'before';

    cfg.output_mode = cfg.output_mode || 'single';
    cfg.output_column = cfg.output_column || 'AI_Response';
    cfg.json_fields = Array.isArray(cfg.json_fields) ? cfg.json_fields : [];

    cfg.on_error = cfg.on_error || 'null';
    cfg.max_retries = cfg.max_retries !== undefined ? cfg.max_retries : 2;
    cfg.concurrency = cfg.concurrency !== undefined ? cfg.concurrency : 3;
    cfg.rate_limit_rps = cfg.rate_limit_rps !== undefined ? cfg.rate_limit_rps : 10;
    cfg.include_token_columns = !!cfg.include_token_columns;

    const cols = Array.isArray(upstreamCols) ? upstreamCols : [];

    // Lock & status derivation
    const isLocked = Boolean(node.is_cached || node.locked || (this.canvas && this.canvas.cachedNodeIds && this.canvas.cachedNodeIds.has(node.id)));
    let initialStatusText = 'Ready to run. Click "Run LLM Tool Only" to preview.';
    let initialMetricsText = '';
    let hasMetrics = false;

    if (isLocked) {
      initialStatusText = '🔒 Output locked. Subsequent workflow runs will use cached results.';
    } else if (window.appLastResult && window.appLastResult.node_results && window.appLastResult.node_results[node.id]) {
      const prevRes = window.appLastResult.node_results[node.id];
      const recCount = prevRes.record_counts ? (prevRes.record_counts['O'] || Object.values(prevRes.record_counts)[0] || 0) : 0;
      initialStatusText = `✓ Output available (${recCount.toLocaleString()} records).`;
      if (prevRes.messages) {
        const tokenMsg = prevRes.messages.find(m => m.includes('Tokens:'));
        if (tokenMsg) {
          const m = tokenMsg.match(/Tokens:\s*([^\(]+)/);
          if (m) {
            initialMetricsText = m[1].trim();
            hasMetrics = true;
          }
        }
      }
    }

    // Helper for rendering column chips
    const colChipsHtml = cols.map(c => {
      const colName = typeof c === 'string' ? c : (c.name || c.field || '');
      return `<button type="button" class="btn-col-chip" data-col="${this.escapeHtml(colName)}" style="padding: 2px 7px; font-size: 11px; border: 1px solid var(--border-color); background: var(--bg-surface-elevated, #2a2a38); color: var(--text-color); border-radius: 4px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px;">
        <span style="color: #8b5cf6; font-weight: bold;">+</span> [${this.escapeHtml(colName)}]
      </button>`;
    }).join(' ') || '<span style="font-size: 11px; color: var(--text-muted);">No upstream columns detected. Connect an input node to see columns.</span>';

    // Helper for column select options in RAG
    const colOptionsHtml = cols.map(c => {
      const colName = typeof c === 'string' ? c : (c.name || c.field || '');
      const sel = colName === cfg.rag_context.column ? 'selected' : '';
      return `<option value="${this.escapeHtml(colName)}" ${sel}>${this.escapeHtml(colName)}</option>`;
    }).join('');

    container.innerHTML = `
      <div class="llm-config-wrapper" style="display: flex; flex-direction: column; gap: 14px; font-size: 12px;">

        <!-- 0. Standalone Run & Output Lock Action Bar -->
        <div class="cfg-section llm-action-bar" style="border: 1px solid rgba(139,92,246,0.35); border-radius: 6px; padding: 10px 12px; background: rgba(139,92,246,0.08); display: flex; flex-direction: column; gap: 8px;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <button type="button" id="btn-llm-run-standalone" class="btn btn-primary btn-sm btn-run-standalone" style="background: #8b5cf6; border-color: #7c3aed; display: inline-flex; align-items: center; gap: 6px; font-weight: 600; padding: 4px 12px; height: 28px;" title="Execute only this LLM tool and preview outputs without running the rest of the workflow">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
              <span>Run LLM Tool Only</span>
            </button>
            <label class="form-check" style="margin: 0; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; user-select: none;" title="Freeze/lock the output so workflow runs don't rerun the LLM or consume tokens">
              <input type="checkbox" id="cfg-llm-lock-output" ${isLocked ? 'checked' : ''}>
              <span id="cfg-llm-lock-label" style="font-weight: 600; font-size: 11px; color: ${isLocked ? '#8b5cf6' : 'var(--text-color)'}; display: inline-flex; align-items: center; gap: 3px;">
                <span>🔒</span> Lock Output (Freeze)
              </span>
            </label>
          </div>
          <div id="llm-run-status-line" style="font-size: 10.5px; color: var(--text-muted); display: flex; align-items: center; justify-content: space-between;">
            <span id="llm-standalone-status-text">${initialStatusText}</span>
            <span id="llm-standalone-tokens-pill" style="font-size: 10px; padding: 1px 6px; border-radius: 4px; background: rgba(0,0,0,0.2); display: ${hasMetrics ? 'inline-block' : 'none'};">${initialMetricsText}</span>
          </div>
        </div>

        <!-- 1. LLM Connection Header & Card -->
        <div class="cfg-section" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; background: var(--bg-surface-subtle, rgba(255,255,255,0.02));">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px;">
            <div style="font-weight: 600; font-size: 12px; color: var(--text-color); display: flex; align-items: center; gap: 6px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2.2"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>
              LLM Connection
            </div>
            <span id="llm-status-badge" style="font-size: 10.5px; padding: 2px 6px; border-radius: 4px; background: rgba(139,92,246,0.15); color: #8b5cf6;">Ready</span>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 8px;">
            <div>
              <label class="form-label" style="font-size: 11px; margin-bottom: 3px;">Provider</label>
              <select id="cfg-llm-provider" class="form-control form-control-sm" style="font-size: 11.5px;">
                <option value="ollama" ${cfg.provider_type === 'ollama' ? 'selected' : ''}>Ollama (Local)</option>
                <option value="lm_studio" ${cfg.provider_type === 'lm_studio' ? 'selected' : ''}>LM Studio (Local)</option>
                <option value="openai" ${cfg.provider_type === 'openai' ? 'selected' : ''}>OpenAI</option>
                <option value="gemini" ${cfg.provider_type === 'gemini' ? 'selected' : ''}>Google Gemini</option>
                <option value="azure_openai" ${cfg.provider_type === 'azure_openai' ? 'selected' : ''}>Azure OpenAI</option>
                <option value="openai_compat" ${cfg.provider_type === 'openai_compat' ? 'selected' : ''}>OpenAI-Compatible (vLLM, Groq)</option>
              </select>
            </div>
            <div>
              <label class="form-label" style="font-size: 11px; margin-bottom: 3px;">Base URL</label>
              <input type="text" id="cfg-llm-base-url" class="form-control form-control-sm" value="${this.escapeHtml(cfg.connection.base_url)}" placeholder="http://localhost:11434" style="font-size: 11.5px;">
            </div>
          </div>

          <div id="cfg-llm-auth-row" style="margin-bottom: 8px; display: ${['openai', 'gemini', 'azure_openai'].includes(cfg.provider_type) ? 'block' : 'none'};">
            <label class="form-label" style="font-size: 11px; margin-bottom: 3px;">API Key</label>
            <input type="password" id="cfg-llm-api-key" class="form-control form-control-sm" value="${this.escapeHtml(cfg.connection.api_key)}" placeholder="Paste API key here..." style="font-size: 11.5px;">
          </div>

          <div style="display: flex; gap: 8px; align-items: flex-end; margin-bottom: 10px;">
            <div style="flex: 1;">
              <label class="form-label" style="font-size: 11px; margin-bottom: 3px;">Model</label>
              <div style="position: relative;">
                <input type="text" id="cfg-llm-model" list="cfg-llm-model-list" class="form-control form-control-sm" value="${this.escapeHtml(cfg.model)}" placeholder="e.g. llama3.2, gpt-4o-mini" style="font-size: 11.5px;">
                <datalist id="cfg-llm-model-list">
                  <option value="llama3.2">llama3.2</option>
                  <option value="llama3.1">llama3.1</option>
                  <option value="mistral">mistral</option>
                  <option value="phi3">phi3</option>
                  <option value="gemma2">gemma2</option>
                  <option value="gpt-4o-mini">gpt-4o-mini</option>
                  <option value="gpt-4o">gpt-4o</option>
                  <option value="gemini-2.0-flash">gemini-2.0-flash</option>
                </datalist>
              </div>
            </div>
            <button type="button" id="btn-llm-fetch-models" class="btn btn-secondary btn-sm" style="font-size: 11px; padding: 4px 8px; height: 30px;" title="Fetch models from local or remote provider">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 3px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>Fetch
            </button>
            <button type="button" id="btn-llm-test-conn" class="btn btn-primary btn-sm" style="font-size: 11px; padding: 4px 10px; height: 30px; background: #8b5cf6; border-color: #7c3aed;" title="Test connectivity to model server">
              Test
            </button>
          </div>

          <!-- Connection test alert area -->
          <div id="llm-test-result" style="display: none; font-size: 11px; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px;"></div>

          <!-- Advanced LLM Parameters -->
          <details style="margin-top: 4px;">
            <summary style="font-size: 11px; color: var(--text-muted); cursor: pointer; user-select: none;">Advanced parameters (Temperature, Tokens, Timeout)</summary>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 8px;">
              <div>
                <label class="form-label" style="font-size: 10px;">Temperature (<span id="temp-val">${cfg.temperature}</span>)</label>
                <input type="range" id="cfg-llm-temp" min="0.0" max="1.0" step="0.05" value="${cfg.temperature}" style="width: 100%;">
              </div>
              <div>
                <label class="form-label" style="font-size: 10px;">Max Tokens</label>
                <input type="number" id="cfg-llm-max-tokens" class="form-control form-control-sm" value="${cfg.max_tokens}" min="1" max="8192" style="font-size: 11px;">
              </div>
              <div>
                <label class="form-label" style="font-size: 10px;">Timeout (sec)</label>
                <input type="number" id="cfg-llm-timeout" class="form-control form-control-sm" value="${cfg.timeout_seconds}" min="5" max="300" style="font-size: 11px;">
              </div>
            </div>
          </details>
        </div>

        <!-- 2. Prompt Template Editor Card -->
        <div class="cfg-section" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; background: var(--bg-surface-subtle, rgba(255,255,255,0.02));">
          <div style="font-weight: 600; font-size: 12px; color: var(--text-color); margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
              Prompt Template
            </div>
            <button type="button" id="btn-llm-preview-prompt" class="btn btn-secondary btn-sm" style="font-size: 10.5px; padding: 2px 8px;">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 3px;"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
              Preview Prompt
            </button>
          </div>

          <div style="margin-bottom: 8px;">
            <label class="form-label" style="font-size: 11px; margin-bottom: 3px;">System Prompt (Role & Guidelines)</label>
            <textarea id="cfg-llm-sys-prompt" class="form-control" rows="2" style="font-size: 11px; resize: vertical;" placeholder="You are an accurate data assistant...">${this.escapeHtml(cfg.system_prompt)}</textarea>
          </div>

          <div style="margin-bottom: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 3px;">
              <label class="form-label" style="font-size: 11px; margin: 0;">User Prompt Template</label>
              <span style="font-size: 10px; color: var(--text-muted);">Use {{[ColumnName]}} for row values</span>
            </div>
            <textarea id="cfg-llm-user-prompt" class="form-control" rows="4" style="font-size: 11.5px; font-family: monospace; resize: vertical;" placeholder="e.g. Extract the sentiment of this text: {{[ReviewText]}}&#10;Respond with Positive, Neutral, or Negative.">${this.escapeHtml(cfg.user_prompt_template)}</textarea>
          </div>

          <!-- Column Insertion Chips -->
          <div>
            <div style="font-size: 10.5px; color: var(--text-muted); margin-bottom: 5px;">Click a field to insert into prompt:</div>
            <div class="col-chips-container" style="display: flex; flex-wrap: wrap; gap: 5px; max-height: 80px; overflow-y: auto; padding: 4px; background: rgba(0,0,0,0.1); border-radius: 4px;">
              ${colChipsHtml}
            </div>
          </div>
        </div>

        <!-- 3. RAG / Context Injection Card (Collapsible) -->
        <div class="cfg-section" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; background: var(--bg-surface-subtle, rgba(255,255,255,0.02));">
          <div style="display: flex; align-items: center; justify-content: space-between;">
            <label class="form-check" style="font-size: 11.5px; font-weight: 600; margin: 0; cursor: pointer;">
              <input type="checkbox" id="cfg-llm-rag-enable" ${cfg.rag_context.enabled ? 'checked' : ''}>
              <span style="color: var(--text-color); display: flex; align-items: center; gap: 6px;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2.2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                Context / RAG Injection
              </span>
            </label>
            <span style="font-size: 10.5px; color: var(--text-muted);">Augment prompts with knowledge</span>
          </div>

          <div id="cfg-llm-rag-body" style="margin-top: 10px; display: ${cfg.rag_context.enabled ? 'block' : 'none'};">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
              <div>
                <label class="form-label" style="font-size: 10.5px; margin-bottom: 2px;">Context Source</label>
                <select id="cfg-llm-rag-source" class="form-control form-control-sm" style="font-size: 11px;">
                  <option value="static" ${cfg.rag_context.source === 'static' ? 'selected' : ''}>Static Text Block</option>
                  <option value="column" ${cfg.rag_context.source === 'column' ? 'selected' : ''}>From Column (Per-Row)</option>
                  <option value="file" ${cfg.rag_context.source === 'file' ? 'selected' : ''}>From File (Shared Doc)</option>
                </select>
              </div>
              <div>
                <label class="form-label" style="font-size: 10.5px; margin-bottom: 2px;">Placement</label>
                <select id="cfg-llm-rag-placement" class="form-control form-control-sm" style="font-size: 11px;">
                  <option value="before" ${cfg.rag_context.placement === 'before' ? 'selected' : ''}>Before User Prompt</option>
                  <option value="after" ${cfg.rag_context.placement === 'after' ? 'selected' : ''}>After User Prompt</option>
                  <option value="system" ${cfg.rag_context.placement === 'system' ? 'selected' : ''}>In System Instructions</option>
                </select>
              </div>
            </div>

            <!-- Static text input -->
            <div id="cfg-rag-src-static" style="display: ${cfg.rag_context.source === 'static' ? 'block' : 'none'}; margin-bottom: 8px;">
              <textarea id="cfg-llm-rag-text" class="form-control" rows="3" style="font-size: 11px;" placeholder="Paste domain guidelines, category definitions, or reference knowledge...">${this.escapeHtml(cfg.rag_context.text)}</textarea>
            </div>

            <!-- Column selector -->
            <div id="cfg-rag-src-column" style="display: ${cfg.rag_context.source === 'column' ? 'block' : 'none'}; margin-bottom: 8px;">
              <select id="cfg-llm-rag-col" class="form-control form-control-sm" style="font-size: 11px;">
                <option value="">-- Select Context Column --</option>
                ${colOptionsHtml}
              </select>
            </div>

            <!-- File path picker -->
            <div id="cfg-rag-src-file" style="display: ${cfg.rag_context.source === 'file' ? 'block' : 'none'}; margin-bottom: 8px;">
              <div style="display: flex; gap: 6px;">
                <input type="text" id="cfg-llm-rag-file" class="form-control form-control-sm" value="${this.escapeHtml(cfg.rag_context.file_path)}" placeholder="Path to .txt or .md reference file..." style="font-size: 11px; flex: 1;">
              </div>
            </div>
          </div>
        </div>

        <!-- 4. Output & Execution Options Card -->
        <div class="cfg-section" style="border: 1px solid var(--border-color); border-radius: 6px; padding: 12px; background: var(--bg-surface-subtle, rgba(255,255,255,0.02));">
          <div style="font-weight: 600; font-size: 12px; color: var(--text-color); margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" stroke-width="2.2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
            Output & Execution
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
            <div>
              <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Output Mode</label>
              <select id="cfg-llm-out-mode" class="form-control form-control-sm" style="font-size: 11px;">
                <option value="single" ${cfg.output_mode === 'single' ? 'selected' : ''}>Single Column (Raw Response)</option>
                <option value="json_parse" ${cfg.output_mode === 'json_parse' ? 'selected' : ''}>JSON Parse (Extract Fields)</option>
              </select>
            </div>
            <div>
              <label class="form-label" style="font-size: 11px; margin-bottom: 2px;">Output Column Name</label>
              <input type="text" id="cfg-llm-out-col" class="form-control form-control-sm" value="${this.escapeHtml(cfg.output_column)}" style="font-size: 11px;">
            </div>
          </div>

          <!-- JSON Parse Table -->
          <div id="cfg-llm-json-container" style="display: ${cfg.output_mode === 'json_parse' ? 'block' : 'none'}; margin-bottom: 10px; padding: 8px; background: rgba(0,0,0,0.15); border-radius: 4px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <span style="font-size: 11px; font-weight: 600;">JSON Field Extractions</span>
              <button type="button" id="btn-add-json-field" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 1px 6px;">+ Add Field</button>
            </div>
            <div id="json-fields-list" style="display: flex; flex-direction: column; gap: 4px;">
              <!-- Dynamically populated -->
            </div>
          </div>

          <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 8px;">
            <div>
              <label class="form-label" style="font-size: 10.5px; margin-bottom: 2px;">On Row Error</label>
              <select id="cfg-llm-on-error" class="form-control form-control-sm" style="font-size: 10.5px;">
                <option value="null" ${cfg.on_error === 'null' ? 'selected' : ''}>Null & Continue</option>
                <option value="error_message" ${cfg.on_error === 'error_message' ? 'selected' : ''}>Error Message</option>
                <option value="stop" ${cfg.on_error === 'stop' ? 'selected' : ''}>Stop Workflow</option>
              </select>
            </div>
            <div>
              <label class="form-label" style="font-size: 10.5px; margin-bottom: 2px;">Concurrency</label>
              <input type="number" id="cfg-llm-concurrency" class="form-control form-control-sm" value="${cfg.concurrency}" min="1" max="20" style="font-size: 10.5px;" title="Parallel simultaneous requests">
            </div>
            <div>
              <label class="form-label" style="font-size: 10.5px; margin-bottom: 2px;">Rate Limit (req/s)</label>
              <input type="number" id="cfg-llm-rps" class="form-control form-control-sm" value="${cfg.rate_limit_rps}" min="1" max="100" style="font-size: 10.5px;" title="Requests per second limit">
            </div>
          </div>

          <div style="border-top: 1px solid var(--border-subtle); padding-top: 6px;">
            <label class="form-check" style="font-size: 11px; margin: 0; cursor: pointer;">
              <input type="checkbox" id="cfg-llm-inc-tokens" ${cfg.include_token_columns ? 'checked' : ''}>
              <span>Include token metrics columns (_input_tokens, _output_tokens, _latency_ms)</span>
            </label>
          </div>
        </div>

        <!-- Prompt Preview Modal / Drawer container -->
        <div id="llm-preview-modal" style="display: none; border: 1px solid #8b5cf6; border-radius: 6px; padding: 12px; background: var(--bg-surface-elevated, #242432); margin-top: 4px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="font-weight: 600; color: #8b5cf6; font-size: 11.5px;">Prompt Render Preview (First 3 Rows)</div>
            <button type="button" id="btn-close-preview" class="btn btn-secondary btn-sm" style="font-size: 10px; padding: 1px 6px;">Close</button>
          </div>
          <div id="llm-preview-content" style="max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 10.5px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; white-space: pre-wrap;"></div>
        </div>

      </div>
    `;

    // 2. Wire Events & Handlers
    const saveChanges = () => {
      this.canvas.onWorkflowChange();
    };

    // 0. Standalone Run & Output Lock Wireup
    const runStandaloneBtn = container.querySelector('#btn-llm-run-standalone');
    const statusTextEl = container.querySelector('#llm-standalone-status-text');
    const tokensPillEl = container.querySelector('#llm-standalone-tokens-pill');
    const lockCheckbox = container.querySelector('#cfg-llm-lock-output');
    const lockLabel = container.querySelector('#cfg-llm-lock-label');

    if (runStandaloneBtn) {
      runStandaloneBtn.addEventListener('click', async () => {
        runStandaloneBtn.disabled = true;
        runStandaloneBtn.innerHTML = `
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="animation: spin 0.8s linear infinite; margin-right: 4px;">
            <circle cx="12" cy="12" r="10" stroke-opacity="0.25"></circle>
            <path d="M12 2a10 10 0 0 1 10 10" stroke-linecap="round"></path>
          </svg>
          <span>Running LLM...</span>
        `;
        if (statusTextEl) statusTextEl.textContent = 'Executing upstream lineage & sending batch to LLM...';
        if (tokensPillEl) tokensPillEl.style.display = 'none';

        saveChanges();

        try {
          const wfData = this.canvas.getWorkflowData();
          const resp = await fetch('/api/run-node', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              workflow: wfData,
              node_id: node.id,
              force_rerun: true
            })
          });

          const res = await resp.json();
          if (res.success) {
            const nodeRes = (res.node_results && res.node_results[node.id]) || {};
            const recCount = nodeRes.record_counts ? (nodeRes.record_counts['O'] || Object.values(nodeRes.record_counts)[0] || 0) : 0;
            const duration = res.total_duration_ms ? `${(res.total_duration_ms / 1000).toFixed(1)}s` : '';
            
            if (statusTextEl) statusTextEl.textContent = `✓ Generated ${recCount.toLocaleString()} records in ${duration}.`;
            
            if (nodeRes.messages && tokensPillEl) {
              const tokenMsg = nodeRes.messages.find(m => m.includes('Tokens:'));
              if (tokenMsg) {
                const tokenMatch = tokenMsg.match(/Tokens:\s*([^\(]+)/);
                if (tokenMatch) {
                  tokensPillEl.textContent = tokenMatch[1].trim();
                  tokensPillEl.style.display = 'inline-block';
                }
              }
            }

            // Sync lock state if node is marked locked
            if (node.is_cached || node.locked) {
              await fetch('/api/node-cache/lock', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ node_id: node.id, locked: true })
              });
            }

            // Immediately display results in Data Review Pane
            if (window.appResultsPanel) {
              window.appResultsPanel.showNodeResults(node);
              if (res.logs) {
                res.logs.forEach(l => window.appResultsPanel.appendLog(l.level || 'INFO', l.message, l.time));
              }
            }

            // Update canvas node execution visuals
            if (this.canvas) {
              this.canvas.updateNodeExecutionVisuals(res.node_results || {});
            }

            if (window.showToast) {
              window.showToast('success', 'LLM Process Finished', `Processed ${recCount.toLocaleString()} records in ${duration}.`);
            }
          } else {
            if (statusTextEl) statusTextEl.textContent = `Error: ${res.error || 'Execution failed'}`;
            if (window.showToast) {
              window.showToast('error', 'Execution Error', res.error || 'Failed to execute LLM node.');
            }
          }
        } catch (err) {
          if (statusTextEl) statusTextEl.textContent = `Error: ${err.message}`;
          if (window.showToast) window.showToast('error', 'Execution Error', err.message);
        } finally {
          runStandaloneBtn.disabled = false;
          runStandaloneBtn.innerHTML = `
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
            <span>Run LLM Tool Only</span>
          `;
        }
      });
    }

    if (lockCheckbox) {
      lockCheckbox.addEventListener('change', async (e) => {
        const locked = e.target.checked;
        node.is_cached = locked;
        node.locked = locked;
        if (this.canvas && this.canvas.cachedNodeIds) {
          if (locked) this.canvas.cachedNodeIds.add(node.id);
          else this.canvas.cachedNodeIds.delete(node.id);
        }

        if (lockLabel) lockLabel.style.color = locked ? '#8b5cf6' : 'var(--text-color)';

        try {
          const resp = await fetch('/api/node-cache/lock', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ node_id: node.id, locked: locked })
          });
          const res = await resp.json();
          if (locked) {
            if (statusTextEl) statusTextEl.textContent = `🔒 Output locked. Subsequent workflow runs will use cached results.`;
            if (window.showToast) {
              window.showToast('info', 'Output Locked', `Tool '${node.name || 'LLM Process'}' locked. Workflow runs will use cached data without calling the LLM.`);
            }
          } else {
            if (statusTextEl) statusTextEl.textContent = `Output unlocked. Next workflow run will re-execute the LLM.`;
            if (window.showToast) {
              window.showToast('info', 'Output Unlocked', `Tool '${node.name || 'LLM Process'}' unlocked.`);
            }
          }
        } catch (err) {
          console.warn('Failed to toggle lock on server:', err);
        }

        // Re-render node element to update lock badge
        if (this.canvas) {
          const existingEl = document.getElementById(`node-elem-${node.id}`);
          if (existingEl) existingEl.remove();
          this.canvas.renderNodeElement(node);
          this.canvas.renderWires();
          this.canvas.updateSelectionVisuals();
          this.canvas.onWorkflowChange();
        }
      });
    }

    // Provider change
    const providerSelect = container.querySelector('#cfg-llm-provider');
    const baseUrlInput = container.querySelector('#cfg-llm-base-url');
    const authRow = container.querySelector('#cfg-llm-auth-row');
    const modelInput = container.querySelector('#cfg-llm-model');

    providerSelect.addEventListener('change', (e) => {
      const p = e.target.value;
      cfg.provider_type = p;
      if (p === 'ollama') {
        baseUrlInput.value = 'http://localhost:11434';
        authRow.style.display = 'none';
        if (!cfg.model || cfg.model.startsWith('gpt-') || cfg.model.startsWith('gemini')) modelInput.value = 'llama3.2';
      } else if (p === 'lm_studio') {
        baseUrlInput.value = 'http://localhost:1234/v1';
        authRow.style.display = 'none';
      } else if (p === 'openai') {
        baseUrlInput.value = 'https://api.openai.com/v1';
        authRow.style.display = 'block';
        if (!cfg.model || cfg.model.startsWith('llama')) modelInput.value = 'gpt-4o-mini';
      } else if (p === 'gemini') {
        baseUrlInput.value = 'https://generativelanguage.googleapis.com';
        authRow.style.display = 'block';
        if (!cfg.model || cfg.model.startsWith('llama')) modelInput.value = 'gemini-2.0-flash';
      } else if (p === 'azure_openai') {
        authRow.style.display = 'block';
      } else {
        authRow.style.display = 'none';
      }
      cfg.connection.base_url = baseUrlInput.value;
      cfg.model = modelInput.value;
      saveChanges();
    });

    baseUrlInput.addEventListener('input', (e) => {
      cfg.connection.base_url = e.target.value.trim();
      saveChanges();
    });

    container.querySelector('#cfg-llm-api-key')?.addEventListener('input', (e) => {
      cfg.connection.api_key = e.target.value.trim();
      saveChanges();
    });

    modelInput.addEventListener('input', (e) => {
      cfg.model = e.target.value.trim();
      saveChanges();
    });

    // Advanced parameters
    const tempSlider = container.querySelector('#cfg-llm-temp');
    const tempDisplay = container.querySelector('#temp-val');
    tempSlider.addEventListener('input', (e) => {
      tempDisplay.textContent = e.target.value;
      cfg.temperature = parseFloat(e.target.value);
      saveChanges();
    });

    container.querySelector('#cfg-llm-max-tokens').addEventListener('input', (e) => {
      cfg.max_tokens = parseInt(e.target.value, 10) || 512;
      saveChanges();
    });

    container.querySelector('#cfg-llm-timeout').addEventListener('input', (e) => {
      cfg.timeout_seconds = parseInt(e.target.value, 10) || 30;
      saveChanges();
    });

    // Test Connection Button
    const testBtn = container.querySelector('#btn-llm-test-conn');
    const testResultEl = container.querySelector('#llm-test-result');
    const statusBadge = container.querySelector('#llm-status-badge');

    testBtn.addEventListener('click', async () => {
      testResultEl.style.display = 'block';
      testResultEl.style.background = 'rgba(139,92,246,0.15)';
      testResultEl.style.color = '#8b5cf6';
      testResultEl.textContent = 'Testing connection...';

      try {
        const resp = await fetch('/api/ai/test-connection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider_type: cfg.provider_type,
            connection: cfg.connection
          })
        });
        const res = await resp.json();
        if (res.success) {
          testResultEl.style.background = 'rgba(34,197,94,0.15)';
          testResultEl.style.color = '#22c55e';
          testResultEl.textContent = `Connected! ${res.message} (${res.models_available} models found)`;
          statusBadge.textContent = 'Connected';
          statusBadge.style.color = '#22c55e';
          statusBadge.style.background = 'rgba(34,197,94,0.15)';
        } else {
          testResultEl.style.background = 'rgba(239,68,68,0.15)';
          testResultEl.style.color = '#ef4444';
          testResultEl.textContent = `Connection failed: ${res.message || 'Unknown error'}`;
          statusBadge.textContent = 'Disconnected';
          statusBadge.style.color = '#ef4444';
          statusBadge.style.background = 'rgba(239,68,68,0.15)';
        }
      } catch (err) {
        testResultEl.style.background = 'rgba(239,68,68,0.15)';
        testResultEl.style.color = '#ef4444';
        testResultEl.textContent = `Error: ${err.message}`;
      }
    });

    // Fetch Models Button
    const fetchModelsBtn = container.querySelector('#btn-llm-fetch-models');
    const modelDatalist = container.querySelector('#cfg-llm-model-list');

    fetchModelsBtn.addEventListener('click', async () => {
      fetchModelsBtn.disabled = true;
      fetchModelsBtn.textContent = 'Fetching...';
      try {
        const resp = await fetch('/api/ai/models', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider_type: cfg.provider_type,
            connection: cfg.connection
          })
        });
        const res = await resp.json();
        if (res.success && res.models && res.models.length > 0) {
          modelDatalist.innerHTML = '';
          res.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.name;
            opt.textContent = m.family ? `${m.name} (${m.family})` : m.name;
            modelDatalist.appendChild(opt);
          });
          if (!modelInput.value && res.models[0]) {
            modelInput.value = res.models[0].name;
            cfg.model = res.models[0].name;
            saveChanges();
          }
          alert(`Discovered ${res.models.length} model(s) from ${cfg.provider_type}!`);
        } else {
          alert(`No models returned: ${res.error || 'Server responded with 0 models'}`);
        }
      } catch (err) {
        alert(`Failed to fetch models: ${err.message}`);
      } finally {
        fetchModelsBtn.disabled = false;
        fetchModelsBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 3px;"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>Fetch`;
      }
    });

    // Prompts
    const sysPromptInput = container.querySelector('#cfg-llm-sys-prompt');
    const userPromptInput = container.querySelector('#cfg-llm-user-prompt');

    sysPromptInput.addEventListener('input', (e) => {
      cfg.system_prompt = e.target.value;
      saveChanges();
    });

    userPromptInput.addEventListener('input', (e) => {
      cfg.user_prompt_template = e.target.value;
      saveChanges();
    });

    // Column Chips Click -> Insert {{[Col]}} at cursor
    container.querySelectorAll('.btn-col-chip').forEach(btn => {
      btn.addEventListener('click', () => {
        const col = btn.dataset.col;
        const tag = `{{[${col}]}}`;
        const start = userPromptInput.selectionStart || userPromptInput.value.length;
        const end = userPromptInput.selectionEnd || userPromptInput.value.length;
        const val = userPromptInput.value;
        userPromptInput.value = val.substring(0, start) + tag + val.substring(end);
        userPromptInput.focus();
        userPromptInput.selectionStart = userPromptInput.selectionEnd = start + tag.length;
        cfg.user_prompt_template = userPromptInput.value;
        saveChanges();
      });
    });

    // Preview Prompt Button
    const previewBtn = container.querySelector('#btn-llm-preview-prompt');
    const previewModal = container.querySelector('#llm-preview-modal');
    const previewContent = container.querySelector('#llm-preview-content');
    const closePreviewBtn = container.querySelector('#btn-close-preview');

    closePreviewBtn.addEventListener('click', () => {
      previewModal.style.display = 'none';
    });

    previewBtn.addEventListener('click', async () => {
      previewModal.style.display = 'block';
      previewContent.textContent = 'Rendering preview with upstream data...';

      // Find upstream node ID to pull cached data if available
      let upstreamNodeId = null;
      if (this.canvas && this.canvas.connections) {
        const conn = this.canvas.connections.find(c => c.target === node.id && (!c.targetHandle || c.targetHandle === 'I'));
        if (conn) upstreamNodeId = conn.source;
      }

      try {
        const resp = await fetch('/api/ai/preview-prompt', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            node_id: upstreamNodeId,
            user_prompt_template: cfg.user_prompt_template,
            system_prompt: cfg.system_prompt,
            rag_context: cfg.rag_context
          })
        });
        const res = await resp.json();
        if (res.success && res.previews && res.previews.length > 0) {
          previewContent.innerHTML = res.previews.map((p, idx) => `
<div style="border-bottom: 1px dashed var(--border-color); padding-bottom: 8px; margin-bottom: 8px;">
  <span style="color: #8b5cf6; font-weight: bold;">[Record #${idx + 1}]</span> (${p.total_chars} chars)
  <div style="color: var(--text-muted); font-size: 10px; margin-top: 2px;">System:</div>
  <div style="background: rgba(255,255,255,0.03); padding: 4px; border-radius: 3px;">${this.escapeHtml(p.system_prompt)}</div>
  <div style="color: var(--text-muted); font-size: 10px; margin-top: 4px;">User:</div>
  <div style="background: rgba(255,255,255,0.03); padding: 4px; border-radius: 3px;">${this.escapeHtml(p.user_prompt)}</div>
</div>
          `).join('');
        } else {
          // If no upstream run cached, perform client-side template render with mock/column names
          const mockRow = {};
          cols.forEach(c => {
            const name = typeof c === 'string' ? c : (c.name || c.field || '');
            mockRow[name] = `<${name}_val>`;
          });
          let rendered = cfg.user_prompt_template;
          Object.keys(mockRow).forEach(k => {
            rendered = rendered.split(`{{[${k}]}}`).join(mockRow[k]);
          });
          previewContent.innerHTML = `
<div style="color: var(--text-muted); margin-bottom: 4px;">Note: Upstream data cache not yet generated. Showing placeholder render:</div>
<div style="background: rgba(255,255,255,0.03); padding: 6px; border-radius: 3px;">${this.escapeHtml(rendered)}</div>
          `;
        }
      } catch (err) {
        previewContent.textContent = `Preview error: ${err.message}`;
      }
    });

    // RAG Controls
    const ragEnable = container.querySelector('#cfg-llm-rag-enable');
    const ragBody = container.querySelector('#cfg-llm-rag-body');
    const ragSource = container.querySelector('#cfg-llm-rag-source');
    const ragPlacement = container.querySelector('#cfg-llm-rag-placement');
    const ragSrcStatic = container.querySelector('#cfg-rag-src-static');
    const ragSrcCol = container.querySelector('#cfg-rag-src-column');
    const ragSrcFile = container.querySelector('#cfg-rag-src-file');

    ragEnable.addEventListener('change', (e) => {
      cfg.rag_context.enabled = e.target.checked;
      ragBody.style.display = cfg.rag_context.enabled ? 'block' : 'none';
      saveChanges();
    });

    ragSource.addEventListener('change', (e) => {
      const src = e.target.value;
      cfg.rag_context.source = src;
      ragSrcStatic.style.display = src === 'static' ? 'block' : 'none';
      ragSrcCol.style.display = src === 'column' ? 'block' : 'none';
      ragSrcFile.style.display = src === 'file' ? 'block' : 'none';
      saveChanges();
    });

    ragPlacement.addEventListener('change', (e) => {
      cfg.rag_context.placement = e.target.value;
      saveChanges();
    });

    container.querySelector('#cfg-llm-rag-text').addEventListener('input', (e) => {
      cfg.rag_context.text = e.target.value;
      saveChanges();
    });

    container.querySelector('#cfg-llm-rag-col').addEventListener('change', (e) => {
      cfg.rag_context.column = e.target.value;
      saveChanges();
    });

    container.querySelector('#cfg-llm-rag-file').addEventListener('input', (e) => {
      cfg.rag_context.file_path = e.target.value;
      saveChanges();
    });

    // Output Mode & JSON table
    const outMode = container.querySelector('#cfg-llm-out-mode');
    const outCol = container.querySelector('#cfg-llm-out-col');
    const jsonContainer = container.querySelector('#cfg-llm-json-container');
    const jsonFieldsList = container.querySelector('#json-fields-list');

    outMode.addEventListener('change', (e) => {
      cfg.output_mode = e.target.value;
      jsonContainer.style.display = cfg.output_mode === 'json_parse' ? 'block' : 'none';
      saveChanges();
    });

    outCol.addEventListener('input', (e) => {
      cfg.output_column = e.target.value.trim() || 'AI_Response';
      saveChanges();
    });

    const renderJsonFields = () => {
      jsonFieldsList.innerHTML = '';
      if (!cfg.json_fields || cfg.json_fields.length === 0) {
        jsonFieldsList.innerHTML = '<span style="font-size: 10px; color: var(--text-muted);">No fields mapped. Click "+ Add Field" to map JSON keys.</span>';
        return;
      }
      cfg.json_fields.forEach((item, idx) => {
        const row = document.createElement('div');
        row.style.display = 'flex';
        row.style.gap = '6px';
        row.style.alignItems = 'center';
        row.innerHTML = `
          <input type="text" class="form-control form-control-sm json-key" value="${this.escapeHtml(item.field_name || '')}" placeholder="JSON key (e.g. sentiment)" style="font-size: 10.5px; flex: 1;">
          <span style="font-size: 10px; color: var(--text-muted);">&rarr;</span>
          <input type="text" class="form-control form-control-sm json-col" value="${this.escapeHtml(item.output_col || '')}" placeholder="Output column name" style="font-size: 10.5px; flex: 1;">
          <button type="button" class="btn btn-secondary btn-sm btn-del-json" style="padding: 1px 6px; font-size: 10px; color: #ef4444;">&times;</button>
        `;
        row.querySelector('.json-key').addEventListener('input', (e) => {
          item.field_name = e.target.value.trim();
          saveChanges();
        });
        row.querySelector('.json-col').addEventListener('input', (e) => {
          item.output_col = e.target.value.trim();
          saveChanges();
        });
        row.querySelector('.btn-del-json').addEventListener('click', () => {
          cfg.json_fields.splice(idx, 1);
          renderJsonFields();
          saveChanges();
        });
        jsonFieldsList.appendChild(row);
      });
    };

    renderJsonFields();

    container.querySelector('#btn-add-json-field').addEventListener('click', () => {
      cfg.json_fields.push({ field_name: '', output_col: '' });
      renderJsonFields();
      saveChanges();
    });

    // Execution knobs
    container.querySelector('#cfg-llm-on-error').addEventListener('change', (e) => {
      cfg.on_error = e.target.value;
      saveChanges();
    });

    container.querySelector('#cfg-llm-concurrency').addEventListener('input', (e) => {
      cfg.concurrency = parseInt(e.target.value, 10) || 3;
      saveChanges();
    });

    container.querySelector('#cfg-llm-rps').addEventListener('input', (e) => {
      cfg.rate_limit_rps = parseFloat(e.target.value) || 10;
      saveChanges();
    });

    container.querySelector('#cfg-llm-inc-tokens').addEventListener('change', (e) => {
      cfg.include_token_columns = e.target.checked;
      saveChanges();
    });
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
}


