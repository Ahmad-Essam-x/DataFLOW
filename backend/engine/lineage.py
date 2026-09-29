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


def _get_summarize_out_name(act: Dict[str, Any]) -> str:
    field = act.get("field") or ""
    action_type = act.get("action", "GroupBy")
    custom_out = str(act.get("output_name") or act.get("output") or "").strip()
    act_lower = action_type.lower()
    if act_lower == "groupby":
        return custom_out or field
    if custom_out:
        return custom_out
    if act_lower == "count":
        return f"Count_{field}" if field else "Count"
    elif act_lower in ("mean", "average", "avg"):
        return f"Avg_{field}" if field else "Avg"
    elif act_lower == "countdistinct":
        return f"Distinct_{field}" if field else "Distinct"
    elif act_lower in ("countdistinctnonnull", "count_distinct_non_null"):
        return f"DistinctNonNull_{field}" if field else "DistinctNonNull"
    elif act_lower in ("countnull", "count_null"):
        return f"Nulls_{field}" if field else "Nulls"
    elif act_lower in ("countnonnull", "count_non_null"):
        return f"NonNulls_{field}" if field else "NonNulls"
    elif act_lower in ("countblank", "count_blank"):
        return f"Blank_{field}" if field else "Blank"
    elif act_lower in ("countnonblank", "count_non_blank"):
        return f"NonBlank_{field}" if field else "NonBlank"
    elif act_lower == "product":
        return f"Product_{field}" if field else "Product"
    elif act_lower == "percentile":
        pct_str = str(act.get("percentile", 50)).replace(".0", "")
        return f"Percentile_{pct_str}_{field}" if field else f"Percentile_{pct_str}"
    elif act_lower == "longest":
        return f"Longest_{field}" if field else "Longest"
    elif act_lower == "shortest":
        return f"Shortest_{field}" if field else "Shortest"
    elif act_lower in ("concatdistinct", "concatenate_distinct"):
        return f"ConcatDistinct_{field}" if field else "ConcatDistinct"
    elif act_lower in ("concat", "concatenate"):
        return f"Concat_{field}" if field else "Concat"
    elif act_lower in ("stddev", "std_dev"):
        return f"StdDev_{field}" if field else "StdDev"
    elif act_lower in ("variance", "var"):
        return f"Var_{field}" if field else "Var"
    elif field:
        return f"{action_type}_{field}"
    else:
        return action_type


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
                    sources = list(up_info["sources"]) if up_info else ([(primary_up_id, orig)] if primary_up_id else [])
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
                        "sources": list(info.get("sources", [])),
                        "category": info.get("category", "passthrough"),
                        "hops": info.get("hops", []) + [{
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "action": "Pass-through",
                            "column": c,
                            "detail": "All fields selected"
                        }],
                        "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid]))
                    }

        elif ntype == "formula":
            # Inherit pass-through first
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }

            formulas = cfg.get("formulas") or cfg.get("expressions") or []
            for f in formulas:
                out_col = str(f.get("output_field") or f.get("field") or f.get("column") or "").strip()
                expr = str(f.get("expression") or "").strip()
                if not out_col:
                    continue

                refs = re.findall(r'\[([^\]]+)\]', expr)
                sources = []
                prior_hops = []
                prior_ancestors = []

                for r in refs:
                    # Look up in node_result first (to support chained formulas in the same node), then primary_up
                    up_c = node_result.get(r) or primary_up.get(r)
                    if up_c:
                        sources.extend(up_c.get("sources", []))
                        prior_hops.extend(up_c.get("hops", []))
                        prior_ancestors.extend(up_c.get("ancestor_node_ids", []))
                    elif primary_up_id:
                        sources.append((primary_up_id, r))
                        prior_ancestors.append(primary_up_id)

                # If formula updates an existing column in-place and has no bracketed references, keep previous hops
                if not prior_hops and out_col in node_result:
                    prior_hops = list(node_result[out_col].get("hops", []))
                    prior_ancestors = list(node_result[out_col].get("ancestor_node_ids", []))
                    if not sources:
                        sources = list(node_result[out_col].get("sources", []))

                formula_hop = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "action": "Calculated Formula",
                    "column": out_col,
                    "detail": expr or "Formula calculation"
                }

                # Deduplicate hops preserving order
                deduped_hops = []
                for h in prior_hops:
                    if h not in deduped_hops:
                        deduped_hops.append(h)
                deduped_hops.append(formula_hop)

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)) if sources else ([(primary_up_id, out_col)] if primary_up_id else [(nid, out_col)]),
                    "category": "calculated",
                    "hops": deduped_hops,
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                }

        elif ntype == "multi_row_formula":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }
            out_col = str(cfg.get("output_field") or cfg.get("field") or "New_Field").strip()
            expr = str(cfg.get("expression") or "").strip()
            if out_col:
                raw_refs = re.findall(r'\[([^\]]+)\]', expr)
                sources = []
                prior_hops = []
                prior_ancestors = []
                for r in raw_refs:
                    clean_r = re.sub(r'^(?:Row\s*[+-]?\s*\d+\s*:\s*)', '', r, flags=re.IGNORECASE).strip()
                    if clean_r.lower() == out_col.lower():
                        continue
                    up_c = node_result.get(clean_r) or primary_up.get(clean_r)
                    if up_c:
                        sources.extend(up_c.get("sources", []))
                        prior_hops.extend(up_c.get("hops", []))
                        prior_ancestors.extend(up_c.get("ancestor_node_ids", []))
                    elif primary_up_id:
                        sources.append((primary_up_id, clean_r))
                        prior_ancestors.append(primary_up_id)

                if not prior_hops and out_col in node_result:
                    prior_hops = list(node_result[out_col].get("hops", []))
                    prior_ancestors = list(node_result[out_col].get("ancestor_node_ids", []))
                    if not sources:
                        sources = list(node_result[out_col].get("sources", []))

                hop = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "action": "Multi-Row Calculation",
                    "column": out_col,
                    "detail": expr or "Multi-Row Formula"
                }

                deduped_hops = []
                for h in prior_hops:
                    if h not in deduped_hops:
                        deduped_hops.append(h)
                deduped_hops.append(hop)

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)) if sources else ([(primary_up_id, out_col)] if primary_up_id else [(nid, out_col)]),
                    "category": "calculated",
                    "hops": deduped_hops,
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                }

        elif ntype == "multi_field_formula":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }
            selected_fields = cfg.get("selected_fields") or cfg.get("fields") or []
            output_mode = str(cfg.get("output_mode", "update")).lower()
            output_prefix = str(cfg.get("output_prefix", "") or "")
            output_suffix = str(cfg.get("output_suffix", "") or "")
            expr = str(cfg.get("expression") or "").strip()

            target_fields = [f for f in selected_fields if f in primary_up] if selected_fields else list(primary_up.keys())

            for f in target_fields:
                up_info = primary_up.get(f, {})
                sources = list(up_info.get("sources", [(primary_up_id, f)] if primary_up_id else []))
                prior_hops = list(up_info.get("hops", []))
                prior_ancestors = list(up_info.get("ancestor_node_ids", [primary_up_id] if primary_up_id else []))

                if output_mode == "create_new":
                    out_col = f"{output_prefix}{f}{output_suffix}"
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Multi-Field Calculation",
                        "column": out_col,
                        "detail": f"Derived from [{f}]: {expr}" if expr else f"Derived from [{f}]"
                    }
                    node_result[out_col] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": prior_hops + [hop],
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                    }
                else:
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Multi-Field Calculation",
                        "column": f,
                        "detail": expr or f"Updated [{f}]"
                    }
                    node_result[f] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": prior_hops + [hop],
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                    }

        elif ntype == "summarize":
            actions = cfg.get("actions") or []
            if not actions:
                # No actions configured: pass through incoming schema
                for c, info in primary_up.items():
                    node_result[c] = {
                        "sources": list(info.get("sources", [])),
                        "category": info.get("category", "passthrough"),
                        "hops": list(info.get("hops", [])),
                        "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                    }
            else:
                for a in actions:
                    src_col = a.get("field") or ""
                    action_type = a.get("action", "GroupBy")
                    out_col = _get_summarize_out_name(a)
                    if not out_col:
                        continue

                    # Handle name collision by appending _2, _3
                    safe_col = out_col
                    counter = 2
                    while safe_col in node_result:
                        safe_col = f"{out_col}_{counter}"
                        counter += 1
                    out_col = safe_col

                    up_info = primary_up.get(src_col) if src_col else None
                    sources = list(up_info["sources"]) if up_info else ([(primary_up_id, src_col)] if (primary_up_id and src_col) else ([(primary_up_id, "*")] if primary_up_id else []))
                    prior_hops = list(up_info["hops"]) if up_info else []
                    prior_ancestors = list(up_info["ancestor_node_ids"]) if up_info else ([primary_up_id] if primary_up_id else [])

                    is_groupby = action_type.lower() == "groupby"
                    is_renamed = bool(is_groupby and src_col and out_col != src_col)

                    if is_groupby:
                        action_label = "Group By"
                        detail_label = f"Grouped by [{src_col}]" + (f" renamed to '{out_col}'" if is_renamed else "")
                        category = "renamed" if is_renamed else "passthrough"
                    else:
                        action_label = f"Aggregate ({action_type})"
                        detail_label = f"{action_type} of [{src_col}]" if src_col else f"{action_type} calculation"
                        category = "calculated"

                    node_result[out_col] = {
                        "sources": sources,
                        "category": category,
                        "hops": prior_hops + [{
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "action": action_label,
                            "column": out_col,
                            "detail": detail_label
                        }],
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                    }

        elif ntype == "record_id":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }
            col_name = str(cfg.get("column_name", "RecordID") or "RecordID").strip()
            rec_hop = {
                "node_id": nid,
                "node_name": nname,
                "node_type": ntype,
                "action": "Generated Record ID",
                "column": col_name,
                "detail": f"Sequential ID starting at {cfg.get('start_value', 1)}"
            }
            node_result[col_name] = {
                "sources": [(nid, col_name)],
                "category": "calculated",
                "hops": [rec_hop],
                "ancestor_node_ids": [nid]
            }

        elif ntype == "datetime":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }
            col = cfg.get("field") or cfg.get("column")
            out_col = cfg.get("output_field") or (f"{col}_DateTime" if col else "DateTime_Out")
            mode = cfg.get("mode", "parse")
            up_info = primary_up.get(col, {}) if col else {}
            sources = list(up_info.get("sources", [(primary_up_id, col)] if (primary_up_id and col) else []))
            prior_hops = list(up_info.get("hops", []))
            prior_ancestors = list(up_info.get("ancestor_node_ids", [primary_up_id] if primary_up_id else []))

            hop = {
                "node_id": nid,
                "node_name": nname,
                "node_type": ntype,
                "action": f"Date/Time ({mode.title()})",
                "column": out_col,
                "detail": f"{mode.title()} from [{col}]" if col else "Date conversion"
            }
            node_result[out_col] = {
                "sources": sources if sources else [(nid, out_col)],
                "category": "calculated" if out_col != col else "renamed",
                "hops": prior_hops + [hop],
                "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
            }

        elif ntype == "text_to_columns":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", []))
                }
            col = cfg.get("column")
            num_cols = int(cfg.get("num_columns", 2))
            split_type = cfg.get("split_type", "columns")
            if split_type == "columns" and col:
                up_info = primary_up.get(col, {})
                sources = list(up_info.get("sources", [(primary_up_id, col)] if primary_up_id else []))
                prior_hops = list(up_info.get("hops", []))
                prior_ancestors = list(up_info.get("ancestor_node_ids", [primary_up_id] if primary_up_id else []))
                delims = cfg.get("delimiters", ",")

                for i in range(1, num_cols + 1):
                    new_col = f"{col}_{i}"
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Split Column",
                        "column": new_col,
                        "detail": f"Part {i} of [{col}] delimited by '{delims}'"
                    }
                    node_result[new_col] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": prior_hops + [hop],
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid]))
                    }

        elif ntype == "union":
            for pred in node_preds:
                up_rich = rich_lineage.get(pred["source"], {})
                for c, info in up_rich.items():
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Union Stream",
                        "column": c,
                        "detail": f"Combined from {pred['source']}"
                    }
                    if c not in node_result:
                        node_result[c] = {
                            "sources": list(info.get("sources", [])),
                            "category": info.get("category", "passthrough"),
                            "hops": list(info.get("hops", [])) + [hop],
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid]))
                        }
                    else:
                        for s in info.get("sources", []):
                            if s not in node_result[c]["sources"]:
                                node_result[c]["sources"].append(s)
                        for a in info.get("ancestor_node_ids", []):
                            if a not in node_result[c]["ancestor_node_ids"]:
                                node_result[c]["ancestor_node_ids"].append(a)

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
                    if is_right and c in node_result:
                        right_c = f"Right_{c}"
                        node_result[right_c] = {
                            "sources": list(info.get("sources", [])),
                            "category": "joined",
                            "hops": list(info.get("hops", [])) + [{**hop, "column": right_c}],
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid]))
                        }
                    elif c not in node_result:
                        node_result[c] = {
                            "sources": list(info.get("sources", [])),
                            "category": "joined" if is_right else info.get("category", "passthrough"),
                            "hops": list(info.get("hops", [])) + [hop],
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid]))
                        }
                    else:
                        for s in info.get("sources", []):
                            if s not in node_result[c]["sources"]:
                                node_result[c]["sources"].append(s)
                        for a in info.get("ancestor_node_ids", []):
                            if a not in node_result[c]["ancestor_node_ids"]:
                                node_result[c]["ancestor_node_ids"].append(a)

        else:
            # Default pass-through
            for pred in node_preds:
                up_rich = rich_lineage.get(pred["source"], {})
                for c, info in up_rich.items():
                    if c not in node_result:
                        node_result[c] = {
                            "sources": list(info.get("sources", [])),
                            "category": info.get("category", "passthrough"),
                            "hops": list(info.get("hops", [])),
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid]))
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
                formulas = cfg.get("formulas") or cfg.get("expressions") or []
                for f in formulas:
                    expr = f.get("expression") or ""
                    if re.search(col_pattern, expr, re.IGNORECASE):
                        out_col = f.get("output_field") or f.get("field") or f.get("column") or "Field"
                        matched_usage = {
                            "usage": "Formula calculation",
                            "detail": f"{out_col} = {expr}"
                        }
                        break
                if not matched_usage and ntype == "multi_row_formula":
                    expr = cfg.get("expression") or ""
                    row_pattern = rf'\[(?:Row\s*[+-]?\s*\d+\s*:\s*)?{re.escape(col)}\]'
                    if re.search(row_pattern, expr, re.IGNORECASE):
                        out_col = cfg.get("output_field") or cfg.get("field") or "New_Field"
                        matched_usage = {
                            "usage": "Multi-Row Calculation",
                            "detail": f"{out_col} = {expr}"
                        }

            elif ntype == "multi_field_formula":
                selected_fields = cfg.get("selected_fields") or cfg.get("fields") or []
                expr = cfg.get("expression") or ""
                if (not selected_fields or col in selected_fields) and (re.search(col_pattern, expr, re.IGNORECASE) or "_CurrentField" in expr):
                    matched_usage = {
                        "usage": "Multi-Field Calculation",
                        "detail": expr or f"Formula applied to [{col}]"
                    }

            elif ntype == "datetime":
                if cfg.get("field") == col or cfg.get("column") == col:
                    out_col = cfg.get("output_field") or f"{col}_DateTime"
                    matched_usage = {
                        "usage": "DateTime Conversion",
                        "detail": f"{cfg.get('mode', 'parse').title()} from [{col}] -> {out_col}"
                    }

            elif ntype == "text_to_columns":
                if cfg.get("column") == col:
                    matched_usage = {
                        "usage": "Text Split",
                        "detail": f"Split [{col}] into {cfg.get('num_columns', 2)} columns"
                    }

            elif ntype == "record_id":
                group_by = cfg.get("group_by", [])
                if isinstance(group_by, str):
                    group_by = [group_by]
                if col in group_by:
                    matched_usage = {
                        "usage": "Record ID Grouping",
                        "detail": f"Group key for RecordID generation"
                    }

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
                        action_type = a.get("action", "GroupBy")
                        out_name = _get_summarize_out_name(a)
                        matched_usage = {
                            "usage": f"Aggregation ({action_type})",
                            "detail": f"{action_type} of [{col}] -> {out_name}"
                        }
                        break

            elif ntype == "join":
                l_fields = cfg.get("left_fields") or []
                r_fields = cfg.get("right_fields") or []
                join_keys = cfg.get("join_keys") or []
                for jk in join_keys:
                    if jk.get("left_key"): l_fields.append(jk.get("left_key"))
                    if jk.get("right_key"): r_fields.append(jk.get("right_key"))
                if col in l_fields or col in r_fields:
                    matched_usage = {
                        "usage": "Join key",
                        "detail": f"Used as join key match"
                    }

            elif ntype in ("sort", "unique", "clean", "sample"):
                sort_fields = [f.get("field") for f in (cfg.get("fields") or [])]
                clean_cols = cfg.get("columns") or []
                group_cols = cfg.get("group_by") or []
                if isinstance(group_cols, str): group_cols = [group_cols]
                if col in sort_fields or col in clean_cols or col in group_cols or cfg.get("field") == col or cfg.get("column") == col:
                    matched_usage = {
                        "usage": f"{ntype.title()} operation",
                        "detail": f"Used in {ntype} configuration"
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
