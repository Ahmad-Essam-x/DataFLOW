import time
import requests
from backend.engine.ai import http as llm_http
from typing import List, Optional

from .provider_base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    ModelInfo,
    ConnectionTestResult
)

class OllamaProvider(LLMProvider):
    provider_name = "ollama"
    requires_api_key = False
    default_base_url = "http://localhost:11434"
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        
    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        start_time = time.time()
        
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": config.temperature,
                "num_predict": config.max_tokens,
                "top_p": config.top_p
            }
        }
        
        try:
            response = llm_http.post(url, json=payload, timeout=config.timeout_seconds)
            latency_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                error_msg = f"Ollama API returned status code {response.status_code}: {response.text}"
                return LLMResponse(
                    text="",
                    input_tokens=0,
                    output_tokens=0,
                    model=config.model,
                    latency_ms=latency_ms,
                    error=error_msg
                )
                
            data = response.json()
            message = data.get("message", {})
            content = message.get("content", "")
            
            prompt_eval_count = data.get("prompt_eval_count", 0)
            eval_count = data.get("eval_count", 0)
            
            return LLMResponse(
                text=content,
                input_tokens=prompt_eval_count,
                output_tokens=eval_count,
                model=config.model,
                latency_ms=latency_ms,
                error=None
            )
            
        except requests.ConnectionError:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="",
                input_tokens=0,
                output_tokens=0,
                model=config.model,
                latency_ms=latency_ms,
                error="Ollama is not running. Start it with: ollama serve"
            )
        except requests.Timeout:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="",
                input_tokens=0,
                output_tokens=0,
                model=config.model,
                latency_ms=latency_ms,
                error=f"Request to Ollama timed out after {config.timeout_seconds} seconds"
            )
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="",
                input_tokens=0,
                output_tokens=0,
                model=config.model,
                latency_ms=latency_ms,
                error=f"An error occurred: {str(e)}"
            )
            
    def test_connection(self) -> ConnectionTestResult:
        try:
            url = f"{self.base_url}/api/tags"
            response = llm_http.get(url, timeout=5)
            
            if response.status_code == 200:
                models = response.json().get("models", [])
                return ConnectionTestResult(
                    success=True,
                    message="Successfully connected to Ollama",
                    models_available=len(models)
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"Failed to connect. Status code: {response.status_code}",
                    models_available=0
                )
        except requests.ConnectionError:
            return ConnectionTestResult(
                success=False,
                message="Ollama is not running. Start it with: ollama serve",
                models_available=0
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                models_available=0
            )
            
    def list_models(self) -> List[ModelInfo]:
        try:
            url = f"{self.base_url}/api/tags"
            response = llm_http.get(url, timeout=10)
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            models_data = data.get("models", [])
            
            result = []
            for m in models_data:
                details = m.get("details", {})
                result.append(ModelInfo(
                    name=m.get("name", "unknown"),
                    size=m.get("size", 0),
                    family=details.get("family", ""),
                    context_length=0
                ))
            return result
        except Exception:
            return []
