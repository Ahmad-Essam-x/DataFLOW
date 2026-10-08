from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class LLMConfig:
    model: str
    temperature: float = 0.3
    max_tokens: int = 512
    top_p: float = 1.0
    timeout_seconds: float = 30.0
    response_schema: Optional[dict] = None  # JSON Schema for structured output (OpenAI/Gemini)

@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_ms: float
    error: Optional[str] = None

@dataclass
class ModelInfo:
    name: str
    size: int = 0
    family: str = ""
    context_length: int = 0

@dataclass
class ConnectionTestResult:
    success: bool
    message: str = ""
    models_available: int = 0

class LLMProvider(ABC):
    provider_name: str = "base"
    requires_api_key: bool = False
    default_base_url: str = ""

    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, config: LLMConfig) -> LLMResponse:
        pass

    @abstractmethod
    def test_connection(self) -> ConnectionTestResult:
        pass

    @abstractmethod
    def list_models(self) -> List[ModelInfo]:
        pass
