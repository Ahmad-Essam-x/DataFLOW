"""
Google Gemini LLM Provider.
Uses the google-generativeai SDK when available, falls back to REST API via requests.
"""
import time
import requests
from backend.engine.ai import http as llm_http
from typing import List, Optional

from .provider_base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    ModelInfo,
    ConnectionTestResult,
)


class GeminiProvider(LLMProvider):
    """Google Gemini provider using the REST API directly (no SDK dependency)."""

    provider_name = "gemini"
    requires_api_key = True
    default_base_url = "https://generativelanguage.googleapis.com"

    def __init__(self, base_url: str = "https://generativelanguage.googleapis.com", api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict:
        """API key goes in a header, never the URL (URLs end up in logs and error messages)."""
        return {"x-goog-api-key": self.api_key} if self.api_key else {}

    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        start_time = time.time()
        model = config.model or "gemini-2.0-flash"

        url = f"{self.base_url}/v1beta/models/{model}:generateContent"

        # Build contents array
        contents = []
        if system_prompt:
            contents.append({
                "role": "user",
                "parts": [{"text": f"[System Instructions]\n{system_prompt}"}],
            })
            contents.append({
                "role": "model",
                "parts": [{"text": "Understood. I will follow these instructions."}],
            })
        contents.append({
            "role": "user",
            "parts": [{"text": user_prompt}],
        })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": config.temperature,
                "maxOutputTokens": config.max_tokens,
                "topP": config.top_p,
            },
        }

        try:
            response = llm_http.post(url, json=payload, headers=self._headers(), timeout=config.timeout_seconds)
            latency_ms = (time.time() - start_time) * 1000

            if response.status_code != 200:
                try:
                    err_data = response.json()
                    err_msg = err_data.get("error", {}).get("message", response.text)
                except Exception:
                    err_msg = response.text
                return LLMResponse(
                    text="",
                    input_tokens=0,
                    output_tokens=0,
                    model=model,
                    latency_ms=latency_ms,
                    error=f"Gemini API error ({response.status_code}): {err_msg}",
                )

            data = response.json()
            candidates = data.get("candidates", [])
            text = ""
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "".join(p.get("text", "") for p in parts)

            # Extract token counts from usageMetadata
            usage = data.get("usageMetadata", {})
            input_tokens = usage.get("promptTokenCount", 0)
            output_tokens = usage.get("candidatesTokenCount", 0)

            return LLMResponse(
                text=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
                latency_ms=latency_ms,
                error=None,
            )

        except requests.ConnectionError:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="", input_tokens=0, output_tokens=0, model=model,
                latency_ms=latency_ms,
                error="Cannot connect to Gemini API. Check your internet connection.",
            )
        except requests.Timeout:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="", input_tokens=0, output_tokens=0, model=model,
                latency_ms=latency_ms,
                error=f"Gemini request timed out after {config.timeout_seconds}s",
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="", input_tokens=0, output_tokens=0, model=model,
                latency_ms=latency_ms,
                error=f"Gemini error: {str(e)}",
            )

    def test_connection(self) -> ConnectionTestResult:
        try:
            url = f"{self.base_url}/v1beta/models"
            response = llm_http.get(url, headers=self._headers(), timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                return ConnectionTestResult(
                    success=True,
                    message="Successfully connected to Google Gemini",
                    models_available=len(models),
                )
            else:
                try:
                    err_msg = response.json().get("error", {}).get("message", response.text)
                except Exception:
                    err_msg = response.text
                return ConnectionTestResult(
                    success=False,
                    message=f"Gemini API error ({response.status_code}): {err_msg}",
                    models_available=0,
                )
        except requests.ConnectionError:
            return ConnectionTestResult(
                success=False,
                message="Cannot connect to Gemini API. Check your internet connection.",
                models_available=0,
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                models_available=0,
            )

    def list_models(self) -> List[ModelInfo]:
        try:
            url = f"{self.base_url}/v1beta/models"
            response = llm_http.get(url, headers=self._headers(), timeout=10)
            if response.status_code != 200:
                return []

            models_data = response.json().get("models", [])
            result = []
            for m in models_data:
                name = m.get("name", "").replace("models/", "")
                # Only include generative models
                if "generateContent" in str(m.get("supportedGenerationMethods", [])):
                    result.append(ModelInfo(
                        name=name,
                        size=0,
                        family="gemini",
                        context_length=m.get("inputTokenLimit", 0),
                    ))
            return result
        except Exception:
            return []
