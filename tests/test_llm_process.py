"""
Comprehensive Unit & Integration Test Suite for LLM Process Tool.
Tests prompt templating, context injection (RAG), rate limiting, providers,
LLMProcessNode execution, and Flask API endpoints.
"""
import unittest
from unittest.mock import patch, MagicMock
import json
import os
import tempfile
import pandas as pd
import numpy as np

from backend.engine.ai.provider_base import (
    LLMConfig,
    LLMResponse,
    ModelInfo,
    ConnectionTestResult,
    LLMProvider,
)
from backend.engine.ai.prompt_renderer import (
    render_template,
    extract_column_references,
    validate_template,
    inject_context,
    preview_prompts,
)
from backend.engine.ai.token_tracker import TokenTracker, estimate_cost
from backend.engine.ai.batch_executor import batch_execute, TokenBucketRateLimiter
from backend.engine.ai.provider_registry import get_provider, list_providers, PROVIDER_REGISTRY
from backend.engine.ai.provider_ollama import OllamaProvider
from backend.engine.ai.provider_openai_compat import OpenAICompatProvider
from backend.engine.ai.provider_gemini import GeminiProvider
from backend.engine.nodes.ai import LLMProcessNode
from backend.engine.nodes.base import NodeExecutionError
from backend.app import app


class MockTestProvider(LLMProvider):
    """Mock provider for unit testing without network calls."""
    provider_name = "mock"

    def __init__(self, responses=None):
        self.responses = responses or ["Mock response"]
        self.call_count = 0
        self.prompts_received = []

    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        self.prompts_received.append((system_prompt, user_prompt))
        idx = self.call_count % len(self.responses)
        self.call_count += 1
        resp = self.responses[idx]

        if isinstance(resp, Exception):
            raise resp

        return LLMResponse(
            text=str(resp),
            input_tokens=15,
            output_tokens=5,
            model=config.model,
            latency_ms=12.5,
            error=None
        )

    def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(success=True, message="Mock connection ok", models_available=2)

    def list_models(self):
        return [ModelInfo(name="mock-model-1"), ModelInfo(name="mock-model-2")]


class TestPromptRenderer(unittest.TestCase):
    """Tests for prompt_renderer.py."""

    def test_basic_template_substitution(self):
        row = pd.Series({"Name": "Alice", "Age": 30, "City": "Paris"})
        template = "Hello {{[Name]}}, you are {{[Age]}} years old and live in {{[City]}}."
        result = render_template(template, row)
        self.assertEqual(result, "Hello Alice, you are 30 years old and live in Paris.")

    def test_null_and_missing_values(self):
        row = pd.Series({"Name": "Bob", "Comment": None, "Rating": np.nan})
        template = "User: {{[Name]}}, Note: {{[Comment]}}, Stars: {{[Rating]}}"
        result = render_template(template, row)
        self.assertEqual(result, "User: Bob, Note: , Stars: ")

    def test_unresolved_placeholder_preserved(self):
        row = pd.Series({"Name": "Charlie"})
        template = "Hi {{[Name]}}, your balance is {{[NonExistent]}}."
        result = render_template(template, row)
        self.assertEqual(result, "Hi Charlie, your balance is {{[NonExistent]}}.")

    def test_extract_column_references(self):
        template = "Classify: {{[Review]}} and check {{[Author]}} from {{[Location]}}"
        refs = extract_column_references(template)
        self.assertEqual(refs, ["Review", "Author", "Location"])

    def test_validate_template_valid_and_invalid(self):
        available = ["Review", "Author", "Score"]
        # Valid template
        res_valid = validate_template("Analyze {{[Review]}} with score {{[Score]}}", available)
        self.assertTrue(res_valid["valid"])
        self.assertEqual(res_valid["missing_columns"], [])

        # Invalid template
        res_invalid = validate_template("Analyze {{[Review]}} by {{[UnknownCol]}}", available)
        self.assertFalse(res_invalid["valid"])
        self.assertEqual(res_invalid["missing_columns"], ["UnknownCol"])

    def test_inject_context_static_before_and_after(self):
        row = pd.Series({"X": "123"})
        prompt = "Process: {{[X]}}"

        # Placement before
        ctx_before = {"enabled": True, "source": "static", "text": "Guideline: Be brief.", "placement": "before"}
        res1 = inject_context(prompt, row, ctx_before)
        self.assertEqual(res1, "Guideline: Be brief.\n\nProcess: {{[X]}}")

        # Placement after
        ctx_after = {"enabled": True, "source": "static", "text": "Rules: No quotes.", "placement": "after"}
        res2 = inject_context(prompt, row, ctx_after)
        self.assertEqual(res2, "Process: {{[X]}}\n\nRules: No quotes.")

    def test_inject_context_from_column(self):
        row = pd.Series({"Prompt": "Do work", "ExtraContext": "Customer is VIP Tier"})
        ctx = {"enabled": True, "source": "column", "column": "ExtraContext", "placement": "before"}
        res = inject_context("Do work", row, ctx)
        self.assertEqual(res, "Customer is VIP Tier\n\nDo work")

    def test_inject_context_from_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, encoding="utf-8") as f:
            f.write("Company Policy: 30 days return")
            tmp_path = f.name

        try:
            row = pd.Series({"Text": "Customer wants return"})
            ctx = {"enabled": True, "source": "file", "file_path": tmp_path, "placement": "before"}
            res = inject_context("Customer wants return", row, ctx)
            self.assertEqual(res, "Company Policy: 30 days return\n\nCustomer wants return")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def test_preview_prompts(self):
        df = pd.DataFrame({
            "Product": ["Laptop", "Mouse"],
            "Review": ["Great battery", "Broke quickly"]
        })
        previews = preview_prompts(
            template="Sentiment for {{[Product]}}: {{[Review]}}",
            system_prompt="You are a classifier.",
            df=df,
            ctx_config={"enabled": False},
            n=2
        )
        self.assertEqual(len(previews), 2)
        self.assertEqual(previews[0]["user_prompt"], "Sentiment for Laptop: Great battery")
        self.assertEqual(previews[1]["user_prompt"], "Sentiment for Mouse: Broke quickly")


class TestTokenTracker(unittest.TestCase):
    """Tests for token_tracker.py."""

    def test_token_accumulation_and_cost(self):
        tracker = TokenTracker(model_name="gpt-4o-mini")
        r1 = LLMResponse(text="ok", input_tokens=100, output_tokens=50, model="gpt-4o-mini", latency_ms=100.0)
        r2 = LLMResponse(text="ok2", input_tokens=200, output_tokens=100, model="gpt-4o-mini", latency_ms=200.0)
        tracker.record(r1)
        tracker.record(r2)

        summary = tracker.get_summary()
        self.assertEqual(summary["total_input_tokens"], 300)
        self.assertEqual(summary["total_output_tokens"], 150)
        self.assertEqual(summary["total_tokens"], 450)
        self.assertEqual(summary["total_requests"], 2)
        self.assertEqual(summary["failed_requests"], 0)
        self.assertAlmostEqual(summary["avg_latency_ms"], 150.0)
        self.assertGreater(summary["estimated_cost_usd"], 0.0)

    def test_local_model_zero_cost(self):
        cost = estimate_cost("llama3.2:latest", 10000, 5000)
        self.assertEqual(cost, 0.0)


class TestBatchExecutor(unittest.TestCase):
    """Tests for batch_executor.py."""

    def test_rate_limiter(self):
        limiter = TokenBucketRateLimiter(rate=100)
        self.assertTrue(limiter.consume(1))

    def test_batch_execute_ordering_and_results(self):
        mock_provider = MockTestProvider(responses=["Res A", "Res B", "Res C"])
        prompts = ["P1", "P2", "P3"]
        config = LLMConfig(model="mock-model")

        responses = batch_execute(
            provider=mock_provider,
            system_prompt="sys",
            prompts=prompts,
            llm_config=config,
            concurrency=2,
            rate_limit_rps=50
        )

        self.assertEqual(len(responses), 3)
        self.assertEqual([r.text for r in responses], ["Res A", "Res B", "Res C"])

    def test_batch_execute_error_handling_null(self):
        # Provider that throws an exception
        failing_provider = MockTestProvider(responses=[ValueError("API timeout")])
        config = LLMConfig(model="mock-model")

        responses = batch_execute(
            provider=failing_provider,
            system_prompt="sys",
            prompts=["P1"],
            llm_config=config,
            max_retries=1,
            on_error="null"
        )
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0].text, "")
        self.assertIn("API timeout", responses[0].error)

    def test_batch_execute_error_handling_error_message(self):
        failing_provider = MockTestProvider(responses=[ValueError("Quota exceeded")])
        config = LLMConfig(model="mock-model")

        responses = batch_execute(
            provider=failing_provider,
            system_prompt="sys",
            prompts=["P1"],
            llm_config=config,
            max_retries=0,
            on_error="error_message"
        )
        self.assertEqual(len(responses), 1)
        self.assertTrue(responses[0].text.startswith("[ERROR]"))


class TestAIProviders(unittest.TestCase):
    """Tests for provider abstractions and registry."""

    def test_provider_registry_listing(self):
        providers = list_providers()
        ids = [p["id"] for p in providers]
        self.assertIn("ollama", ids)
        self.assertIn("openai", ids)
        self.assertIn("gemini", ids)
        self.assertIn("lm_studio", ids)
        self.assertIn("openai_compat", ids)

    def test_get_provider_factory(self):
        p_ollama = get_provider("ollama", {"base_url": "http://localhost:11434"})
        self.assertIsInstance(p_ollama, OllamaProvider)

        p_openai = get_provider("openai", {"api_key": "test-key"})
        self.assertIsInstance(p_openai, OpenAICompatProvider)
        self.assertEqual(p_openai.base_url, "https://api.openai.com/v1")

        p_gemini = get_provider("gemini", {"api_key": "test-gemini-key"})
        self.assertIsInstance(p_gemini, GeminiProvider)

    @patch("requests.post")
    def test_ollama_provider_generate(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "message": {"content": "Positive"},
            "prompt_eval_count": 20,
            "eval_count": 2,
            "model": "llama3.2"
        }

        provider = OllamaProvider(base_url="http://localhost:11434")
        cfg = LLMConfig(model="llama3.2")
        resp = provider.generate("sys", "user", cfg)

        self.assertEqual(resp.text, "Positive")
        self.assertEqual(resp.input_tokens, 20)
        self.assertEqual(resp.output_tokens, 2)
        self.assertIsNone(resp.error)

    @patch("requests.post")
    def test_openai_compat_provider_generate(self, mock_post):
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {
            "choices": [{"message": {"content": "Extracted info"}}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 5},
            "model": "gpt-4o-mini"
        }

        provider = OpenAICompatProvider(base_url="https://api.openai.com/v1", api_key="sk-test")
        cfg = LLMConfig(model="gpt-4o-mini")
        resp = provider.generate("sys", "user", cfg)

        self.assertEqual(resp.text, "Extracted info")
        self.assertEqual(resp.input_tokens, 15)
        self.assertIsNone(resp.error)


class TestLLMProcessNode(unittest.TestCase):
    """Tests for LLMProcessNode canvas execution."""

    def test_empty_dataframe_passthrough(self):
        df = pd.DataFrame({"Text": []})
        node = LLMProcessNode("llm_1", {
            "model": "mock",
            "user_prompt_template": "{{[Text]}}"
        })
        res = node.execute({"I": df})
        self.assertTrue(res["O"].empty)

    def test_missing_column_in_template_raises_error(self):
        df = pd.DataFrame({"ExistingCol": ["hello"]})
        node = LLMProcessNode("llm_2", {
            "model": "mock",
            "user_prompt_template": "{{[UnknownCol]}}"
        })
        with self.assertRaises(NodeExecutionError) as ctx:
            node.execute({"I": df})
        self.assertIn("UnknownCol", str(ctx.exception))

    @patch("backend.engine.nodes.ai.get_provider")
    def test_single_column_output_mode(self, mock_get_provider):
        mock_provider = MockTestProvider(responses=["Classified A", "Classified B"])
        mock_get_provider.return_value = mock_provider

        df = pd.DataFrame({"Review": ["Good product", "Bad product"]})
        node = LLMProcessNode("llm_3", {
            "provider_type": "ollama",
            "model": "llama3.2",
            "user_prompt_template": "Classify: {{[Review]}}",
            "output_mode": "single",
            "output_column": "Sentiment",
            "include_token_columns": True
        })

        res = node.execute({"I": df})
        out_df = res["O"]

        self.assertIn("Sentiment", out_df.columns)
        self.assertIn("_input_tokens", out_df.columns)
        self.assertIn("_output_tokens", out_df.columns)
        self.assertIn("_latency_ms", out_df.columns)
        self.assertEqual(out_df["Sentiment"].tolist(), ["Classified A", "Classified B"])

    @patch("backend.engine.nodes.ai.get_provider")
    def test_json_parse_output_mode(self, mock_get_provider):
        # Provider returns structured JSON string
        json_resp_1 = json.dumps({"sentiment": "Positive", "confidence": "0.95"})
        json_resp_2 = json.dumps({"sentiment": "Negative", "confidence": "0.88"})
        mock_provider = MockTestProvider(responses=[json_resp_1, json_resp_2])
        mock_get_provider.return_value = mock_provider

        df = pd.DataFrame({"Text": ["Loved it", "Hated it"]})
        node = LLMProcessNode("llm_4", {
            "provider_type": "ollama",
            "model": "llama3.2",
            "user_prompt_template": "Parse JSON: {{[Text]}}",
            "output_mode": "json_parse",
            "output_column": "Raw_Response",
            "json_fields": [
                {"field_name": "sentiment", "output_col": "Extracted_Sentiment"},
                {"field_name": "confidence", "output_col": "Extracted_Confidence"},
            ]
        })

        res = node.execute({"I": df})
        out_df = res["O"]

        self.assertIn("Extracted_Sentiment", out_df.columns)
        self.assertIn("Extracted_Confidence", out_df.columns)
        self.assertIn("Raw_Response", out_df.columns)
        self.assertEqual(out_df["Extracted_Sentiment"].tolist(), ["Positive", "Negative"])
        self.assertEqual(out_df["Extracted_Confidence"].tolist(), ["0.95", "0.88"])


class TestFlaskAIEndpoints(unittest.TestCase):
    """Tests for the 4 new AI REST API endpoints."""

    def setUp(self):
        self.client = app.test_client()

    def test_api_ai_providers_list(self):
        resp = self.client.get("/api/ai/providers")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        provider_ids = [p["id"] for p in data["providers"]]
        self.assertIn("ollama", provider_ids)
        self.assertIn("gemini", provider_ids)

    @patch("backend.engine.ai.provider_ollama.OllamaProvider.test_connection")
    def test_api_ai_test_connection(self, mock_test):
        mock_test.return_value = ConnectionTestResult(success=True, message="Connected to Ollama", models_available=3)

        resp = self.client.post("/api/ai/test-connection", json={
            "provider_type": "ollama",
            "connection": {"base_url": "http://localhost:11434"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["models_available"], 3)

    @patch("backend.engine.ai.provider_ollama.OllamaProvider.list_models")
    def test_api_ai_models_endpoint(self, mock_list):
        mock_list.return_value = [ModelInfo(name="llama3.2:latest", family="llama")]

        resp = self.client.post("/api/ai/models", json={
            "provider_type": "ollama",
            "connection": {"base_url": "http://localhost:11434"}
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["models"]), 1)
        self.assertEqual(data["models"][0]["name"], "llama3.2:latest")

    def test_api_ai_preview_prompt(self):
        resp = self.client.post("/api/ai/preview-prompt", json={
            "user_prompt_template": "Classify this text: {{[Comment]}}",
            "system_prompt": "You are a classifier.",
            "sample_data": [
                {"Comment": "Fast delivery!"},
                {"Comment": "Damaged package."}
            ]
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["previews"]), 2)
        self.assertEqual(data["previews"][0]["user_prompt"], "Classify this text: Fast delivery!")
        self.assertEqual(data["previews"][1]["user_prompt"], "Classify this text: Damaged package.")


if __name__ == "__main__":
    unittest.main()
