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
                src_path = cfg.get("file_path") or cfg.get("path") or cfg.get("filename") or ""
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
            fields = cfg.get("fields") or cfg.get("columns") or []
            if fields:
                unknown_item = next(
                    (f for f in fields if (f.get("original") == "*Unknown" or f.get("name") == "*Unknown" or f.get("field") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = True

                configured_origs = set()
                for f in fields:
                    orig = f.get("original") or f.get("name") or f.get("field")
                    if not orig or orig == "*Unknown":
                        continue
                    configured_origs.add(orig)

                    keep = f.get("keep") if "keep" in f else f.get("selected", True)
                    if not keep:
                        continue

                    renamed = (f.get("rename") or orig).strip()
                    if not renamed:
                        renamed = orig
                    is_renamed = bool(renamed != orig)

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

                # Forward dynamic unknown columns if select_unknown is True
                if select_unknown:
                    for orig, up_info in primary_up.items():
                        if orig not in configured_origs and orig not in node_result:
                            current_hop = {
                                "node_id": nid,
                                "node_name": nname,
                                "node_type": ntype,
                                "action": "Pass-through (Dynamic)",
                                "column": orig,
                                "detail": f"Dynamic unknown column kept: '{orig}'"
                            }
                            clean_hops = _clean_and_order_hops(up_info.get("hops", []), current_hop, topo_order)
                            node_result[orig] = {
                                "sources": list(up_info.get("sources", [])),
                                "category": up_info.get("category", "passthrough"),
                                "hops": clean_hops,
                                "ancestor_node_ids": list(dict.fromkeys(up_info.get("ancestor_node_ids", []) + [nid])),
                                "root_origins": list(up_info.get("root_origins", [])),
                                "derivation_tree": up_info.get("derivation_tree")
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
            out_col = str(cfg.get("output_field") or cfg.get("new_field_name") or cfg.get("field_name") or cfg.get("field") or "New_Field").strip()
            is_new = cfg.get("is_new_field", True) if "is_new_field" in cfg else (cfg.get("create_new_field", True) if "create_new_field" in cfg else (cfg.get("new_field", True) if "new_field" in cfg else True))
            expr = str(cfg.get("expression") or "").strip()
            group_by = cfg.get("group_by_fields") or cfg.get("group_by", [])
            if isinstance(group_by, str) and group_by:
                group_by = [group_by]
            elif not isinstance(group_by, list):
                group_by = []

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
                    if clean_r.lower() == out_col.lower() and is_new:
                        continue
                    if clean_r not in clean_refs:
                        clean_refs.append(clean_r)

                for g in group_by:
                    if g not in clean_refs and g != out_col:
                        clean_refs.append(g)

                for clean_r in clean_refs:
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
            output_mode = str(cfg.get("output_mode", "create_new" if cfg.get("output_new_fields") else "update")).lower()
            output_prefix = str(cfg.get("output_prefix") or cfg.get("prefix") or "")
            output_suffix = str(cfg.get("output_suffix") or cfg.get("suffix") or "")
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

        elif ntype in ("datetime", "date_time"):
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }
            col = cfg.get("field") or cfg.get("column") or (list(primary_up.keys())[0] if primary_up else None)
            mode = cfg.get("conversion_type") or cfg.get("mode", "parse")
            default_out = f"{col}_DateTime" if mode != "date_to_string" else f"{col}_String"
            out_col = cfg.get("output_column") or cfg.get("output_field") or (default_out if col else "DateTime_Out")
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
                "action": f"Date/Time ({str(mode).title()})",
                "column": out_col,
                "detail": f"{str(mode).title()} from [{col}]" if col else "Date conversion",
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
                    "action": f"Date/Time ({str(mode).title()})", "detail": hop["detail"],
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
                root_name = str(cfg.get("root_name") or "").strip()

                for i in range(1, num_cols + 1):
                    new_col = f"{root_name}{i}" if root_name else f"{col}_{i}"
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
            base_joined: Dict[str, Any] = {}
            col_sources: Dict[str, str] = {}

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
                    if is_right and c in base_joined:
                        right_c = f"Right_{c}"
                        while right_c in base_joined:
                            right_c = f"Right_{right_c}"
                        right_hop = {**hop, "column": right_c}
                        base_joined[right_c] = {
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
                        col_sources[right_c] = "R"
                    elif c not in base_joined:
                        base_joined[c] = {
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
                        col_sources[c] = "R" if is_right else "L"
                    else:
                        for s in info.get("sources", []):
                            if s not in base_joined[c]["sources"]:
                                base_joined[c]["sources"].append(s)
                        for a in info.get("ancestor_node_ids", []):
                            if a not in base_joined[c]["ancestor_node_ids"]:
                                base_joined[c]["ancestor_node_ids"].append(a)
                        base_joined[c]["root_origins"] = _merge_root_origins(
                            base_joined[c].get("root_origins", []),
                            info.get("root_origins", [])
                        )

            select_fields = cfg.get("select_fields") or cfg.get("fields")
            if select_fields and isinstance(select_fields, list):
                unknown_item = next(
                    (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = False

                configured_cols = set()
                available_cols = list(base_joined.keys())

                for sf in select_fields:
                    orig = sf.get("original") or sf.get("field") or sf.get("name")
                    if not orig or orig == "*Unknown":
                        continue

                    sf_source = sf.get("source")
                    matched_col = None
                    if sf_source == "R":
                        if orig in base_joined and col_sources.get(orig) == "R":
                            matched_col = orig
                        elif f"Right_{orig}" in base_joined:
                            matched_col = f"Right_{orig}"
                    elif sf_source == "L":
                        if orig in base_joined and col_sources.get(orig) == "L":
                            matched_col = orig
                    if not matched_col:
                        if orig in base_joined:
                            matched_col = orig
                        elif f"Right_{orig}" in base_joined:
                            matched_col = f"Right_{orig}"

                    if not matched_col or matched_col not in base_joined:
                        continue

                    configured_cols.add(matched_col)
                    keep = sf.get("keep") if "keep" in sf else sf.get("selected", True)
                    if not keep:
                        continue

                    renamed = (sf.get("rename") or matched_col).strip()
                    if not renamed:
                        renamed = matched_col
                    is_renamed = bool(renamed != matched_col)

                    base_info = base_joined[matched_col]
                    if is_renamed:
                        rename_hop = {
                            "node_id": nid, "node_name": nname, "node_type": ntype,
                            "action": "Renamed in Join", "column": renamed,
                            "detail": f"Renamed from '{matched_col}' to '{renamed}'"
                        }
                        clean_hops = _clean_and_order_hops(base_info.get("hops", []), rename_hop, topo_order)
                        tree = {
                            "node_id": nid, "node_name": nname, "node_type": ntype, "column": renamed,
                            "action": "Renamed in Join", "detail": f"Renamed from '{matched_col}' to '{renamed}'",
                            "inputs": [base_info.get("derivation_tree")] if base_info.get("derivation_tree") else []
                        }
                        node_result[renamed] = {
                            "sources": list(base_info.get("sources", [])),
                            "category": "renamed",
                            "hops": clean_hops,
                            "ancestor_node_ids": list(base_info.get("ancestor_node_ids", [])),
                            "root_origins": list(base_info.get("root_origins", [])),
                            "derivation_tree": tree
                        }
                    else:
                        node_result[matched_col] = base_info

                if select_unknown:
                    for c in available_cols:
                        if c not in configured_cols and c not in node_result:
                            node_result[c] = base_joined[c]
            else:
                node_result = base_joined

        elif ntype == "join_multiple":
            input_ups = [rich_lineage.get(p["source"], {}) for p in node_preds]
            raw_joined: Dict[str, Any] = {}
            col_sources_multi: Dict[str, int] = {}
            occupied = set()

            for in_idx, up_dict in enumerate(input_ups, 1):
                src_nid = node_preds[in_idx - 1]["source"] if in_idx - 1 < len(node_preds) else f"Input_{in_idx}"
                for c, info in up_dict.items():
                    target_name = c
                    if target_name in occupied:
                        cand = f"Input{in_idx}_{c}"
                        while cand in occupied:
                            cand = f"Input{in_idx}_{cand}"
                        target_name = cand
                    occupied.add(target_name)

                    hop = {
                        "node_id": nid,
                        "node_name": nname,
                        "node_type": ntype,
                        "action": f"Multi-Join (Input {in_idx})",
                        "column": target_name,
                        "detail": f"Joined from {src_nid}" + (f" (as '{target_name}')" if target_name != c else "")
                    }
                    raw_joined[target_name] = {
                        "sources": list(info.get("sources", [(src_nid, c)])),
                        "category": "joined" if in_idx > 1 else info.get("category", "passthrough"),
                        "hops": _clean_and_order_hops(info.get("hops", []), hop, topo_order),
                        "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                        "root_origins": list(info.get("root_origins", [])),
                        "derivation_tree": {
                            "node_id": nid, "node_name": nname, "node_type": ntype, "column": target_name,
                            "action": f"Multi-Join (Input {in_idx})", "detail": f"Joined from {src_nid}",
                            "inputs": [info.get("derivation_tree")] if info.get("derivation_tree") else []
                        }
                    }
                    col_sources_multi[target_name] = in_idx

            select_fields = cfg.get("select_fields") or cfg.get("fields")
            if select_fields and isinstance(select_fields, list):
                unknown_item = next(
                    (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = False

                configured_cols = set()
                available_cols = list(raw_joined.keys())

                for sf in select_fields:
                    orig = sf.get("original") or sf.get("field") or sf.get("name")
                    if not orig or orig == "*Unknown":
                        continue
                    sf_src = sf.get("source")
                    matched_col = None
                    if sf_src is not None:
                        cand = f"Input{sf_src}_{orig}"
                        if cand in raw_joined:
                            matched_col = cand
                    if not matched_col:
                        if orig in raw_joined:
                            matched_col = orig

                    if not matched_col or matched_col not in raw_joined:
                        continue

                    configured_cols.add(matched_col)
                    keep = sf.get("keep") if "keep" in sf else sf.get("selected", True)
                    if not keep:
                        continue

                    renamed = (sf.get("rename") or matched_col).strip() or matched_col
                    is_renamed = bool(renamed != matched_col)
                    base_info = raw_joined[matched_col]

                    if is_renamed:
                        rename_hop = {
                            "node_id": nid, "node_name": nname, "node_type": ntype,
                            "action": "Renamed in Join Multiple", "column": renamed,
                            "detail": f"Renamed from '{matched_col}' to '{renamed}'"
                        }
                        node_result[renamed] = {
                            "sources": list(base_info.get("sources", [])),
                            "category": "renamed",
                            "hops": _clean_and_order_hops(base_info.get("hops", []), rename_hop, topo_order),
                            "ancestor_node_ids": list(base_info.get("ancestor_node_ids", [])),
                            "root_origins": list(base_info.get("root_origins", [])),
                            "derivation_tree": {
                                "node_id": nid, "node_name": nname, "node_type": ntype, "column": renamed,
                                "action": "Renamed in Join Multiple", "detail": f"Renamed from '{matched_col}' to '{renamed}'",
                                "inputs": [base_info.get("derivation_tree")] if base_info.get("derivation_tree") else []
                            }
                        }
                    else:
                        node_result[matched_col] = base_info

                if select_unknown:
                    for c in available_cols:
                        if c not in configured_cols and c not in node_result:
                            node_result[c] = raw_joined[c]
            else:
                node_result = raw_joined

        elif ntype == "append_fields":
            t_up = {}
            s_up = {}
            t_id = None
            s_id = None
            for pred in node_preds:
                t_port = pred.get("target_port") or "T"
                if t_port in ("S", "Source"):
                    s_up = rich_lineage.get(pred["source"], {})
                    s_id = pred["source"]
                else:
                    t_up = rich_lineage.get(pred["source"], {})
                    t_id = pred["source"]
            if not s_up and len(node_preds) > 1 and not s_id:
                s_id = node_preds[1]["source"]
                s_up = rich_lineage.get(s_id, {})
            if not t_up and node_preds:
                t_id = node_preds[0]["source"]
                t_up = rich_lineage.get(t_id, {})

            prefix = cfg.get("source_prefix", "Source_")
            raw_appended = {}
            for c, info in t_up.items():
                raw_appended[c] = info
            for c, info in s_up.items():
                out_name = f"{prefix}{c}" if c in raw_appended else c
                hop = {
                    "node_id": nid, "node_name": nname, "node_type": ntype,
                    "action": "Appended Field (Cartesian)", "column": out_name,
                    "detail": f"Appended from {s_id or 'Source'}"
                }
                raw_appended[out_name] = {
                    "sources": list(info.get("sources", [(s_id, c)] if s_id else [])),
                    "category": "joined",
                    "hops": _clean_and_order_hops(info.get("hops", []), hop, topo_order),
                    "ancestor_node_ids": list(dict.fromkeys(info.get("ancestor_node_ids", []) + [nid])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": {
                        "node_id": nid, "node_name": nname, "node_type": ntype, "column": out_name,
                        "action": "Appended Field (Cartesian)", "detail": hop["detail"],
                        "inputs": [info.get("derivation_tree")] if info.get("derivation_tree") else []
                    }
                }

            select_fields = cfg.get("select_fields") or cfg.get("fields")
            if select_fields and isinstance(select_fields, list):
                unknown_item = next(
                    (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = False

                configured_cols = set()
                available_cols = list(raw_appended.keys())
                for sf in select_fields:
                    orig = sf.get("original") or sf.get("field") or sf.get("name")
                    if not orig or orig == "*Unknown":
                        continue
                    matched_col = orig if orig in raw_appended else (f"{prefix}{orig}" if f"{prefix}{orig}" in raw_appended else None)
                    if not matched_col:
                        continue
                    configured_cols.add(matched_col)
                    keep = sf.get("keep") if "keep" in sf else sf.get("selected", True)
                    if not keep:
                        continue
                    renamed = (sf.get("rename") or matched_col).strip() or matched_col
                    is_renamed = bool(renamed != matched_col)
                    base_info = raw_appended[matched_col]
                    if is_renamed:
                        rename_hop = {
                            "node_id": nid, "node_name": nname, "node_type": ntype,
                            "action": "Renamed in Append Fields", "column": renamed,
                            "detail": f"Renamed from '{matched_col}' to '{renamed}'"
                        }
                        node_result[renamed] = {
                            "sources": list(base_info.get("sources", [])),
                            "category": "renamed",
                            "hops": _clean_and_order_hops(base_info.get("hops", []), rename_hop, topo_order),
                            "ancestor_node_ids": list(base_info.get("ancestor_node_ids", [])),
                            "root_origins": list(base_info.get("root_origins", [])),
                            "derivation_tree": {
                                "node_id": nid, "node_name": nname, "node_type": ntype, "column": renamed,
                                "action": "Renamed in Append Fields", "detail": f"Renamed from '{matched_col}' to '{renamed}'",
                                "inputs": [base_info.get("derivation_tree")] if base_info.get("derivation_tree") else []
                            }
                        }
                    else:
                        node_result[matched_col] = base_info

                if select_unknown:
                    for c in available_cols:
                        if c not in configured_cols and c not in node_result:
                            node_result[c] = raw_appended[c]
            else:
                node_result = raw_appended

        elif ntype == "find_replace":
            f_up = {}
            r_up = {}
            f_id = None
            r_id = None
            for pred in node_preds:
                t_port = pred.get("target_port") or "F"
                if t_port in ("R", "Replace"):
                    r_up = rich_lineage.get(pred["source"], {})
                    r_id = pred["source"]
                else:
                    f_up = rich_lineage.get(pred["source"], {})
                    f_id = pred["source"]
            if not r_up and len(node_preds) > 1 and not r_id:
                r_id = node_preds[1]["source"]
                r_up = rich_lineage.get(r_id, {})
            if not f_up and node_preds:
                f_id = node_preds[0]["source"]
                f_up = rich_lineage.get(f_id, {})

            for c, info in f_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }

            action = cfg.get("action", "replace")
            find_field = cfg.get("find_field")
            if action == "replace" and find_field and find_field in node_result:
                rep_field = cfg.get("replace_with_field")
                rep_info = r_up.get(rep_field, {}) if rep_field else {}
                orig_info = node_result[find_field]
                sources = list(orig_info.get("sources", [])) + list(rep_info.get("sources", [(r_id, rep_field)] if (r_id and rep_field) else []))
                hop = {
                    "node_id": nid, "node_name": nname, "node_type": ntype,
                    "action": "Find & Replace", "column": find_field,
                    "detail": f"Replaced values from [{rep_field}] in {r_id}" if rep_field else "Find & Replace"
                }
                clean_hops = _clean_and_order_hops(orig_info.get("hops", []) + rep_info.get("hops", []), hop, topo_order)
                tree = {
                    "node_id": nid, "node_name": nname, "node_type": ntype, "column": find_field,
                    "action": "Find & Replace", "detail": hop["detail"],
                    "inputs": [t for t in [orig_info.get("derivation_tree"), rep_info.get("derivation_tree")] if t]
                }
                node_result[find_field] = {
                    "sources": list(dict.fromkeys(sources)),
                    "category": "calculated",
                    "hops": clean_hops,
                    "ancestor_node_ids": list(dict.fromkeys(orig_info.get("ancestor_node_ids", []) + rep_info.get("ancestor_node_ids", []) + [nid])),
                    "root_origins": _merge_root_origins(orig_info.get("root_origins", []), rep_info.get("root_origins", [])),
                    "derivation_tree": tree
                }
            elif action == "append":
                append_cols = cfg.get("append_fields", [])
                for col in append_cols:
                    rep_info = r_up.get(col, {})
                    target_col = col if col not in node_result else f"{col}_R"
                    hop = {
                        "node_id": nid, "node_name": nname, "node_type": ntype,
                        "action": "Find & Append Field", "column": target_col,
                        "detail": f"Appended from [{col}] in {r_id}"
                    }
                    clean_hops = _clean_and_order_hops(rep_info.get("hops", []), hop, topo_order)
                    tree = {
                        "node_id": nid, "node_name": nname, "node_type": ntype, "column": target_col,
                        "action": "Find & Append Field", "detail": hop["detail"],
                        "inputs": [rep_info.get("derivation_tree")] if rep_info.get("derivation_tree") else []
                    }
                    node_result[target_col] = {
                        "sources": list(rep_info.get("sources", [(r_id, col)] if r_id else [])),
                        "category": "joined",
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys(rep_info.get("ancestor_node_ids", []) + [nid])),
                        "root_origins": list(rep_info.get("root_origins", [])),
                        "derivation_tree": tree
                    }

        elif ntype == "transpose":
            key_fields = cfg.get("key_columns") or cfg.get("key_fields", [])
            data_fields = cfg.get("data_columns") or cfg.get("data_fields", [])
            name_col = cfg.get("name_column", "Name")
            value_col = cfg.get("value_column", "Value")

            for k in key_fields:
                if k in primary_up:
                    node_result[k] = {
                        "sources": list(primary_up[k].get("sources", [])),
                        "category": "passthrough",
                        "hops": list(primary_up[k].get("hops", [])),
                        "ancestor_node_ids": list(primary_up[k].get("ancestor_node_ids", [])),
                        "root_origins": list(primary_up[k].get("root_origins", [])),
                        "derivation_tree": primary_up[k].get("derivation_tree")
                    }

            data_cols = [d for d in data_fields if d in primary_up] if data_fields else [c for c in primary_up if c not in key_fields]
            data_sources = []
            data_origins = []
            data_trees = []
            for d in data_cols:
                info = primary_up.get(d, {})
                data_sources.extend(info.get("sources", [(primary_up_id, d)] if primary_up_id else []))
                data_origins.extend(info.get("root_origins", []))
                if info.get("derivation_tree"):
                    data_trees.append(info.get("derivation_tree"))

            for out_c, act_name, desc in [(name_col, "Transposed Name", "Transposed column name from data fields"),
                                          (value_col, "Transposed Value", "Transposed column values from data fields")]:
                hop = {
                    "node_id": nid, "node_name": nname, "node_type": ntype,
                    "action": act_name, "column": out_c, "detail": desc,
                    "inputs": data_cols
                }
                clean_hops = _clean_and_order_hops([], hop, topo_order)
                tree = {
                    "node_id": nid, "node_name": nname, "node_type": ntype, "column": out_c,
                    "action": act_name, "detail": desc, "inputs": data_trees
                }
                node_result[out_c] = {
                    "sources": list(dict.fromkeys(data_sources)) if data_sources else ([(primary_up_id, "*")] if primary_up_id else [(nid, out_c)]),
                    "category": "calculated",
                    "hops": clean_hops,
                    "ancestor_node_ids": list(dict.fromkeys([primary_up_id, nid] if primary_up_id else [nid])),
                    "root_origins": _merge_root_origins(data_origins),
                    "derivation_tree": tree
                }

        elif ntype == "crosstab":
            group_by = cfg.get("group_by", [])
            if isinstance(group_by, str):
                group_by = [group_by]
            elif not isinstance(group_by, list):
                group_by = []
            header_field = cfg.get("header_field")
            value_field = cfg.get("value_field")

            for g in group_by:
                if g in primary_up:
                    node_result[g] = {
                        "sources": list(primary_up[g].get("sources", [])),
                        "category": "passthrough",
                        "hops": list(primary_up[g].get("hops", [])),
                        "ancestor_node_ids": list(primary_up[g].get("ancestor_node_ids", [])),
                        "root_origins": list(primary_up[g].get("root_origins", [])),
                        "derivation_tree": primary_up[g].get("derivation_tree")
                    }

            pivot_sources = []
            pivot_origins = []
            pivot_trees = []
            for col_ref in [header_field, value_field]:
                if col_ref and col_ref in primary_up:
                    info = primary_up[col_ref]
                    pivot_sources.extend(info.get("sources", []))
                    pivot_origins.extend(info.get("root_origins", []))
                    if info.get("derivation_tree"):
                        pivot_trees.append(info.get("derivation_tree"))

            known_cols = cfg.get("preview_columns") or cfg.get("columns") or []
            for col in known_cols:
                if col not in node_result:
                    hop = {
                        "node_id": nid, "node_name": nname, "node_type": ntype,
                        "action": "CrossTab Pivot", "column": col,
                        "detail": f"Pivoted from header [{header_field}] and value [{value_field}]",
                        "inputs": [c for c in [header_field, value_field] if c]
                    }
                    clean_hops = _clean_and_order_hops([], hop, topo_order)
                    tree = {
                        "node_id": nid, "node_name": nname, "node_type": ntype, "column": col,
                        "action": "CrossTab Pivot", "detail": hop["detail"], "inputs": pivot_trees
                    }
                    node_result[col] = {
                        "sources": list(dict.fromkeys(pivot_sources)) if pivot_sources else ([(primary_up_id, "*")] if primary_up_id else [(nid, col)]),
                        "category": "calculated",
                        "hops": clean_hops,
                        "ancestor_node_ids": list(dict.fromkeys([primary_up_id, nid] if primary_up_id else [nid])),
                        "root_origins": _merge_root_origins(pivot_origins),
                        "derivation_tree": tree
                    }

        elif ntype == "llm_process":
            for c, info in primary_up.items():
                node_result[c] = {
                    "sources": list(info.get("sources", [])),
                    "category": info.get("category", "passthrough"),
                    "hops": list(info.get("hops", [])),
                    "ancestor_node_ids": list(info.get("ancestor_node_ids", [])),
                    "root_origins": list(info.get("root_origins", [])),
                    "derivation_tree": info.get("derivation_tree")
                }

            user_template = str(cfg.get("user_prompt_template") or cfg.get("prompt_template") or cfg.get("prompt") or "")
            ref_cols = []
            if user_template:
                ref_cols.extend(re.findall(r'\{\{\[([^\]]+)\]\}\}', user_template))
                for col_m in re.findall(r'\[([^\]]+)\]', user_template):
                    if col_m in primary_up and col_m not in ref_cols:
                        ref_cols.append(col_m)
            if cfg.get("system_prompt_source") == "column" and cfg.get("system_prompt_column"):
                sys_col = str(cfg.get("system_prompt_column"))
                if sys_col in primary_up and sys_col not in ref_cols:
                    ref_cols.append(sys_col)

            input_sources = []
            input_origins = []
            input_trees = []
            for rc in ref_cols:
                if rc in primary_up:
                    info = primary_up[rc]
                    input_sources.extend(info.get("sources", [(primary_up_id, rc)] if primary_up_id else []))
                    input_origins.extend(info.get("root_origins", []))
                    if info.get("derivation_tree"):
                        input_trees.append(info.get("derivation_tree"))

            out_cols = []
            output_mode = cfg.get("output_mode", "single")
            if output_mode == "json_parse" and isinstance(cfg.get("json_fields"), list) and cfg.get("json_fields"):
                for jf in cfg.get("json_fields", []):
                    jname = (jf.get("name") if isinstance(jf, dict) else str(jf)).strip()
                    if jname:
                        out_cols.append(jname)
            if not out_cols:
                out_col = str(cfg.get("output_column") or "AI_Response").strip() or "AI_Response"
                out_cols.append(out_col)

            for oc in out_cols:
                hop = {
                    "node_id": nid, "node_name": nname, "node_type": ntype,
                    "action": "AI LLM Process", "column": oc,
                    "detail": f"Generated via LLM using prompt referencing: {', '.join(ref_cols) if ref_cols else 'no variables'}",
                    "inputs": ref_cols
                }
                clean_hops = _clean_and_order_hops([], hop, topo_order)
                tree = {
                    "node_id": nid, "node_name": nname, "node_type": ntype, "column": oc,
                    "action": "AI LLM Process", "detail": hop["detail"], "inputs": input_trees
                }
                node_result[oc] = {
                    "sources": list(dict.fromkeys(input_sources)) if input_sources else ([(primary_up_id, "*")] if primary_up_id else [(nid, oc)]),
                    "category": "calculated",
                    "hops": clean_hops,
                    "ancestor_node_ids": list(dict.fromkeys([primary_up_id, nid] if primary_up_id else [nid])),
                    "root_origins": _merge_root_origins(input_origins),
                    "derivation_tree": tree
                }

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
    column_name: Optional[str] = None,
    *,
    lineage: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Computes downstream nodes that depend on fields from source_node_id.

    Args:
        workflow: Workflow dict.
        source_node_id: Node whose downstream impact to trace.
        column_name: If provided, restrict to a single column.
        lineage: Pre-computed result of compute_rich_lineage(workflow). Pass this
                 when the caller already has lineage to avoid computing it twice
                 (e.g., endpoints that call both compute_rich_lineage and this function).

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

    # Inspect each downstream node for column usage.
    # Use caller-supplied lineage if available to avoid recomputing the full graph.
    rich_upstream = lineage if lineage is not None else compute_rich_lineage(workflow)
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

            # Determine which column names entering nid derive from (source_node_id, col)
            relevant_cols = {col}
            pred_conns = [c for c in connections if (c.get("target") or c.get("to_node")) == nid]
            for pconn in pred_conns:
                pid = pconn.get("source") or pconn.get("from_node")
                if pid == source_node_id:
                    relevant_cols.add(col)
                if pid in rich_upstream:
                    for out_c, out_info in rich_upstream[pid].items():
                        srcs = out_info.get("sources", [])
                        if (source_node_id, col) in srcs or (source_node_id, "*") in srcs:
                            relevant_cols.add(out_c)
                        for ro in out_info.get("root_origins", []):
                            if ro.get("node_id") == source_node_id and (col in ro.get("columns", []) or "*" in ro.get("columns", [])):
                                relevant_cols.add(out_c)

            col_pattern = r'\[(?:' + '|'.join(re.escape(c) for c in relevant_cols) + r')\]'

            if ntype == "filter":
                expr = cfg.get("expression") or ""
                if re.search(col_pattern, expr, re.IGNORECASE) or any(cfg.get("field") == c for c in relevant_cols):
                    matched_usage = {
                        "usage": "Filter condition",
                        "detail": expr or f"Filtered on [{', '.join(relevant_cols)}]"
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
                    group_by = cfg.get("group_by_fields") or cfg.get("group_by") or []
                    if isinstance(group_by, str):
                        group_by = [group_by]
                    if any(c in group_by for c in relevant_cols):
                        matched_usage = {
                            "usage": "Multi-Row Grouping",
                            "detail": f"Group key for Multi-Row Formula calculation"
                        }
                    else:
                        expr = cfg.get("expression") or ""
                        row_pattern = rf'\[(?:Row\s*[+-]?\s*\d+\s*:\s*)?(?:' + '|'.join(re.escape(c) for c in relevant_cols) + r')\]'
                        if re.search(row_pattern, expr, re.IGNORECASE) or re.search(col_pattern, expr, re.IGNORECASE):
                            out_col = cfg.get("output_field") or cfg.get("new_field_name") or cfg.get("field_name") or cfg.get("field") or "New_Field"
                            matched_usage = {
                                "usage": "Multi-Row Calculation",
                                "detail": f"{out_col} = {expr}"
                            }

            elif ntype == "multi_field_formula":
                selected_fields = cfg.get("selected_fields") or cfg.get("fields") or []
                expr = cfg.get("expression") or ""
                if (not selected_fields or any(c in selected_fields for c in relevant_cols)) and (re.search(col_pattern, expr, re.IGNORECASE) or "_CurrentField" in expr or not expr):
                    matched_usage = {
                        "usage": "Multi-Field Calculation",
                        "detail": expr or f"Formula applied to [{', '.join(relevant_cols)}]"
                    }

            elif ntype in ("datetime", "date_time"):
                if any(cfg.get("field") == c or cfg.get("column") == c for c in relevant_cols):
                    out_col = cfg.get("output_column") or cfg.get("output_field") or f"{col}_DateTime"
                    mode = cfg.get("conversion_type") or cfg.get("mode", "parse")
                    matched_usage = {
                        "usage": "DateTime Conversion",
                        "detail": f"{str(mode).title()} from [{col}] -> {out_col}"
                    }

            elif ntype == "text_to_columns":
                if any(cfg.get("column") == c for c in relevant_cols):
                    matched_usage = {
                        "usage": "Text Split",
                        "detail": f"Split [{col}] into {cfg.get('num_columns', 2)} columns"
                    }

            elif ntype == "record_id":
                group_by = cfg.get("group_by", [])
                if isinstance(group_by, str):
                    group_by = [group_by]
                if any(c in group_by for c in relevant_cols):
                    matched_usage = {
                        "usage": "Record ID Grouping",
                        "detail": f"Group key for RecordID generation"
                    }

            elif ntype == "select":
                fields = cfg.get("fields") or cfg.get("columns") or []
                unknown_item = next(
                    (f for f in fields if (f.get("original") == "*Unknown" or f.get("name") == "*Unknown" or f.get("field") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = True

                found_field = None
                matched_c = None
                ordered_cols = [col] + [c for c in relevant_cols if c != col]
                for c in ordered_cols:
                    for f in fields:
                        orig = f.get("original") or f.get("name") or f.get("field")
                        if orig == c:
                            found_field = f
                            matched_c = c
                            break
                    if found_field is not None:
                        break

                if found_field is not None:
                    keep = found_field.get("keep") if "keep" in found_field else found_field.get("selected", True)
                    rename = (found_field.get("rename") or "").strip()
                    if not keep:
                        matched_usage = {"usage": "Dropped in Select", "detail": f"Field '{matched_c}' deselected"}
                    elif rename and rename != matched_c:
                        matched_usage = {"usage": "Renamed in Select", "detail": f"Renamed to '{rename}'"}
                    else:
                        matched_usage = {"usage": "Selected field", "detail": f"Kept in schema"}
                elif fields:
                    if not select_unknown:
                        matched_usage = {"usage": "Dropped in Select", "detail": f"Field dropped (*Unknown unchecked)"}
                    else:
                        matched_usage = {"usage": "Selected field (Dynamic)", "detail": f"Field kept via *Unknown"}
                else:
                    matched_usage = {"usage": "Selected field", "detail": "All fields selected"}

            elif ntype == "summarize":
                actions = cfg.get("actions") or []
                matching_acts = [a for a in actions if a.get("field") in relevant_cols]
                if matching_acts:
                    act_names = list(dict.fromkeys(a.get("action", "GroupBy") for a in matching_acts))
                    act_descs = [f"{a.get('action', 'GroupBy')} of [{a.get('field')}] -> {_get_summarize_out_name(a)}" for a in matching_acts]
                    matched_usage = {
                        "usage": f"Aggregation ({', '.join(act_names)})",
                        "detail": f"Used in {len(matching_acts)} aggregation(s): {'; '.join(act_descs)}"
                    }

            elif ntype == "join":
                l_fields = list(cfg.get("left_fields") or [])
                r_fields = list(cfg.get("right_fields") or [])
                join_keys = cfg.get("join_keys") or []
                for jk in join_keys:
                    if jk.get("left_key"): l_fields.append(jk.get("left_key"))
                    if jk.get("right_key"): r_fields.append(jk.get("right_key"))
                l_keys = cfg.get("left_keys") or []
                r_keys = cfg.get("right_keys") or []
                l_fields.extend(l_keys)
                r_fields.extend(r_keys)

                if any(c in l_fields or c in r_fields for c in relevant_cols):
                    matched_usage = {
                        "usage": "Join key",
                        "detail": f"Used as join key match"
                    }
                else:
                    select_fields = cfg.get("select_fields") or cfg.get("fields") or []
                    unknown_item = next(
                        (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                        None
                    )
                    if unknown_item is not None:
                        select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                    elif "select_unknown" in cfg:
                        select_unknown = bool(cfg["select_unknown"])
                    else:
                        select_unknown = False

                    found_sf = None
                    matched_c = None
                    ordered_cols = [col] + [c for c in relevant_cols if c != col]
                    for c in ordered_cols:
                        for sf in select_fields:
                            sf_name = sf.get("field") or sf.get("original") or sf.get("name")
                            if sf_name == c or sf_name == f"Right_{c}":
                                found_sf = sf
                                matched_c = c
                                break
                        if found_sf is not None:
                            break

                    if found_sf is not None:
                        keep = found_sf.get("keep") if "keep" in found_sf else found_sf.get("selected", True)
                        rename = found_sf.get("rename")
                        if not keep:
                            matched_usage = {"usage": "Dropped in Join", "detail": f"Field '{matched_c}' deselected in Join"}
                        elif rename and rename != matched_c:
                            matched_usage = {"usage": "Renamed in Join", "detail": f"Renamed to '{rename}' in Join"}
                        else:
                            matched_usage = {"usage": "Joined field", "detail": f"Output in joined stream"}
                    elif select_fields:
                        if not select_unknown:
                            matched_usage = {"usage": "Dropped in Join", "detail": f"Field dropped (*Unknown unchecked in Join)"}
                        else:
                            matched_usage = {"usage": "Joined field (Dynamic)", "detail": f"Field kept via *Unknown in Join"}
                    else:
                        matched_usage = {"usage": "Joined field", "detail": f"Output in joined stream"}

            elif ntype == "join_multiple":
                join_keys = cfg.get("join_keys") or []
                key_fields = []
                for jk in join_keys:
                    if isinstance(jk, dict):
                        key_fields.extend(jk.values())
                    elif isinstance(jk, (list, tuple)):
                        key_fields.extend(jk)
                input_keys = cfg.get("input_keys") or []
                for ik in input_keys:
                    if isinstance(ik, list):
                        key_fields.extend(ik)
                    elif isinstance(ik, str):
                        key_fields.append(ik)
                if any(c in key_fields for c in relevant_cols):
                    matched_usage = {
                        "usage": "Multi-Join key",
                        "detail": f"Used as join key match across multiple inputs"
                    }
                else:
                    select_fields = cfg.get("select_fields") or cfg.get("fields") or []
                    unknown_item = next(
                        (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                        None
                    )
                    if unknown_item is not None:
                        select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                    elif "select_unknown" in cfg:
                        select_unknown = bool(cfg["select_unknown"])
                    else:
                        select_unknown = False

                    found_sf = None
                    matched_c = None
                    ordered_cols = [col] + [c for c in relevant_cols if c != col]
                    for c in ordered_cols:
                        for sf in select_fields:
                            sf_name = sf.get("field") or sf.get("original") or sf.get("name")
                            if sf_name == c or sf_name.endswith(f"_{c}"):
                                found_sf = sf
                                matched_c = c
                                break
                        if found_sf is not None:
                            break

                    if found_sf is not None:
                        keep = found_sf.get("keep") if "keep" in found_sf else found_sf.get("selected", True)
                        if not keep:
                            matched_usage = {"usage": "Dropped in Join Multiple", "detail": f"Field '{matched_c}' deselected in Multi-Join"}
                        else:
                            matched_usage = {"usage": "Multi-Joined field", "detail": f"Output in multi-join stream"}
                    elif select_fields:
                        if not select_unknown:
                            matched_usage = {"usage": "Dropped in Join Multiple", "detail": f"Field dropped (*Unknown unchecked in Multi-Join)"}
                        else:
                            matched_usage = {"usage": "Multi-Joined field (Dynamic)", "detail": f"Field kept via *Unknown in Multi-Join"}
                    else:
                        matched_usage = {"usage": "Multi-Joined field", "detail": f"Output in multi-join stream"}

            elif ntype == "append_fields":
                select_fields = cfg.get("select_fields") or cfg.get("fields") or []
                prefix = cfg.get("source_prefix", "Source_")
                unknown_item = next(
                    (sf for sf in select_fields if (sf.get("field") == "*Unknown" or sf.get("original") == "*Unknown" or sf.get("name") == "*Unknown")),
                    None
                )
                if unknown_item is not None:
                    select_unknown = unknown_item.get("keep") if "keep" in unknown_item else unknown_item.get("selected", True)
                elif "select_unknown" in cfg:
                    select_unknown = bool(cfg["select_unknown"])
                else:
                    select_unknown = False

                found_sf = None
                matched_c = None
                ordered_cols = [col] + [c for c in relevant_cols if c != col]
                for c in ordered_cols:
                    for sf in select_fields:
                        sf_name = sf.get("field") or sf.get("original") or sf.get("name")
                        if sf_name == c or sf_name == f"{prefix}{c}":
                            found_sf = sf
                            matched_c = c
                            break
                    if found_sf is not None:
                        break

                if found_sf is not None:
                    keep = found_sf.get("keep") if "keep" in found_sf else found_sf.get("selected", True)
                    if not keep:
                        matched_usage = {"usage": "Dropped in Append Fields", "detail": f"Field '{matched_c}' deselected in Append Fields"}
                    else:
                        matched_usage = {"usage": "Appended Cartesian field", "detail": f"Retained in Cartesian join output"}
                elif select_fields:
                    if not select_unknown:
                        matched_usage = {"usage": "Dropped in Append Fields", "detail": f"Field dropped (*Unknown unchecked in Append Fields)"}
                    else:
                        matched_usage = {"usage": "Appended Cartesian field (Dynamic)", "detail": f"Field kept via *Unknown in Append Fields"}
                else:
                    matched_usage = {
                        "usage": "Appended Cartesian field",
                        "detail": f"Passed through Cartesian product"
                    }

            elif ntype == "find_replace":
                if any(cfg.get("find_field") == c for c in relevant_cols):
                    matched_usage = {"usage": "Find Field", "detail": f"Target column for find and replace"}
                elif any(cfg.get("find_value_field") == c for c in relevant_cols):
                    matched_usage = {"usage": "Find Value Field", "detail": f"Key to search for in Find stream"}
                elif any(cfg.get("replace_with_field") == c for c in relevant_cols):
                    matched_usage = {"usage": "Replace Value Field", "detail": f"Replacement text field"}
                elif any(c in (cfg.get("append_fields") or []) for c in relevant_cols):
                    matched_usage = {"usage": "Appended Field", "detail": f"Field appended from reference table"}

            elif ntype == "transpose":
                key_fields = cfg.get("key_fields") or cfg.get("key_columns") or []
                data_fields = cfg.get("data_fields") or cfg.get("data_columns") or []
                if any(c in key_fields for c in relevant_cols):
                    matched_usage = {"usage": "Transpose Key Field", "detail": f"Key retained across transposition"}
                elif any(c in data_fields for c in relevant_cols):
                    matched_usage = {"usage": "Transpose Data Field", "detail": f"Pivoted into Name/Value rows"}

            elif ntype == "crosstab":
                group_by = cfg.get("group_by") or cfg.get("group_columns") or []
                if isinstance(group_by, str): group_by = [group_by]
                if any(c in group_by for c in relevant_cols):
                    matched_usage = {"usage": "CrossTab Group By", "detail": f"Group key in Cross Tab"}
                elif any(cfg.get("header_field") == c for c in relevant_cols):
                    matched_usage = {"usage": "CrossTab Header Field", "detail": f"Values pivoted into column headers"}
                elif any(cfg.get("value_field") == c for c in relevant_cols):
                    matched_usage = {"usage": "CrossTab Value Field", "detail": f"Values aggregated in pivot cells"}

            elif ntype == "llm_process":
                user_template = str(cfg.get("user_prompt_template") or cfg.get("prompt_template") or cfg.get("prompt") or "")
                sys_col = str(cfg.get("system_prompt_column") or "") if cfg.get("system_prompt_source") == "column" else ""
                ref_cols = set(re.findall(r'\{\{\[([^\]]+)\]\}\}', user_template)) | set(re.findall(r'\[([^\]]+)\]', user_template))
                if sys_col:
                    ref_cols.add(sys_col)
                if any(c in ref_cols for c in relevant_cols):
                    out_col = cfg.get("output_column") or "AI_Response"
                    matched_usage = {
                        "usage": "LLM Prompt Variable",
                        "detail": f"Referenced in LLM prompt template to generate [{out_col}]"
                    }

            elif ntype in ("sort", "unique", "clean", "sample", "auto_field", "browse"):
                sort_fields = [f.get("field") for f in (cfg.get("fields") or []) if isinstance(f, dict)]
                clean_cols = cfg.get("columns") or []
                group_cols = cfg.get("group_by") or []
                fields_list = [f if isinstance(f, str) else (f.get("field") or f.get("name")) for f in (cfg.get("fields") or [])]
                if isinstance(group_cols, str): group_cols = [group_cols]
                if (any(c in sort_fields or c in clean_cols or c in group_cols or c in fields_list
                        or cfg.get("field") == c or cfg.get("column") == c for c in relevant_cols)
                        or ntype in ("auto_field", "browse")):
                    matched_usage = {
                        "usage": f"{ntype.replace('_', ' ').title()} operation",
                        "detail": f"Processed by {ntype.replace('_', ' ').title()} tool"
                    }

            elif ntype in ("output_data", "output"):
                matched_usage = {
                    "usage": "Exported to destination",
                    "detail": cfg.get("path") or cfg.get("filename") or "Final output sink"
                }

            if not matched_usage and nid in rich_upstream:
                derives = any(
                    (source_node_id, col) in cinfo.get("sources", []) or
                    any(ro.get("node_id") == source_node_id and (col in ro.get("columns", []) or "*" in ro.get("columns", []))
                        for ro in cinfo.get("root_origins", []))
                    for cinfo in rich_upstream[nid].values()
                )
                if derives:
                    matched_usage = {
                        "usage": f"{ntype.replace('_', ' ').title()} stream",
                        "detail": f"Carries data derived from [{col}]"
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
