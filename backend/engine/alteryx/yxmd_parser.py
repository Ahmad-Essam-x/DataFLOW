"""
Core XML Parser for Alteryx (.yxmd) Workflow Documents.
Ingests native Alteryx XML, normalizes coordinates, containers, annotations, and wires,
maps supported tools to native DataFlow nodes, and creates graceful non-destructive
fallback nodes (unsupported_tool) for divergent or unsupported tools.
"""
import os
import re
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple, Set

from .models import ConversionWarning, YxmdParseResult
from .tool_mappers import resolve_tool_mapper

logger = logging.getLogger(__name__)


def _clean_color(color_str: str, default: str = "#0284c7") -> str:
    """Normalizes color representations (e.g. #RRGGBB or hex integer)."""
    if not color_str:
        return default
    c = str(color_str).strip()
    if c.startswith("#"):
        return c
    try:
        val = int(c)
        return f"#{val:06x}"
    except Exception:
        return default


def _extract_coords(node_elem: ET.Element) -> Tuple[int, int]:
    """Extracts (x, y) coordinates from <Position> element."""
    pos = node_elem.find("Position")
    if pos is None:
        gui = node_elem.find("GuiSettings")
        if gui is not None:
            pos = gui.find("Position")
    
    if pos is not None:
        try:
            x = int(float(pos.attrib.get("x", "100")))
            y = int(float(pos.attrib.get("y", "100")))
            return max(20, x), max(20, y)
        except (ValueError, TypeError):
            pass
    return 100, 100


def _extract_dimensions(node_elem: ET.Element, default_w: int = 240, default_h: int = 160) -> Tuple[int, int]:
    """Extracts width and height from <Position> or <GuiSettings> element."""
    pos = node_elem.find("Position")
    if pos is None:
        gui = node_elem.find("GuiSettings")
        if gui is not None:
            pos = gui.find("Position")
            
    if pos is not None:
        try:
            w = int(float(pos.attrib.get("width", str(default_w))))
            h = int(float(pos.attrib.get("height", str(default_h))))
            return max(60, w), max(40, h)
        except (ValueError, TypeError):
            pass
    return default_w, default_h


def parse_yxmd_content(xml_content: str, source_name: str = "Workflow") -> YxmdParseResult:
    """
    Parses Alteryx .yxmd XML string into a DataFlow workflow schema.
    Returns YxmdParseResult containing the workflow dictionary, stats, and warnings.
    """
    warnings: List[ConversionWarning] = []
    
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        warnings.append(ConversionWarning(
            tool_id="root",
            tool_name="XML Parser",
            severity="error",
            message=f"Failed to parse Alteryx XML: {str(e)}"
        ))
        empty_wf = {
            "name": source_name,
            "nodes": [],
            "connections": [],
            "containers": [],
            "comments": []
        }
        return YxmdParseResult(workflow=empty_wf, warnings=warnings)

    # 1. Workflow Metadata
    wf_name = source_name.replace(".yxmd", "").replace("_", " ").title()
    meta_info = root.find(".//Properties/MetaInfo")
    if meta_info is not None:
        name_elem = meta_info.find("Name")
        if name_elem is not None and name_elem.text:
            wf_name = name_elem.text.strip()

    nodes_elem = root.find("Nodes")
    connections_elem = root.find("Connections")

    nodes: List[Dict[str, Any]] = []
    containers: List[Dict[str, Any]] = []
    comments: List[Dict[str, Any]] = []
    
    node_id_to_type: Dict[str, str] = {}
    tool_id_to_node_id: Dict[str, str] = {}
    container_child_map: Dict[str, List[str]] = {}

    total_tools = 0
    mapped_tools = 0
    fallback_tools = 0
    seen_tool_ids: Set[str] = set()

    def _process_node(node_elem: ET.Element, current_container_id: Optional[str] = None):
        nonlocal total_tools, mapped_tools, fallback_tools
        tool_id = node_elem.attrib.get("ToolID", "").strip()
        if not tool_id or tool_id in seen_tool_ids:
            return
        seen_tool_ids.add(tool_id)

        dataflow_node_id = f"alteryx_{tool_id}"
        tool_id_to_node_id[tool_id] = dataflow_node_id

        gui_settings = node_elem.find("GuiSettings")
        plugin = gui_settings.attrib.get("Plugin", "").strip() if gui_settings is not None else ""
        eng_settings = node_elem.find("EngineSettings")
        macro = eng_settings.attrib.get("Macro", "").strip() if eng_settings is not None else ""
        if not plugin and macro:
            macro_base = os.path.splitext(os.path.basename(macro))[0]
            plugin = f"macro.{macro_base}"
        props = node_elem.find("Properties")
        config = props.find("Configuration") if props is not None else None
        annotation = props.find("Annotation") if props is not None else None

        x, y = _extract_coords(node_elem)
        w, h = _extract_dimensions(node_elem)

        # Check if this is a Tool Container
        if "toolcontainer" in plugin.lower():
            caption = "Tool Container"
            disabled = False
            folded = False
            color = "#0284c7"
            text_color = "#ffffff"

            if config is not None:
                cap_elem = config.find("Caption")
                if cap_elem is not None and cap_elem.text:
                    caption = cap_elem.text.strip()
                dis_elem = config.find("Disabled")
                if dis_elem is not None:
                    disabled = dis_elem.attrib.get("value", "").lower() == "true"
                fold_elem = config.find("Folded")
                if fold_elem is not None:
                    folded = fold_elem.attrib.get("value", "").lower() == "true"
                style_elem = config.find("Style")
                if style_elem is not None:
                    fill = style_elem.attrib.get("FillColor")
                    if fill:
                        color = _clean_color(fill, "#0284c7")
                    t_col = style_elem.attrib.get("TextColor")
                    if t_col:
                        text_color = _clean_color(t_col, "#ffffff")

            child_node_ids: List[str] = []
            child_nodes = node_elem.find("ChildNodes")
            if child_nodes is not None:
                for cn in child_nodes.findall("Node"):
                    cid = cn.attrib.get("ToolID", "").strip()
                    if cid:
                        child_node_ids.append(f"alteryx_{cid}")
                    _process_node(cn, current_container_id=dataflow_node_id)

            container_child_map[dataflow_node_id] = child_node_ids

            containers.append({
                "id": dataflow_node_id,
                "title": caption,
                "color": color,
                "textColor": text_color,
                "borderStyle": "solid",
                "borderWidth": 2,
                "x": x,
                "y": y,
                "width": max(260, w),
                "height": max(180, h),
                "collapsed": folded,
                "disabled": disabled,
                "nodeIds": child_node_ids
            })
            return

        # Check if this is a Text Box / Comment / Explorer Box
        if "textbox" in plugin.lower() or "htmlbox" in plugin.lower():
            text_content = ""
            bg_color = "#fef08a"
            fg_color = "#1e293b"
            font_size = 13

            if "htmlbox" in plugin.lower():
                bg_color = "#e0f2fe"
                fg_color = "#0369a1"
                if config is not None:
                    url_elem = config.find("URL")
                    if url_elem is not None and url_elem.text:
                        text_content = f"Explorer Box: {url_elem.text.strip()}"
                    else:
                        text_content = "Explorer Box"
            elif config is not None:
                t_elem = config.find("Text")
                if t_elem is not None and t_elem.text:
                    text_content = t_elem.text.strip()
                font_elem = config.find("Font")
                if font_elem is not None:
                    try:
                        font_size = int(float(font_elem.attrib.get("size", "13")))
                    except Exception:
                        pass
                fill_elem = config.find("FillColor")
                if fill_elem is not None:
                    r = fill_elem.attrib.get("r", "254")
                    g = fill_elem.attrib.get("g", "240")
                    b = fill_elem.attrib.get("b", "138")
                    bg_color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"
                txt_elem = config.find("TextColor")
                if txt_elem is not None:
                    r = txt_elem.attrib.get("r", "30")
                    g = txt_elem.attrib.get("g", "41")
                    b = txt_elem.attrib.get("b", "59")
                    fg_color = f"#{int(r):02x}{int(g):02x}{int(b):02x}"

            comments.append({
                "id": dataflow_node_id,
                "text": text_content,
                "color": bg_color,
                "textColor": fg_color,
                "fontSize": font_size,
                "x": x,
                "y": y,
                "width": max(160, w),
                "height": max(60, h)
            })
            return

        # Standard ETL tool node
        total_tools += 1
        mapper = resolve_tool_mapper(plugin)

        # Determine custom node label / annotation
        custom_name = ""
        if annotation is not None:
            name_elem = annotation.find("Name")
            if name_elem is not None and name_elem.text and name_elem.text.strip():
                custom_name = name_elem.text.strip()
            if not custom_name:
                ann_text = annotation.find("DefaultAnnotationText")
                if ann_text is not None and ann_text.text and ann_text.text.strip():
                    custom_name = ann_text.text.strip()

        if mapper is not None and config is not None:
            try:
                node_type, node_config = mapper(config, tool_id, warnings)
                mapped_tools += 1
            except Exception as map_err:
                logger.warning("Error mapping tool %s (%s): %s", tool_id, plugin, map_err)
                node_type = "unsupported_tool"
                node_config = {
                    "original_tool": plugin.split(".")[-1] or "Unknown Tool",
                    "original_plugin": plugin,
                    "tool_id": tool_id,
                    "raw_xml": ET.tostring(config, encoding="unicode") if config is not None else "",
                    "error": str(map_err)
                }
                fallback_tools += 1
                warnings.append(ConversionWarning(
                    tool_id=tool_id,
                    tool_name=plugin.split(".")[-1],
                    severity="warning",
                    message=f"Configuration mapping encountered an error: {str(map_err)}. Converted to passthrough fallback."
                ))
        else:
            # Unsupported Tool Fallback
            fallback_tools += 1
            short_name = plugin.split(".")[-1] if plugin else "Macro / Custom Tool"
            raw_xml_str = ET.tostring(config, encoding="unicode") if config is not None else ""
            
            node_type = "unsupported_tool"
            node_config = {
                "original_tool": short_name,
                "original_plugin": plugin,
                "tool_id": tool_id,
                "raw_xml": raw_xml_str
            }
            warnings.append(ConversionWarning(
                tool_id=tool_id,
                tool_name=short_name,
                severity="info",
                message=f"Alteryx tool '{short_name}' ({plugin or 'Unknown Plugin'}) is preserved as a passthrough fallback node."
            ))

        node_id_to_type[dataflow_node_id] = node_type
        clean_display_name = custom_name or node_config.get("original_tool") or node_type.replace("_", " ").title()

        nodes.append({
            "id": dataflow_node_id,
            "type": node_type,
            "name": clean_display_name,
            "x": x,
            "y": y,
            "config": node_config,
            "container_id": current_container_id
        })

    # 1. Process root Nodes
    if nodes_elem is not None:
        for node_elem in nodes_elem.findall("Node"):
            _process_node(node_elem, current_container_id=None)

    # 2. Safety sweep: check any unvisited <Node> anywhere in the document tree
    for node_elem in root.findall(".//Node"):
        _process_node(node_elem, current_container_id=None)

    # 3. Synchronize container nodeIds and container_id on nodes
    valid_node_ids = set(n["id"] for n in nodes)
    for container in containers:
        c_id = container["id"]
        container["nodeIds"] = [nid for nid in container.get("nodeIds", []) if nid in valid_node_ids]
        for child_id in container["nodeIds"]:
            for n in nodes:
                if n["id"] == child_id and not n.get("container_id"):
                    n["container_id"] = c_id

    # 4. Connections Mapping
    connections: List[Dict[str, Any]] = []
    connection_elements = []
    if connections_elem is not None:
        connection_elements.extend(connections_elem.findall(".//Connection"))
    for c in root.findall(".//Connection"):
        if c not in connection_elements:
            connection_elements.append(c)

    conn_counter = 1

    for conn_elem in connection_elements:
        origin = conn_elem.find("Origin")
        dest = conn_elem.find("Destination")
        if origin is None or dest is None:
            continue

        orig_tool = origin.attrib.get("ToolID", "").strip()
        dest_tool = dest.attrib.get("ToolID", "").strip()
        orig_conn = origin.attrib.get("Connection", "Output").strip()
        dest_conn = dest.attrib.get("Connection", "Input").strip()

        src_node_id = tool_id_to_node_id.get(orig_tool)
        tgt_node_id = tool_id_to_node_id.get(dest_tool)

        if not src_node_id or not tgt_node_id:
            continue
        if src_node_id not in valid_node_ids or tgt_node_id not in valid_node_ids:
            continue

        # Map Origin Connection Handles
        orig_lower = orig_conn.lower()
        if orig_lower in ("true", "t"):
            src_handle = "T"
        elif orig_lower in ("false", "f"):
            src_handle = "F"
        elif orig_lower in ("join", "j"):
            src_handle = "J"
        elif orig_lower in ("left", "l"):
            src_handle = "L"
        elif orig_lower in ("right", "r"):
            src_handle = "R"
        elif orig_lower in ("unique", "u"):
            src_handle = "U"
        elif orig_lower in ("duplicate", "duplicates", "d"):
            src_handle = "D"
        else:
            src_handle = "O"

        # Map Destination Connection Handles based on target node type
        tgt_type = node_id_to_type.get(tgt_node_id, "")
        dest_lower = dest_conn.lower()

        if tgt_type == "join":
            if "left" in dest_lower or dest_lower == "#1" or dest_lower == "l":
                tgt_handle = "L"
            elif "right" in dest_lower or dest_lower == "#2" or dest_lower == "r":
                tgt_handle = "R"
            else:
                tgt_handle = "L"
        elif tgt_type == "append_fields":
            if "target" in dest_lower or dest_lower == "t":
                tgt_handle = "T"
            elif "source" in dest_lower or dest_lower == "s":
                tgt_handle = "S"
            else:
                tgt_handle = "T"
        elif tgt_type == "find_replace":
            if "target" in dest_lower or "find" in dest_lower or dest_lower == "f":
                tgt_handle = "F"
            elif "source" in dest_lower or "replace" in dest_lower or dest_lower == "r":
                tgt_handle = "R"
            else:
                tgt_handle = "F"
        elif tgt_type == "schema_fit":
            if "model" in dest_lower or dest_lower == "m":
                tgt_handle = "M"
            elif "target" in dest_lower or dest_lower == "t":
                tgt_handle = "T"
            else:
                tgt_handle = "S"
        else:
            tgt_handle = "I"

        conn_id = f"conn_{src_node_id}_{src_handle}_{tgt_node_id}_{tgt_handle}_{conn_counter}"
        conn_counter += 1

        connections.append({
            "id": conn_id,
            "source": src_node_id,
            "sourceHandle": src_handle,
            "target": tgt_node_id,
            "targetHandle": tgt_handle
        })

    workflow_dict = {
        "name": wf_name,
        "description": f"Imported from Alteryx workflow '{source_name}'",
        "viewport": None,
        "nodes": nodes,
        "connections": connections,
        "containers": containers,
        "comments": comments,
        "metadata": {
            "source_format": "Alteryx .yxmd",
            "imported_from": source_name,
            "total_tools": total_tools,
            "mapped_tools": mapped_tools,
            "fallback_tools": fallback_tools
        }
    }

    return YxmdParseResult(
        workflow=workflow_dict,
        warnings=warnings,
        total_tools=total_tools,
        mapped_tools=mapped_tools,
        fallback_tools=fallback_tools,
        containers_count=len(containers),
        comments_count=len(comments)
    )


def parse_yxmd_file(file_path: str) -> YxmdParseResult:
    """Reads a .yxmd file from disk and parses it into DataFlow format."""
    clean_path = os.path.abspath(file_path)
    if not os.path.isfile(clean_path):
        raise FileNotFoundError(f"Alteryx workflow file not found: {clean_path}")

    with open(clean_path, "r", encoding="utf-8-sig", errors="replace") as f:
        xml_content = f.read()

    filename = os.path.basename(clean_path)
    return parse_yxmd_content(xml_content, source_name=filename)
