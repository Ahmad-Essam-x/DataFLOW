"""
Provider Registry & Factory.
Discovers, lists, and instantiates LLM providers for the LLM Process tool.
"""
from typing import Dict, Any, List, Optional, Type

from .provider_base import LLMProvider, LLMConfig, LLMResponse, ModelInfo, ConnectionTestResult
from .provider_ollama import OllamaProvider
from .provider_openai_compat import OpenAICompatProvider


# --- Provider Registry -----------------------------------------------------------
# Maps provider_type string -> provider class
# 'openai', 'azure_openai', 'lm_studio' are convenience aliases for OpenAICompatProvider
# with different default base URLs.

PROVIDER_REGISTRY: Dict[str, Type[LLMProvider]] = {
    "ollama": OllamaProvider,
    "openai_compat": OpenAICompatProvider,
    "openai": OpenAICompatProvider,
    "azure_openai": OpenAICompatProvider,
    "lm_studio": OpenAICompatProvider,
}

# Lazy-register optional providers (Gemini)
try:
    from .provider_gemini import GeminiProvider
    PROVIDER_REGISTRY["gemini"] = GeminiProvider
except ImportError:
    pass


# Default base URLs per alias
_DEFAULT_URLS: Dict[str, str] = {
    "ollama": "http://localhost:11434",
    "openai": "https://api.openai.com/v1",
    "lm_studio": "http://localhost:1234/v1",
    "openai_compat": "",
    "azure_openai": "",
    "gemini": "https://generativelanguage.googleapis.com",
}


def get_provider(provider_type: str, connection_config: Dict[str, Any]) -> LLMProvider:
    """
    Factory: instantiate an LLMProvider from a type string and connection dict.
    connection_config keys: base_url, api_key, endpoint, default_model
    """
    if provider_type not in PROVIDER_REGISTRY:
        available = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(f"Unknown provider type '{provider_type}'. Available: {available}")

    cls = PROVIDER_REGISTRY[provider_type]
    cfg = dict(connection_config)

    # Fill in default base_url if not specified
    if not cfg.get("base_url") and provider_type in _DEFAULT_URLS:
        cfg["base_url"] = _DEFAULT_URLS[provider_type]

    # Instantiate based on provider class type
    if cls is OllamaProvider:
        return OllamaProvider(base_url=cfg.get("base_url", "http://localhost:11434"))
    elif cls is OpenAICompatProvider:
        return OpenAICompatProvider(
            base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            api_key=cfg.get("api_key", ""),
            default_model=cfg.get("default_model", "gpt-4o-mini"),
        )
    else:
        # GeminiProvider or any future provider — pass connection config
        return cls(
            base_url=cfg.get("base_url", ""),
            api_key=cfg.get("api_key", ""),
        )


def list_providers() -> List[Dict[str, Any]]:
    """Return metadata about all available providers for the frontend."""
    providers = [
        {
            "id": "ollama",
            "name": "Ollama (Local)",
            "requires_api_key": False,
            "default_url": "http://localhost:11434",
            "description": "Run local models (Llama 3, Mistral, Phi, Gemma) via Ollama — free, no API key",
        },
        {
            "id": "lm_studio",
            "name": "LM Studio (Local)",
            "requires_api_key": False,
            "default_url": "http://localhost:1234/v1",
            "description": "Run local GGUF models via LM Studio — free, no API key",
        },
        {
            "id": "openai",
            "name": "OpenAI",
            "requires_api_key": True,
            "default_url": "https://api.openai.com/v1",
            "description": "OpenAI API (GPT-4o, GPT-4o-mini, GPT-4.1)",
        },
        {
            "id": "gemini",
            "name": "Google Gemini",
            "requires_api_key": True,
            "default_url": "https://generativelanguage.googleapis.com",
            "description": "Google Gemini API (Gemini 2.0 Flash, Gemini 2.5 Pro)",
        },
        {
            "id": "azure_openai",
            "name": "Azure OpenAI",
            "requires_api_key": True,
            "default_url": "",
            "description": "Azure-hosted OpenAI models with enterprise governance",
        },
        {
            "id": "openai_compat",
            "name": "OpenAI-Compatible",
            "requires_api_key": False,
            "default_url": "",
            "description": "Any OpenAI-compatible endpoint (vLLM, Groq, Together, Fireworks)",
        },
    ]
    # Only include gemini if the provider is actually available
    if "gemini" not in PROVIDER_REGISTRY:
        providers = [p for p in providers if p["id"] != "gemini"]
    return providers
