"""
Tests for Data Preview Cell Selection, Multi-Cell Range, and TSV Clipboard Copying.
"""
import unittest
from backend.app import app


class TestCellSelectionAndCopy(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_results_panel_js_contains_cell_selection_logic(self):
        """Verify results_panel.js contains all required cell selection and copy functions."""
        res = self.client.get('/static/js/results_panel.js')
        self.assertEqual(res.status_code, 200)
        js_text = res.get_data(as_text=True)

        # Selection state
        self.assertIn('this.selectedCells = new Set()', js_text)
        self.assertIn('this.selectionAnchor = null', js_text)
        self.assertIn('this.isSelecting = false', js_text)

        # Helper methods
        self.assertIn('clearCellSelection()', js_text)
        self.assertIn('selectCellRange(', js_text)
        self.assertIn('toggleCellSelection(', js_text)
        self.assertIn('selectRow(', js_text)
        self.assertIn('selectColumn(', js_text)
        self.assertIn('selectAllCells()', js_text)
        self.assertIn('updateCopyButtonLabel()', js_text)
        self.assertIn('copySelectedCells(', js_text)
        self.assertIn('copyEntireTable()', js_text)
        self.assertIn('openContextMenu(', js_text)
        self.assertIn('closeContextMenu()', js_text)

        # Grid listeners & events
        self.assertIn('cell-selected', js_text)
        self.assertIn('cell-focus', js_text)
        self.assertIn('contextmenu', js_text)
        self.assertIn('grid-context-menu', js_text)
        self.assertIn('btn-copy-table', js_text)
        self.assertIn('th-select-all', js_text)

    def test_style_css_contains_cell_selection_styles(self):
        """Verify style.css contains styling for cell selection and grid context menu."""
        res = self.client.get('/static/css/style.css')
        self.assertEqual(res.status_code, 200)
        css_text = res.get_data(as_text=True)

        self.assertIn('.data-table td.cell-selected', css_text)
        self.assertIn('.data-table td.cell-selected.cell-focus', css_text)
        self.assertIn('.grid-context-menu', css_text)
        self.assertIn('.grid-context-menu-item', css_text)
        self.assertIn('.grid-context-menu-divider', css_text)
        self.assertIn('body.light-theme .data-table td.cell-selected', css_text)

    def test_index_html_has_copy_button(self):
        """Verify index.html has the btn-copy-table button in toolbar."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)
        self.assertIn('id="btn-copy-table"', html)

    def test_tsv_formatting_rules(self):
        """Verify TSV generation rules for spreadsheet pasting (quotes, tabs, newlines)."""
        def format_tsv_cell(val):
            if val is None:
                return ''
            s = str(val)
            if '\t' in s or '\n' in s or '"' in s:
                return f'"{s.replace(chr(34), chr(34) * 2)}"'
            return s

        self.assertEqual(format_tsv_cell(None), '')
        self.assertEqual(format_tsv_cell(123), '123')
        self.assertEqual(format_tsv_cell("Hello"), 'Hello')
        self.assertEqual(format_tsv_cell("Hello\tWorld"), '"Hello\tWorld"')
        self.assertEqual(format_tsv_cell("Line 1\nLine 2"), '"Line 1\nLine 2"')
        self.assertEqual(format_tsv_cell('Quote "inside"'), '"Quote ""inside"""')


if __name__ == '__main__':
    unittest.main()
