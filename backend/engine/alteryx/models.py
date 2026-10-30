"""
Models for Alteryx Ingestion & Compatibility Engine.
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class ConversionWarning:
    tool_id: str
    tool_name: str
    severity: str  # 'info', 'warning', 'error'
    message: str
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class YxmdParseResult:
    workflow: Dict[str, Any]
    warnings: List[ConversionWarning] = field(default_factory=list)
    total_tools: int = 0
    mapped_tools: int = 0
    fallback_tools: int = 0
    containers_count: int = 0
    comments_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workflow": self.workflow,
            "warnings": [w.to_dict() for w in self.warnings],
            "stats": {
                "total_tools": self.total_tools,
                "mapped_tools": self.mapped_tools,
                "fallback_tools": self.fallback_tools,
                "containers_count": self.containers_count,
                "comments_count": self.comments_count,
                "coverage_pct": round((self.mapped_tools / max(1, self.total_tools)) * 100, 1),
                "substituted_tools": self.substituted_tools()
            }
        }

    def substituted_tools(self) -> List[Dict[str, Any]]:
        """Tools DataFlow could not convert. They pass data through unchanged, so results can differ from Alteryx."""
        out = []
        for node in self.workflow.get("nodes", []):
            if node.get("type") == "unsupported_tool":
                cfg = node.get("config") or {}
                out.append({"node_id": node.get("id"), "tool_id": cfg.get("tool_id"),
                            "tool": cfg.get("original_tool") or "Unknown tool"})
        return out
