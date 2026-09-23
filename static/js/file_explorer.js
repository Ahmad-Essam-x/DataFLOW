/**
 * Interactive File & Directory Explorer Modal Component for Antigravity DataFlow.
 * Allows users to browse workspace directories, create folders, select target files or output directories.
 */
class FileExplorerModal {
  constructor() {
    this.modalEl = null;
    this.currentPath = "";
    this.parentPath = null;
    this.workspaceRoot = "";
    this.dataDir = "";
    this.outputDir = "";
    this.folders = [];
    this.files = [];
    this.selectedItem = null;
    this.mode = "all"; // "file", "directory", or "all"
    this.onSelectCallback = null;

    this.initDOM();
  }

  initDOM() {
    if (document.getElementById("file-explorer-modal")) {
      this.modalEl = document.getElementById("file-explorer-modal");
      return;
    }

    const modalHtml = `
      <div id="file-explorer-modal" class="app-modal" style="display: none;">
        <div class="modal-backdrop" id="fe-backdrop"></div>
        <div class="modal-dialog modal-dialog-lg" style="width: 720px; max-width: 95vw;">
          <div class="modal-header">
            <div class="modal-title-wrap">
              <div class="modal-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
              </div>
              <h2 id="fe-title">File & Directory Explorer</h2>
            </div>
            <button class="modal-close-btn" id="fe-close-btn">&times;</button>
          </div>

          <div class="modal-body" style="gap: 12px; padding: 16px;">
            <!-- Path Toolbar -->
            <div style="display: flex; gap: 6px; align-items: center;">
              <button type="button" class="btn btn-secondary btn-sm" id="fe-btn-up" title="Up one level" style="padding: 6px 10px;">
                ⬆️ Up
              </button>
              <input type="text" class="form-control" id="fe-path-input" style="flex: 1; font-family: var(--font-mono); font-size: 12px;" placeholder="Folder path...">
              <button type="button" class="btn btn-secondary btn-sm" id="fe-btn-go" style="padding: 6px 10px;">Go</button>
            </div>

            <!-- Quick Shortcuts -->
            <div style="display: flex; gap: 6px; align-items: center; font-size: 11px;">
              <span style="color: var(--text-muted); font-weight: 500;">Shortcuts:</span>
              <button type="button" class="btn btn-secondary btn-sm" id="fe-sc-root" style="padding: 2px 8px; font-size: 11px;">🏠 Root</button>
              <button type="button" class="btn btn-secondary btn-sm" id="fe-sc-data" style="padding: 2px 8px; font-size: 11px;">📂 Data</button>
              <button type="button" class="btn btn-secondary btn-sm" id="fe-sc-outputs" style="padding: 2px 8px; font-size: 11px;">📤 Outputs</button>
            </div>

            <!-- File List Container -->
            <div id="fe-list-box" style="height: 280px; overflow-y: auto; background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: 6px; padding: 4px;">
              <div id="fe-loading" style="padding: 20px; text-align: center; color: var(--text-muted);">Loading directory contents...</div>
              <div id="fe-items-container"></div>
            </div>

            <!-- Bottom Selection Bar -->
            <div style="display: flex; gap: 8px; align-items: center; margin-top: 4px;">
              <div style="flex: 1;">
                <label style="font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; display: block;">File / Folder Name</label>
                <input type="text" class="form-control" id="fe-target-name" placeholder="Target name or filename...">
              </div>
              <div style="width: 140px;" id="fe-ext-filter-wrap">
                <label style="font-size: 11px; color: var(--text-secondary); margin-bottom: 2px; display: block;">Filter Type</label>
                <select class="form-control" id="fe-ext-filter">
                  <option value="all">All Files (*.*)</option>
                  <option value=".csv">CSV (*.csv)</option>
                  <option value=".xlsx">Excel (*.xlsx)</option>
                  <option value=".tsv">TSV (*.tsv)</option>
                  <option value=".json">JSON (*.json)</option>
                  <option value=".parquet">Parquet (*.parquet)</option>
                </select>
              </div>
            </div>
          </div>

          <div class="modal-footer" style="padding: 12px 20px;">
            <button type="button" class="btn btn-secondary" id="fe-btn-cancel">Cancel</button>
            <button type="button" class="btn btn-primary" id="fe-btn-confirm">Select Path</button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML("beforeend", modalHtml);
    this.modalEl = document.getElementById("file-explorer-modal");
    this.bindEvents();
  }

  bindEvents() {
    const backdrop = document.getElementById("fe-backdrop");
    const closeBtn = document.getElementById("fe-close-btn");
    const cancelBtn = document.getElementById("fe-btn-cancel");
    const confirmBtn = document.getElementById("fe-btn-confirm");
    const btnUp = document.getElementById("fe-btn-up");
    const btnGo = document.getElementById("fe-btn-go");
    const pathInput = document.getElementById("fe-path-input");
    const scRoot = document.getElementById("fe-sc-root");
    const scData = document.getElementById("fe-sc-data");
    const scOutputs = document.getElementById("fe-sc-outputs");
    const extFilter = document.getElementById("fe-ext-filter");

    const close = () => this.close();

    backdrop.addEventListener("click", close);
    closeBtn.addEventListener("click", close);
    cancelBtn.addEventListener("click", close);

    btnUp.addEventListener("click", () => {
      if (this.parentPath) this.loadDirectory(this.parentPath);
    });

    btnGo.addEventListener("click", () => {
      const val = pathInput.value.trim();
      if (val) this.loadDirectory(val);
    });

    pathInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = pathInput.value.trim();
        if (val) this.loadDirectory(val);
      }
    });

    scRoot.addEventListener("click", () => this.loadDirectory(this.workspaceRoot));
    scData.addEventListener("click", () => this.loadDirectory(this.dataDir));
    scOutputs.addEventListener("click", () => this.loadDirectory(this.outputDir));

    extFilter.addEventListener("change", () => this.renderItems());

    confirmBtn.addEventListener("click", () => {
      const targetNameInput = document.getElementById("fe-target-name").value.trim();
      let chosenPath = this.currentPath;

      if (targetNameInput) {
        if (targetNameInput.includes("/") || targetNameInput.includes("\\") || targetNameInput.startsWith("C:")) {
          chosenPath = targetNameInput;
        } else {
          chosenPath = `${this.currentPath}/${targetNameInput}`;
        }
      } else if (this.selectedItem) {
        chosenPath = this.selectedItem.path;
      }

      if (this.onSelectCallback) {
        this.onSelectCallback(chosenPath, {
          currentPath: this.currentPath,
          targetName: targetNameInput,
          selectedItem: this.selectedItem
        });
      }
      this.close();
    });
  }

  async open(options = {}) {
    const {
      title = "File & Directory Explorer",
      mode = "all", // "file", "directory", "all"
      initialPath = "",
      defaultFilename = "",
      onSelect = null
    } = options;

    this.mode = mode;
    this.onSelectCallback = onSelect;
    this.selectedItem = null;

    document.getElementById("fe-title").textContent = title;
    document.getElementById("fe-target-name").value = defaultFilename;
    document.getElementById("fe-btn-confirm").textContent = mode === "directory" ? "Select Directory" : "Select Path";

    this.modalEl.style.display = "flex";
    await this.loadDirectory(initialPath);
  }

  close() {
    if (this.modalEl) this.modalEl.style.display = "none";
  }

  async loadDirectory(pathStr = "") {
    const loadingEl = document.getElementById("fe-loading");
    const containerEl = document.getElementById("fe-items-container");
    loadingEl.style.display = "block";
    containerEl.innerHTML = "";

    try {
      const res = await fetch(`/api/browse?path=${encodeURIComponent(pathStr)}`);
      const data = await res.json();

      if (data.success) {
        this.currentPath = data.current_path;
        this.parentPath = data.parent_path;
        this.workspaceRoot = data.workspace_root;
        this.dataDir = data.data_dir;
        this.outputDir = data.output_dir;
        this.folders = data.folders || [];
        this.files = data.files || [];

        document.getElementById("fe-path-input").value = this.currentPath;
        document.getElementById("fe-btn-up").disabled = !this.parentPath;

        this.renderItems();
      } else {
        containerEl.innerHTML = `<div style="padding: 16px; color: var(--color-error)">Error loading path: ${data.error}</div>`;
      }
    } catch (err) {
      containerEl.innerHTML = `<div style="padding: 16px; color: var(--color-error)">Failed to connect: ${err.message}</div>`;
    } finally {
      loadingEl.style.display = "none";
    }
  }

  renderItems() {
    const containerEl = document.getElementById("fe-items-container");
    const filterExt = document.getElementById("fe-ext-filter").value;
    containerEl.innerHTML = "";

    let itemsHtml = "";

    // Folders first
    this.folders.forEach(f => {
      itemsHtml += `
        <div class="fe-item fe-folder" data-path="${f.path}" style="display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 4px; cursor: pointer; user-select: none;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>
          <span style="font-weight: 500; font-size: 12px; color: var(--text-primary); flex: 1;">${f.name}</span>
          <span style="font-size: 10px; color: var(--text-muted);">Folder</span>
        </div>
      `;
    });

    // Files second (filtered)
    if (this.mode !== "directory") {
      this.files.forEach(file => {
        if (filterExt !== "all" && file.extension !== filterExt) return;

        itemsHtml += `
          <div class="fe-item fe-file" data-path="${file.path}" data-name="${file.name}" style="display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 4px; cursor: pointer; user-select: none;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            <span style="font-size: 12px; color: var(--text-primary); flex: 1;">${file.name}</span>
            <span style="font-size: 10px; color: var(--text-muted);">${file.size_kb} KB</span>
          </div>
        `;
      });
    }

    if (!itemsHtml) {
      itemsHtml = `<div style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 12px;">This directory is empty</div>`;
    }

    containerEl.innerHTML = itemsHtml;

    // Item click and double-click listeners
    containerEl.querySelectorAll(".fe-item").forEach(itemEl => {
      itemEl.addEventListener("click", () => {
        containerEl.querySelectorAll(".fe-item").forEach(el => el.style.background = "");
        itemEl.style.background = "var(--bg-surface-elevated)";

        const isFolder = itemEl.classList.contains("fe-folder");
        const path = itemEl.getAttribute("data-path");
        const name = itemEl.getAttribute("data-name") || "";

        this.selectedItem = { path, isFolder, name };
        if (!isFolder && name) {
          document.getElementById("fe-target-name").value = name;
        }
      });

      itemEl.addEventListener("dblclick", () => {
        const isFolder = itemEl.classList.contains("fe-folder");
        const path = itemEl.getAttribute("data-path");

        if (isFolder) {
          this.loadDirectory(path);
        } else {
          document.getElementById("fe-btn-confirm").click();
        }
      });
    });
  }
}

// Global File Explorer instance
window.fileExplorer = new FileExplorerModal();
