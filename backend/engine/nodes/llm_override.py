"""
LLM Override Tool Node.
Authentic Alteryx GenAI tool that configures and passes Large Language Model (LLM)
connection parameters downstream to AI-assisted tools (e.g. Schema Fit, LLM Process).
"""
import pandas as pd
from typing import Dict, Any, Optional

from .base import BaseNode, sanitize_dataframe


class LLMOverrideNode(BaseNode):
    type_name = "llm_override"
    category = "ai"
    display_name = "LLM Override"
    description = "Configure and pass LLM connection settings to downstream AI tools"
    input_ports = []
    output_ports = ["M"]

    def execute(
        self,
        inputs: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, pd.DataFrame]:
        cfg = self.config or {}

        provider_type = cfg.get("provider_type", "ollama")
        model = cfg.get("model", "")
        conn = cfg.get("connection", {})
        base_url = conn.get("base_url", "")
        api_key = conn.get("api_key", "")
        from backend.engine.ai.secrets import resolve_api_key, store_api_key
        if api_key:
            store_api_key(provider_type, base_url, api_key)  # downstream tools resolve it from the store
        else:
            api_key = resolve_api_key(provider_type, base_url)
        temperature = cfg.get("temperature", 0.3)
        max_tokens = cfg.get("max_tokens", 1024)
        top_p = cfg.get("top_p", 1.0)
        timeout_seconds = cfg.get("timeout_seconds", 30.0)

        # Build clean config payload for downstream nodes
        llm_config_payload = {
            "provider_type": provider_type,
            "model": model,
            # The key is deliberately NOT carried in the DataFrame: df.attrs is written to cache files on spill/lock.
            # Downstream tools get it from the credential store via get_provider().
            "connection": {
                "base_url": base_url,
                "api_key": "",
            },
            "temperature": float(temperature) if temperature is not None else 0.3,
            "max_tokens": int(max_tokens) if max_tokens is not None else 1024,
            "top_p": float(top_p) if top_p is not None else 1.0,
            "timeout_seconds": float(timeout_seconds) if timeout_seconds is not None else 30.0,
        }

        # Build summary metadata DataFrame for display on port M
        masked_key = "stored" if api_key else "None"  # never echo any part of the key into output data
        summary_rows = [
            {"Setting": "Provider", "Value": str(provider_type)},
            {"Setting": "Model", "Value": str(model or "Default")},
            {"Setting": "Base URL", "Value": str(base_url or "Default")},
            {"Setting": "API Key", "Value": masked_key},
            {"Setting": "Temperature", "Value": str(temperature)},
            {"Setting": "Max Tokens", "Value": str(max_tokens)},
        ]
        df_model = pd.DataFrame(summary_rows)
        df_model.attrs["llm_config"] = llm_config_payload
        df_model = sanitize_dataframe(df_model)

        self.messages.append(
            f"LLM Override: Providing connection settings for {provider_type} / {model or 'default model'} on port M."
        )

        return {"M": df_model}
