import time
import requests
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

from .provider_base import (
    LLMProvider,
    LLMConfig,
    LLMResponse,
    ModelInfo,
    ConnectionTestResult
)

class OpenAICompatProvider(LLMProvider):
    provider_name = "openai_compat"
    requires_api_key = True
    default_base_url = "https://api.openai.com/v1"
    
    def __init__(self, base_url: str = "https://api.openai.com/v1", api_key: str = "", default_model: str = "gpt-4o-mini"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.default_model = default_model
        
        self.is_azure = "openai.azure.com" in self.base_url.lower()
        
    def _get_headers(self) -> dict:
        headers = {
            "Content-Type": "application/json"
        }
        if self.is_azure:
            headers["api-key"] = self.api_key
        else:
            headers["Authorization"] = f"Bearer {self.api_key}"
            
        return headers
        
    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        start_time = time.time()
        
        url = f"{self.base_url}/chat/completions"
        if self.is_azure:
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            if 'api-version' not in query_params:
                url += "?api-version=2024-02-15-preview"
                
        payload = {
            "model": config.model or self.default_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p
        }
        
        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=self._get_headers(),
                timeout=config.timeout_seconds
            )
            latency_ms = (time.time() - start_time) * 1000
            
            if response.status_code != 200:
                error_msg = self._handle_error_response(response)
                return LLMResponse(
                    text="",
                    input_tokens=0,
                    output_tokens=0,
                    model=config.model,
                    latency_ms=latency_ms,
                    error=error_msg
                )
                
            data = response.json()
            
            choices = data.get("choices", [])
            content = ""
            if choices and len(choices) > 0:
                message = choices[0].get("message", {})
                content = message.get("content", "")
                
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            return LLMResponse(
                text=content,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
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
                error=f"Connection refused to {self.base_url}. Is the service running?"
            )
        except requests.Timeout:
            latency_ms = (time.time() - start_time) * 1000
            return LLMResponse(
                text="",
                input_tokens=0,
                output_tokens=0,
                model=config.model,
                latency_ms=latency_ms,
                error=f"Request timed out after {config.timeout_seconds} seconds"
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
            
    def _handle_error_response(self, response: requests.Response) -> str:
        status = response.status_code
        try:
            data = response.json()
            message = data.get("error", {}).get("message", response.text)
        except Exception:
            message = response.text
            
        if status == 401:
            return f"Unauthorized (401): Invalid API key or missing authentication. {message}"
        elif status == 429:
            return f"Rate Limited (429): You have exceeded your rate limit. {message}"
        elif status == 500:
            return f"Server Error (500): The API provider encountered an error. {message}"
        elif status == 404:
            return f"Not Found (404): The API endpoint or model was not found. {message}"
        else:
            return f"API Error ({status}): {message}"
            
    def test_connection(self) -> ConnectionTestResult:
        try:
            url = f"{self.base_url}/models"
            if self.is_azure:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if 'api-version' not in query_params:
                    url += "?api-version=2024-02-15-preview"
                    
            response = requests.get(
                url, 
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                models = response.json().get("data", [])
                return ConnectionTestResult(
                    success=True,
                    message="Successfully connected",
                    models_available=len(models)
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    message=self._handle_error_response(response),
                    models_available=0
                )
        except requests.ConnectionError:
            return ConnectionTestResult(
                success=False,
                message=f"Connection refused to {self.base_url}. Is the service running?",
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
            url = f"{self.base_url}/models"
            if self.is_azure:
                parsed_url = urlparse(url)
                query_params = parse_qs(parsed_url.query)
                if 'api-version' not in query_params:
                    url += "?api-version=2024-02-15-preview"
                    
            response = requests.get(
                url, 
                headers=self._get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            models_data = data.get("data", [])
            
            result = []
            for m in models_data:
                result.append(ModelInfo(
                    name=m.get("id", "unknown"),
                    size=0,
                    family="openai-compat",
                    context_length=0
                ))
            return result
        except Exception:
            return []
