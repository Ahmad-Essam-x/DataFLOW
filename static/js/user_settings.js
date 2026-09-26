/**
 * UserSettings — Unified User Preference Persistence.
 *
 * Single source of truth for all user preferences. Writes immediately to
 * localStorage (so settings survive page refresh without any flash) and
 * asynchronously persists to the Flask backend (so settings survive across
 * browsers / devices and server restarts).
 *
 * Usage:
 *   window.userSettings.get('theme', 'dark')
 *   window.userSettings.set('theme', 'light')
 *   await window.userSettings.load()   // called once by app.js on DOMContentLoaded
 */

class UserSettings {
  constructor() {
    /** @type {Record<string, any>} In-memory settings cache */
    this._cache = {};

    /** Debounce timer handle for the server POST */
    this._saveTimer = null;

    /** Flag so we don't re-apply settings mid-load */
    this._loaded = false;

    // Default values for every known setting key.
    this._defaults = {
      theme:               'dark',
      wire_probes_enabled: true,
      wire_style:          'bezier',
      node_badge_duration: '3000',
      grid_snap:           16,
      auto_cache_upstream: false,
      minimap_visible:     true,
      minimap_collapsed:   false,
      panel_dimensions:    {},
      results_page_size:   100,
      execution_timeout:   60,
      use_amp_engine:             true,
      max_engine_threads:         'auto',
      ui_zoom:             1.0,
      palette_visible:     true,
      config_visible:             true,
      results_visible:            true,
      show_histograms:            false,
      node_tooltips_enabled:      true,
      wireless_tooltips_enabled:  true,
      autosave_enabled:           true,
      autosave_interval:          30,
    };

    // Seed from localStorage on construction (synchronous, zero-flicker).
    this._seedFromLocalStorage();
  }

  // ---------------------------------------------------------------------------
  // Internal helpers
  // ---------------------------------------------------------------------------

  _seedFromLocalStorage() {
    const raw = localStorage.getItem('userSettings_v1');
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        Object.assign(this._cache, parsed);
      } catch (_) { /* ignore */ }
    }

    // Migrate legacy individual localStorage keys.
    const legacy = {
      'alteryx_theme':                'theme',
      'dataflow_wire_probes_enabled': 'wire_probes_enabled',
      'dataflow_wire_style':          'wire_style',
      'dataflow_node_badge_duration': 'node_badge_duration',
      'dataflow_grid_snap':           'grid_snap',
      'dataflow_auto_cache_upstream': 'auto_cache_upstream',
      'dataflow_overview_enabled':    'minimap_visible',
      'dataflow_overview_collapsed':  'minimap_collapsed',
      'dataflow_panel_dimensions':    'panel_dimensions',
      'dataflow_execution_timeout':   'execution_timeout',
      'dataflow_ui_zoom':             'ui_zoom',
      'dataflow_palette_visible':     'palette_visible',
      'dataflow_config_visible':      'config_visible',
      'dataflow_results_visible':     'results_visible',
      'dataflow_show_histograms':     'show_histograms',
      'dataflow_node_tooltips':       'node_tooltips_enabled',
      'dataflow_wireless_tooltips':   'wireless_tooltips_enabled',
    };

    for (const [oldKey, newKey] of Object.entries(legacy)) {
      if (this._cache[newKey] === undefined) {
        const val = localStorage.getItem(oldKey);
        if (val !== null) {
          this._cache[newKey] = this._coerce(newKey, val);
        }
      }
    }
  }

  _coerce(key, rawValue) {
    const def = this._defaults[key];
    if (typeof def === 'boolean') {
      return rawValue === 'true' || rawValue === true;
    }
    if (typeof def === 'number') {
      const n = parseFloat(rawValue);
      return isNaN(n) ? def : n;
    }
    if (typeof def === 'object' && def !== null) {
      try { return JSON.parse(rawValue); } catch (_) { return def; }
    }
    if (key === 'theme') {
      if (rawValue === 'theme-light')         return 'light';
      if (rawValue === 'theme-high-contrast') return 'high-contrast';
      if (rawValue === 'theme-dark')          return 'dark';
    }
    return rawValue;
  }

  _writeLocalStorage() {
    try {
      localStorage.setItem('userSettings_v1', JSON.stringify(this._cache));
    } catch (_) { /* quota exceeded etc — ignore */ }
  }

  _scheduleServerSave() {
    if (this._saveTimer) clearTimeout(this._saveTimer);
    this._saveTimer = setTimeout(() => this._flushToServer(), 800);
  }

  async _flushToServer() {
    try {
      await fetch('/api/user-settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this._cache)
      });
    } catch (err) {
      console.warn('[UserSettings] Failed to persist to server:', err);
    }
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  get(key, defaultValue) {
    if (this._cache[key] !== undefined) return this._cache[key];
    if (defaultValue !== undefined)     return defaultValue;
    if (this._defaults[key] !== undefined) return this._defaults[key];
    return undefined;
  }

  set(key, value) {
    this._cache[key] = value;
    this._writeLocalStorage();
    this._scheduleServerSave();
  }

  async load() {
    try {
      const res = await fetch('/api/user-settings');
      if (res.ok) {
        const serverData = await res.json();
        Object.assign(this._cache, serverData);
        this._writeLocalStorage();
      }
    } catch (err) {
      console.warn('[UserSettings] Could not load from server, using localStorage values:', err);
    }
    this._loaded = true;
    this.applyAll();
  }

  applyAll() {
    this._applyTheme();
    this._applyUIScale();
    this._applyCanvasSettings();
    this._applyMinimapSettings();
    this._applyResultsSettings();
    this._applyPanelDimensions();
    this._applyViewPanelsVisibility();
    if (window.appMenuBar && typeof window.appMenuBar.syncMenuStates === 'function') {
      window.appMenuBar.syncMenuStates();
    }
  }

  // ---------------------------------------------------------------------------
  // Per-setting apply helpers
  // ---------------------------------------------------------------------------

  _applyUIScale() {
    const raw = this.get('ui_zoom', 1.0);
    const scale = parseFloat(raw);
    if (!isNaN(scale) && scale >= 0.5 && scale <= 2.5) {
      document.documentElement.style.zoom = `${scale}`;
    }
  }

  _applyTheme() {
    const raw = this.get('theme', 'dark');
    let themeClass;
    if (raw === 'light')              themeClass = 'theme-light';
    else if (raw === 'high-contrast') themeClass = 'theme-high-contrast';
    else                              themeClass = 'theme-dark';

    document.documentElement.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
    document.documentElement.classList.add(themeClass);
    document.body.classList.remove('theme-dark', 'theme-light', 'theme-high-contrast');
    document.body.classList.add(themeClass);

    const label   = document.getElementById('theme-toggle-label');
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    const toggleBtn = document.getElementById('btn-theme-toggle');

    if (themeClass === 'theme-light') {
      if (label) label.textContent = 'Light Mode';
      if (sunIcon)  sunIcon.style.display  = 'none';
      if (moonIcon) moonIcon.style.display = 'block';
    } else if (themeClass === 'theme-high-contrast') {
      if (label) label.textContent = 'Contrast';
      if (sunIcon)  sunIcon.style.display  = 'block';
      if (moonIcon) moonIcon.style.display = 'none';
    } else {
      if (label) label.textContent = 'Dark Mode';
      if (sunIcon)  sunIcon.style.display  = 'none';
      if (moonIcon) moonIcon.style.display = 'block';
    }
    if (toggleBtn) {
      toggleBtn.title = `Current: ${label ? label.textContent : themeClass} (Click to toggle theme)`;
      toggleBtn.setAttribute('aria-pressed', themeClass !== 'theme-light' ? 'true' : 'false');
    }
  }

  _applyCanvasSettings() {
    const canvas = window.appCanvas;
    if (!canvas) return;

    const wpe = this.get('wire_probes_enabled', true);
    canvas.wireProbesEnabled = wpe;
    if (!wpe && canvas.hideWireProbe) canvas.hideWireProbe();

    const ws = this.get('wire_style', 'bezier');
    if (canvas.wireStyle !== ws) {
      canvas.wireStyle = ws === 'orthogonal' ? 'orthogonal' : 'bezier';
      if (canvas.renderWires) canvas.renderWires();
    }

    canvas.nodeBadgeDuration = this.get('node_badge_duration', '3000');

    const snap = parseInt(this.get('grid_snap', 16), 10);
    if (!isNaN(snap)) canvas.gridSnapSize = snap;

    canvas.autoCacheUpstream = Boolean(this.get('auto_cache_upstream', false));

    const nte = Boolean(this.get('node_tooltips_enabled', true));
    canvas.nodeTooltipsEnabled = nte;
    if (canvas.wrapper) {
      canvas.wrapper.classList.toggle('node-tooltips-disabled', !nte);
    }

    const wte = Boolean(this.get('wireless_tooltips_enabled', true));
    canvas.wirelessTooltipsEnabled = wte;
    if (canvas.wrapper) {
      canvas.wrapper.classList.toggle('wireless-tooltips-disabled', !wte);
    }
    if (!wte && canvas.wrapper) {
      canvas.wrapper.querySelectorAll('.wireless-badge.is-visible').forEach(b => b.classList.remove('is-visible'));
    }
  }

  _applyMinimapSettings() {
    const minimap = window.appMiniMap;
    if (!minimap || typeof minimap.toggle !== 'function') return;
    const visible = Boolean(this.get('minimap_visible', true));
    // Only call toggle if state differs to avoid extra renders
    if (minimap.visible !== visible) {
      minimap.toggle(visible);
    }
  }

  _applyResultsSettings() {
    const rp = window.appResultsPanel;
    if (!rp || typeof rp.setPageSize !== 'function') return;
    const pageSize = parseInt(this.get('results_page_size', 100), 10);
    if (!isNaN(pageSize)) rp.setPageSize(pageSize);
  }

  _applyPanelDimensions() {
    const dims = this.get('panel_dimensions', {});
    if (!dims || typeof dims !== 'object') return;
    const paletteRibbon = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
    const configPanel   = document.getElementById('config-panel') || document.getElementById('config-sidebar');
    const resultsPanel  = document.getElementById('results-panel');
    if (paletteRibbon && dims.paletteHeight) paletteRibbon.style.height = `${dims.paletteHeight}px`;
    if (configPanel   && dims.configWidth)   configPanel.style.width    = `${dims.configWidth}px`;
    if (resultsPanel  && dims.resultsHeight) resultsPanel.style.height  = `${dims.resultsHeight}px`;
  }

  _applyViewPanelsVisibility() {
    // 1. Tool Palette
    const paletteVisible = Boolean(this.get('palette_visible', true));
    const paletteEl = document.getElementById('tool-palette-ribbon') || document.getElementById('palette-bar');
    if (paletteEl) {
      paletteEl.style.display = paletteVisible ? 'flex' : 'none';
    }

    // 2. Config Panel
    const configVisible = Boolean(this.get('config_visible', true));
    const configEl = document.getElementById('config-panel') || document.getElementById('config-sidebar');
    if (configEl) {
      configEl.style.display = configVisible ? 'flex' : 'none';
    }

    // 3. Results Panel
    const resultsVisible = Boolean(this.get('results_visible', true));
    const resultsEl = document.getElementById('results-panel');
    if (resultsEl) {
      resultsEl.classList.toggle('collapsed', !resultsVisible);
    }

    // 4. In-Grid Histograms
    const showHist = Boolean(this.get('show_histograms', false));
    if (window.appResultsPanel) {
      window.appResultsPanel.showHistograms = showHist;
      const toggleHistBtn = document.getElementById('btn-toggle-histograms');
      if (toggleHistBtn) toggleHistBtn.classList.toggle('active', showHist);
      if (window.appResultsPanel.gridWrapper) {
        window.appResultsPanel.gridWrapper.classList.toggle('hide-histograms', !showHist);
      }
    }
  }
}

// Instantiate the singleton immediately so any subsequent script can use it.
window.userSettings = new UserSettings();
