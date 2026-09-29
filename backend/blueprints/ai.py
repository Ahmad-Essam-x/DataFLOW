"""
AI & LLM Services REST API Blueprint.
Provides provider connection discovery, health testing, model listings,
and prompt preview rendering for the LLMProcessNode.
"""
import pandas as pd
from flask import Blueprint, request, jsonify

import backend.extensions as ext

bp = Blueprint("ai", __name__)


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
        template = data.get("user_prompt_template", "")
        system_prompt = data.get("system_prompt", "")
        rag_context = data.get("rag_context", {})
        sample_rows = data.get("sample_data", [])

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
                "message": "No sample data available to preview. Run upstream node first or provide sample data.",
            })

        previews = preview_prompts(template, system_prompt, sample_df, rag_context, n=3)
        return jsonify({"success": True, "previews": previews})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
