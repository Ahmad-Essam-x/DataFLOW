"""
AI & LLM Services REST API Blueprint.
Provides provider connection discovery, health testing, model listings,
prompt preview rendering, live progress polling, and token cost estimation
for the LLMProcessNode.
"""
import pandas as pd
from flask import Blueprint, request, jsonify

import backend.extensions as ext

bp = Blueprint("ai", __name__)

# Module-level progress store: node_id -> {completed, total, done}
# Written by LLMProcessNode._progress_cb during batch execution.
_llm_progress: dict = {}


@bp.route("/api/ai/providers", methods=["GET"])
def api_ai_providers():
    """Returns available LLM provider definitions."""
    try:
        from backend.engine.ai.provider_registry import list_providers
        return jsonify({"success": True, "providers": list_providers()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/ai/test-connection", methods=["POST"])
def api_ai_test_connection():
    """Tests connection to an LLM provider (Ollama, OpenAI, Gemini, etc.)."""
    try:
        from backend.engine.ai.provider_registry import get_provider
        data = request.get_json(silent=True) or {}
        provider_type = data.get("provider_type", "ollama")
        connection = data.get("connection", {})
        provider = get_provider(provider_type, connection)
        result = provider.test_connection()
        return jsonify({
            "success": result.success,
            "message": result.message,
            "models_available": result.models_available,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Connection test failed: {str(e)}",
            "models_available": 0,
        }), 200


@bp.route("/api/ai/models", methods=["GET", "POST"])
def api_ai_models():
    """Lists available models from the target provider."""
    try:
        from backend.engine.ai.provider_registry import get_provider
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            provider_type = data.get("provider_type", "ollama")
            connection = data.get("connection", {})
        else:
            provider_type = request.args.get("provider", "ollama")
            connection = {
                "base_url": request.args.get("base_url", ""),
                "api_key": request.args.get("api_key", ""),
            }
        provider = get_provider(provider_type, connection)
        models = provider.list_models()
        return jsonify({
            "success": True,
            "models": [
                {
                    "name": m.name,
                    "size": m.size,
                    "family": m.family,
                    "context_length": m.context_length,
                }
                for m in models
            ],
        })
    except Exception as e:
        return jsonify({"success": False, "models": [], "error": str(e)}), 200


@bp.route("/api/ai/preview-prompt", methods=["POST"])
def api_ai_preview_prompt():
    """Renders user & system prompt templates against sample rows for preview."""
    try:
        from backend.engine.ai.prompt_renderer import preview_prompts
        data = request.get_json(silent=True) or {}
        template     = data.get("user_prompt_template", "")
        system_prompt = data.get("system_prompt", "")
        # Accept both legacy single rag_context dict and new rag_contexts list
        rag_contexts  = data.get("rag_contexts") or data.get("rag_context", {})
        sample_rows   = data.get("sample_data", [])

        if sample_rows:
            sample_df = pd.DataFrame(sample_rows)
        else:
            node_id = data.get("node_id")
            sample_df = pd.DataFrame()
            if node_id:
                df = ext.executor.cache_manager.get_dataframe(node_id)
                if df is not None and not df.empty:
                    sample_df = df.head(5)

        if sample_df.empty:
            return jsonify({
                "success": False,
                "previews": [],
                "message": "No sample data available. Run upstream node first or provide sample data.",
            })

        previews = preview_prompts(template, system_prompt, sample_df, rag_contexts, n=3)
        return jsonify({"success": True, "previews": previews})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/ai/progress/<node_id>", methods=["GET"])
def api_ai_progress(node_id):
    """Poll live batch progress for a running LLM node.

    Returns ``{completed, total, done}`` updated in real-time by the
    node's progress_callback.  Returns zeros when no run is in progress.
    """
    state = _llm_progress.get(node_id, {"completed": 0, "total": 0, "done": False})
    return jsonify(state)


@bp.route("/api/ai/estimate-tokens", methods=["POST"])
def api_ai_estimate_tokens():
    """Estimate token count and cost before running the LLM node.

    Request body::

        {
          "user_prompt_template": "...",
          "system_prompt": "...",
          "model": "gpt-4o-mini",
          "max_tokens": 512,
          "node_id": "node_abc"   // used to fetch cached upstream data
        }

    Response::

        {
          "success": true,
          "row_count": 200,
          "est_input_tokens": 45000,
          "est_output_tokens": 102400,
          "est_total_tokens": 147400,
          "est_cost_usd": 0.062
        }
    """
    try:
        from backend.engine.ai.prompt_renderer import render_template, preview_prompts
        from backend.engine.ai.token_tracker import estimate_cost

        data          = request.get_json(silent=True) or {}
        template      = data.get("user_prompt_template", "")
        system_prompt = data.get("system_prompt", "")
        model         = data.get("model", "")
        max_tokens    = int(data.get("max_tokens", 512))
        node_id       = data.get("node_id", "")

        # Fetch upstream DataFrame
        sample_df = pd.DataFrame()
        if node_id:
            df = ext.executor.cache_manager.get_dataframe(node_id)
            if df is not None and not df.empty:
                sample_df = df

        if sample_df.empty:
            return jsonify({
                "success": False,
                "message": "No upstream data available. Run the upstream node first.",
            })

        # Estimate via character count on all rows
        total_user_chars = 0
        for i in range(len(sample_df)):
            row = sample_df.iloc[i]
            rendered = render_template(template, row)
            total_user_chars += len(rendered)

        sys_chars = len(system_prompt) * len(sample_df)
        est_input  = (total_user_chars + sys_chars) // 4
        est_output = max_tokens * len(sample_df)
        est_cost   = estimate_cost(model, est_input, est_output)

        return jsonify({
            "success": True,
            "row_count": len(sample_df),
            "est_input_tokens": est_input,
            "est_output_tokens": est_output,
            "est_total_tokens": est_input + est_output,
            "est_cost_usd": round(est_cost, 6),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/ai/schema-fit/preview", methods=["POST"])
def api_ai_schema_fit_preview():
    """Generates an on-demand preview of schema fitting transformation steps and output data."""
    try:
        from backend.engine.nodes.schema_fit import SchemaFitNode
        data = request.get_json(silent=True) or {}

        config = data.get("config", {})
        target_node_id = data.get("target_node_id")
        source_node_id = data.get("source_node_id")
        model_node_id = data.get("model_node_id")

        target_port = data.get("target_port", "O")
        source_port = data.get("source_port", "O")
        model_port = data.get("model_port", "M")

        df_target = None
        df_source = None
        df_model = None

        # Fetch cached DataFrames
        if target_node_id:
            df_target = ext.executor.cache_manager.get_dataframe(target_node_id, target_port)
            if df_target is None and hasattr(ext.executor, "_local_data_cache"):
                df_target = ext.executor._local_data_cache.get(target_node_id, {}).get(target_port)

        if source_node_id:
            df_source = ext.executor.cache_manager.get_dataframe(source_node_id, source_port)
            if df_source is None and hasattr(ext.executor, "_local_data_cache"):
                df_source = ext.executor._local_data_cache.get(source_node_id, {}).get(source_port)

        if model_node_id:
            df_model = ext.executor.cache_manager.get_dataframe(model_node_id, model_port)
            if df_model is None and hasattr(ext.executor, "_local_data_cache"):
                df_model = ext.executor._local_data_cache.get(model_node_id, {}).get(model_port)

        # Allow raw sample rows in payload if provided directly
        if df_target is None and data.get("target_sample"):
            df_target = pd.DataFrame(data["target_sample"])
            if data.get("target_columns"):
                t_cols = [c for c in data["target_columns"] if c in df_target.columns]
                if t_cols:
                    df_target = df_target[t_cols]
        if df_source is None and data.get("source_sample"):
            df_source = pd.DataFrame(data["source_sample"])
            if data.get("source_columns"):
                s_cols = [c for c in data["source_columns"] if c in df_source.columns]
                if s_cols:
                    df_source = df_source[s_cols]

        if df_target is None or df_target.empty:
            return jsonify({
                "success": False,
                "message": "Target reference data not available. Please run the Target upstream node first.",
            })

        if df_source is None or df_source.empty:
            return jsonify({
                "success": False,
                "message": "Source unformatted data not available. Please run the Source upstream node first.",
            })

        # Run SchemaFitNode in preview mode (sample up to 20 rows of source for fast preview)
        node_instance = SchemaFitNode(node_id="preview", config=config)
        inputs_map = {"T": df_target, "S": df_source.head(20).copy()}
        if df_model is not None:
            inputs_map["M"] = df_model

        outputs = node_instance.execute(inputs_map)
        df_steps = outputs.get("T", pd.DataFrame())
        df_data = outputs.get("D", pd.DataFrame())

        steps_records = df_steps.to_dict(orient="records") if isinstance(df_steps, pd.DataFrame) else []
        preview_records = df_data.head(5).to_dict(orient="records") if isinstance(df_data, pd.DataFrame) else []
        columns = list(df_data.columns) if isinstance(df_data, pd.DataFrame) else []

        return jsonify({
            "success": True,
            "steps": steps_records,
            "data_preview": preview_records,
            "columns": columns,
            "row_count": len(df_data) if isinstance(df_data, pd.DataFrame) else 0,
            "messages": getattr(node_instance, "messages", []),
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

