"""
Column-Level Data Lineage & Impact Analysis Engine for Antigravity DataFlow.
Traces upstream origins of columns and computes downstream impact across the workflow DAG.
"""
import os
import re
from typing import Dict, List, Any, Tuple, Optional, Set

ColumnRef = Tuple[str, str]  # (node_id, column_name)


def _merge_root_origins(*origins_lists: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merges root origin entries by node_id, aggregating their column lists."""
    merged: Dict[str, Dict[str, Any]] = {}
    for o_list in origins_lists:
        if not o_list:
            continue
        for item in o_list:
            if not isinstance(item, dict):
                continue
            nid = item.get("node_id")
            if not nid:
                continue
            cols = list(item.get("columns") or [])
            if not cols and item.get("column"):
                cols = [item.get("column")]

            if nid not in merged:
                merged[nid] = {
                    "node_id": nid,
                    "node_name": item.get("node_name") or nid,
                    "node_type": item.get("node_type") or "input_data",
                    "source_file": item.get("source_file") or (item.get("detail") if item.get("detail") != "Raw Input Data" else ""),
                    "columns": list(cols)
                }
            else:
                for c in cols:
                    if c not in merged[nid]["columns"]:
                        merged[nid]["columns"].append(c)
                if not merged[nid]["source_file"] and (item.get("source_file") or item.get("detail")):
                    merged[nid]["source_file"] = item.get("source_file") or item.get("detail")
    return list(merged.values())


def _clean_and_order_hops(
    prior_hops: List[Dict[str, Any]],
    current_hop: Optional[Dict[str, Any]],
    topo_order: List[str]
) -> List[Dict[str, Any]]:
    """
    Cleans, deduplicates, and orders hops into a strictly chronological, non-interleaved pipeline:
    1. Consolidates origin hops per unique source node with explicit column references.
    2. Groups and places origin hops strictly at the start (ordered by DAG topology).
    3. Orders intermediate transformation hops in DAG topological execution order (preserving
       intra-node sequence for chained formulas).
    4. Appends the current node's hop at the end.
    """
    topo_pos = {nid: idx for idx, nid in enumerate(topo_order)}
    origin_hops_by_node: Dict[str, Dict[str, Any]] = {}
    non_origin_hops: List[Dict[str, Any]] = []

    for h in prior_hops:
        if not isinstance(h, dict):
            continue
        nid = h.get("node_id", "")
        is_origin = (h.get("action") == "Origin") or (h.get("node_type") in ("input_data", "text_input"))
        if is_origin:
            cols = list(h.get("columns") or [])
            if not cols and h.get("column"):
                cols = [h.get("column")]
            if nid not in origin_hops_by_node:
                origin_hops_by_node[nid] = {
                    "node_id": nid,
                    "node_name": h.get("node_name", nid),
                    "node_type": h.get("node_type", "input_data"),
                    "action": "Origin",
                    "columns": list(cols),
                    "source_file": h.get("source_file") or (h.get("detail") if h.get("detail") != "Raw Input Data" else "")
                }
            else:
                for c in cols:
                    if c not in origin_hops_by_node[nid]["columns"]:
                        origin_hops_by_node[nid]["columns"].append(c)
                if not origin_hops_by_node[nid]["source_file"] and h.get("source_file"):
                    origin_hops_by_node[nid]["source_file"] = h.get("source_file")
        else:
            dup = False
            for existing in non_origin_hops:
                if (existing.get("node_id") == nid and
                    existing.get("column") == h.get("column") and
                    existing.get("action") == h.get("action") and
                    existing.get("detail") == h.get("detail")):
                    dup = True
                    break
            if not dup:
                non_origin_hops.append(dict(h))

    clean_origins: List[Dict[str, Any]] = []
    for nid, orig_info in origin_hops_by_node.items():
        cols = orig_info["columns"]
        src_file = orig_info.get("source_file") or ""
        base_file = os.path.basename(src_file) if src_file else ""

        if len(cols) == 1:
            col_str = cols[0]
            detail_str = f"Source column: [{col_str}]"
        else:
            col_str = ", ".join(cols)
            detail_str = f"Source columns: {', '.join(f'[{c}]' for c in cols)}"
        if base_file:
            detail_str += f" ({base_file})"

        clean_origins.append({
            "node_id": nid,
            "node_name": orig_info["node_name"],
            "node_type": orig_info["node_type"],
            "action": "Origin",
            "column": col_str,
            "columns": cols,
            "detail": detail_str,
            "source_file": src_file
        })

    clean_origins.sort(key=lambda o: topo_pos.get(o["node_id"], 999999))
    non_origin_hops.sort(key=lambda h: topo_pos.get(h.get("node_id", ""), 999999))

    result = clean_origins + non_origin_hops
    if current_hop:
        if not result or (result[-1].get("node_id") != current_hop.get("node_id") or result[-1].get("column") != current_hop.get("column") or result[-1].get("action") != current_hop.get("action")):
            result.append(dict(current_hop))
    return result


def _ensure_column_rich_lineage(col_info: Dict[str, Any], col_name: str, node_id: str, node_name: str, node_type: str) -> None:
    """Guarantees that root_origins and derivation_tree exist for any column."""
    if "root_origins" not in col_info or not col_info["root_origins"]:
        origins = []
        hops = col_info.get("hops", [])
        for h in hops:
            if h.get("action") == "Origin" or h.get("node_type") in ("input_data", "text_input"):
                origins.append({
                    "node_id": h.get("node_id"),
                    "node_name": h.get("node_name"),
                    "node_type": h.get("node_type", "input_data"),
                    "columns": h.get("columns") or ([h.get("column")] if h.get("column") else [col_name]),
                    "source_file": h.get("source_file") or h.get("detail", "")
                })
        if origins:
            col_info["root_origins"] = _merge_root_origins(origins)
        elif col_info.get("sources"):
            inferred = []
            for src_nid, src_col in col_info["sources"]:
                inferred.append({
                    "node_id": src_nid,
                    "node_name": src_nid,
                    "node_type": "input_data",
                    "columns": [src_col],
                    "source_file": ""
                })
            col_info["root_origins"] = _merge_root_origins(inferred)
        else:
            col_info["root_origins"] = [{
                "node_id": node_id,
                "node_name": node_name,
                "node_type": node_type,
                "columns": [col_name],
                "source_file": ""
            }]

    if "derivation_tree" not in col_info or not col_info["derivation_tree"]:
        hops = col_info.get("hops", [])
        if hops:
            last_hop = hops[-1]
            tree = {
                "node_id": last_hop.get("node_id", node_id),
                "node_name": last_hop.get("node_name", node_name),
                "node_type": last_hop.get("node_type", node_type),
                "column": col_name,
                "action": last_hop.get("action", "Output"),
                "detail": last_hop.get("detail", ""),
                "inputs": []
            }
            curr = tree
            for h in reversed(hops[:-1]):
                parent = {
                    "node_id": h.get("node_id"),
                    "node_name": h.get("node_name"),
                    "node_type": h.get("node_type"),
                    "column": h.get("column", col_name),
                    "action": h.get("action", ""),
                    "detail": h.get("detail", ""),
                    "inputs": []
                }
                curr["inputs"].append(parent)
                curr = parent
            col_info["derivation_tree"] = tree


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
            if not cols and cfg.get("data") and isinstance(cfg["data"], list) and len(cfg["data"]) > 0 and isinstance(cfg["data"][0], dict):
                cols = list(cfg["data"][0].keys())
            if isinstance(cols, list):
                src_path = cfg.get("path") or cfg.get("filename") or ""
                base_file = os.path.basename(src_path) if src_path else ""
                for c in cols:
                    c_str = str(c)
                    detail = f"Source column: [{c_str}]"
                    if base_file:
                        detail += f" ({base_file})"
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
                                "columns": [c_str],
                                "detail": detail,
                                "source_file": src_path or base_file or "Raw Input Data"
                            }
                        ],
                        "ancestor_node_ids": [nid],
                        "root_origins": [
                            {
                                "node_id": nid,
                                "node_name": nname,
                                "node_type": ntype,
                                "columns": [c_str],
                                "source_file": src_path or base_file or "Raw Input Data"
                            }
                        ],
                        "derivation_tree": {
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "column": c_str,
                            "action": "Origin",
                            "detail": detail,
                            "inputs": []
                        }
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
                    root_origins = list(up_info.get("root_origins", [])) if up_info else []
                    up_tree = up_info.get("derivation_tree") if up_info else None

                    current_hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Renamed" if is_renamed else "Pass-through",
                        "column": renamed,
                        "detail": f"Renamed from '{orig}'" if is_renamed else f"Kept '{orig}'"
                    }

                    clean_hops = _clean_and_order_hops(prior_hops, current_hop, topo_order)

                    if is_renamed:
                        derivation_tree = {
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "column": renamed,
                            "action": "Renamed",
                            "detail": f"Renamed from '{orig}' to '{renamed}'",
                            "inputs": [up_tree] if up_tree else []
                        }
                    else:
                        derivation_tree = up_tree or {
                            "node_id": nid,
                            "node_name": nname,
                            "node_type": ntype,
                            "column": renamed,
                            "action": "Pass-through",
                            "detail": f"Kept '{orig}'",
                            "inputs": []
                        }

                    node_result[renamed] = {
                        "sources": sources,
                        "category": "renamed" if is_renamed else (up_info.get("category", "passthrough") if up_info else "passthrough"),
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                        "root_origins": root_origins,
                        "derivation_tree": derivation_tree
                    }
            else:
                for c, info in primary_up.items():
                    current_hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Pass-through",
                        "column": c,
                        "detail": "All fields selected"
                    }
                    clean_hops = _clean_and_order_hops(info.get("hops", []), current_hop, topo_order)
                    node_result[c] = {
                        "sources": list(info.get("sources", [])),
                        "category": info.get("category", "passthrough"),
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                        "root_origins": list(info.get("root_origins", [])),
                        "derivation_tree": info.get("derivation_tree")
                    }

        elif ntype == "formula":
            # Inherit pass-through first
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
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
                input_origins = []
                input_trees = []

                for r in refs:
                    up_c = node_result.get(r) or primary_up.get(r)
                    if up_c:
                        sources.extend(up_c.get("sources", []))
                        prior_hops.extend(up_c.get("hops", []))
                        prior_ancestors.extend(up_c.get("ancestor_node_ids", []))
                        input_origins.extend(up_c.get("root_origins", []))
                        if up_c.get("derivation_tree"):
                            input_trees.append(up_c.get("derivation_tree"))
                    elif primary_up_id:
                        sources.append((primary_up_id, r))
                        prior_ancestors.append(primary_up_id)
                        input_trees.append({
                            "node_id": primary_up_id,
                            "node_name": primary_up_id,
                            "node_type": "unknown",
                            "column": r,
                            "action": "Upstream Column",
                            "detail": f"Column [{r}]",
                            "inputs": []
                        })

                if not prior_hops and out_col in node_result:
                    prior_hops = list(node_result[out_col].get("hops", []))
                    prior_ancestors = list(node_result[out_col].get("ancestor_node_ids", []))
                    input_origins = list(node_result[out_col].get("root_origins", []))
                    if not sources:
                        sources = list(node_result[out_col].get("sources", []))

                formula_hop = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "action": "Calculated Formula",
                    "column": out_col,
                    "detail": expr or "Formula calculation",
                    "inputs": refs
                }

                clean_hops = _clean_and_order_hops(prior_hops, formula_hop, topo_order)
                merged_roots = _merge_root_origins(input_origins)
                if not merged_roots and not sources:
                    merged_roots = [{"node_id": nid, "node_name": nname, "node_type": ntype, "columns": [out_col], "detail": "Formula Literal"}]

                derivation_tree = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "column": out_col,
                    "action": "Calculated Formula",
                    "detail": expr or "Formula calculation",
                    "inputs": input_trees
                }

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)) if sources else ([(primary_up_id, out_col)] if primary_up_id else [(nid, out_col)]),
                    "category": "calculated",
                    "hops": clean_hops,
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                    "root_origins": merged_roots,
                    "derivation_tree": derivation_tree
                }

        elif ntype == "multi_row_formula":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }
            out_col = str(cfg.get("output_field") or cfg.get("field") or "New_Field").strip()
            expr = str(cfg.get("expression") or "").strip()
            if out_col:
                raw_refs = re.findall(r'\[([^\]]+)\]', expr)
                sources = []
                prior_hops = []
                prior_ancestors = []
                input_origins = []
                input_trees = []
                clean_refs = []
                for r in raw_refs:
                    clean_r = re.sub(r'^(?:Row\s*[+-]?\s*\d+\s*:\s*)', '', r, flags=re.IGNORECASE).strip()
                    if clean_r.lower() == out_col.lower():
                        continue
                    if clean_r not in clean_refs:
                        clean_refs.append(clean_r)
                    up_c = node_result.get(clean_r) or primary_up.get(clean_r)
                    if up_c:
                        sources.extend(up_c.get("sources", []))
                        prior_hops.extend(up_c.get("hops", []))
                        prior_ancestors.extend(up_c.get("ancestor_node_ids", []))
                        input_origins.extend(up_c.get("root_origins", []))
                        if up_c.get("derivation_tree"):
                            input_trees.append(up_c.get("derivation_tree"))
                    elif primary_up_id:
                        sources.append((primary_up_id, clean_r))
                        prior_ancestors.append(primary_up_id)

                if not prior_hops and out_col in node_result:
                    prior_hops = list(node_result[out_col].get("hops", []))
                    prior_ancestors = list(node_result[out_col].get("ancestor_node_ids", []))
                    input_origins = list(node_result[out_col].get("root_origins", []))
                    if not sources:
                        sources = list(node_result[out_col].get("sources", []))

                hop = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "action": "Multi-Row Calculation",
                    "column": out_col,
                    "detail": expr or "Multi-Row Formula",
                    "inputs": clean_refs
                }

                clean_hops = _clean_and_order_hops(prior_hops, hop, topo_order)
                merged_roots = _merge_root_origins(input_origins)
                if not merged_roots:
                    merged_roots = [{"node_id": nid, "node_name": nname, "node_type": ntype, "columns": [out_col], "detail": "Multi-Row Calculation"}]

                derivation_tree = {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "column": out_col,
                    "action": "Multi-Row Calculation",
                    "detail": expr or "Multi-Row Formula",
                    "inputs": input_trees
                }

                node_result[out_col] = {
                    "sources": list(dict.fromkeys(sources)) if sources else ([(primary_up_id, out_col)] if primary_up_id else [(nid, out_col)]),
                    "category": "calculated",
                    "hops": clean_hops,
                    "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                    "root_origins": merged_roots,
                    "derivation_tree": derivation_tree
                }

        elif ntype == "multi_field_formula":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
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
                root_origins = list(up_info.get("root_origins", []))
                up_tree = up_info.get("derivation_tree")

                if output_mode == "create_new":
                    out_col = f"{output_prefix}{f}{output_suffix}"
                    detail = f"Derived from [{f}]: {expr}" if expr else f"Derived from [{f}]"
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Multi-Field Calculation",
                        "column": out_col,
                        "detail": detail,
                        "inputs": [f]
                    }
                    clean_hops = _clean_and_order_hops(prior_hops, hop, topo_order)
                    tree = {
                        "node_id": nid, "node_name": nname, "node_type": ntype, "column": out_col,
                        "action": "Multi-Field Calculation", "detail": detail,
                        "inputs": [up_tree] if up_tree else []
                    }
                    node_result[out_col] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                        "root_origins": root_origins,
                        "derivation_tree": tree
                    }
                else:
                    detail = expr or f"Updated [{f}]"
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Multi-Field Calculation",
                        "column": f,
                        "detail": detail,
                        "inputs": [f]
                    }
                    clean_hops = _clean_and_order_hops(prior_hops, hop, topo_order)
                    tree = {
                        "node_id": nid, "node_name": nname, "node_type": ntype, "column": f,
                        "action": "Multi-Field Calculation", "detail": detail,
                        "inputs": [up_tree] if up_tree else []
                    }
                    node_result[f] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                        "root_origins": root_origins,
                        "derivation_tree": tree
                    }

        elif ntype == "summarize":
            actions = cfg.get("actions") or []
            if not actions:
                for c, info in primary_up.items():
                    node_result[c] = {
                        "sources": list(info.get("sources", [])),
                        "category": info.get("category", "passthrough"),
                        "hops": list(info.get("hops", [])),
                        "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                        "root_origins": list(info.get("root_origins", [])),
                        "derivation_tree": info.get("derivation_tree")
                    }
            else:
                for a in actions:
                    src_col = a.get("field") or ""
                    action_type = a.get("action", "GroupBy")
                    out_col = _get_summarize_out_name(a)
                    if not out_col:
                        continue

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
                    root_origins = list(up_info.get("root_origins", [])) if up_info else []
                    up_tree = up_info.get("derivation_tree") if up_info else None

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

                    sum_hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": action_label,
                        "column": out_col,
                        "detail": detail_label,
                        "inputs": [src_col] if src_col else []
                    }

                    clean_hops = _clean_and_order_hops(prior_hops, sum_hop, topo_order)
                    tree = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "column": out_col,
                        "action": action_label,
                        "detail": detail_label,
                        "inputs": [up_tree] if up_tree else []
                    }

                    node_result[out_col] = {
                        "sources": sources,
                        "category": category,
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                        "root_origins": _merge_root_origins(root_origins),
                        "derivation_tree": tree
                    }

        elif ntype == "record_id":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
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
                "ancestor_node_ids": [nid],
                "root_origins": [{
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "columns": [col_name],
                    "detail": "Generated Record ID"
                }],
                "derivation_tree": {
                    "node_id": nid,
                    "node_name": nname,
                    "node_type": ntype,
                    "column": col_name,
                    "action": "Generated Record ID",
                    "detail": rec_hop["detail"],
                    "inputs": []
                }
            }

        elif ntype == "datetime":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }
            col = cfg.get("field") or cfg.get("column")
            out_col = cfg.get("output_field") or (f"{col}_DateTime" if col else "DateTime_Out")
            mode = cfg.get("mode", "parse")
            up_info = primary_up.get(col, {}) if col else {}
            sources = list(up_info.get("sources", [(primary_up_id, col)] if (primary_up_id and col) else []))
            prior_hops = list(up_info.get("hops", []))
            prior_ancestors = list(up_info.get("ancestor_node_ids", [primary_up_id] if primary_up_id else []))
            root_origins = list(up_info.get("root_origins", []))
            up_tree = up_info.get("derivation_tree")

            hop = {
                "node_id": nid,
                "node_name": nname,
                "node_type": ntype,
                "action": f"Date/Time ({mode.title()})",
                "column": out_col,
                "detail": f"{mode.title()} from [{col}]" if col else "Date conversion",
                "inputs": [col] if col else []
            }
            clean_hops = _clean_and_order_hops(prior_hops, hop, topo_order)
            node_result[out_col] = {
                "sources": sources if sources else [(nid, out_col)],
                "category": "calculated" if out_col != col else "renamed",
                "hops": clean_hops,
                "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                "root_origins": _merge_root_origins(root_origins),
                "derivation_tree": {
                    "node_id": nid, "node_name": nname, "node_type": ntype, "column": out_col,
                    "action": f"Date/Time ({mode.title()})", "detail": hop["detail"],
                    "inputs": [up_tree] if up_tree else []
                }
            }

        elif ntype == "text_to_columns":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }
            col = cfg.get("column")
            num_cols = int(cfg.get("num_columns", 2))
            split_type = cfg.get("split_type", "columns")
            if split_type == "columns" and col:
                up_info = primary_up.get(col, {})
                sources = list(up_info.get("sources", [(primary_up_id, col)] if primary_up_id else []))
                prior_hops = list(up_info.get("hops", []))
                prior_ancestors = list(up_info.get("ancestor_node_ids", [primary_up_id] if primary_up_id else []))
                root_origins = list(up_info.get("root_origins", []))
                up_tree = up_info.get("derivation_tree")
                delims = cfg.get("delimiters", ",")

                for i in range(1, num_cols + 1):
                    new_col = f"{col}_{i}"
                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": "Split Column",
                        "column": new_col,
                        "detail": f"Part {i} of [{col}] delimited by '{delims}'",
                        "inputs": [col]
                    }
                    clean_hops = _clean_and_order_hops(prior_hops, hop, topo_order)
                    node_result[new_col] = {
                        "sources": sources,
                        "category": "calculated",
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(prior_ancestors + [nid])),
                        "root_origins": _merge_root_origins(root_origins),
                        "derivation_tree": {
                            "node_id": nid, "node_name": nname, "node_type": ntype, "column": new_col,
                            "action": "Split Column", "detail": hop["detail"],
                            "inputs": [up_tree] if up_tree else []
                        }
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
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                            "root_origins": list(info.get("root_origins", [])),
                            "derivation_tree": info.get("derivation_tree")
                        }
                    else:
                        for s in info.get("sources", []):
                            if s not in node_result[c]["sources"]:
                                node_result[c]["sources"].append(s)
                        for a in info.get("ancestor_node_ids", []):
                            if a not in node_result[c]["ancestor_node_ids"]:
                                node_result[c]["ancestor_node_ids"].append(a)
                        node_result[c]["root_origins"] = _merge_root_origins(
                            node_result[c].get("root_origins", []),
                            info.get("root_origins", [])
                        )
                        node_result[c]["hops"] = _clean_and_order_hops(
                            node_result[c]["hops"] + info.get("hops", []),
                            hop,
                            topo_order
                        )

        elif ntype == "join":
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
                    up_tree = info.get("derivation_tree")
                    if is_right and c in node_result:
                        right_c = f"Right_{c}"
                        right_hop = {**hop, "column": right_c}
                        node_result[right_c] = {
                            "sources": list(info.get("sources", [])),
                            "category": "joined",
                            "hops": _clean_and_order_hops(info.get("hops", []), right_hop, topo_order),
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                            "root_origins": list(info.get("root_origins", [])),
                            "derivation_tree": {
                                "node_id": nid, "node_name": nname, "node_type": ntype, "column": right_c,
                                "action": "Right Input Join", "detail": f"Joined from {pred['source']}",
                                "inputs": [up_tree] if up_tree else []
                            }
                        }
                    elif c not in node_result:
                        node_result[c] = {
                            "sources": list(info.get("sources", [])),
                            "category": "joined" if is_right else info.get("category", "passthrough"),
                            "hops": _clean_and_order_hops(info.get("hops", []), hop, topo_order),
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                            "root_origins": list(info.get("root_origins", [])),
                            "derivation_tree": {
                                "node_id": nid, "node_name": nname, "node_type": ntype, "column": c,
                                "action": "Right Input Join" if is_right else "Left Input Join",
                                "detail": f"Joined from {pred['source']}",
                                "inputs": [up_tree] if up_tree else []
                            }
                        }
                    else:
                        for s in info.get("sources", []):
                            if s not in node_result[c]["sources"]:
                                node_result[c]["sources"].append(s)
                        for a in info.get("ancestor_node_ids", []):
                            if a not in node_result[c]["ancestor_node_ids"]:
                                node_result[c]["ancestor_node_ids"].append(a)
                        node_result[c]["root_origins"] = _merge_root_origins(
                            node_result[c].get("root_origins", []),
                            info.get("root_origins", [])
                        )

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
                            "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                            "root_origins": list(info.get("root_origins", [])),
                            "derivation_tree": info.get("derivation_tree")
                        }

        rich_lineage[nid] = node_result

    # Final guarantee pass: ensure root_origins and derivation_tree exist on every column
    for n_id, cols_dict in rich_lineage.items():
        node_obj = nodes.get(n_id, {})
        n_type = node_obj.get("type", "")
        n_name = node_obj.get("name") or n_type or n_id
        for col_name, c_info in cols_dict.items():
            _ensure_column_rich_lineage(c_info, col_name, n_id, n_name, n_type)

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
