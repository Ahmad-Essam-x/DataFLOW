/**
 * Database Connections Manager UI.
 * Handles named database connections (DuckDB, SQLite, PostgreSQL, Snowflake).
 * Provides master-detail list, type switching, pre-flight testing, and OS-keyring integration.
 */

export class ConnectionManagerUI {
  constructor() {
    this.modal = document.getElementById('modal-database-connections');
    this.listContainer = document.getElementById('conn-list-container');
    this.editorContainer = document.getElementById('conn-editor-content');
    this.searchInput = document.getElementById('conn-search-input');
    this.btnNew = document.getElementById('btn-conn-new');
    this.btnSave = document.getElementById('btn-conn-save');
    this.btnDelete = document.getElementById('btn-conn-delete');
    this.btnTest = document.getElementById('btn-conn-test');
    this.testIndicator = document.getElementById('conn-test-indicator');

    this.connections = [];
    this.selectedConnId = null;
    this.currentForm = {
      name: '',
      type: 'duckdb',
      database: '',
      host: 'localhost',
      port: 5432,
      username: '',
      password: '',
      schema_name: 'public'
    };

    this.initEvents();
  }

  initEvents() {
    if (this.btnNew) {
      this.btnNew.addEventListener('click', () => this.createNew());
    }

    if (this.searchInput) {
      this.searchInput.addEventListener('input', (e) => {
        this.renderList(e.target.value.trim().toLowerCase());
      });
    }

    if (this.btnSave) {
      this.btnSave.addEventListener('click', () => this.saveCurrent());
    }

    if (this.btnDelete) {
      this.btnDelete.addEventListener('click', () => this.deleteCurrent());
    }

    if (this.btnTest) {
      this.btnTest.addEventListener('click', () => this.testCurrent());
    }
  }

  async openModal(preselectConnId = null) {
    if (!this.modal) return;
    this.modal.style.display = 'flex';
    this.clearTestIndicator();
    await this.loadConnections();
    if (preselectConnId && this.connections.some(c => c.id === preselectConnId)) {
      this.selectConnection(preselectConnId);
    } else if (this.connections.length > 0) {
      this.selectConnection(this.connections[0].id);
    } else {
      this.createNew();
    }
  }

  closeModal() {
    if (this.modal) {
      this.modal.style.display = 'none';
    }
  }

  async loadConnections() {
    try {
      const res = await fetch('/api/connections');
      const data = await res.json();
      if (data.success && Array.isArray(data.connections)) {
        this.connections = data.connections;
      } else {
        this.connections = [];
      }
    } catch (err) {
      console.error('Failed to load database connections:', err);
      this.connections = [];
    }
    this.renderList(this.searchInput ? this.searchInput.value.trim().toLowerCase() : '');
    // Notify application
    if (window.eventBus) {
      window.eventBus.emit('connections:loaded', this.connections);
    }
  }

  renderList(filterText = '') {
    if (!this.listContainer) return;
    const filtered = this.connections.filter(c => {
      if (!filterText) return true;
      return (c.name || '').toLowerCase().includes(filterText) ||
             (c.type || '').toLowerCase().includes(filterText) ||
             (c.database || '').toLowerCase().includes(filterText);
    });

    if (filtered.length === 0) {
      this.listContainer.innerHTML = `
        <div style="padding: 24px 12px; text-align: center; color: var(--text-muted); font-size: 11.5px;">
          ${this.connections.length === 0 ? 'No database connections yet.<br>Click <b>+ New</b> to connect.' : 'No matching connections.'}
        </div>
      `;
      return;
    }

    this.listContainer.innerHTML = filtered.map(conn => {
      const isActive = conn.id === this.selectedConnId;
      const type = (conn.type || 'sqlite').toLowerCase();
      const badgeClass = `badge-${type}`;
      const subtitle = type === 'sqlite' || type === 'duckdb' 
        ? (conn.database ? conn.database.split(/[\\/]/).pop() : ':memory:')
        : `${conn.host || 'localhost'}:${conn.port || 5432}`;

      return `
        <div class="conn-item ${isActive ? 'active' : ''}" data-conn-id="${conn.id}">
          <div style="overflow: hidden; padding-right: 6px;">
            <div class="conn-item-title">${this.escapeHtml(conn.name || 'Untitled Connection')}</div>
            <div class="conn-item-sub">${this.escapeHtml(subtitle)}</div>
          </div>
          <span class="conn-badge ${badgeClass}">${type}</span>
        </div>
      `;
    }).join('');

    this.listContainer.querySelectorAll('.conn-item').forEach(el => {
      el.addEventListener('click', () => {
        const id = el.getAttribute('data-conn-id');
        this.selectConnection(id);
      });
    });
  }

  selectConnection(connId) {
    this.selectedConnId = connId;
    const conn = this.connections.find(c => c.id === connId);
    if (!conn) return;

    this.currentForm = {
      id: conn.id,
      name: conn.name || '',
      type: (conn.type || 'duckdb').toLowerCase(),
      database: conn.database || '',
      host: conn.host || 'localhost',
      port: conn.port || (conn.type === 'postgresql' ? 5432 : 3306),
      username: conn.username || '',
      password: '',
      schema_name: conn.schema_name || 'public'
    };

    if (this.btnDelete) this.btnDelete.style.display = 'inline-block';
    this.clearTestIndicator();
    this.renderEditor();
    this.renderList(this.searchInput ? this.searchInput.value.trim().toLowerCase() : '');
  }

  createNew() {
    this.selectedConnId = null;
    this.currentForm = {
      name: 'New Database Connection',
      type: 'duckdb',
      database: '',
      host: 'localhost',
      port: 5432,
      username: '',
      password: '',
      schema_name: 'public'
    };

    if (this.btnDelete) this.btnDelete.style.display = 'none';
    this.clearTestIndicator();
    this.renderEditor();
    this.renderList(this.searchInput ? this.searchInput.value.trim().toLowerCase() : '');
  }

  renderEditor() {
    if (!this.editorContainer) return;
    const f = this.currentForm;
    const isFileBased = f.type === 'sqlite' || f.type === 'duckdb';

    this.editorContainer.innerHTML = `
      <div style="margin-bottom: 14px;">
        <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 5px; color: var(--text-primary);">Connection Name</label>
        <input type="text" id="form-conn-name" class="form-control" value="${this.escapeHtml(f.name)}" placeholder="e.g. Local DuckDB Store, Production Warehouse" style="font-size: 12.5px; font-weight: 500;">
      </div>

      <div style="margin-bottom: 14px;">
        <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 6px; color: var(--text-primary);">Database Engine</label>
        <div class="conn-type-selector">
          <div class="conn-type-card ${f.type === 'duckdb' ? 'active' : ''}" data-type="duckdb">
            <span style="font-size: 14px;">🦆</span>
            <span>DuckDB</span>
          </div>
          <div class="conn-type-card ${f.type === 'sqlite' ? 'active' : ''}" data-type="sqlite">
            <span style="font-size: 14px;">🪶</span>
            <span>SQLite</span>
          </div>
          <div class="conn-type-card ${f.type === 'postgresql' ? 'active' : ''}" data-type="postgresql">
            <span style="font-size: 14px;">🐘</span>
            <span>PostgreSQL</span>
          </div>
          <div class="conn-type-card ${f.type === 'snowflake' ? 'active' : ''}" data-type="snowflake">
            <span style="font-size: 14px;">❄️</span>
            <span>Snowflake</span>
          </div>
        </div>
      </div>

      <!-- File-Based Engine Config (DuckDB & SQLite) -->
      <div id="section-file-db" style="${isFileBased ? '' : 'display: none;'}">
        <div class="form-group" style="margin-bottom: 14px;">
          <label style="display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; font-weight: 600; margin-bottom: 5px;">
            <span>Database File Path</span>
            <a href="#" id="link-use-memory" style="font-size: 11px; color: var(--color-primary); text-decoration: none;">Use In-Memory (:memory:)</a>
          </label>
          <div style="display: flex; gap: 6px;">
            <input type="text" id="form-conn-file" class="form-control" value="${this.escapeHtml(f.database)}" placeholder="e.g. data/my_database.duckdb or C:/path/file.db" style="flex: 1; font-size: 12px;">
            <button type="button" class="btn btn-secondary" id="btn-browse-db-file" style="white-space: nowrap; padding: 6px 12px; font-size: 11.5px;">🖥️ Browse...</button>
          </div>
          <div class="form-hint" style="margin-top: 4px; font-size: 11px; color: var(--text-muted);">
            Accepts relative workspace paths, absolute system paths, or <code>:memory:</code> for an ephemeral database.
          </div>
        </div>
      </div>

      <!-- Client-Server Engine Config (Postgres, Snowflake) -->
      <div id="section-server-db" style="${!isFileBased ? '' : 'display: none;'}">
        <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 10px; margin-bottom: 12px;">
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Host / Server</label>
            <input type="text" id="form-conn-host" class="form-control" value="${this.escapeHtml(f.host)}" placeholder="e.g. localhost or db.internal.net" style="font-size: 12px;">
          </div>
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Port</label>
            <input type="number" id="form-conn-port" class="form-control" value="${f.port || 5432}" style="font-size: 12px;">
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Database Name</label>
            <input type="text" id="form-conn-dbname" class="form-control" value="${this.escapeHtml(f.database)}" placeholder="e.g. analytics_db" style="font-size: 12px;">
          </div>
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Schema (Optional)</label>
            <input type="text" id="form-conn-schema" class="form-control" value="${this.escapeHtml(f.schema_name)}" placeholder="e.g. public" style="font-size: 12px;">
          </div>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Username</label>
            <input type="text" id="form-conn-user" class="form-control" value="${this.escapeHtml(f.username)}" placeholder="e.g. postgres" style="font-size: 12px;">
          </div>
          <div>
            <label style="display: block; font-size: 11.5px; font-weight: 600; margin-bottom: 4px;">Password</label>
            <div style="display: flex; gap: 4px;">
              <input type="password" id="form-conn-pass" class="form-control" placeholder="${f.id ? '(Unchanged — stored in OS Keyring)' : 'Enter password...'}" style="flex: 1; font-size: 12px;">
              <button type="button" class="btn btn-secondary" id="btn-toggle-pwd" style="padding: 4px 8px; font-size: 12px;" title="Show/Hide Password">👁️</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Inspection Preview Area (When saved) -->
      ${f.id ? `
        <div style="margin-top: 16px; padding: 12px; border: 1px solid var(--border-subtle); border-radius: 6px; background: var(--bg-surface);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 11.5px; font-weight: 600;">Table Explorer & Verification</span>
            <button type="button" class="btn btn-secondary btn-sm" id="btn-inspect-tables" style="font-size: 11px; padding: 3px 8px;">↻ Inspect Tables</button>
          </div>
          <div id="conn-inspect-result" style="margin-top: 8px; font-size: 11.5px; color: var(--text-muted);">
            Click 'Inspect Tables' to list schemas and verified tables in this database.
          </div>
        </div>
      ` : ''}
    `;

    // Bind Type Cards
    this.editorContainer.querySelectorAll('.conn-type-card').forEach(card => {
      card.addEventListener('click', () => {
        const type = card.getAttribute('data-type');
        this.currentForm.type = type;
        if (type === 'postgresql' && (!this.currentForm.port || this.currentForm.port === 3306)) {
          this.currentForm.port = 5432;
        }
        this.renderEditor();
      });
    });

    // In-Memory shortcut
    const memLink = this.editorContainer.querySelector('#link-use-memory');
    if (memLink) {
      memLink.addEventListener('click', (e) => {
        e.preventDefault();
        const fileInput = this.editorContainer.querySelector('#form-conn-file');
        if (fileInput) fileInput.value = ':memory:';
      });
    }

    // Browse Button
    const browseBtn = this.editorContainer.querySelector('#btn-browse-db-file');
    if (browseBtn) {
      browseBtn.addEventListener('click', async () => {
        try {
          const res = await fetch('/api/dialog/open-file');
          const json = await res.json();
          if (json.success && json.path) {
            const fileInput = this.editorContainer.querySelector('#form-conn-file');
            if (fileInput) fileInput.value = json.path;
          }
        } catch (err) {
          // If native dialog not active, fallback
          const manual = prompt('Enter database file path:', this.currentForm.database || '');
          if (manual !== null) {
            const fileInput = this.editorContainer.querySelector('#form-conn-file');
            if (fileInput) fileInput.value = manual.trim();
          }
        }
      });
    }

    // Toggle Password Visibility
    const togglePwd = this.editorContainer.querySelector('#btn-toggle-pwd');
    if (togglePwd) {
      togglePwd.addEventListener('click', () => {
        const pwdInput = this.editorContainer.querySelector('#form-conn-pass');
        if (pwdInput) {
          pwdInput.type = pwdInput.type === 'password' ? 'text' : 'password';
        }
      });
    }

    // Inspect Tables Button
    const inspectBtn = this.editorContainer.querySelector('#btn-inspect-tables');
    if (inspectBtn && f.id) {
      inspectBtn.addEventListener('click', async () => {
        const resEl = this.editorContainer.querySelector('#conn-inspect-result');
        if (resEl) resEl.innerHTML = '<span>⏳ Introspecting database schema...</span>';
        try {
          const res = await fetch(`/api/connections/${f.id}/tables`);
          const json = await res.json();
          if (json.success && Array.isArray(json.tables)) {
            if (json.tables.length === 0) {
              resEl.innerHTML = '<span style="color: var(--text-muted);">✓ Connected, but no tables or views found yet in this database.</span>';
            } else {
              resEl.innerHTML = `
                <div style="color: var(--color-success); font-weight: 600; margin-bottom: 4px;">
                  ✓ Found ${json.tables.length} table${json.tables.length > 1 ? 's' : ''}:
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 4px; max-height: 90px; overflow-y: auto;">
                  ${json.tables.map(t => `<span style="background: var(--bg-hover); padding: 2px 6px; border-radius: 4px; font-family: var(--font-mono, monospace); font-size: 10.5px;">${this.escapeHtml(t)}</span>`).join('')}
                </div>
              `;
            }
          } else {
            resEl.innerHTML = `<span style="color: var(--color-error);">× Inspection failed: ${this.escapeHtml(json.error || 'Unknown error')}</span>`;
          }
        } catch (err) {
          if (resEl) resEl.innerHTML = `<span style="color: var(--color-error);">× Network error: ${err.message}</span>`;
        }
      });
    }
  }

  gatherFormData() {
    const f = this.currentForm;
    const nameInput = document.getElementById('form-conn-name');
    if (nameInput) f.name = nameInput.value.trim();

    const isFileBased = f.type === 'sqlite' || f.type === 'duckdb';
    if (isFileBased) {
      const fileInput = document.getElementById('form-conn-file');
      if (fileInput) f.database = fileInput.value.trim();
    } else {
      const hostInput = document.getElementById('form-conn-host');
      const portInput = document.getElementById('form-conn-port');
      const dbInput = document.getElementById('form-conn-dbname');
      const schemaInput = document.getElementById('form-conn-schema');
      const userInput = document.getElementById('form-conn-user');
      const passInput = document.getElementById('form-conn-pass');

      if (hostInput) f.host = hostInput.value.trim();
      if (portInput) f.port = parseInt(portInput.value, 10) || 5432;
      if (dbInput) f.database = dbInput.value.trim();
      if (schemaInput) f.schema_name = schemaInput.value.trim();
      if (userInput) f.username = userInput.value.trim();
      if (passInput && passInput.value) f.password = passInput.value;
    }

    return f;
  }

  async testCurrent() {
    this.gatherFormData();
    const f = this.currentForm;

    if (!f.name) {
      this.showTestIndicator('error', 'Please provide a Connection Name.');
      return;
    }

    this.showTestIndicator('loading', 'Testing connectivity...');

    try {
      let res;
      if (f.id && !f.password) {
        // Test saved connection with its keyring credentials
        res = await fetch(`/api/connections/${f.id}/test`, { method: 'POST' });
      } else {
        // Test draft parameters directly
        res = await fetch('/api/connections/test', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            connection: {
              name: f.name,
              type: f.type,
              database: f.database,
              host: f.host,
              port: f.port,
              username: f.username,
              schema_name: f.schema_name
            },
            password: f.password || undefined
          })
        });
      }

      const json = await res.json();
      if (json.success) {
        const countMsg = json.table_count !== undefined ? ` (${json.table_count} tables available)` : '';
        this.showTestIndicator('success', `✓ Connected successfully!${countMsg}`);
      } else {
        this.showTestIndicator('error', `× Test failed: ${json.error || 'Connection refused.'}`);
      }
    } catch (err) {
      this.showTestIndicator('error', `× Network error: ${err.message}`);
    }
  }

  async saveCurrent() {
    this.gatherFormData();
    const f = this.currentForm;

    if (!f.name) {
      alert('Please specify a Connection Name.');
      return;
    }

    if ((f.type === 'sqlite' || f.type === 'duckdb') && !f.database) {
      alert('Please specify a Database File Path (or enter :memory:).');
      return;
    }

    try {
      const payload = {
        connection: {
          name: f.name,
          type: f.type,
          database: f.database,
          host: f.host,
          port: f.port,
          username: f.username,
          schema_name: f.schema_name
        }
      };
      if (f.password) {
        payload.password = f.password;
      }

      let res;
      if (f.id) {
        // Update
        res = await fetch(`/api/connections/${f.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      } else {
        // Create
        res = await fetch('/api/connections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }

      const json = await res.json();
      if (json.success && json.connection) {
        const savedId = json.connection.id;
        await this.loadConnections();
        this.selectConnection(savedId);
        if (window.showToast) {
          window.showToast('success', 'Database Connected', `Saved connection "${f.name}".`);
        }
        if (window.eventBus) {
          window.eventBus.emit('connections:updated', json.connection);
        }
      } else {
        alert(`Save failed: ${json.error || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Save error: ${err.message}`);
    }
  }

  async deleteCurrent() {
    const f = this.currentForm;
    if (!f.id) return;

    if (!confirm(`Are you sure you want to delete database connection "${f.name}"?\nThis removes stored credentials from Windows Credential Manager.`)) {
      return;
    }

    try {
      const res = await fetch(`/api/connections/${f.id}`, { method: 'DELETE' });
      const json = await res.json();
      if (json.success) {
        if (window.showToast) {
          window.showToast('info', 'Connection Deleted', `Removed connection "${f.name}".`);
        }
        await this.loadConnections();
        if (this.connections.length > 0) {
          this.selectConnection(this.connections[0].id);
        } else {
          this.createNew();
        }
        if (window.eventBus) {
          window.eventBus.emit('connections:updated', null);
        }
      } else {
        alert(`Delete failed: ${json.error || 'Unknown error'}`);
      }
    } catch (err) {
      alert(`Delete error: ${err.message}`);
    }
  }

  showTestIndicator(status, message) {
    if (!this.testIndicator) return;
    this.testIndicator.style.display = 'inline-block';
    if (status === 'loading') {
      this.testIndicator.style.color = 'var(--text-muted)';
      this.testIndicator.innerHTML = `<span>⏳ ${this.escapeHtml(message)}</span>`;
    } else if (status === 'success') {
      this.testIndicator.style.color = 'var(--color-success)';
      this.testIndicator.innerHTML = `<span>${this.escapeHtml(message)}</span>`;
    } else {
      this.testIndicator.style.color = 'var(--color-error)';
      this.testIndicator.innerHTML = `<span>${this.escapeHtml(message)}</span>`;
    }
  }

  clearTestIndicator() {
    if (!this.testIndicator) return;
    this.testIndicator.style.display = 'none';
    this.testIndicator.innerHTML = '';
  }

  escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

// Global initialization
document.addEventListener('DOMContentLoaded', () => {
  const ui = new ConnectionManagerUI();
  window.connectionManagerUI = ui;
  window.openDatabaseConnectionsModal = (connId = null) => {
    ui.openModal(connId);
  };
});
