"""
Fallback Node for Unsupported or Divergent Tools (Alteryx Ingestion Compatibility).

When an external workflow (e.g. Alteryx .yxmd) contains a tool not natively implemented
in DataFlow (such as spatial operations, predictive macros, or regex parsing), it is mapped
to an UnsupportedToolNode.

Execution behavior:
- Acts as a non-destructive passthrough: forwards records from input to output.
- Preserves the original tool configuration, plugin DLL, Tool ID, and raw XML block.
- Generates transparent log warnings rather than failing the pipeline.
"""
from typing import Dict, Any, Optional
import pandas as pd
import logging

from .base import BaseNode, sanitize_dataframe

logger = logging.getLogger(__name__)


class UnsupportedToolNode(BaseNode):
    type_name = "unsupported_tool"
    category = "fallback"
    display_name = "Unsupported Tool"
    description = "Preserved Alteryx tool not natively implemented. Operates as a non-destructive passthrough."
    input_ports = ["I"]
    output_ports = ["O"]

    def __init__(self, node_id: str, config: Dict[str, Any]):
        super().__init__(node_id, config)
        self.original_tool = self.config.get("original_tool", "Unknown Tool")
        self.original_plugin = self.config.get("original_plugin", "")
        self.alteryx_tool_id = self.config.get("tool_id", node_id)
        self.raw_xml = self.config.get("raw_xml", "")

    def execute(self, inputs: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> Dict[str, pd.DataFrame]:
        self.messages = []
        
        # Determine incoming data from port 'I' or first available port
        incoming_df = None
        for port in ["I", "L", "R", "T", "S", "F"]:
            if port in inputs and isinstance(inputs[port], pd.DataFrame):
                incoming_df = inputs[port]
                break

        if incoming_df is None and inputs:
            # Pick any available dataframe
            first_val = next(iter(inputs.values()))
            if isinstance(first_val, pd.DataFrame):
                incoming_df = first_val

        tool_label = f"'{self.original_tool}' (Tool #{self.alteryx_tool_id})" if self.alteryx_tool_id else f"'{self.original_tool}'"
        
        if incoming_df is not None:
            clean_df = sanitize_dataframe(incoming_df)
            msg = (
                f"Passthrough Notice: {tool_label} is preserved as a fallback. "
                f"Forwarded {len(clean_df):,} records and {len(clean_df.columns)} columns downstream."
            )
            self.messages.append(msg)
            logger.info("[%s] %s", self.node_id, msg)
            return {"O": clean_df}
        else:
            msg = f"Passthrough Notice: {tool_label} had no incoming dataset connected."
            self.messages.append(msg)
            return {"O": pd.DataFrame()}
