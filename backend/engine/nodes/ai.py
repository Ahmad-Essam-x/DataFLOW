"""
LLM Process Node — enhanced.

Enhancements over the original:
- Prompt deduplication cache: identical (system, user) pairs skip the API call.
- Pre-flight token/cost estimate logged before the batch starts.
- Dynamic system prompt: can be sourced from a per-row column.
- Multi-context injection: config supports a list of RAG blocks (rag_contexts).
- Jinja2 template syntax via prompt_renderer (backward-compat with {{[Col]}}).
- Structured output mode: passes response_schema to the provider.
- Dual output ports O (success) and E (error rows) when on_error != 'stop'.
- Live progress written to blueprints.ai._llm_progress keyed by node_id.
"""
import json
import pandas as pd
from typing import Dict, Any, List, Optional, Union

from .base import BaseNode, NodeExecutionError, sanitize_dataframe
from backend.engine.ai.provider_base import LLMConfig, LLMResponse
from backend.engine.ai.provider_registry import get_provider
from backend.engine.ai.egress import EgressNotApproved
from backend.engine.ai.prompt_renderer import (
    render_template,
    extract_column_references,
    validate_template,
    inject_contexts,
    collect_system_contexts,
)
from backend.engine.ai.batch_executor import batch_execute
from backend.engine.ai.token_tracker import TokenTracker, estimate_cost


class LLMProcessNode(BaseNode):
    type_name = "llm_process"
    category = "ai"
    display_name = "LLM Process"
    description = "Process each record through an LLM with a configurable prompt"
    input_ports = ["I"]
    output_ports = ["O", "E"]   # E = error rows (optional, empty when no errors)

    def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, pd.DataFrame]:

        df = self.get_single_input(inputs, "I")
        if df.empty:
            self.messages.append("LLM Process: Input is empty, passing through.")
            return {"O": df.copy(), "E": df.copy()}

        df = sanitize_dataframe(df.copy())

        # ------------------------------------------------------------------ #
        # 1.  Extract configuration
        # ------------------------------------------------------------------ #
        provider_type   = self.config.get("provider_type", "ollama")
        connection      = self.config.get("connection", {})
        model_name      = self.config.get("model", "")
        temperature     = float(self.config.get("temperature", 0.3))
        max_tokens      = int(self.config.get("max_tokens", 512))
        top_p           = float(self.config.get("top_p", 1.0))
        timeout_seconds = float(self.config.get("timeout_seconds", 30.0))

        system_prompt_text   = self.config.get("system_prompt", "")
        user_template        = self.config.get("user_prompt_template", "")

        # Dynamic system prompt from a column
        sys_prompt_source = self.config.get("system_prompt_source", "static")
        sys_prompt_column = self.config.get("system_prompt_column", "")

        # RAG / context — accept list (rag_contexts) or legacy single dict
        raw_ctx = self.config.get("rag_contexts")
        if raw_ctx and isinstance(raw_ctx, list):
            ctx_list = [c for c in raw_ctx if isinstance(c, dict)]
        else:
            legacy = self.config.get("rag_context", {})
            ctx_list = [legacy] if isinstance(legacy, dict) and legacy.get("enabled") else []

        output_mode   = self.config.get("output_mode", "single")  # single|json_parse|structured
        output_column = self.config.get("output_column", "AI_Response")
        json_fields   = self.config.get("json_fields", [])
        # JSON Schema for structured output mode
        response_schema_raw = self.config.get("response_schema", "")
        response_schema: Optional[dict] = None
        if output_mode == "structured" and response_schema_raw:
            try:
                response_schema = json.loads(response_schema_raw) if isinstance(response_schema_raw, str) else response_schema_raw
            except (json.JSONDecodeError, TypeError):
                response_schema = None

        on_error       = self.config.get("on_error", "null")
        max_retries    = int(self.config.get("max_retries", 2))
        concurrency    = int(self.config.get("concurrency", 3))
        rate_limit_rps = float(self.config.get("rate_limit_rps", 10.0))
        include_token_columns = self.config.get("include_token_columns", False)

        # ------------------------------------------------------------------ #
        # 2.  Validate
        # ------------------------------------------------------------------ #
        if not user_template.strip():
            raise NodeExecutionError(
                "LLM Process: User prompt template is empty. Please configure a prompt."
            )
        if not model_name.strip():
            raise NodeExecutionError(
                "LLM Process: No model selected. Please select a model."
            )

        available_cols = list(df.columns)
        tv = validate_template(user_template, available_cols)
        if not tv["valid"]:
            missing = ", ".join(tv["missing_columns"])
            raise NodeExecutionError(
                f"LLM Process: Prompt template references columns that don't exist: {missing}. "
                f"Available: {', '.join(available_cols[:20])}"
            )

        if sys_prompt_source == "column" and sys_prompt_column and sys_prompt_column not in available_cols:
            raise NodeExecutionError(
                f"LLM Process: System prompt column '{sys_prompt_column}' not found. "
                f"Available: {', '.join(available_cols[:20])}"
            )

        # ------------------------------------------------------------------ #
        # 3.  Initialise provider
        # ------------------------------------------------------------------ #
        try:
            provider = get_provider(provider_type, connection)
        except EgressNotApproved as e:
            raise NodeExecutionError(f"LLM Process: {e}")
        except Exception as e:
            raise NodeExecutionError(
                f"LLM Process: Failed to initialise {provider_type} provider: {e}"
            )

        llm_config = LLMConfig(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            timeout_seconds=timeout_seconds,
            response_schema=response_schema,
        )

        # ------------------------------------------------------------------ #
        # 4.  Build per-row prompts and system prompts
        # ------------------------------------------------------------------ #
        user_prompts: List[str] = []
        system_prompts: Union[str, List[str]]

        if sys_prompt_source == "column" and sys_prompt_column:
            # Per-row dynamic system prompt
            sys_list: List[str] = []
            for idx in range(len(df)):
                row = df.iloc[idx]
                base_sys = str(row.get(sys_prompt_column, '') or '')
                base_sys = collect_system_contexts(base_sys, row, ctx_list)
                sys_list.append(base_sys)
            system_prompts = sys_list
        else:
            # Static system prompt (inject system-placement contexts using row 0)
            if ctx_list and len(df) > 0:
                system_prompts = collect_system_contexts(
                    system_prompt_text, df.iloc[0], ctx_list
                )
            else:
                system_prompts = system_prompt_text

        for idx in range(len(df)):
            row = df.iloc[idx]
            rendered = render_template(user_template, row)
            rendered = inject_contexts(rendered, row, ctx_list)
            user_prompts.append(rendered)

        # ------------------------------------------------------------------ #
        # 5.  Pre-flight cost estimate
        # ------------------------------------------------------------------ #
        sys_sample = (
            system_prompts[0] if isinstance(system_prompts, list) else system_prompts
        )
        total_prompt_chars = (
            sum(len(p) for p in user_prompts)
            + len(sys_sample) * len(user_prompts)
        )
        est_input_tokens  = total_prompt_chars // 4
        est_output_tokens = max_tokens * len(user_prompts)
        est_cost          = estimate_cost(model_name, est_input_tokens, est_output_tokens)
        self.messages.append(
            f"LLM Process: Pre-flight estimate — "
            f"~{est_input_tokens:,} input tokens, "
            f"~{est_output_tokens:,} max output tokens"
            + (f", est. cost ~${est_cost:.4f}" if est_cost > 0 else " (local/free model)")
        )

        # ------------------------------------------------------------------ #
        # 6.  Execute batch with progress reporting
        # ------------------------------------------------------------------ #
        self.messages.append(
            f"LLM Process: Sending {len(user_prompts)} records to "
            f"{provider_type}/{model_name} "
            f"(concurrency={concurrency}, rate={rate_limit_rps} req/s)..."
        )

        # Resolve node_id for progress tracking (base class may expose it)
        node_id = getattr(self, 'node_id', None) or getattr(self, 'id', None) or ''

        def _progress_cb(completed: int, total: int):
            try:
                from backend.blueprints.ai import _llm_progress
                _llm_progress[node_id] = {
                    "completed": completed,
                    "total": total,
                    "done": completed >= total,
                }
            except Exception:
                pass

        # Persist dedup cache on the node instance across test-runs in same session
        if not hasattr(self, '_prompt_cache'):
            self._prompt_cache: dict = {}

        tracker = TokenTracker(model_name=model_name)

        try:
            responses = batch_execute(
                provider=provider,
                system_prompt=system_prompts,
                prompts=user_prompts,
                llm_config=llm_config,
                concurrency=concurrency,
                rate_limit_rps=rate_limit_rps,
                max_retries=max_retries,
                on_error=on_error,
                progress_callback=_progress_cb,
                prompt_cache=self._prompt_cache,
            )
        except Exception as e:
            raise NodeExecutionError(f"LLM Process: Execution failed: {e}")

        for r in responses:
            if r is not None:
                tracker.record(r)

        # ------------------------------------------------------------------ #
        # 7.  Write output columns
        # ------------------------------------------------------------------ #
        if output_mode == "single":
            df[output_column] = [
                (r.text if r is not None else "") for r in responses
            ]

        elif output_mode == "json_parse":
            parsed_rows = []
            for r in responses:
                parsed: dict = {}
                if r is not None and r.text:
                    try:
                        text = r.text.strip()
                        if text.startswith("```"):
                            lines = text.split("\n")
                            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
                        data = json.loads(text)
                        if isinstance(data, dict):
                            parsed = data
                    except (json.JSONDecodeError, ValueError):
                        pass
                parsed_rows.append(parsed)

            for field_map in json_fields:
                field_name = field_map.get("field_name", "")
                out_col    = field_map.get("output_col", field_name)
                df[out_col] = [
                    str(row.get(field_name, "")) if row else "" for row in parsed_rows
                ]
            df[output_column] = [(r.text if r is not None else "") for r in responses]

        elif output_mode == "structured":
            # Provider enforced the schema — parse fields from response JSON
            parsed_rows = []
            for r in responses:
                parsed = {}
                if r is not None and r.text:
                    try:
                        text = r.text.strip()
                        data = json.loads(text)
                        if isinstance(data, dict):
                            parsed = data
                    except (json.JSONDecodeError, ValueError):
                        pass
                parsed_rows.append(parsed)

            # Auto-expand top-level schema properties as columns
            if response_schema and "properties" in response_schema:
                for prop in response_schema["properties"]:
                    df[prop] = [str(row.get(prop, "")) if row else "" for row in parsed_rows]

            # Also expand any json_fields mappings if provided
            for field_map in json_fields:
                field_name = field_map.get("field_name", "")
                out_col    = field_map.get("output_col", field_name)
                df[out_col] = [
                    str(row.get(field_name, "")) if row else "" for row in parsed_rows
                ]
            df[output_column] = [(r.text if r is not None else "") for r in responses]

        # ------------------------------------------------------------------ #
        # 8.  Optional telemetry columns
        # ------------------------------------------------------------------ #
        if include_token_columns:
            df["_input_tokens"]  = [(r.input_tokens  if r else 0)       for r in responses]
            df["_output_tokens"] = [(r.output_tokens if r else 0)       for r in responses]
            df["_latency_ms"]    = [(round(r.latency_ms, 1) if r else 0.0) for r in responses]
            df["_error"]         = [(r.error if r and r.error else "")  for r in responses]

        # ------------------------------------------------------------------ #
        # 9.  Split success / error rows → O and E ports
        # ------------------------------------------------------------------ #
        error_mask   = [bool(r is not None and r.error) for r in responses]
        success_mask = [not e for e in error_mask]

        df_success = sanitize_dataframe(df[success_mask].copy())
        df_errors  = sanitize_dataframe(df[error_mask].copy())

        # ------------------------------------------------------------------ #
        # 10.  Summary message
        # ------------------------------------------------------------------ #
        summary      = tracker.get_summary()
        error_count  = summary["failed_requests"]
        total_tokens = summary["total_tokens"]
        est_actual   = summary["estimated_cost_usd"]
        avg_latency  = summary["avg_latency_ms"]

        cache_hits = len(user_prompts) - sum(
            1 for r in responses if r is not None and r.latency_ms > 0
        )

        msg = (
            f"LLM Process: Completed {len(user_prompts)} records. "
            f"Tokens: {summary['total_input_tokens']:,} in / "
            f"{summary['total_output_tokens']:,} out ({total_tokens:,} total). "
            f"Avg latency: {avg_latency:.0f}ms."
        )
        if cache_hits > 0:
            msg += f" Cache hits: {cache_hits} (skipped API)."
        if error_count > 0:
            msg += f" Errors: {error_count}/{len(user_prompts)} — routed to E port."
        if est_actual > 0:
            msg += f" Estimated cost: ${est_actual:.4f}."
        self.messages.append(msg)

        return {"O": df_success, "E": df_errors}
