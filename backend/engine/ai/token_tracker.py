import time
from typing import Any, Dict

# Very rough heuristic pricing USD per 1M tokens (input, output)
COST_ESTIMATES = {
    "gpt-4o-mini": (0.150, 0.600),
    "gpt-4o": (5.0, 15.0),
    "gemini-1.5-flash": (0.35, 1.05),
    "gemini-1.5-pro": (3.5, 10.5),
    "local": (0.0, 0.0),
    "default": (1.0, 3.0)
}

def estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    model_lower = model_name.lower()
    
    price_in, price_out = COST_ESTIMATES["default"]
    
    if "local" in model_lower or "llama" in model_lower or "mistral" in model_lower:
        price_in, price_out = COST_ESTIMATES["local"]
    elif "gpt-4o-mini" in model_lower:
        price_in, price_out = COST_ESTIMATES["gpt-4o-mini"]
    elif "gpt-4o" in model_lower:
        price_in, price_out = COST_ESTIMATES["gpt-4o"]
    elif "gemini" in model_lower and "flash" in model_lower:
        price_in, price_out = COST_ESTIMATES["gemini-1.5-flash"]
    elif "gemini" in model_lower and "pro" in model_lower:
        price_in, price_out = COST_ESTIMATES["gemini-1.5-pro"]
        
    return (input_tokens / 1_000_000.0) * price_in + (output_tokens / 1_000_000.0) * price_out

class TokenTracker:
    def __init__(self, model_name: str = "default"):
        self.model_name = model_name
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_requests = 0
        self.failed_requests = 0
        self.total_latency_ms = 0.0
        
    def record(self, response: Any):
        """Record stats from an LLMResponse.
        Assuming response has attributes: input_tokens, output_tokens, latency_ms, error (boolean)
        """
        self.total_requests += 1
        
        # Handle cases where response might be None or just string due to error handling
        if response is None or isinstance(response, str):
            self.failed_requests += 1
            return
            
        # Try to extract properties, using generic hasattr checks
        is_error = getattr(response, "error", False)
        if is_error:
            self.failed_requests += 1
            
        self.total_input_tokens += getattr(response, "input_tokens", 0)
        self.total_output_tokens += getattr(response, "output_tokens", 0)
        self.total_latency_ms += getattr(response, "latency_ms", 0.0)
        
    def get_summary(self) -> Dict[str, Any]:
        avg_latency = 0.0
        successful_reqs = self.total_requests - self.failed_requests
        if successful_reqs > 0:
            avg_latency = self.total_latency_ms / successful_reqs
            
        total_tokens = self.total_input_tokens + self.total_output_tokens
        
        est_cost = estimate_cost(self.model_name, self.total_input_tokens, self.total_output_tokens)
        
        return {
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": total_tokens,
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "avg_latency_ms": avg_latency,
            "total_latency_ms": self.total_latency_ms,
            "estimated_cost_usd": est_cost
        }
