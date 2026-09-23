"""
LLM Process Node.
Processes each record through an LLM with a configurable prompt template,
optional RAG context injection, and structured output parsing.
"""
import json
import pandas as pd
from typing import Dict, Any, List, Optional

from .base import BaseNode, NodeExecutionError, sanitize_dataframe
from backend.engine.ai.provider_base import LLMConfig, LLMResponse
from backend.engine.ai.provider_registry import get_provider, list_providers
from backend.engine.ai.prompt_renderer import (
    render_template,
    extract_column_references,
    validate_template,
    inject_context,
)
from backend.engine.ai.batch_executor import batch_execute
from backend.engine.ai.token_tracker import TokenTracker


class LLMProcessNode(BaseNode):
    type_name = "llm_process"
    category = "ai"
    display_name = "LLM Process"
    description = "Process each record through an LLM with a configurable prompt"
    input_ports = ["I"]
    output_ports = ["O"]

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        df = self.get_single_input(inputs, "I")
        if df.empty:
            self.messages.append("LLM Process: Input is empty, passing through.")
            return {"O": df.copy()}

        df = sanitize_dataframe(df.copy())

        # --- 1. Validate configuration ------------------------------------------------
        provider_type = self.config.get("provider_type", "ollama")
        connection = self.config.get("connection", {})
        model_name = self.config.get("model", "")
        temperature = float(self.config.get("temperature", 0.3))
        max_tokens = int(self.config.get("max_tokens", 512))
        top_p = float(self.config.get("top_p", 1.0))
        timeout_seconds = float(self.config.get("timeout_seconds", 30.0))

        system_prompt = self.config.get("system_prompt", "")
        user_template = self.config.get("user_prompt_template", "")
        rag_context = self.config.get("rag_context", {})

        output_mode = self.config.get("output_mode", "single")
        output_column = self.config.get("output_column", "AI_Response")
        json_fields = self.config.get("json_fields", [])

        on_error = self.config.get("on_error", "null")
        max_retries = int(self.config.get("max_retries", 2))
        concurrency = int(self.config.get("concurrency", 3))
        rate_limit_rps = float(self.config.get("rate_limit_rps", 10.0))
        include_token_columns = self.config.get("include_token_columns", False)

        if not user_template.strip():
            raise NodeExecutionError("LLM Process: User prompt template is empty. Please configure a prompt.")

        if not model_name.strip():
            raise NodeExecutionError("LLM Process: No model selected. Please select a model.")

        # Validate template columns exist
        available_cols = list(df.columns)
        template_validation = validate_template(user_template, available_cols)
        if not template_validation["valid"]:
            missing = ", ".join(template_validation["missing_columns"])
            raise NodeExecutionError(
                f"LLM Process: Prompt template references columns that don't exist: {missing}. "
                f"Available columns: {', '.join(available_cols[:20])}"
            )

        # --- 2. Initialize provider ----------------------------------------------------
        try:
            provider = get_provider(provider_type, connection)
        except Exception as e:
            raise NodeExecutionError(f"LLM Process: Failed to initialize {provider_type} provider: {str(e)}")

        llm_config = LLMConfig(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            timeout_seconds=timeout_seconds,
        )

        # --- 3. Build prompts for each row --------------------------------------------
        prompts = []
        for idx in range(len(df)):
            row = df.iloc[idx]
            rendered = render_template(user_template, row)

            # Inject RAG context
            if rag_context.get("enabled", False):
                placement = rag_context.get("placement", "before")
                if placement != "system":
                    rendered = inject_context(rendered, row, rag_context)

            prompts.append(rendered)

        # Build system prompt (with optional system-level context)
        final_system_prompt = system_prompt
        if rag_context.get("enabled", False) and rag_context.get("placement") == "system":
            # For system placement, inject context into system prompt using first row as reference
            final_system_prompt = inject_context(
                system_prompt, df.iloc[0], {**rag_context, "placement": "after"}
            )

        # --- 4. Execute batch ---------------------------------------------------------
        self.messages.append(
            f"LLM Process: Sending {len(prompts)} records to {provider_type}/{model_name} "
            f"(concurrency={concurrency}, rate={rate_limit_rps} req/s)..."
        )

        tracker = TokenTracker(model_name=model_name)

        try:
            responses = batch_execute(
                provider=provider,
                system_prompt=final_system_prompt,
                prompts=prompts,
                llm_config=llm_config,
                concurrency=concurrency,
                rate_limit_rps=rate_limit_rps,
                max_retries=max_retries,
                on_error=on_error,
            )
        except Exception as e:
            raise NodeExecutionError(f"LLM Process: Execution failed: {str(e)}")

        # Record all responses in token tracker
        for r in responses:
            if r is not None:
                tracker.record(r)

        # --- 5. Write results to output columns ---------------------------------------
        if output_mode == "single":
            df[output_column] = [
                (r.text if r is not None else "") for r in responses
            ]
        elif output_mode == "json_parse":
            # Parse JSON responses and extract specified fields
            parsed_rows = []
            for r in responses:
                parsed = {}
                if r is not None and r.text:
                    try:
                        # Try to parse the response as JSON
                        text = r.text.strip()
                        # Handle markdown code blocks
                        if text.startswith("```"):
                            lines = text.split("\n")
                            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
                        data = json.loads(text)
                        if isinstance(data, dict):
                            parsed = data
                    except (json.JSONDecodeError, ValueError):
                        # If JSON parse fails, put raw text in first field
                        pass
                parsed_rows.append(parsed)

            for field_map in json_fields:
                field_name = field_map.get("field_name", "")
                output_col = field_map.get("output_col", field_name)
                df[output_col] = [
                    str(row.get(field_name, "")) if row else "" for row in parsed_rows
                ]

            # Also keep the raw response if in JSON parse mode
            df[output_column] = [
                (r.text if r is not None else "") for r in responses
            ]

        # --- 6. Add telemetry columns -------------------------------------------------
        if include_token_columns:
            df["_input_tokens"] = [
                (r.input_tokens if r is not None else 0) for r in responses
            ]
            df["_output_tokens"] = [
                (r.output_tokens if r is not None else 0) for r in responses
            ]
            df["_latency_ms"] = [
                (round(r.latency_ms, 1) if r is not None else 0.0) for r in responses
            ]
            df["_error"] = [
                (r.error if r is not None and r.error else "") for r in responses
            ]

        # --- 7. Summary message -------------------------------------------------------
        summary = tracker.get_summary()
        error_count = summary["failed_requests"]
        total_tokens = summary["total_tokens"]
        est_cost = summary["estimated_cost_usd"]
        avg_latency = summary["avg_latency_ms"]

        msg = (
            f"LLM Process: Completed {len(prompts)} records. "
            f"Tokens: {summary['total_input_tokens']:,} in / {summary['total_output_tokens']:,} out ({total_tokens:,} total). "
            f"Avg latency: {avg_latency:.0f}ms."
        )
        if error_count > 0:
            msg += f" Errors: {error_count}/{len(prompts)}."
        if est_cost > 0:
            msg += f" Estimated cost: ${est_cost:.4f}."
        self.messages.append(msg)

        return {"O": sanitize_dataframe(df)}
