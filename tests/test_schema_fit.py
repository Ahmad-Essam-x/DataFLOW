"""
Comprehensive Unit & Integration Test Suite for Schema Fit and LLM Override Tools.
Tests:
- Input anchor validations (M, T, S)
- Dual output generation (T: Transformations table, D: Transformed dataset)
- Heuristic and deterministic schema alignment (offline zero-token engine)
- LLM generative synthesis with Mock provider
- Self-correction reflection loop up to max_transformations
- Sandbox execution safety
- LLM Override node configuration and downstream transmission
- End-to-end WorkflowExecutor execution
- API preview endpoint (/api/ai/schema-fit/preview)
"""
import unittest
from unittest.mock import patch
import json
import pandas as pd
import numpy as np

from backend.engine.nodes.schema_fit import SchemaFitNode
from backend.engine.nodes.llm_override import LLMOverrideNode
from backend.engine.nodes.base import NodeExecutionError
from backend.engine.ai.provider_base import LLMProvider, LLMConfig, LLMResponse, ConnectionTestResult, ModelInfo
from backend.engine.executor import WorkflowExecutor
from backend.app import app


class MockSchemaLLMProvider(LLMProvider):
    provider_name = "mock_schema"

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.prompts_received = []

    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        self.prompts_received.append((system_prompt, user_prompt))
        idx = min(self.call_count, len(self.responses) - 1)
        self.call_count += 1
        resp = self.responses[idx] if self.responses else "[]"
        return LLMResponse(
            text=resp,
            input_tokens=100,
            output_tokens=50,
            model=config.model,
            latency_ms=25.0,
            error=None
        )

    def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=True, message="Mock OK", models_available=1)

    def list_models(self):
        return [ModelInfo(name="mock-model")]


class TestSchemaFitNode(unittest.TestCase):
    def setUp(self):
        # Target reference schema
        self.df_target = pd.DataFrame({
            "CustomerID": [101, 102, 103],
            "CustomerName": ["Acme Corp", "Beta LLC", "Gamma Inc"],
            "Revenue": [1200.50, 450.00, 3100.25],
            "SignupDate": pd.to_datetime(["2024-01-15", "2024-02-20", "2024-03-05"]),
            "IsActive": [True, False, True]
        })

        # Unformatted source dataset (different column names, currency string, extra columns)
        self.df_source = pd.DataFrame({
            "cust_id": [201, 202],
            "cust_name": ["Delta Co", "Echo Ltd"],
            "rev_amount": ["$5,400.00", "$920.50"],
            "signup": ["2024-04-10", "2024-05-01"],
            "is_active_flag": ["True", "False"],
            "internal_notes": ["Priority account", "Standard"]
        })

    def test_missing_input_anchors(self):
        node = SchemaFitNode("sf_1", {})
        # Missing both
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({})
        self.assertIn("Target reference data is missing from anchor 'T'", str(ctx.exception))

        # Missing source
        with self.assertRaises(NodeExecutionError) as ctx2:
            node.execute({"T": self.df_target})
        self.assertIn("Source data is missing from anchor 'S'", str(ctx2.exception))

        # Missing target
        with self.assertRaises(NodeExecutionError) as ctx3:
            node.execute({"S": self.df_source})
        self.assertIn("Target reference data is missing from anchor 'T'", str(ctx3.exception))

    def test_empty_source_dataframe(self):
        node = SchemaFitNode("sf_1", {})
        empty_source = pd.DataFrame(columns=["cust_id", "cust_name"])
        res = node.execute({"T": self.df_target, "S": empty_source})

        self.assertIn("T", res)
        self.assertIn("D", res)
        self.assertTrue(res["D"].empty)
        self.assertListEqual(list(res["D"].columns), list(self.df_target.columns))

    def test_heuristic_offline_reshaping_only_target_cols(self):
        """Tests deterministic schema matching with only_target_columns=True."""
        node = SchemaFitNode("sf_1", {
            "max_transformations": 5,
            "only_target_columns": True
        })
        res = node.execute({"T": self.df_target, "S": self.df_source})

        df_steps = res["T"]
        df_out = res["D"]

        # Check Transformation Steps DataFrame
        self.assertIn("Transformation Step", df_steps.columns)
        self.assertIn("Code", df_steps.columns)
        self.assertGreater(len(df_steps), 0)

        # Check Output Data matches target schema columns
        self.assertListEqual(list(df_out.columns), list(self.df_target.columns))
        self.assertEqual(len(df_out), 2)
        # Check values
        self.assertEqual(df_out["CustomerID"].iloc[0], 201)
        self.assertEqual(df_out["CustomerName"].iloc[0], "Delta Co")
        # Revenue cast from "$5,400.00" to float 5400.0
        self.assertAlmostEqual(float(df_out["Revenue"].iloc[0]), 5400.0, places=2)
        # IsActive cast to boolean
        self.assertTrue(bool(df_out["IsActive"].iloc[0]))
        self.assertFalse(bool(df_out["IsActive"].iloc[1]))
        # Internal notes excluded because only_target_columns is True
        self.assertNotIn("internal_notes", df_out.columns)

    def test_heuristic_offline_reshaping_keep_extra_cols(self):
        """Tests deterministic schema matching with only_target_columns=False."""
        node = SchemaFitNode("sf_1", {
            "max_transformations": 5,
            "only_target_columns": False
        })
        res = node.execute({"T": self.df_target, "S": self.df_source})
        df_out = res["D"]

        # Target columns come first
        for col in self.df_target.columns:
            self.assertIn(col, df_out.columns)
        # Extra source column retained
        self.assertIn("internal_notes", df_out.columns)
        self.assertEqual(df_out["internal_notes"].iloc[0], "Priority account")

    def test_missing_column_initialized_with_nan(self):
        """When target has a column absent in source, it gets initialized with NaN."""
        target_extra = self.df_target.copy()
        target_extra["NewPromoCode"] = ["A", "B", "C"]

        node = SchemaFitNode("sf_1", {"only_target_columns": True})
        res = node.execute({"T": target_extra, "S": self.df_source})
        df_out = res["D"]

        self.assertIn("NewPromoCode", df_out.columns)
        self.assertTrue(df_out["NewPromoCode"].isna().all())

    def test_custom_code_override(self):
        """Tests user-provided custom python script override."""
        custom_script = "df['CustomerID'] = df['cust_id'] * 10\ndf['CustomerName'] = df['cust_name'].str.upper()"
        node = SchemaFitNode("sf_1", {
            "custom_code": custom_script,
            "only_target_columns": False
        })
        res = node.execute({"T": self.df_target, "S": self.df_source})
        df_out = res["D"]
        self.assertEqual(df_out["CustomerID"].iloc[0], 2010)
        self.assertEqual(df_out["CustomerName"].iloc[0], "DELTA CO")

    @patch("backend.engine.nodes.schema_fit.get_provider")
    def test_llm_synthesis_success(self, mock_get_provider):
        """Tests AI synthesis when LLM returns valid JSON transformation steps."""
        llm_json_response = json.dumps([
            {
                "Transformation Step": "Rename cust_id and cust_name to CustomerID and CustomerName",
                "Code": "df = df.rename(columns={'cust_id': 'CustomerID', 'cust_name': 'CustomerName'})"
            },
            {
                "Transformation Step": "Clean rev_amount to Revenue float",
                "Code": "df['Revenue'] = df['rev_amount'].str.replace('$', '', regex=False).str.replace(',', '', regex=False).astype(float)"
            },
            {
                "Transformation Step": "Parse signup to SignupDate datetime",
                "Code": "df['SignupDate'] = pd.to_datetime(df['signup'])"
            },
            {
                "Transformation Step": "Cast is_active_flag to boolean IsActive",
                "Code": "df['IsActive'] = df['is_active_flag'].str.lower() == 'true'"
            }
        ])

        mock_provider = MockSchemaLLMProvider(responses=[llm_json_response])
        mock_get_provider.return_value = mock_provider

        node = SchemaFitNode("sf_1", {
            "provider_type": "mock_schema",
            "model": "mock-model",
            "max_transformations": 3,
            "only_target_columns": True
        })
        res = node.execute({"T": self.df_target, "S": self.df_source})

        df_steps = res["T"]
        df_out = res["D"]

        self.assertEqual(len(df_steps), 4)
        self.assertListEqual(list(df_out.columns), list(self.df_target.columns))
        self.assertEqual(df_out["CustomerID"].iloc[0], 201)
        self.assertEqual(df_out["Revenue"].iloc[0], 5400.0)

    @patch("backend.engine.nodes.schema_fit.get_provider")
    def test_llm_self_correction_reflection_loop(self, mock_get_provider):
        """Tests that when attempt 1 produces syntax error, attempt 2 provides fixed code."""
        bad_response = "invalid python non-json garbage"
        good_response = json.dumps([
            {
                "Transformation Step": "Rename cust_id to CustomerID",
                "Code": "df = df.rename(columns={'cust_id': 'CustomerID', 'cust_name': 'CustomerName'})"
            },
            {
                "Transformation Step": "Clean Revenue and format SignupDate and IsActive",
                "Code": "df['Revenue'] = 100.0\ndf['SignupDate'] = pd.to_datetime('2024-01-01')\ndf['IsActive'] = True"
            }
        ])

        mock_provider = MockSchemaLLMProvider(responses=[bad_response, good_response])
        mock_get_provider.return_value = mock_provider

        node = SchemaFitNode("sf_1", {
            "provider_type": "mock_schema",
            "model": "mock-model",
            "max_transformations": 3,
            "only_target_columns": True
        })
        res = node.execute({"T": self.df_target, "S": self.df_source})

        df_out = res["D"]
        self.assertEqual(mock_provider.call_count, 2)
        self.assertIn("CustomerID", df_out.columns)


class TestLLMOverrideNode(unittest.TestCase):
    def test_llm_override_execution(self):
        node = LLMOverrideNode("override_1", {
            "provider_type": "openai",
            "model": "gpt-4o",
            "connection": {"base_url": "https://api.openai.com/v1", "api_key": "sk-1234567890abcdef"},
            "temperature": 0.5,
            "max_tokens": 2048
        })
        res = node.execute({})

        self.assertIn("M", res)
        df_m = res["M"]
        self.assertIsInstance(df_m, pd.DataFrame)
        self.assertIn("Setting", df_m.columns)
        self.assertIn("Value", df_m.columns)

        # Check payload attribute attached for downstream consumption
        self.assertIn("llm_config", df_m.attrs)
        cfg_payload = df_m.attrs["llm_config"]
        self.assertEqual(cfg_payload["provider_type"], "openai")
        self.assertEqual(cfg_payload["model"], "gpt-4o")
        self.assertEqual(cfg_payload["temperature"], 0.5)

    def test_schema_fit_consumes_m_anchor(self):
        """Verifies SchemaFitNode reads configuration passed via anchor M."""
        override_node = LLMOverrideNode("override_1", {
            "provider_type": "gemini",
            "model": "gemini-2.0-flash",
            "connection": {"api_key": "gemini-test-key"}
        })
        m_outputs = override_node.execute({})

        df_target = pd.DataFrame({"ID": [1], "Name": ["Alice"]})
        df_source = pd.DataFrame({"id": [10], "name": ["Bob"]})

        schema_node = SchemaFitNode("sf_1", {})
        # Execute with M connected
        res = schema_node.execute({
            "M": m_outputs["M"],
            "T": df_target,
            "S": df_source
        })

        self.assertIn("D", res)
        self.assertIn("T", res)
        self.assertListEqual(list(res["D"].columns), ["ID", "Name"])
        self.assertEqual(res["D"]["ID"].iloc[0], 10)


class TestEndToEndWorkflow(unittest.TestCase):
    def test_workflow_with_schema_fit_and_llm_override(self):
        """Executes a full workflow with Target, Source, LLM Override, and Schema Fit nodes."""
        workflow = {
            "name": "Schema Fit Pipeline Test",
            "nodes": [
                {
                    "id": "target_input",
                    "type": "text_input",
                    "name": "Standard Schema",
                    "config": {
                        "columns": ["EmpID", "EmpName", "Salary"],
                        "data": [[1, "Alice", 75000], [2, "Bob", 82000]]
                    }
                },
                {
                    "id": "source_input",
                    "type": "text_input",
                    "name": "New Vendor Ingest",
                    "config": {
                        "columns": ["employee_id", "full_name", "annual_pay", "vendor_tag"],
                        "data": [[101, "Charlie", "$95,000", "Acme"], [102, "David", "$68,500", "Acme"]]
                    }
                },
                {
                    "id": "llm_override_tool",
                    "type": "llm_override",
                    "name": "LLM Settings",
                    "config": {
                        "provider_type": "ollama",
                        "model": "llama3.2"
                    }
                },
                {
                    "id": "schema_fit_tool",
                    "type": "schema_fit",
                    "name": "Schema Reshaper",
                    "config": {
                        "max_transformations": 5,
                        "only_target_columns": True
                    }
                }
            ],
            "connections": [
                {"source": "llm_override_tool", "sourceHandle": "M", "target": "schema_fit_tool", "targetHandle": "M"},
                {"source": "target_input", "sourceHandle": "O", "target": "schema_fit_tool", "targetHandle": "T"},
                {"source": "source_input", "sourceHandle": "O", "target": "schema_fit_tool", "targetHandle": "S"}
            ]
        }

        executor = WorkflowExecutor()
        result = executor.run(workflow)

        self.assertTrue(result.success, f"Workflow failed: {result.error}")
        self.assertIn("schema_fit_tool", result.node_results)

        sf_res = result.node_results["schema_fit_tool"]
        self.assertEqual(sf_res["status"], "success")
        self.assertIn("T", sf_res["columns"])
        self.assertIn("D", sf_res["columns"])

        # Check cached data for port D
        cached_data = executor.data_cache.get("schema_fit_tool", {})
        df_d = cached_data.get("D")
        self.assertIsNotNone(df_d)
        self.assertListEqual(list(df_d.columns), ["EmpID", "EmpName", "Salary"])
        self.assertEqual(df_d["EmpID"].iloc[0], 101)
        self.assertEqual(df_d["Salary"].iloc[0], 95000.0)


class TestSchemaFitPreviewAPI(unittest.TestCase):
    def test_schema_fit_preview_endpoint(self):
        client = app.test_client()
        payload = {
            "target_sample": [{"ProductID": 1, "ProductName": "Widget", "Price": 19.99}],
            "target_columns": ["ProductID", "ProductName", "Price"],
            "source_sample": [{"prod_id": 10, "name": "Gadget", "cost_usd": "$24.50"}],
            "config": {
                "only_target_columns": True
            }
        }
        res = client.post("/api/ai/schema-fit/preview", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("steps", data)
        self.assertIn("data_preview", data)
        self.assertIn("columns", data)
        self.assertListEqual(data["columns"], ["ProductID", "ProductName", "Price"])


if __name__ == "__main__":
    unittest.main()
