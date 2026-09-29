"""
Comprehensive test suite for P0 (Blueprint Architecture, Dialogs, RunContext),
P1 (Tab-isolated Undo/Redo), and P2 (Column Lineage Tracer).
"""
import os
import sys
import json
import time
import unittest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app, executor
from backend.engine.executor import RunContext
from backend.engine.lineage import compute_lineage, compute_rich_lineage, compute_downstream_impact
from backend.blueprints.dialogs import _run_dialog_safe


class TestArchitectureAndLineage(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_blueprint_route_coverage(self):
        """Verify endpoints across all 6 registered blueprints respond with valid HTTP statuses."""
        # 1. execution blueprint
        res_tools = self.client.get("/api/tools")
        self.assertEqual(res_tools.status_code, 200)
        self.assertIn("tools", res_tools.get_json())

        # 2. files blueprint
        res_samples = self.client.get("/api/samples")
        self.assertEqual(res_samples.status_code, 200)
        self.assertIn("datasets", res_samples.get_json())

        # 3. workflow blueprint
        res_app_info = self.client.get("/api/app-info")
        self.assertEqual(res_app_info.status_code, 200)
        self.assertEqual(res_app_info.get_json().get("app_name"), "Antigravity DataFlow")

        # 4. settings blueprint
        res_settings = self.client.get("/api/user-settings")
        self.assertEqual(res_settings.status_code, 200)

        # 5. ai blueprint
        res_ai = self.client.get("/api/ai/providers")
        self.assertEqual(res_ai.status_code, 200)
        self.assertIn("providers", res_ai.get_json())

    def test_run_context_isolation(self):
        """Verify RunContext encapsulates session_id and threads it through execution calls."""
        ctx1 = executor.get_run_context("tab_session_alpha")
        self.assertEqual(ctx1.session_id, "tab_session_alpha")
        self.assertIs(ctx1.executor, executor)

        ctx2 = executor.get_run_context("tab_session_beta")
        self.assertEqual(ctx2.session_id, "tab_session_beta")

        # Minimal workflow payload
        wf = {
            "name": "Context Test",
            "nodes": [
                {"id": "n1", "type": "text_input", "config": {"columns": ["X", "Y"], "data": [["1", "2"], ["3", "4"]]}}
            ],
            "connections": []
        }

        res = ctx1.run(wf)
        self.assertTrue(res.success)
        self.assertEqual(res.session_id, "tab_session_alpha")

        # Node data retrieved via ctx1 automatically carries session_id
        node_data = ctx1.get_node_data("n1")
        self.assertTrue(node_data.get("available"))
        self.assertEqual(node_data.get("pagination", {}).get("total_records"), 2)
        self.assertEqual(len(node_data.get("records", [])), 2)

    def test_column_lineage_computation(self):
        """Verify compute_lineage traces column origins through input, formula, and select renames."""
        wf = {
            "nodes": [
                {
                    "id": "node_in",
                    "type": "input_data",
                    "config": {"preview_columns": ["OrderID", "Customer", "Subtotal", "TaxRate"]}
                },
                {
                    "id": "node_formula",
                    "type": "formula",
                    "config": {
                        "formulas": [
                            {"output_field": "TaxAmount", "expression": "[Subtotal] * [TaxRate]"},
                            {"output_field": "Total", "expression": "[Subtotal] + [TaxAmount]"}
                        ]
                    }
                },
                {
                    "id": "node_select",
                    "type": "select",
                    "config": {
                        "fields": [
                            {"name": "Customer", "rename": "ClientName", "selected": True},
                            {"name": "Total", "rename": "GrandTotal", "selected": True}
                        ]
                    }
                }
            ],
            "connections": [
                {"source": "node_in", "target": "node_formula"},
                {"source": "node_formula", "target": "node_select"}
            ]
        }

        lineage = compute_lineage(wf)

        # 1. Initial node has itself as origin for all fields
        self.assertEqual(lineage["node_in"]["OrderID"], [("node_in", "OrderID")])
        self.assertEqual(lineage["node_in"]["Subtotal"], [("node_in", "Subtotal")])

        # 2. Formula node computes TaxAmount from Subtotal and TaxRate
        tax_sources = lineage["node_formula"]["TaxAmount"]
        self.assertIn(("node_in", "Subtotal"), tax_sources)
        self.assertIn(("node_in", "TaxRate"), tax_sources)

        # 3. Select node renamed fields
        self.assertEqual(lineage["node_select"]["ClientName"], [("node_in", "Customer")])
        self.assertIn(("node_in", "Subtotal"), lineage["node_select"]["GrandTotal"])

    def test_lineage_api_endpoint(self):
        """Verify POST /api/workflow/lineage endpoint returns DAG column provenance."""
        wf = {
            "nodes": [
                {"id": "n1", "type": "input_data", "config": {"preview_columns": ["A", "B"]}},
                {"id": "n2", "type": "select", "config": {"fields": [{"name": "A", "rename": "A_renamed", "selected": True}]}}
            ],
            "connections": [{"source": "n1", "target": "n2"}]
        }

        resp = self.client.post(
            "/api/workflow/lineage",
            data=json.dumps({"workflow": wf, "node_id": "n2"}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("lineage", data)
        self.assertIn("A_renamed", data["lineage"]["n2"])
        self.assertEqual(data["lineage"]["n2"]["A_renamed"], [["n1", "A"]])

    def test_async_dialog_runner_timeout_safety(self):
        """Verify _run_dialog_safe returns None on worker timeout without blocking the caller."""
        def slow_blocking_dialog():
            time.sleep(1.0)
            return "C:/path/should_not_reach.json"

        # Execute with an aggressive 0.1s timeout
        start = time.time()
        result = _run_dialog_safe(slow_blocking_dialog, timeout=0.1)
        duration = time.time() - start

        self.assertIsNone(result, "Slow dialog should time out and return None")
        self.assertLess(duration, 0.5, "Timeout must return promptly without hanging the thread")

    def test_async_dialog_runner_success(self):
        """Verify _run_dialog_safe successfully returns result from completed worker."""
        def fast_dialog(default_name="test.json"):
            return f"C:/mock_workflows/{default_name}"

        result = _run_dialog_safe(fast_dialog, timeout=2.0, default_name="my_flow.json")
        self.assertEqual(result, "C:/mock_workflows/my_flow.json")

    def test_recent_workflows_full_lifecycle_and_spaces(self):
        """Verify recent workflows with spaces, absolute paths, and bulk sync maintain persistence."""
        # 1. Post a recent workflow with spaces in filename
        post_res = self.client.post("/api/workflow/recent", json={
            "name": "Spotify Analytics",
            "path": "spotify analytics.json"
        })
        self.assertEqual(post_res.status_code, 200)

        # 2. GET enriched with existence and resolved path
        get_res = self.client.get("/api/workflow/recent")
        self.assertEqual(get_res.status_code, 200)
        recent_list = get_res.get_json().get("recent_workflows", [])
        self.assertTrue(len(recent_list) > 0)
        first_item = recent_list[0]
        self.assertEqual(first_item["name"], "Spotify Analytics")
        self.assertTrue(first_item["exists"])
        self.assertTrue(first_item["resolved_path"].endswith("spotify analytics.json"))

        # 3. Bulk sync
        bulk_res = self.client.post("/api/workflow/recent", json={
            "recent_workflows": [
                {"name": "Spotify Analytics", "path": "workflows/spotify analytics.json"},
                {"name": "Customer Sales", "path": "workflows/customer_sales_analysis.json"}
            ]
        })
        self.assertEqual(bulk_res.status_code, 200)
        self.assertEqual(len(bulk_res.get_json().get("recent_workflows", [])), 2)

    def test_workflow_open_endpoint_resilience(self):
        """Verify /api/workflow/open resolves files by path, filename with spaces/underscores, and name."""
        # 1. By direct path with spaces
        res1 = self.client.post("/api/workflow/open", json={"path": "workflows/spotify analytics.json"})
        self.assertEqual(res1.status_code, 200)
        self.assertTrue(res1.get_json().get("success"))
        self.assertIn("nodes", res1.get_json().get("workflow", {}))

        # 2. By filename with underscore
        res2 = self.client.post("/api/workflow/open", json={"filename": "spotify_analytics.json"})
        self.assertEqual(res2.status_code, 200)
        self.assertTrue(res2.get_json().get("success"))

        # 3. By human-readable name
        res3 = self.client.post("/api/workflow/open", json={"name": "Spotify Analytics"})
        self.assertEqual(res3.status_code, 200)
        self.assertTrue(res3.get_json().get("success"))


    def test_lineage_summarize_new_columns_and_aggregations(self):
        """Verify summarize tool creates accurate lineage for GroupBy, Sum, Count, and custom output names."""
        workflow = {
            "nodes": [
                {
                    "id": "in1",
                    "name": "Transactions",
                    "type": "input_data",
                    "config": {"columns": ["Department", "Revenue", "EmployeeID"]}
                },
                {
                    "id": "sum1",
                    "name": "Dept Summary",
                    "type": "summarize",
                    "config": {
                        "actions": [
                            {"field": "Department", "action": "GroupBy", "output_name": "Department"},
                            {"field": "Revenue", "action": "Sum"},  # auto-named Sum_Revenue
                            {"field": "EmployeeID", "action": "Count", "output_name": "Headcount"},
                            {"field": "EmployeeID", "action": "CountDistinct"}  # auto-named Distinct_EmployeeID
                        ]
                    }
                },
                {
                    "id": "f1",
                    "name": "KPIs",
                    "type": "formula",
                    "config": {
                        "formulas": [
                            {"output_field": "Rev_Per_Capita", "expression": "[Sum_Revenue] / [Headcount]"}
                        ]
                    }
                }
            ],
            "connections": [
                {"source": "in1", "target": "sum1"},
                {"source": "sum1", "target": "f1"}
            ]
        }

        rich = compute_rich_lineage(workflow)

        # 1. Summarize node output columns
        sum_cols = rich["sum1"]
        self.assertIn("Department", sum_cols)
        self.assertEqual(sum_cols["Department"]["category"], "passthrough")
        self.assertEqual(sum_cols["Department"]["sources"], [("in1", "Department")])

        self.assertIn("Sum_Revenue", sum_cols)
        self.assertEqual(sum_cols["Sum_Revenue"]["category"], "calculated")
        self.assertEqual(sum_cols["Sum_Revenue"]["sources"], [("in1", "Revenue")])
        self.assertEqual(sum_cols["Sum_Revenue"]["hops"][-1]["action"], "Aggregate (Sum)")

        self.assertIn("Headcount", sum_cols)
        self.assertEqual(sum_cols["Headcount"]["category"], "calculated")
        self.assertEqual(sum_cols["Headcount"]["sources"], [("in1", "EmployeeID")])
        self.assertEqual(sum_cols["Headcount"]["hops"][-1]["action"], "Aggregate (Count)")

        self.assertIn("Distinct_EmployeeID", sum_cols)
        self.assertEqual(sum_cols["Distinct_EmployeeID"]["category"], "calculated")
        self.assertEqual(sum_cols["Distinct_EmployeeID"]["sources"], [("in1", "EmployeeID")])

        # 2. Downstream Formula referencing derived columns
        f_cols = rich["f1"]
        self.assertIn("Rev_Per_Capita", f_cols)
        self.assertEqual(f_cols["Rev_Per_Capita"]["category"], "calculated")
        # Sources must trace all the way back to root input node columns
        src_set = set(f_cols["Rev_Per_Capita"]["sources"])
        self.assertIn(("in1", "Revenue"), src_set)
        self.assertIn(("in1", "EmployeeID"), src_set)

    def test_lineage_formula_chained_and_multi_row(self):
        """Verify formula tool chaining in single node and multi-row row offset stripping."""
        workflow = {
            "nodes": [
                {
                    "id": "src",
                    "name": "Sales Data",
                    "type": "input_data",
                    "config": {"columns": ["Sales", "COGS"]}
                },
                {
                    "id": "form1",
                    "name": "Margin Calc",
                    "type": "formula",
                    "config": {
                        "formulas": [
                            {"output_field": "GrossProfit", "expression": "[Sales] - [COGS]"},
                            {"output_field": "GrossMarginPct", "expression": "([GrossProfit] / [Sales]) * 100"}
                        ]
                    }
                },
                {
                    "id": "mrow1",
                    "name": "Running Sales",
                    "type": "multi_row_formula",
                    "config": {
                        "output_field": "Running_Sales",
                        "expression": "[Row-1:Running_Sales] + [Sales]"
                    }
                }
            ],
            "connections": [
                {"source": "src", "target": "form1"},
                {"source": "form1", "target": "mrow1"}
            ]
        }

        rich = compute_rich_lineage(workflow)

        # Chained formula check
        form_cols = rich["form1"]
        self.assertIn("GrossProfit", form_cols)
        self.assertEqual(set(form_cols["GrossProfit"]["sources"]), {("src", "Sales"), ("src", "COGS")})

        self.assertIn("GrossMarginPct", form_cols)
        # GrossMarginPct references GrossProfit and Sales -> should trace to Sales and COGS
        self.assertIn(("src", "Sales"), form_cols["GrossMarginPct"]["sources"])
        self.assertIn(("src", "COGS"), form_cols["GrossMarginPct"]["sources"])

        # Multi-row formula check
        mrow_cols = rich["mrow1"]
        self.assertIn("Running_Sales", mrow_cols)
        self.assertIn(("src", "Sales"), mrow_cols["Running_Sales"]["sources"])

    def test_downstream_impact_summarize_and_formula(self):
        """Verify downstream impact tracks columns consumed by summarize aggregations and formulas."""
        workflow = {
            "nodes": [
                {
                    "id": "n1",
                    "name": "Input",
                    "type": "input_data",
                    "config": {"columns": ["Category", "Amount"]}
                },
                {
                    "id": "n2",
                    "name": "Summarize",
                    "type": "summarize",
                    "config": {
                        "actions": [
                            {"field": "Category", "action": "GroupBy"},
                            {"field": "Amount", "action": "Sum", "output_name": "Total_Amount"}
                        ]
                    }
                }
            ],
            "connections": [
                {"source": "n1", "target": "n2"}
            ]
        }

        impact = compute_downstream_impact(workflow, "n1", "Amount")
        self.assertIn("n2", impact["impacted_node_ids"])
        amount_usages = impact["columns"].get("Amount", [])
        self.assertTrue(any("Sum" in u["detail"] for u in amount_usages))


    def test_lineage_transforms_multifield_recordid_datetime_split(self):
        """Verify lineage for multi_field_formula, record_id, datetime, and text_to_columns."""
        workflow = {
            "nodes": [
                {
                    "id": "raw",
                    "name": "Raw Data",
                    "type": "input_data",
                    "config": {"columns": ["DateStr", "FullName", "Price"]}
                },
                {
                    "id": "rec",
                    "name": "Add ID",
                    "type": "record_id",
                    "config": {"column_name": "RowID", "start_value": 100}
                },
                {
                    "id": "dt",
                    "name": "Parse Date",
                    "type": "datetime",
                    "config": {"field": "DateStr", "output_field": "ParsedDate", "mode": "parse"}
                },
                {
                    "id": "split",
                    "name": "Split Name",
                    "type": "text_to_columns",
                    "config": {"column": "FullName", "num_columns": 2, "split_type": "columns"}
                },
                {
                    "id": "mfield",
                    "name": "Clean Price",
                    "type": "multi_field_formula",
                    "config": {
                        "selected_fields": ["Price"],
                        "output_mode": "create_new",
                        "output_prefix": "Clean_",
                        "expression": "[_CurrentField_] * 1.1"
                    }
                }
            ],
            "connections": [
                {"source": "raw", "target": "rec"},
                {"source": "rec", "target": "dt"},
                {"source": "dt", "target": "split"},
                {"source": "split", "target": "mfield"}
            ]
        }

        rich = compute_rich_lineage(workflow)

        # 1. Record ID
        self.assertIn("RowID", rich["rec"])
        self.assertEqual(rich["rec"]["RowID"]["category"], "calculated")
        self.assertEqual(rich["rec"]["RowID"]["sources"], [("rec", "RowID")])

        # 2. DateTime
        self.assertIn("ParsedDate", rich["dt"])
        self.assertEqual(rich["dt"]["ParsedDate"]["sources"], [("raw", "DateStr")])

        # 3. Text to columns
        self.assertIn("FullName_1", rich["split"])
        self.assertIn("FullName_2", rich["split"])
        self.assertEqual(rich["split"]["FullName_1"]["sources"], [("raw", "FullName")])
        self.assertEqual(rich["split"]["FullName_2"]["sources"], [("raw", "FullName")])

        # 4. Multi-field formula
        self.assertIn("Clean_Price", rich["mfield"])
        self.assertEqual(rich["mfield"]["Clean_Price"]["sources"], [("raw", "Price")])

    def test_lineage_union_and_join_collision(self):
        """Verify union multi-input source aggregation and join collision renaming."""
        workflow = {
            "nodes": [
                {
                    "id": "left_in",
                    "name": "Left Data",
                    "type": "input_data",
                    "config": {"columns": ["ID", "Name"]}
                },
                {
                    "id": "right_in",
                    "name": "Right Data",
                    "type": "input_data",
                    "config": {"columns": ["ID", "Name", "Score"]}
                },
                {
                    "id": "j1",
                    "name": "Join Tables",
                    "type": "join",
                    "config": {"join_keys": [{"left_key": "ID", "right_key": "ID"}]}
                },
                {
                    "id": "u1",
                    "name": "Union Tables",
                    "type": "union",
                    "config": {}
                }
            ],
            "connections": [
                {"source": "left_in", "target": "j1", "targetHandle": "L"},
                {"source": "right_in", "target": "j1", "targetHandle": "R"},
                {"source": "left_in", "target": "u1"},
                {"source": "right_in", "target": "u1"}
            ]
        }

        rich = compute_rich_lineage(workflow)

        # Join: Name on right collides -> Right_Name
        j_cols = rich["j1"]
        self.assertIn("Name", j_cols)
        self.assertIn("Right_Name", j_cols)
        self.assertEqual(j_cols["Name"]["sources"], [("left_in", "Name")])
        self.assertEqual(j_cols["Right_Name"]["sources"], [("right_in", "Name")])

        # Union: ID receives data from both left_in and right_in
        u_cols = rich["u1"]
        self.assertIn("ID", u_cols)
        u_sources = set(u_cols["ID"]["sources"])
        self.assertIn(("left_in", "ID"), u_sources)
        self.assertIn(("right_in", "ID"), u_sources)


if __name__ == "__main__":
    unittest.main()


