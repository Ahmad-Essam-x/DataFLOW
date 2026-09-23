"""
Core SQL Compiler Engine.
Topologically sorts workflow nodes, resolves port-scoped CTE lineage,
generates Common Table Expressions (CTEs), and produces complete executable SQL scripts.
"""
import re
import datetime
from typing import Dict, Any, List, Optional, Set, Tuple, Union

from backend.engine.dag import DAG, WorkflowValidationError
from backend.engine.sql_compiler.dialects import SQLDialect, get_dialect
from backend.engine.sql_compiler.node_transpilers import get_node_transpiler, NodeTranspileError


def _slugify(text: str) -> str:
    """Produces a clean SQL identifier slug from node names."""
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", text.strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "node"


class SQLCompiler:
    """Compiles an Antigravity DataFlow visual workflow DAG into executable SQL."""

    def __init__(
        self,
        workflow: Dict[str, Any],
        dialect: Optional[Union[SQLDialect, str]] = None,
        options: Optional[Dict[str, Any]] = None
    ):
        self.workflow = workflow
        if isinstance(dialect, SQLDialect):
            self.dialect = dialect
        else:
            self.dialect = get_dialect(dialect)
        self.options = dict(options or {})
        self.warnings: List[str] = []

    def compile(self) -> Dict[str, Any]:
        """Main entrypoint: compiles workflow and returns SQL string and metadata."""
        nodes = self.workflow.get("nodes", [])
        connections = self.workflow.get("connections", [])

        if not nodes:
            return {
                "success": True,
                "sql": "-- Workflow is empty. No SQL generated.\nSELECT 1 AS empty_pipeline WHERE 1=0;",
                "dialect": self.dialect.name,
                "warnings": ["Workflow contains no nodes."],
                "ctes_generated": 0
            }

        # 1. Filter disabled containers and nodes
        containers = self.workflow.get("containers", [])
        disabled_container_ids = {c["id"] for c in containers if c.get("disabled")}
        disabled_node_ids = set()

        for c in containers:
            if c.get("disabled"):
                disabled_node_ids.update(c.get("node_ids") or c.get("nodeIds") or [])

        for n in nodes:
            if n.get("disabled") or n.get("container_id") in disabled_container_ids or n.get("containerId") in disabled_container_ids:
                disabled_node_ids.add(n["id"])

        # Filter out comments and container nodes from execution graph
        doc_node_ids = {n["id"] for n in nodes if n.get("type") in ["tool_container", "comment"]}
        skipped_ids = disabled_node_ids.union(doc_node_ids)

        active_nodes = [n for n in nodes if n["id"] not in skipped_ids]
        active_connections = [
            c for c in connections
            if (c.get("source") or c.get("from_node")) not in skipped_ids
            and (c.get("target") or c.get("to_node")) not in skipped_ids
        ]

        if not active_nodes:
            return {
                "success": True,
                "sql": "-- All nodes are disabled or empty.\nSELECT 1 AS empty_pipeline WHERE 1=0;",
                "dialect": self.dialect.name,
                "warnings": ["All nodes in the workflow are disabled or bypassed."],
                "ctes_generated": 0
            }

        # 2. Build DAG & Topological Execution Order
        try:
            dag = DAG(active_nodes, active_connections)
            execution_order = dag.topological_sort()
        except WorkflowValidationError as e:
            return {
                "success": False,
                "sql": f"-- Compilation Error: Workflow contains cycles or invalid connections: {str(e)}",
                "dialect": self.dialect.name,
                "error": str(e),
                "warnings": [str(e)],
                "ctes_generated": 0
            }

        node_map = {n["id"]: n for n in active_nodes}

        # 3. Analyze output port consumption (which ports are actually wired to downstream nodes)
        consumed_ports: Set[Tuple[str, str]] = set()  # (source_node_id, source_port)
        incoming_by_target: Dict[str, List[Dict[str, Any]]] = {}

        for conn in active_connections:
            src = conn.get("source") or conn.get("from_node")
            src_port = conn.get("sourceHandle") or conn.get("from_port") or "O"
            tgt = conn.get("target") or conn.get("to_node")
            tgt_port = conn.get("targetHandle") or conn.get("to_port") or "I"

            if src and tgt:
                consumed_ports.add((src, src_port))
                if tgt not in incoming_by_target:
                    incoming_by_target[tgt] = []
                incoming_by_target[tgt].append({
                    "source": src,
                    "source_port": src_port,
                    "target_port": tgt_port
                })

        # 4. Generate unique CTE names for each active (node_id, port)
        # Multi-output nodes: Filter (T, F), Join (J, L, R), Unique (U, D)
        multi_output_types = {"filter", "join", "unique"}
        cte_name_map: Dict[Tuple[str, str], str] = {}
        used_cte_names: Set[str] = set()

        for nid in execution_order:
            node_data = node_map[nid]
            ntype = str(node_data.get("type", "")).lower()
            nname = node_data.get("name") or ntype
            base_slug = f"cte_{_slugify(nname)}"

            is_multi = ntype in multi_output_types
            # Pre-register expected output ports
            expected_ports = ["O"]
            if ntype == "filter":
                expected_ports = ["T", "F"]
            elif ntype == "join":
                expected_ports = ["J", "L", "R"]
            elif ntype == "unique":
                expected_ports = ["U", "D"]

            for port in expected_ports:
                if is_multi:
                    cand = f"{base_slug}_{port.lower()}"
                else:
                    cand = base_slug

                # Ensure uniqueness
                final_name = cand
                counter = 2
                while final_name in used_cte_names:
                    final_name = f"{cand}_{counter}"
                    counter += 1

                used_cte_names.add(final_name)
                cte_name_map[(nid, port)] = final_name

        # 5. Compile each node in topological order
        compiled_ctes: List[Dict[str, Any]] = []
        table_mappings = self.options.get("table_mappings", {})
        context = {
            "table_mappings": table_mappings,
            "dialect": self.dialect,
        }

        for nid in execution_order:
            node_data = node_map[nid]
            ntype = str(node_data.get("type", "")).lower()
            nname = node_data.get("name") or ntype

            # Skip OutputDataNode in CTE chain if it simply exports
            if ntype == "output_data":
                continue

            # Gather incoming inputs
            edges = incoming_by_target.get(nid, [])
            input_sources: Dict[str, Any] = {}

            for edge in edges:
                src_id = edge["source"]
                src_port = edge["source_port"]
                tgt_port = edge["target_port"]
                src_cte = cte_name_map.get((src_id, src_port))

                if not src_cte:
                    # Fallback to single port CTE
                    src_cte = cte_name_map.get((src_id, "O"), f"cte_{_slugify(src_id)}")

                if ntype == "union":
                    if tgt_port not in input_sources:
                        input_sources[tgt_port] = []
                    input_sources[tgt_port].append(src_cte)
                else:
                    input_sources[tgt_port] = src_cte

            transpiler = get_node_transpiler(ntype)
            try:
                port_queries = transpiler(node_data, input_sources, self.dialect, context)
            except Exception as ex:
                self.warnings.append(f"Tool '{nname}' ({nid}): {str(ex)}")
                # Emit placeholder CTE on error
                port_queries = {"O": f"SELECT 1 AS placeholder /* Error in {nname}: {str(ex)} */"}

            # For each port query emitted, add as CTE if needed
            for port, query_body in port_queries.items():
                cte_name = cte_name_map.get((nid, port))
                if not cte_name:
                    cte_name = f"cte_{_slugify(nname)}_{port.lower()}"

                # Only prune multi-output ports if they are unconsumed AND not the only branch
                # Keep single output ports and terminal nodes always
                is_consumed = (nid, port) in consumed_ports
                is_terminal = (dag.get_output_edges(nid) == [])
                if ntype in multi_output_types and not is_consumed and not is_terminal:
                    # Port is unused in downstream graph
                    continue

                compiled_ctes.append({
                    "cte_name": cte_name,
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "port": port,
                    "query": query_body.strip()
                })

        if not compiled_ctes:
            return {
                "success": True,
                "sql": "-- No executable SQL transformations found in workflow.\nSELECT 1 AS empty_pipeline WHERE 1=0;",
                "dialect": self.dialect.name,
                "warnings": ["No executable CTEs generated."],
                "ctes_generated": 0
            }

        # 6. Determine final terminal query
        terminal_node_id = self.options.get("terminal_node_id")
        final_cte_name = compiled_ctes[-1]["cte_name"]

        if terminal_node_id:
            # Find matching CTE for the requested terminal node
            matching = [c for c in compiled_ctes if c["node_id"] == terminal_node_id]
            if matching:
                final_cte_name = matching[-1]["cte_name"]

        # 7. Assemble Complete Script
        include_comments = self.options.get("include_comments", True)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        wf_name = self.workflow.get("name") or "Antigravity Visual Workflow"

        header_lines = [
            f"-- ============================================================",
            f"-- Visual Workflow SQL Pushdown Script",
            f"-- Generated by: Antigravity DataFlow",
            f"-- Workflow: {wf_name}",
            f"-- Dialect: {self.dialect.display_name}",
            f"-- Timestamp: {now_str}",
            f"-- ============================================================",
            ""
        ]

        cte_blocks = []
        for idx, cte in enumerate(compiled_ctes):
            name = cte["cte_name"]
            nname = cte["node_name"]
            ntype = cte["node_type"]
            port = cte["port"]
            query = cte["query"]

            # Indent query body by 2 spaces
            indented = "\n".join(f"  {line}" if line.strip() else "" for line in query.split("\n"))

            comment_str = ""
            if include_comments:
                comment_str = f"  -- [{nname}] ({ntype})"
                if port != "O":
                    comment_str += f" - Port {port}"
                comment_str += "\n"

            cte_blocks.append(f"{comment_str}  {name} AS (\n{indented}\n  )")

        joined_ctes = ",\n\n".join(cte_blocks)
        full_sql = (
            "\n".join(header_lines) +
            f"WITH\n{joined_ctes}\n\n"
            f"SELECT * FROM {final_cte_name};"
        )

        return {
            "success": True,
            "sql": full_sql,
            "dialect": self.dialect.name,
            "terminal_cte": final_cte_name,
            "ctes_generated": len(compiled_ctes),
            "warnings": self.warnings
        }


def compile_workflow_to_sql(
    workflow: Dict[str, Any],
    dialect: Optional[Union[SQLDialect, str]] = None,
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Convenience functional wrapper for SQLCompiler."""
    compiler = SQLCompiler(workflow, dialect=dialect, options=options)
    return compiler.compile()
