import unittest
import pandas as pd
from backend.engine.executor import WorkflowExecutor
from backend.engine.error_diagnostics import diagnose_error, ErrorDiagnostic

class TestDiagnostics(unittest.TestCase):

    def test_formula_missing_column_diagnostic(self):
        df = pd.DataFrame({"customer_id": [1, 2, 3], "revenue": [100.0, 250.0, 50.0]})
        wf = {
            "nodes": [
                {
                    "id": "node_input",
                    "type": "input_data",
                    "name": "Input Customers",
                    "config": {"source_type": "inline", "data": df.to_dict(orient="records")}
                },
                {
                    "id": "node_formula",
                    "type": "formula",
                    "name": "Tax Calculator",
                    "config": {
                        "formulas": [
                            # Deliberate typo: [revenu] instead of [revenue]
                            {"output_field": "tax", "expression": "[revenu] * 0.15"}
                        ]
                    }
                }
            ],
            "connections": [
                {
                    "from_node": "node_input",
                    "from_port": "O",
                    "to_node": "node_formula",
                    "to_port": "I"
                }
            ]
        }
        executor = WorkflowExecutor()
        res = executor.run(wf)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.diagnostic)
        diag = res.diagnostic
        self.assertEqual(diag["error_code"], "COLUMN_NOT_FOUND")
        self.assertEqual(diag["node_id"], "node_formula")
        self.assertIn("revenu", diag["title"])
        # Fuzzy match should recommend 'revenue'
        self.assertIn("revenue", diag["suggestion"])

    def test_missing_input_connection_diagnostic(self):
        wf = {
            "nodes": [
                {
                    "id": "node_filter",
                    "type": "filter",
                    "name": "Filter Orders",
                    "config": {"mode": "basic", "conditions": [{"column": "status", "operator": "==", "value": "active"}]}
                }
            ],
            "connections": []
        }
        executor = WorkflowExecutor()
        res = executor.run(wf)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.diagnostic)
        self.assertEqual(res.diagnostic["error_code"], "MISSING_CONNECTION")
        self.assertEqual(res.diagnostic["node_id"], "node_filter")

    def test_circular_dependency_diagnostic(self):
        wf = {
            "nodes": [
                {"id": "n1", "type": "select", "name": "Select 1", "config": {}},
                {"id": "n2", "type": "select", "name": "Select 2", "config": {}}
            ],
            "connections": [
                {"from_node": "n1", "from_port": "O", "to_node": "n2", "to_port": "I"},
                {"from_node": "n2", "from_port": "O", "to_node": "n1", "to_port": "I"}
            ]
        }
        executor = WorkflowExecutor()
        res = executor.run(wf)
        self.assertFalse(res.success)
        self.assertIsNotNone(res.diagnostic)
        self.assertEqual(res.diagnostic["error_code"], "CIRCULAR_DEPENDENCY")

if __name__ == "__main__":
    unittest.main()
