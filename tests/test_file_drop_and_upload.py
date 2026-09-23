import unittest
import json
import os
import io
import pandas as pd
from backend.app import app, DATA_DIR
from backend.engine.executor import WorkflowExecutor

class TestFileDropAndUpload(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.executor = WorkflowExecutor()
        self.created_files = []

    def tearDown(self):
        for f in self.created_files:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

    def test_upload_csv_file(self):
        """Test uploading a CSV file to /api/upload."""
        csv_data = "id,name,department,salary\n1,Alice,Engineering,120000\n2,Bob,Marketing,95000\n3,Charlie,Sales,105000\n"
        data = {
            'file': (io.BytesIO(csv_data.encode('utf-8')), 'employees.csv')
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['original_name'], 'employees.csv')
        self.assertEqual(json_data['file_type'], 'csv')
        self.assertEqual(json_data['delimiter'], ',')
        self.assertEqual(json_data['columns'], ['id', 'name', 'department', 'salary'])
        self.assertEqual(json_data['row_count'], 3)
        self.assertEqual(len(json_data['preview']), 3)

        uploaded_path = os.path.join(DATA_DIR, json_data['file_name'])
        self.created_files.append(uploaded_path)
        self.assertTrue(os.path.exists(uploaded_path))

    def test_upload_tsv_file_delimiter_detection(self):
        """Test uploading a TSV file and verifying tab delimiter detection."""
        tsv_data = "sku\titem\tqty\nA101\tWidget\t45\nB202\tGadget\t12\n"
        data = {
            'file': (io.BytesIO(tsv_data.encode('utf-8')), 'inventory.tsv')
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['file_type'], 'csv')
        self.assertEqual(json_data['delimiter'], '\t')
        self.assertEqual(json_data['columns'], ['sku', 'item', 'qty'])
        self.assertEqual(json_data['row_count'], 2)

        uploaded_path = os.path.join(DATA_DIR, json_data['file_name'])
        self.created_files.append(uploaded_path)

    def test_upload_excel_multi_sheet(self):
        """Test uploading a multi-sheet Excel (.xlsx) file and extracting all sheets."""
        excel_buffer = io.BytesIO()
        df1 = pd.DataFrame({'order_id': [101, 102], 'amount': [500, 750]})
        df2 = pd.DataFrame({'customer_id': [1, 2], 'name': ['Acme Corp', 'Global Tech']})
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df1.to_excel(writer, sheet_name='Orders', index=False)
            df2.to_excel(writer, sheet_name='Customers', index=False)

        excel_buffer.seek(0)
        data = {
            'file': (excel_buffer, 'quarterly_report.xlsx')
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['file_type'], 'excel')
        self.assertIn('Orders', json_data['sheets'])
        self.assertIn('Customers', json_data['sheets'])
        self.assertEqual(len(json_data['sheets']), 2)

        uploaded_path = os.path.join(DATA_DIR, json_data['file_name'])
        self.created_files.append(uploaded_path)

        # Verify that an Input Data tool can execute on the second sheet ('Customers')
        workflow = {
            'name': 'ExcelSheetTest',
            'nodes': [
                {
                    'id': 'node_excel_input',
                    'type': 'input_data',
                    'name': 'Customers Sheet',
                    'config': {
                        'file_path': json_data['file_name'],
                        'file_type': 'excel',
                        'sheet_name': 'Customers'
                    }
                }
            ],
            'connections': []
        }
        exec_res = self.executor.run(workflow)
        self.assertTrue(exec_res.success)
        node_res = exec_res.node_results['node_excel_input']
        self.assertEqual(node_res['record_counts']['O'], 2)
        self.assertIn('customer_id', node_res['columns']['O'])
        self.assertIn('name', node_res['columns']['O'])

    def test_upload_security_rejection(self):
        """Verify that unsafe or non-data file extensions are rejected with HTTP 400."""
        unsafe_data = "echo 'malicious script'\n"
        data = {
            'file': (io.BytesIO(unsafe_data.encode('utf-8')), 'script.sh')
        }
        res = self.client.post('/api/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 400)
        json_data = res.get_json()
        self.assertFalse(json_data['success'])
        self.assertIn('Unsupported file extension', json_data['error'])

    def test_html_dropzone_and_modal_elements(self):
        """Verify templates/index.html includes dropzone overlay and Excel sheet modal."""
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        html = res.get_data(as_text=True)

        self.assertIn('id="canvas-dropzone-overlay"', html)
        self.assertIn('class="dropzone-card"', html)
        self.assertIn('id="modal-excel-sheet"', html)
        self.assertIn('id="excel-sheet-list"', html)
        self.assertIn('id="btn-excel-confirm-sheet"', html)
        self.assertIn('id="btn-excel-import-all"', html)

    def test_css_dropzone_and_sheet_styles(self):
        """Verify static/css/style.css defines styles for dropzone overlay and sheet modal."""
        res = self.client.get('/static/css/style.css')
        self.assertEqual(res.status_code, 200)
        css = res.get_data(as_text=True)

        self.assertIn('.canvas-dropzone-overlay', css)
        self.assertIn('.dropzone-card', css)
        self.assertIn('.excel-sheet-list', css)
        self.assertIn('.excel-sheet-option', css)

    def test_js_canvas_drop_handlers(self):
        """Verify static/js/canvas.js implements handleDroppedFiles and promptExcelSheetSelection."""
        res = self.client.get('/static/js/canvas.js')
        self.assertEqual(res.status_code, 200)
        js = res.get_data(as_text=True)

        self.assertIn('handleDroppedFiles', js)
        self.assertIn('promptExcelSheetSelection', js)
        self.assertIn('canvas-dropzone-overlay', js)

if __name__ == '__main__':
    unittest.main()
