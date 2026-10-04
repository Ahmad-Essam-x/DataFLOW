/**
 * Safe, resilient async blob downloader for DataFLOW.
 * Prevents SPA browser navigation on 404/500 errors by fetching data asynchronously
 * and serving it via Blob Object URLs, preserving canvas state and unsaved workflows.
 */
(function(window) {
  'use strict';

  async function safeDownloadFile(url, fallbackFilename = 'export_result', options = {}) {
    const { onStart, onFinish } = options;

    if (typeof onStart === 'function') {
      try { onStart(); } catch (_) {}
    }

    try {
      const response = await fetch(url);

      if (!response.ok) {
        let errMessage = `Export failed (HTTP ${response.status})`;
        try {
          const json = await response.json();
          errMessage = json.error || json.message || errMessage;
        } catch (_) {
          const text = await response.text().catch(() => '');
          if (text && text.length < 250) {
            errMessage = text;
          }
        }

        if (window.showToast) {
          window.showToast('error', 'Export Error', errMessage);
        } else {
          console.error('[Download Error]', errMessage);
        }

        if (typeof onFinish === 'function') {
          try { onFinish(false, errMessage); } catch (_) {}
        }
        return false;
      }

      // Extract filename from Content-Disposition header if present
      let filename = fallbackFilename;
      const disposition = response.headers.get('content-disposition');
      if (disposition && disposition.includes('filename=')) {
        const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
        if (match && match[1]) {
          filename = match[1].replace(/['"]/g, '').trim();
        }
      }

      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const tempLink = document.createElement('a');
      tempLink.href = objectUrl;
      tempLink.download = filename;
      tempLink.style.display = 'none';
      document.body.appendChild(tempLink);
      tempLink.click();

      setTimeout(() => {
        if (tempLink.parentNode) {
          document.body.removeChild(tempLink);
        }
        window.URL.revokeObjectURL(objectUrl);
      }, 500);

      if (window.showToast) {
        window.showToast('success', 'Export Complete', `Successfully exported '${filename}'.`);
      }

      if (typeof onFinish === 'function') {
        try { onFinish(true, filename); } catch (_) {}
      }
      return true;
    } catch (err) {
      const msg = err.message || 'Network error occurred during download.';
      if (window.showToast) {
        window.showToast('error', 'Download Failed', msg);
      } else {
        console.error('[Download Failed]', err);
      }

      if (typeof onFinish === 'function') {
        try { onFinish(false, msg); } catch (_) {}
      }
      return false;
    }
  }

  window.safeDownloadFile = safeDownloadFile;
})(window);
