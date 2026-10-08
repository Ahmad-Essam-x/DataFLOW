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
