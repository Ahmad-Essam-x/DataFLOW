/**
 * Top Menu Bar (File, Edit, View, Options, Help).
 * Provides authentic desktop application menubar with nested submenus,
 * keyboard accelerators, checkmark states, user settings, and recent workflows.
 */

class MenuBar {
  constructor() {
    this.menubar = document.getElementById('main-menubar');
    this.activeMenu = null;
    this.isMenuOpen = false;

    this.initEvents();
    this.syncMenuStates();
    this.renderRecentWorkflows();
  }

  initEvents() {
    if (!this.menubar) return;

    // 1. Click on Menubar buttons
    const menuButtons = this.menubar.querySelectorAll('.menubar-btn');
    menuButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const item = btn.closest('.menubar-item');
        const menuName = item.dataset.menu;

        if (this.isMenuOpen && this.activeMenu === menuName) {
          this.closeAllMenus();
        } else {
          this.openMenu(menuName);
        }
      });

      // Hover over other buttons when a menu is already open
      btn.addEventListener('mouseenter', () => {
        if (this.isMenuOpen) {
          const item = btn.closest('.menubar-item');
          const menuName = item.dataset.menu;
          if (this.activeMenu !== menuName) {
            this.openMenu(menuName);
          }
        }
      });
    });

    // 2. Click on menu action items
    document.querySelectorAll('.menubar-action[data-action]').forEach(actionBtn => {
      actionBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const action = actionBtn.dataset.action;
        this.closeAllMenus();
        this.handleAction(action);
      });
    });

    // 3. Wire Probe Status Pill in Menubar (if standalone pill present)
    const probePill = document.querySelector('.menubar-probe-pill');
    if (probePill) {
      probePill.addEventListener('click', (e) => {
        e.stopPropagation();
        if (window.appCanvas) {
          window.appCanvas.setWireProbesEnabled(!window.appCanvas.wireProbesEnabled);
          this.syncMenuStates();
        }
      });
    }

    // 4. Click outside to dismiss menus
    document.addEventListener('click', (e) => {
      if (this.menubar && !this.menubar.contains(e.target)) {
        this.closeAllMenus();
      }
    });

    // 5. Global Keyboard Accelerators
    window.addEventListener('keydown', (e) => {
      const activeTag = document.activeElement ? document.activeElement.tagName.toLowerCase() : '';
      const isInput = activeTag === 'input' || activeTag === 'textarea' || (document.activeElement && document.activeElement.isContentEditable);

      // Escape closes menus and modals
      if (e.key === 'Escape') {
        if (this.isMenuOpen) {
          this.closeAllMenus();
          e.preventDefault();
        }
        this.closeAllModals();
        return;
      }

      // Alt key focuses or toggles menu bar (standard Windows desktop shortcut)
      if (e.key === 'Alt' && !e.ctrlKey && !e.metaKey && !isInput) {
        e.preventDefault();
        if (this.isMenuOpen) {
          this.closeAllMenus();
        } else {
          this.openMenu('file');
        }
        return;
      }

      // Alt+F, Alt+E, Alt+V, Alt+O, Alt+H
      if (e.altKey && !e.ctrlKey && !e.metaKey) {
        const key = e.key.toLowerCase();
        if (key === 'f') { e.preventDefault(); this.openMenu('file'); return; }
        if (key === 'e') { e.preventDefault(); this.openMenu('edit'); return; }
        if (key === 'v') { e.preventDefault(); this.openMenu('view'); return; }
        if (key === 'o') { e.preventDefault(); this.openMenu('options'); return; }
        if (key === 'h') { e.preventDefault(); this.openMenu('help'); return; }
      }

      // Ctrl+Shift+E for Export Workflow to SQL
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'e') {
        e.preventDefault();
        this.handleAction('file:export-sql');
        return;
      }

      // F1 for Shortcuts Modal
      if (e.key === 'F1') {
        e.preventDefault();
        this.openModal('modal-shortcuts');
        return;
      }

    });

    // 6. Modal close handlers
    document.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => {
        const modalId = btn.dataset.close;
        const modal = document.getElementById(modalId);
        if (modal) modal.style.display = 'none';
      });
    });

    document.querySelectorAll('.app-modal .modal-backdrop').forEach(backdrop => {
      backdrop.addEventListener('click', () => {
        const modal = backdrop.closest('.app-modal');
        if (modal) modal.style.display = 'none';
      });
    });

    // 7. User Settings Modal Save
    const saveSettingsBtn = document.getElementById('btn-save-settings');
    if (saveSettingsBtn) {
      saveSettingsBtn.addEventListener('click', () => {
        this.saveUserSettings();
      });
    }

    // 8. Settings Modal Tab Navigation
    document.querySelectorAll('.settings-tab-btn').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        const targetTabId = tabBtn.dataset.settingsTab;
        document.querySelectorAll('.settings-tab-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.settings-tab-pane').forEach(p => {
          p.classList.remove('active');
          p.style.display = 'none';
        });
        tabBtn.classList.add('active');
        const pane = document.getElementById(targetTabId);
        if (pane) {
          pane.classList.add('active');
          pane.style.display = 'flex';
        }
      });
    });
  }

  openMenu(menuName) {
    this.closeAllMenus();
    const item = this.menubar.querySelector(`.menubar-item[data-menu="${menuName}"]`);
    if (!item) return;

    const btn = item.querySelector('.menubar-btn');
    const dropdown = item.querySelector('.menubar-dropdown');
    if (btn && dropdown) {
      btn.classList.add('active');
      dropdown.classList.add('show');
      this.activeMenu = menuName;
      this.isMenuOpen = true;
      this.syncMenuStates();
    }
  }

  closeAllMenus() {
    if (!this.menubar) return;
    this.menubar.querySelectorAll('.menubar-btn').forEach(b => b.classList.remove('active'));
    this.menubar.querySelectorAll('.menubar-dropdown').forEach(d => d.classList.remove('show'));
    this.activeMenu = null;
    this.isMenuOpen = false;
  }

  syncMenuStates() {
    if (!window.appCanvas) return;

    // 1. Wire Probes Checkmark & Status Pill
    const enabled = window.appCanvas.wireProbesEnabled;
    const checkWire = document.getElementById('check-view-wire-probes') || document.getElementById('check-wire-probes');
    if (checkWire) {
      checkWire.textContent = enabled ? '✓' : '';
    }
    const probePill = document.querySelector('.menubar-probe-pill');
    if (probePill) {
      const txt = probePill.querySelector('.probe-text');
      if (txt) txt.textContent = `Wire Probes: ${enabled ? 'ON' : 'OFF'}`;
      probePill.classList.toggle('disabled', !enabled);
    }

    // 1b. Execution Status Badges Duration Checkmarks
    const curBadgeDuration = String(window.appCanvas.nodeBadgeDuration || '3000');
    ['3000', '5000', '10000', 'always', 'off'].forEach(val => {
      const chk = document.getElementById(`check-badge-${val}`);
      if (chk) {
        chk.textContent = curBadgeDuration === val ? '✓' : '';
      }
    });

    // 2. Palette visibility
    const palette = document.getElementById('tool-palette-ribbon');
    const checkPalette = document.getElementById('check-view-palette');
    if (palette && checkPalette) {
      const isVisible = palette.style.display !== 'none';
      checkPalette.textContent = isVisible ? '✓' : '';
    }

    // 3. Config panel visibility
    const config = document.getElementById('config-panel');
    const checkConfig = document.getElementById('check-view-config');
    if (config && checkConfig) {
      const isVisible = config.style.display !== 'none' && !config.classList.contains('collapsed');
      checkConfig.textContent = isVisible ? '✓' : '';
    }

    // 4. Results panel visibility
    const results = document.getElementById('results-panel');
    const checkResults = document.getElementById('check-view-results');
    if (results && checkResults) {
      const isVisible = !results.classList.contains('collapsed');
      checkResults.textContent = isVisible ? '✓' : '';
    }

    // 5. In-grid histograms checkmark
    const checkHist = document.getElementById('check-view-histograms');
    if (checkHist && window.appResultsPanel) {
      checkHist.textContent = window.appResultsPanel.showHistograms ? '✓' : '';
    }

    // 6. Overview window (MiniMap) checkmark
    const checkOverview = document.getElementById('check-view-overview');
    if (checkOverview) {
      const isOverviewVisible = window.appMiniMap ? window.appMiniMap.visible :
        (window.userSettings ? window.userSettings.get('minimap_visible', true) : (localStorage.getItem('dataflow_overview_enabled') !== 'false'));
      checkOverview.textContent = isOverviewVisible ? '✓' : '';
    }

    // 7. Node Tooltips checkmark
    const checkNodeTooltips = document.getElementById('check-view-node-tooltips');
    if (checkNodeTooltips) {
      const nodeTooltipsOn = window.appCanvas ? window.appCanvas.nodeTooltipsEnabled :
        (window.userSettings ? Boolean(window.userSettings.get('node_tooltips_enabled', true)) : true);
      checkNodeTooltips.textContent = nodeTooltipsOn ? '✓' : '';
    }

    // 8. Wireless Connection Tooltips checkmark
    const checkWirelessTooltips = document.getElementById('check-view-wireless-tooltips');
    if (checkWirelessTooltips) {
      const wirelessTooltipsOn = window.appCanvas ? window.appCanvas.wirelessTooltipsEnabled :
        (window.userSettings ? Boolean(window.userSettings.get('wireless_tooltips_enabled', true)) : true);
      checkWirelessTooltips.textContent = wirelessTooltipsOn ? '✓' : '';
    }
  }

  handleAction(action) {
    if (window.app && typeof window.app.executeCommand === 'function') {
      window.app.executeCommand(action);
    } else {
      console.warn('Application command registry not available for action:', action);
    }
  }

  // --------------------------------------------------------------------
  // Recent Workflows History
  // --------------------------------------------------------------------
  addRecentWorkflow(name, path = null, wfData = null) {
    if (!name || typeof name !== 'string') return;
    try {
      if (path && typeof path === 'object' && wfData === null) {
        wfData = path;
        path = null;
      }
      let recent = JSON.parse(localStorage.getItem('dataflow_recent_workflows') || '[]');
      const cleanPath = (typeof path === 'string' && path) ? path : `workflows/${name.replace(/\s+/g, '_').toLowerCase()}.json`;
      // Remove duplicate if already in list
      recent = recent.filter(r => r.name.toLowerCase() !== name.toLowerCase());
      recent.unshift({
        name: name,
        path: cleanPath,
        timestamp: Date.now(),
        data: wfData
      });
      // Keep strictly the last 5 items
      recent = recent.slice(0, 5);
      localStorage.setItem('dataflow_recent_workflows', JSON.stringify(recent));
      this.renderRecentWorkflows();
    } catch (e) {
      console.warn('Could not save recent workflow:', e);
    }
  }

  renderRecentWorkflows() {
    const list = document.getElementById('menu-recent-list');
    if (!list) return;

    try {
      const recent = JSON.parse(localStorage.getItem('dataflow_recent_workflows') || '[]');
      if (recent.length === 0) {
        list.innerHTML = `<div class="menu-empty-note">No recent workflows</div>`;
        return;
      }

      let html = recent.map((r, idx) => {
        const timeAgo = this.formatTimeAgo(r.timestamp);
        const pathDisplay = r.path || 'Local Workflow';
        return `
          <button class="menubar-action btn-recent-item" data-idx="${idx}" title="${this.escapeHtml(r.name)} (${this.escapeHtml(pathDisplay)})">
            <span class="action-icon">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
            </span>
            <div class="recent-info-wrap">
              <span class="recent-name">${this.escapeHtml(r.name)}</span>
              <span class="recent-path">${this.escapeHtml(pathDisplay)}</span>
            </div>
            <span class="recent-time">${timeAgo}</span>
          </button>
        `;
      }).join('');

      html += `
        <div class="menubar-divider"></div>
        <button class="menubar-action btn-clear-recent" id="btn-clear-recent-workflows">
          <span class="action-icon">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </span>
          <span class="action-label">Clear Recent Workflows</span>
        </button>
      `;

      list.innerHTML = html;

      list.querySelectorAll('.btn-recent-item').forEach(btn => {
        btn.addEventListener('click', (e) => {
          e.stopPropagation();
          const idx = parseInt(btn.dataset.idx, 10);
          const item = recent[idx];
          if (item) {
            this.loadRecentItem(item);
          }
          this.closeAllMenus();
        });
      });

      const clearBtn = document.getElementById('btn-clear-recent-workflows');
      if (clearBtn) {
        clearBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          localStorage.removeItem('dataflow_recent_workflows');
          this.renderRecentWorkflows();
          this.closeAllMenus();
          if (window.showToast) window.showToast('info', 'Recent List Cleared', 'Cleared recent workflows history.');
        });
      }
    } catch (e) {
      list.innerHTML = `<div class="menu-empty-note">No recent workflows</div>`;
    }
  }

  async loadRecentItem(item) {
    if (!item) return;

    // Refresh position to top
    this.addRecentWorkflow(item.name, item.path, item.data);

    if (item.data && window.appCanvas) {
      if (typeof window.handleWorkflowLoaded === 'function') {
        window.handleWorkflowLoaded(item.data, item.name);
      } else {
        window.appCanvas.loadWorkflow(item.data);
        const nameInput = document.getElementById('workflow-name-input');
        if (nameInput) nameInput.value = item.name;
        if (window.appResultsPanel) window.appResultsPanel.clear();
        if (window.showToast) window.showToast('success', 'Workflow Loaded', `Opened '${item.name}'.`);
      }
      return;
    }

    // Try loading via path from server
    if (item.path) {
      try {
        const filename = item.path.split('/').pop().split('\\').pop();
        let res = await fetch(`/api/workflow/${encodeURIComponent(filename)}`);
        if (!res.ok) {
          res = await fetch(`/api/sample-workflow/${encodeURIComponent(filename)}`);
        }
        if (res.ok) {
          const wfData = await res.json();
          if (typeof window.handleWorkflowLoaded === 'function') {
            window.handleWorkflowLoaded(wfData, item.name);
          } else if (window.appCanvas) {
            window.appCanvas.loadWorkflow(wfData);
          }
          if (window.showToast) window.showToast('success', 'Workflow Loaded', `Opened '${item.name}'.`);
          return;
        }
      } catch (err) {
        console.warn('Failed to fetch recent workflow file:', err);
      }
    }

    // Fallback: reload with ?open query parameter
    window.location.href = `/?open=${encodeURIComponent(item.name)}`;
  }

  formatTimeAgo(ts) {
    if (!ts) return '';
    const diff = Math.floor((Date.now() - ts) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  // --------------------------------------------------------------------
  // Modals & Settings Management
  // --------------------------------------------------------------------
  openModal(modalId) {
    this.closeAllModals();
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.style.display = 'flex';
    }
  }

  closeAllModals() {
    document.querySelectorAll('.app-modal').forEach(m => m.style.display = 'none');
  }

  openUserSettingsModal() {
    const modal = document.getElementById('modal-user-settings');
    if (!modal) return;

    // Reset active tab to Tab 1: Canvas & Visuals
    const firstTabBtn = modal.querySelector('.settings-tab-btn[data-settings-tab="tab-canvas-visuals"]');
    if (firstTabBtn) firstTabBtn.click();

    // Tab 1: Canvas & Visuals
    const wireCheck = document.getElementById('setting-wire-probes');
    if (wireCheck && window.appCanvas) {
      wireCheck.checked = window.appCanvas.wireProbesEnabled;
    }

    const nodeTipsCheck = document.getElementById('setting-node-tooltips');
    if (nodeTipsCheck && window.appCanvas) {
      nodeTipsCheck.checked = window.appCanvas.nodeTooltipsEnabled;
    }

    const wirelessTipsCheck = document.getElementById('setting-wireless-tooltips');
    if (wirelessTipsCheck && window.appCanvas) {
      wirelessTipsCheck.checked = window.appCanvas.wirelessTooltipsEnabled;
    }

    const snapSelect = document.getElementById('setting-grid-snap');
    if (snapSelect && window.appCanvas) {
      snapSelect.value = String(window.appCanvas.gridSnapSize || 0);
    }

    const wireStyleSelect = document.getElementById('setting-wire-style');
    if (wireStyleSelect && window.appCanvas) {
      wireStyleSelect.value = window.appCanvas.wireStyle || 'bezier';
    }

    const durationSelect = document.getElementById('setting-node-badge-duration');
    if (durationSelect && window.appCanvas) {
      durationSelect.value = String(window.appCanvas.nodeBadgeDuration || '3000');
    }

    // Tab 2: Engine & Memory
    const engineSelect = document.getElementById('setting-execution-engine');
    if (engineSelect && window.userSettings) {
      const isAmp = window.userSettings.get('use_amp_engine', true);
      engineSelect.value = isAmp ? 'amp' : 'classic';
    }

    const threadsSelect = document.getElementById('setting-engine-threads');
    if (threadsSelect && window.userSettings) {
      threadsSelect.value = String(window.userSettings.get('max_engine_threads', 'auto'));
    }

    const autoCacheCheck = document.getElementById('setting-auto-cache-upstream');
    if (autoCacheCheck && window.appCanvas) {
      autoCacheCheck.checked = window.appCanvas.autoCacheUpstream;
    }

    const pageSizeSelect = document.getElementById('setting-page-size');
    if (pageSizeSelect && window.appResultsPanel) {
      pageSizeSelect.value = String(window.appResultsPanel.pageSize || 100);
    }

    const timeoutSelect = document.getElementById('setting-execution-timeout');
    if (timeoutSelect) {
      timeoutSelect.value = window.userSettings
        ? String(window.userSettings.get('execution_timeout', 60))
        : (localStorage.getItem('dataflow_execution_timeout') || '60');
    }

    // Tab 3: Appearance
    const themeSelect = document.getElementById('setting-theme-select');
    if (themeSelect) {
      if (document.body.classList.contains('theme-high-contrast')) {
        themeSelect.value = 'high-contrast';
      } else if (document.body.classList.contains('theme-light')) {
        themeSelect.value = 'light';
      } else {
        themeSelect.value = 'dark';
      }
    }

    const zoomSelect = document.getElementById('setting-ui-zoom');
    if (zoomSelect) {
      const curZoom = window.appUIScale ? window.appUIScale.get() : (window.userSettings ? window.userSettings.get('ui_zoom', 1.0) : 1.0);
      zoomSelect.value = String(curZoom);
      if (!zoomSelect.value) {
        zoomSelect.value = String(Math.round(curZoom * 10) / 10);
      }
    }

    const histCheck = document.getElementById('setting-in-grid-histograms');
    if (histCheck && window.appResultsPanel) {
      histCheck.checked = window.appResultsPanel.showHistograms;
    }

    this.openModal('modal-user-settings');
  }

  saveUserSettings() {
    // 1. Canvas & Visuals
    const wireCheck = document.getElementById('setting-wire-probes');
    if (wireCheck && window.appCanvas) {
      window.appCanvas.setWireProbesEnabled(wireCheck.checked);
    }

    const nodeTipsCheck = document.getElementById('setting-node-tooltips');
    if (nodeTipsCheck && window.appCanvas) {
      window.appCanvas.setNodeTooltipsEnabled(nodeTipsCheck.checked);
    }

    const wirelessTipsCheck = document.getElementById('setting-wireless-tooltips');
    if (wirelessTipsCheck && window.appCanvas) {
      window.appCanvas.setWirelessTooltipsEnabled(wirelessTipsCheck.checked);
    }

    const snapSelect = document.getElementById('setting-grid-snap');
    if (snapSelect && window.appCanvas) {
      window.appCanvas.setGridSnapSize(parseInt(snapSelect.value, 10));
    }

    const wireStyleSelect = document.getElementById('setting-wire-style');
    if (wireStyleSelect && window.appCanvas) {
      window.appCanvas.setWireStyle(wireStyleSelect.value);
    }

    const durationSelect = document.getElementById('setting-node-badge-duration');
    if (durationSelect && window.appCanvas) {
      window.appCanvas.setNodeBadgeDuration(durationSelect.value);
    }

    // 2. Engine & Memory
    const engineSelect = document.getElementById('setting-execution-engine');
    if (engineSelect && window.userSettings) {
      window.userSettings.set('use_amp_engine', engineSelect.value === 'amp');
    }

    const threadsSelect = document.getElementById('setting-engine-threads');
    if (threadsSelect && window.userSettings) {
      window.userSettings.set('max_engine_threads', threadsSelect.value);
    }

    const autoCacheCheck = document.getElementById('setting-auto-cache-upstream');
    if (autoCacheCheck && window.appCanvas) {
      window.appCanvas.setAutoCacheUpstream(autoCacheCheck.checked);
    }

    const pageSizeSelect = document.getElementById('setting-page-size');
    if (pageSizeSelect && window.appResultsPanel) {
      window.appResultsPanel.setPageSize(parseInt(pageSizeSelect.value, 10));
    }

    const timeoutSelect = document.getElementById('setting-execution-timeout');
    if (timeoutSelect) {
      const tv = parseInt(timeoutSelect.value, 10) || 60;
      if (window.userSettings) window.userSettings.set('execution_timeout', tv);
      else localStorage.setItem('dataflow_execution_timeout', String(tv));
    }

    // 3. Appearance Theme
    const themeSelect = document.getElementById('setting-theme-select');
    if (themeSelect) {
      const selected = themeSelect.value;
      const themeClass = selected === 'high-contrast' ? 'theme-high-contrast' : (selected === 'light' ? 'theme-light' : 'theme-dark');
      document.documentElement.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
      document.body.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
      document.documentElement.classList.add(themeClass);
      document.body.classList.add(themeClass);
      if (window.userSettings) window.userSettings.set('theme', selected);
      else localStorage.setItem('alteryx_theme', themeClass);

      // Update theme toggle UI indicators
      const label = document.getElementById('theme-toggle-label');
      const sunIcon = document.getElementById('theme-icon-sun');
      const moonIcon = document.getElementById('theme-icon-moon');
      if (sunIcon && moonIcon) {
        if (selected === 'light') {
          sunIcon.style.display = 'none';
          moonIcon.style.display = 'block';
          if (label) label.textContent = 'Dark';
        } else {
          sunIcon.style.display = 'block';
          moonIcon.style.display = 'none';
          if (label) label.textContent = selected === 'high-contrast' ? 'Contrast' : 'Light';
        }
      }
    }

    // 4. In-Grid Histograms
    const histCheck = document.getElementById('setting-in-grid-histograms');
    if (histCheck && window.appResultsPanel) {
      if (window.appResultsPanel.showHistograms !== histCheck.checked) {
        const toggleBtn = document.getElementById('btn-toggle-histograms');
        if (toggleBtn) {
          toggleBtn.click();
        } else {
          window.appResultsPanel.showHistograms = histCheck.checked;
          window.appResultsPanel.renderGrid();
        }
      }
    }

    // 5. UI Display Scale (Zoom)
    const zoomSelect = document.getElementById('setting-ui-zoom');
    if (zoomSelect) {
      const zVal = parseFloat(zoomSelect.value) || 1.0;
      if (window.appUIScale) {
        window.appUIScale.apply(zVal, false);
      } else if (window.userSettings) {
        window.userSettings.set('ui_zoom', zVal);
        document.documentElement.style.zoom = `${zVal}`;
      }
    }

    this.closeAllModals();
    this.syncMenuStates();
    if (window.showToast) {
      window.showToast('success', 'Settings Saved', 'User preferences applied immediately.');
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
}

// Instantiate globally
window.appMenuBar = new MenuBar();

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    if (window.appMenuBar) window.appMenuBar.syncMenuStates();
  });
}
window.addEventListener('load', () => {
  if (window.appMenuBar) window.appMenuBar.syncMenuStates();
});
