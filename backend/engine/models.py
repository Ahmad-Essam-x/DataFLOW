"""
Pydantic v2 data models for the DataFLOW workflow schema.

Used in WorkflowManager.validate_and_normalize() for load-time schema validation —
catches malformed workflow files with clear errors instead of cryptic KeyErrors at
execution time.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------

class WorkflowNode(BaseModel):
    """A single tool node on the canvas."""

    id: str
    type: str
    name: str = ""
    x: int = 100
    y: int = 100
    config: Dict[str, Any] = Field(default_factory=dict)
    container_id: Optional[str] = None
    is_cached: bool = False

    model_config = {"extra": "allow"}

    @field_validator("id", "type", mode="before")
    @classmethod
    def _non_empty_str(cls, v: Any) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("name", mode="before")
    @classmethod
    def _coerce_name(cls, v: Any) -> str:
        return str(v).strip() if v is not None else ""

    @field_validator("x", "y", mode="before")
    @classmethod
    def _coerce_int(cls, v: Any) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 100

    @field_validator("config", mode="before")
    @classmethod
    def _coerce_config(cls, v: Any) -> Dict[str, Any]:
        return v if isinstance(v, dict) else {}


class WorkflowConnection(BaseModel):
    """A directed edge between two node ports."""

    id: str = ""
    source: str
    sourceHandle: str = "O"
    target: str
    targetHandle: str = "I"

    @field_validator("source", "target", mode="before")
    @classmethod
    def _non_empty_str(cls, v: Any) -> str:
        v = str(v or "").strip()
        if not v:
            raise ValueError("must not be empty")
        return v

    @field_validator("sourceHandle", "targetHandle", mode="before")
    @classmethod
    def _coerce_handle(cls, v: Any) -> str:
        return str(v).strip() if v else ("O" if v is None else "I")


class WorkflowViewport(BaseModel):
    """Canvas pan/zoom state."""

    zoom: float = 1.0
    panX: float = 0.0
    panY: float = 0.0

class WorkflowMetadata(BaseModel):
    """Non-functional metadata stamped on every save."""

    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    version: str = "2.1.0"
    author: str = Field(
        default_factory=lambda: os.environ.get("USERNAME", "Analyst")
    )
    description: str = ""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Top-level Workflow model
# ---------------------------------------------------------------------------

class Workflow(BaseModel):
    """
    Complete workflow document as stored on disk and exchanged with the frontend.

    ``model_config = {"extra": "allow"}`` ensures unknown top-level keys (e.g.
    future fields added by newer UI versions) are preserved round-trip.
    """

    name: str = "Untitled Workflow"
    description: str = ""
    metadata: WorkflowMetadata = Field(default_factory=WorkflowMetadata)
    viewport: WorkflowViewport = Field(default_factory=WorkflowViewport)
    nodes: List[WorkflowNode] = Field(default_factory=list)
    connections: List[WorkflowConnection] = Field(default_factory=list)
    containers: List[Any] = Field(default_factory=list)
    comments: List[Any] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    @field_validator("name", mode="before")
    @classmethod
    def _coerce_name(cls, v: Any) -> str:
        name = str(v).strip() if v else ""
        return name or "Untitled Workflow"

    @field_validator("nodes", mode="before")
    @classmethod
    def _coerce_nodes(cls, v: Any) -> list:
        return v if isinstance(v, list) else []

    @field_validator("connections", mode="before")
    @classmethod
    def _coerce_connections(cls, v: Any) -> list:
        return v if isinstance(v, list) else []

    @field_validator("metadata", mode="before")
    @classmethod
    def _coerce_metadata(cls, v: Any) -> Any:
        return v if isinstance(v, dict) else {}

    @field_validator("viewport", mode="before")
    @classmethod
    def _coerce_viewport(cls, v: Any) -> Any:
        return v if isinstance(v, dict) else {}


# ---------------------------------------------------------------------------
# Execution result models
# ---------------------------------------------------------------------------

class NodeExecutionResult(BaseModel):
    """
    Summary of a single node's execution outcome, as stored in
    ``last_result["node_results"]``.
    """

    node_id: str
    node_name: str = ""
    node_type: str = ""
    status: str = "success"          # "success" | "error" | "skipped"
    row_count: int = 0
    column_count: int = 0
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None

    model_config = {"extra": "allow"}


class ExecutionResult(BaseModel):
    """
    Top-level result object returned by WorkflowExecutor and stored as
    ``window.appLastResult`` on the frontend.
    """

    run_id: str = ""
    status: str = "success"          # "success" | "error" | "partial"
    total_time_ms: float = 0.0
    node_results: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    model_config = {"extra": "allow"}
