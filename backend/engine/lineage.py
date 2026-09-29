"""
Column-Level Data Lineage & Impact Analysis Engine for Antigravity DataFlow.
Traces upstream origins of columns and computes downstream impact across the workflow DAG.
"""
import re
from typing import Dict, List, Any, Tuple, Optional, Set

ColumnRef = Tuple[str, str]  # (node_id, column_name)


def compute_lineage(workflow: Dict[str, Any]) -> Dict[str, Dict[str, List[ColumnRef]]]:
    """
    Computes column-level lineage for all nodes in the workflow DAG.
    Returns:
        Dict[node_id, Dict[column_name, List[Tuple[source_node_id, source_column_name]]]]
    """
    rich = compute_rich_lineage(workflow)
    result: Dict[str, Dict[str, List[ColumnRef]]] = {}
    for nid, cols_dict in rich.items():
        result[nid] = {}
        for cname, cinfo in cols_dict.items():
            result[nid][cname] = cinfo.get("sources", [])
    return result


def compute_rich_lineage(workflow: Dict[str, Any], target_node_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Computes rich column lineage including categories, hops, and ancestor node IDs.
    Returns:
        Dict[node_id, Dict[column_name, {
            "sources": List[Tuple[src_node_id, src_col_name]],
            "category": str ("calculated" | "renamed" | "joined" | "passthrough" | "origin"),
            "hops": List[Dict[str, Any]],
            "ancestor_node_ids": List[str]
        }]]
    """
    nodes = {n["id"]: n for n in workflow.get("nodes", [])}
    connections = workflow.get("connections", [])

    preds: Dict[str, List[Dict[str, str]]] = {}
    for conn in connections:
        tgt = conn.get("target") or conn.get("to_node")
        src = conn.get("source") or conn.get("from_node")
        if tgt and src:
            preds.setdefault(tgt, []).append({
                "source": src,
                "source_port": conn.get("sourceHandle") or conn.get("source_port") or "O",
                "target_port": conn.get("targetHandle") or conn.get("target_port") or "I"
            })

    from backend.engine.dag import DAG
    dag = DAG(workflow.get("nodes", []), workflow.get("connections", []))
    try:
        topo_order = dag.topological_sort()
    except Exception:
        topo_order = list(nodes.keys())

    rich_lineage: Dict[str, Dict[str, Any]] = {}

    for nid in topo_order:
        node = nodes.get(nid)
        if not node:
            continue

        ntype = node.get("type", "")
        nname = node.get("name") or ntype
        cfg = node.get("config", {})
        node_preds = preds.get(nid, [])

        primary_up_id = node_preds[0]["source"] if node_preds else None
        primary_up = rich_lineage.get(primary_up_id, {}) if primary_up_id else {}

        node_result: Dict[str, Any] = {}

        if ntype in ("input_data", "text_input"):
            cols = cfg.get("preview_columns") or cfg.get("columns") or []
            if isinstance(cols, list):
                for c in cols:
                    c_str = str(c)
                    node_result[c_str] = {
                        "sources": [(nid, c_str)],
                        "category": "origin",
                        "hops": [
                            {
                                "node_id": nid,
                                "node_name": nname,
                                "node_type": ntype,
                                "action": "Origin",
                                "column": c_str,
                                "detail": cfg.get("path") or cfg.get("filename") or "Raw Input Data"
                            }
                        ],
                        "ancestor_node_ids": [nid]
                    }

        elif ntype == "select":
            fields = cfg.get("fields") or []
            if fields:
                for f in fields:
                    if not f.get("selected", True):
                        continue
                    orig = f.get("name")
                    renamed = f.get("rename") or orig
                    is_renamed = bool(f.get("rename") and f.get("rename") != orig)

                    up_info = primary_up.get(orig) or primary_up.get(renamed)
                    sources = up_info["sources"] if up_info else ([(primary_up_id, orig)] if primary_up_id else [])
                    prior_hops = list(up_info["hops"]) if up_info else []
                    prior_ancestors = list(up_info["ancestor_node_ids"]) if up_info else ([primary_up_id] if primary_up_id else [])

                    current_hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Renamed" if is_renamed else "Pass-through",
                        "column": renamed,
                        "detail": f"Renamed from '{orig}'" if is_renamed else f"Kept '{orig}'"
                    }

                    node_result[renamed] = {
                        "sources": sources,
                        "category": "renamed" if is_renamed else (up_info.get("category", "passthrough") if up_info else "passthrough"),
                        "hops": prior_hops + [current_hop],
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                    }
            else:
                for c, info in primary_up.items():
                    node_result[c] = {
                        **info,
                        "hops": info["hops"] + [{
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "action": "Pass-through",
                            "column": c,
                            "detail": "All fields selected"
                        }],
                        "ancestor_node_ids": list(dict.fromkeys(info["ancestor_node_ids"] + [nid]))
                    }

        elif ntype == "formula":
            # Inherit pass-through first
            for c, info in primary_up.items():
                node_result[c] = dict(info)

            formulas = cfg.get("formulas") or []
            for f in formulas:
                out_col = f.get("output_field") or f.get("column")
                expr = f.get("expression") or ""
                if not out_col:
                    continue

                refs = re.findall(r'\[([^\]]+)\]', expr)
                sources = []
                prior_hops = []
                prior_ancestors = []

                for r in refs:
                    if r in primary_up:
                        sources.extend(primary_up[r]["sources"])
                        prior_hops.extend(primary_up[r]["hops"])
                        prior_ancestors.extend(primary_up[r]["ancestor_node_ids"])
                    elif primary_up_id:
                        sources.append((primary_up_id, r))
                        prior_ancestors.append(primary_up_id)

                formula_hop = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "action": "Calculated Formula",
                    "column": out_col,
                    "detail": expr or "Formula calculation"
                }

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)),
                    "category": "calculated",
                    "hops": prior_hops + [formula_hop],
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                }

        elif ntype in ("multi_row_formula", "multi_field_formula"):
            for c, info in primary_up.items():
                node_result[c] = dict(info)
            out_col = cfg.get("output_field") or cfg.get("field")
            if out_col:
                expr = cfg.get("expression", "")
                refs = re.findall(r'\[([^\]]+)\]', expr)
                sources = []
                prior_hops = []
                prior_ancestors = []
                for r in refs:
                    if r in primary_up:
                        sources.extend(primary_up[r]["sources"])
                        prior_hops.extend(primary_up[r]["hops"])
                        prior_ancestors.extend(primary_up[r]["ancestor_node_ids"])
                    elif primary_up_id:
                        sources.append((primary_up_id, r))
                        prior_ancestors.append(primary_up_id)

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)),
                    "category": "calculated",
                    "hops": prior_hops + [{
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Multi-Row Calculation",
                        "column": out_col,
                        "detail": expr
                    }],
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                }

        elif ntype == "summarize":
            actions = cfg.get("actions") or []
            for a in actions:
                out_col = a.get("output") or a.get("field")
                src_col = a.get("field")
                action_type = a.get("action", "GroupBy")
                if not out_col:
                    continue

                up_info = primary_up.get(src_col) if src_col else None
                sources = up_info["sources"] if up_info else ([(primary_up_id, src_col)] if (primary_up_id and src_col) else [])
                prior_hops = list(up_info["hops"]) if up_info else []
                prior_ancestors = list(up_info["ancestor_node_ids"]) if up_info else ([primary_up_id] if primary_up_id else [])

                node_result[out_col] = {
                    "sources": sources,
                    "category": "calculated" if action_type.lower() != "groupby" else "passthrough",
                    "hops": prior_hops + [{
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": f"Aggregate ({action_type})",
                        "column": out_col,
                        "detail": f"{action_type} of [{src_col}]"
                    }],
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                }

        elif ntype == "join":
            # Left and Right inputs
            for pred in node_preds:
                up_rich = rich_lineage.get(pred["source"], {})
                is_right = pred.get("target_port") in ("R", "Right")
                for c, info in up_rich.items():
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Right Input Join" if is_right else "Left Input Join",
                        "column": c,
                        "detail": f"Joined from {pred['source']}"
                    }
                    if c not in node_result:
                        node_result[c] = {
                            "sources": list(info["sources"]),
                            "category": "joined" if is_right else info.get("category", "passthrough"),
                            "hops": info["hops"] + [hop],
                            "ancestor_node_ids": list(dict.fromkeys(info["ancestor_node_ids"] + [nid]))
                        }
                    else:
                        node_result[c]["sources"].extend([s for s in info["sources"] if s not in node_result[c]["sources"]])
                        node_result[c]["ancestor_node_ids"] = list(dict.fromkeys(node_result[c]["ancestor_node_ids"] + info["ancestor_node_ids"] + [nid]))

        else:
            # Default pass-through
            for pred in node_preds:
                up_rich = rich_lineage.get(pred["source"], {})
                for c, info in up_rich.items():
                    if c not in node_result:
                        node_result[c] = {
                            "sources": list(info["sources"]),
                            "category": info.get("category", "passthrough"),
                            "hops": list(info["hops"]),
                            "ancestor_node_ids": list(dict.fromkeys(info["ancestor_node_ids"] + [nid]))
                        }

        rich_lineage[nid] = node_result

    if target_node_id:
        return {target_node_id: rich_lineage.get(target_node_id, {})}
    return rich_lineage


def compute_downstream_impact(
    workflow: Dict[str, Any],
    source_node_id: str,
    column_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes downstream nodes that depend on fields from source_node_id.
    Returns:
        {
            "node_id": source_node_id,
            "impacted_nodes": List[str],  # node IDs for canvas X-Ray highlighting
            "columns": Dict[col_name, List[Dict[str, Any]]] # usage details per column
        }
    """
    nodes = {n["id"]: n for n in workflow.get("nodes", [])}
    connections = workflow.get("connections", [])

    # Successor adjacency map
    succs: Dict[str, List[Dict[str, str]]] = {}
    for conn in connections:
        src = conn.get("source") or conn.get("from_node")
        tgt = conn.get("target") or conn.get("to_node")
        if src and tgt:
            succs.setdefault(src, []).append({
                "target": tgt,
                "source_port": conn.get("sourceHandle") or "O",
                "target_port": conn.get("targetHandle") or "I"
            })

    from backend.engine.dag import DAG
    dag = DAG(workflow.get("nodes", []), workflow.get("connections", []))
    try:
        topo_order = dag.topological_sort()
    except Exception:
        topo_order = list(nodes.keys())

    # Find all downstream reachable nodes from source_node_id
    downstream_nodes: Set[str] = set()
    queue = [source_node_id]
    visited = {source_node_id}
    while queue:
        curr = queue.pop(0)
        for edge in succs.get(curr, []):
            nxt = edge["target"]
            if nxt not in visited:
                visited.add(nxt)
                downstream_nodes.add(nxt)
                queue.append(nxt)

    # Inspect each downstream node for column usage
    rich_upstream = compute_rich_lineage(workflow)
    source_columns = list(rich_upstream.get(source_node_id, {}).keys())

    if column_name:
        source_columns = [c for c in source_columns if c.lower() == column_name.lower()]

    columns_impact: Dict[str, List[Dict[str, Any]]] = {}
    impacted_node_set: Set[str] = set()

    for col in source_columns:
        usages = []
        for nid in topo_order:
            if nid not in downstream_nodes:
                continue

            node = nodes.get(nid)
            if not node:
                continue

            ntype = node.get("type", "")
            nname = node.get("name") or ntype
            cfg = node.get("config", {})

            matched_usage = None
            col_pattern = rf'\[{re.escape(col)}\]'

            if ntype == "filter":
                expr = cfg.get("expression") or ""
                if re.search(col_pattern, expr, re.IGNORECASE) or cfg.get("field") == col:
                    matched_usage = {
                        "usage": "Filter condition",
                        "detail": expr or f"Filtered on [{col}]"
                    }

            elif ntype in ("formula", "multi_row_formula"):
                formulas = cfg.get("formulas") or []
                for f in formulas:
                    expr = f.get("expression") or ""
                    if re.search(col_pattern, expr, re.IGNORECASE):
                        matched_usage = {
                            "usage": "Formula calculation",
                            "detail": f"{f.get('output_field')} = {expr}"
                        }
                        break

            elif ntype == "select":
                fields = cfg.get("fields") or []
                for f in fields:
                    if f.get("name") == col:
                        if not f.get("selected", True):
                            matched_usage = {"usage": "Dropped in Select", "detail": f"Field '{col}' deselected"}
                        elif f.get("rename"):
                            matched_usage = {"usage": "Renamed in Select", "detail": f"Renamed to '{f.get('rename')}'"}
                        else:
                            matched_usage = {"usage": "Selected field", "detail": f"Kept in schema"}
                        break

            elif ntype == "summarize":
                actions = cfg.get("actions") or []
                for a in actions:
                    if a.get("field") == col:
                        matched_usage = {
                            "usage": f"Aggregation ({a.get('action', 'GroupBy')})",
                            "detail": f"{a.get('action')} -> {a.get('output')}"
                        }
                        break

            elif ntype == "join":
                l_fields = cfg.get("left_fields") or []
                r_fields = cfg.get("right_fields") or []
                if col in l_fields or col in r_fields:
                    matched_usage = {
                        "usage": "Join key",
                        "detail": f"Used as join key match"
                    }

            elif ntype in ("sort", "unique", "clean", "sample"):
                sort_fields = [f.get("field") for f in (cfg.get("fields") or [])]
                if col in sort_fields or cfg.get("field") == col:
                    matched_usage = {
                        "usage": f"{ntype.title()} operation",
                        "detail": f"Used in tool configuration"
                    }

            elif ntype in ("output_data", "output"):
                matched_usage = {
                    "usage": "Exported to destination",
                    "detail": cfg.get("path") or cfg.get("filename") or "Final output sink"
                }

            if matched_usage:
                impacted_node_set.add(nid)
                usages.append({
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "usage": matched_usage["usage"],
                    "detail": matched_usage["detail"]
                })

        columns_impact[col] = usages

    return {
        "node_id": source_node_id,
        "impacted_node_ids": list(impacted_node_set),
        "columns": columns_impact
    }
