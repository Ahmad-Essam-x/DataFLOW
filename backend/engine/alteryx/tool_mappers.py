"""
Tool Mappers for Alteryx XML Configuration Translation.
Translates Alteryx tool XML <Configuration> elements into native DataFlow node configs.
Supports 25+ core Alteryx Base and Spatial tools.
"""
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple

from .models import ConversionWarning


def _get_text(elem: Optional[ET.Element], path: str, default: str = "") -> str:
    """Helper to safely extract text from an element or sub-element."""
    if elem is None:
        return default
    sub = elem.find(path)
    if sub is not None and sub.text is not None:
        return sub.text.strip()
    return default


def _get_attr(elem: Optional[ET.Element], path: str, attr: str, default: str = "") -> str:
    """Helper to safely extract an attribute from an element or sub-element."""
    if elem is None:
        return default
    if not path or path == ".":
        return elem.attrib.get(attr, default)
    sub = elem.find(path)
    if sub is not None:
        return sub.attrib.get(attr, default)
    return default


def _parse_bool(val: Any, default: bool = False) -> bool:
    """Helper to parse boolean from string or XML attribute."""
    if val is None:
        return default
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "t")


def map_alteryx_type(t: str) -> str:
    """Maps Alteryx data type strings to DataFlow schema types."""
    t_clean = str(t or "").strip().lower()
    if t_clean in ("string", "v_string", "v_wstring", "wstring", "blob", "spatialobj"):
        return "string"
    elif t_clean in ("int64", "int32", "int16", "byte", "integer"):
        return "integer"
    elif t_clean in ("double", "float", "fixeddecimal"):
        return "float"
    elif t_clean in ("bool", "boolean"):
        return "boolean"
    elif t_clean == "date":
        return "date"
    elif t_clean in ("datetime", "timestamp"):
        return "datetime"
    elif t_clean == "time":
        return "time"
    return "string"


# ---------------------------------------------------------------------------
# Individual Tool Translators
# ---------------------------------------------------------------------------

def map_db_file_input(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    file_elem = config.find("File")
    raw_path = file_elem.text.strip() if file_elem is not None and file_elem.text else ""
    
    # Strip Alteryx connection prefixes / suffixes (e.g. "path\to\file.csv|table" or query string)
    clean_path = raw_path.split("|")[0].strip() if "|" in raw_path else raw_path
    
    # Check for proprietary .yxdb
    if clean_path.lower().endswith(".yxdb"):
        warnings.append(ConversionWarning(
            tool_id=tool_id,
            tool_name="DbFileInput",
            severity="warning",
            message=f"Proprietary Alteryx database file (.yxdb) referenced: '{clean_path}'. Please provide a CSV, Excel, or Parquet file."
        ))

    opts = config.find("FormatSpecificOptions")
    delimiter = ","
    has_header = True
    if opts is not None:
        del_val = _get_text(opts, "Delimeter")
        if del_val:
            delimiter = "\t" if del_val in ("\\t", "tab") else del_val
        hdr_val = _get_text(opts, "HeaderRow")
        if hdr_val:
            has_header = _parse_bool(hdr_val, default=True)

    limit_val = _get_attr(file_elem, ".", "RecordLimit")
    record_limit = None
    if limit_val and limit_val.isdigit():
        record_limit = int(limit_val)

    return "input_data", {
        "file_path": clean_path,
        "delimiter": delimiter,
        "has_header": has_header,
        "record_limit": record_limit,
        "alteryx_raw_file": raw_path
    }


def map_db_file_output(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    file_elem = config.find("File")
    raw_path = file_elem.text.strip() if file_elem is not None and file_elem.text else ""
    clean_path = raw_path.split("|")[0].strip() if "|" in raw_path else raw_path
    
    ext = os.path.splitext(clean_path)[1].lower().lstrip(".")
    fmt = "csv"
    if ext in ("xlsx", "xls"):
        fmt = "excel"
    elif ext in ("parquet", "pq"):
        fmt = "parquet"
    elif ext in ("json", "jsonl"):
        fmt = "json"
    elif ext == "tsv":
        fmt = "tsv"

    return "output_data", {
        "file_path": clean_path,
        "filename": os.path.basename(clean_path),
        "format": fmt
    }


def map_text_input(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    fields_elem = config.find("Fields")
    columns = []
    if fields_elem is not None:
        for f in fields_elem.findall("Field"):
            col_name = f.attrib.get("name", "").strip()
            if col_name:
                columns.append(col_name)

    data = []
    data_elem = config.find("Data")
    if data_elem is not None:
        for r in data_elem.findall("r"):
            row_vals = []
            for c in r.findall("c"):
                row_vals.append(c.text if c.text is not None else "")
            # Pad row if fewer cells than columns
            if columns and len(row_vals) < len(columns):
                row_vals.extend([""] * (len(columns) - len(row_vals)))
            data.append(row_vals)

    return "text_input", {
        "columns": columns,
        "data": data
    }


def map_select(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    fields = []
    select_fields = config.find("SelectFields")
    select_unknown = True
    
    if select_fields is not None:
        for sf in select_fields.findall("SelectField"):
            f_name = sf.attrib.get("field", "").strip()
            if not f_name:
                continue
            is_selected = _parse_bool(sf.attrib.get("selected"), default=True)
            rename = sf.attrib.get("rename", "").strip() or f_name
            t_str = sf.attrib.get("type", "").strip()
            mapped_type = map_alteryx_type(t_str) if t_str else "none"

            if f_name == "*Unknown":
                select_unknown = is_selected
            
            fields.append({
                "field": f_name,
                "original": f_name,
                "rename": rename,
                "type": mapped_type,
                "selected": is_selected,
                "keep": is_selected
            })

    return "select", {
        "fields": fields,
        "select_unknown": select_unknown
    }


def map_filter(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    mode_val = _get_text(config, "Mode", "Simple").lower()
    
    if "custom" in mode_val:
        expr = _get_text(config, "Expression", "")
        return "filter", {
            "mode": "custom",
            "expression": expr
        }
    else:
        # Simple mode
        simple = config.find("Simple")
        if simple is not None:
            field = _get_text(simple, "Field")
            op = _get_text(simple, "Operator")
            operands = simple.find("Operands")
            val = _get_text(operands, "Operand") if operands is not None else ""
            
            op_map = {
                "=": "==",
                "!=": "!=",
                "&lt;": "<",
                "<": "<",
                "&gt;": ">",
                ">": ">",
                "&lt;=": "<=",
                "<=": "<=",
                "&gt;=": ">=",
                ">=": ">=",
                "is null": "is_null",
                "is not null": "not_null",
                "is empty": "is_empty",
                "is not empty": "not_empty",
            }
            mapped_op = op_map.get(op.lower(), op)
            return "filter", {
                "mode": "basic",
                "conditions": [{
                    "column": field,
                    "operator": mapped_op,
                    "value": val,
                    # Alteryx compares text case-sensitively; DataFlow's own default is to ignore case.
                    "ignore_case": False
                }],
                "logical_op": "AND"
            }
        expr = _get_text(config, "Expression", "")
        return "filter", {
            "mode": "custom" if expr else "basic",
            "expression": expr,
            "conditions": []
        }


def map_formula(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    formulas = []
    formula_fields = config.find("FormulaFields")
    if formula_fields is not None:
        for ff in formula_fields.findall("FormulaField"):
            field = ff.attrib.get("field", "").strip()
            expr = ff.attrib.get("expression", "").strip()
            t_str = ff.attrib.get("type", "").strip()
            mapped_type = map_alteryx_type(t_str) if t_str else "string"
            if field and expr:
                formulas.append({
                    "output_field": field,
                    "field": field,
                    "expression": expr,
                    "type": mapped_type
                })

    return "formula", {
        "formulas": formulas
    }


def map_multi_row_formula(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    create_new = _parse_bool(_get_attr(config, "CreateNewField", "value"), default=False)
    new_field = _get_text(config, "NewField", "")
    update_field = _get_text(config, "UpdateField", "")
    expr = _get_text(config, "RowExpression", "") or _get_text(config, "Expression", "")
    
    group_fields = []
    gb_elem = config.find("GroupByFields")
    if gb_elem is not None:
        for f in gb_elem.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name:
                group_fields.append(f_name)

    return "multi_row_formula", {
        "create_new_field": create_new,
        "output_field": new_field if create_new else update_field,
        "expression": expr,
        "group_by_fields": group_fields
    }


def map_multi_field_formula(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    fields = []
    fields_elem = config.find("Fields")
    if fields_elem is not None:
        for f in fields_elem.findall("Field"):
            f_name = f.attrib.get("name", "").strip() or f.attrib.get("field", "").strip()
            is_sel = _parse_bool(f.attrib.get("selected"), default=True)
            if f_name and is_sel:
                fields.append(f_name)

    expr = _get_text(config, "Expression", "")
    copy_output = _parse_bool(_get_attr(config, "CopyOutput", "value"), default=False)
    new_addon = _get_text(config, "NewFieldAddOn", "")

    return "multi_field_formula", {
        "selected_fields": fields,
        "expression": expr,
        "copy_output": copy_output,
        "new_field_addon": new_addon
    }


def map_sort(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    sort_fields = []
    sort_info = config.find("SortInfo")
    if sort_info is not None:
        for f in sort_info.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            order = f.attrib.get("order", "Ascending").strip()
            if f_name:
                sort_fields.append({
                    "field": f_name,
                    "order": "asc" if "asc" in order.lower() else "desc"
                })

    return "sort", {
        "fields": sort_fields
    }


def map_join(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    by_rec_pos = _parse_bool(_get_attr(config, "JoinByRecPos", "value"), default=False)
    
    left_keys = []
    right_keys = []
    for ji in config.findall("JoinInfo"):
        conn = ji.attrib.get("connection", "").lower()
        keys = [f.attrib.get("field", "").strip() for f in ji.findall("Field") if f.attrib.get("field")]
        if conn in ("left", "#1"):
            left_keys.extend(keys)
        elif conn in ("right", "#2"):
            right_keys.extend(keys)

    join_keys = []
    for l, r in zip(left_keys, right_keys):
        join_keys.append({"left_key": l, "right_key": r})

    return "join", {
        "join_mode": "record_position" if by_rec_pos else "keys",
        "join_keys": join_keys,
        "left_keys": left_keys,
        "right_keys": right_keys
    }


def map_join_multiple(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    by_rec_pos = _parse_bool(_get_attr(config, "JoinByRecPos", "value"), default=False)
    
    join_keys = []
    ji = config.find("JoinInfo")
    if ji is not None:
        for f in ji.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name:
                join_keys.append(f_name)

    return "join_multiple", {
        "join_mode": "record_position" if by_rec_pos else "keys",
        "join_keys": join_keys
    }


def map_union(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    mode_val = _get_text(config, "Mode", "ByName")
    return "union", {
        "mode": "by_name" if "name" in mode_val.lower() else "by_pos"
    }


def map_summarize(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    actions = []
    sum_fields = config.find("SummarizeFields")
    if sum_fields is not None:
        for sf in sum_fields.findall("SummarizeField"):
            field = sf.attrib.get("field", "").strip()
            action = sf.attrib.get("action", "GroupBy").strip()
            rename = sf.attrib.get("rename", "").strip() or field
            if field:
                actions.append({
                    "field": field,
                    "action": action,
                    "output_name": rename,
                    "rename": rename
                })

    return "summarize", {
        "actions": actions
    }


def map_unique(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    cols = []
    uf = config.find("UniqueFields")
    if uf is not None:
        for f in uf.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name:
                cols.append(f_name)

    return "unique", {
        "columns": cols
    }


def map_sample(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    mode = _get_text(config, "Mode", "First").lower()
    n_str = _get_text(config, "N", "100")
    n_val = int(n_str) if n_str.isdigit() else 100

    sample_type = "first"
    if "last" in mode:
        sample_type = "last"
    elif "random" in mode:
        sample_type = "random"
    elif "percent" in mode:
        sample_type = "percent"

    return "sample", {
        "sample_type": sample_type,
        "records": n_val
    }


def map_record_id(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    field_name = _get_text(config, "FieldName", "RecordID")
    start_str = _get_text(config, "StartValue", "1")
    start_val = int(start_str) if start_str.isdigit() else 1

    return "record_id", {
        "field_name": field_name,
        "start_value": start_val
    }


def map_transpose(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    key_cols = []
    kf = config.find("KeyFields")
    if kf is not None:
        for f in kf.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name and _parse_bool(f.attrib.get("selected"), default=True):
                key_cols.append(f_name)

    data_cols = []
    df = config.find("DataFields")
    if df is not None:
        for f in df.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name and _parse_bool(f.attrib.get("selected"), default=True):
                data_cols.append(f_name)

    return "transpose", {
        "key_columns": key_cols,
        "data_columns": data_cols,
        "name_column": "Name",
        "value_column": "Value"
    }


def map_crosstab(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    group_by = []
    gf = config.find("GroupFields")
    if gf is not None:
        for f in gf.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name:
                group_by.append(f_name)

    header_field = _get_attr(config, "HeaderField", "field")
    data_field = _get_attr(config, "DataField", "field")
    
    methods = []
    meth_elem = config.find("Methods")
    if meth_elem is not None:
        for m in meth_elem.findall("Method"):
            m_name = m.attrib.get("method", "").strip().lower()
            if m_name:
                methods.append(m_name)

    return "crosstab", {
        "group_by": group_by,
        "header_field": header_field,
        "value_field": data_field,
        "agg_methods": methods or ["sum"]
    }


def map_find_replace(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    find_in = _get_text(config, "FieldFind", "")
    find_field = _get_text(config, "FindReplaceField", "")
    replace_with = _get_text(config, "ReplaceWithField", "")
    search_type = _get_text(config, "SearchType", "BeginningOfField")

    return "find_replace", {
        "find_in_field": find_in,
        "find_field": find_field,
        "replace_with_field": replace_with,
        "match_type": "part" if "part" in search_type.lower() else "entire"
    }


def map_append_fields(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    cartesian = _get_text(config, "CartesianMode", "Allow")
    return "append_fields", {
        "cartesian_mode": cartesian
    }


def map_text_to_columns(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    field = _get_text(config, "Field", "")
    delims = _get_text(config, "Delimeters", ",")
    num_str = _get_attr(config, "NumFields", "value", "2")
    num_fields = int(num_str) if num_str.isdigit() else 2

    return "text_to_columns", {
        "column": field,
        "delimiter": delims,
        "num_columns": num_fields,
        "split_to": "columns"
    }


def map_date_time(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    field = _get_text(config, "FieldName", "")
    in_fmt = _get_text(config, "InputFormat", "yyyy-MM-dd")
    out_fmt = _get_text(config, "OutputFormat", "yyyy-MM-dd")

    return "date_time", {
        "field": field,
        "input_format": in_fmt,
        "output_format": out_fmt
    }


def map_clean(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    # 1. Macro values (Cleanse.yxmc)
    val_map = {}
    for v in config.findall("Value"):
        v_name = v.attrib.get("name", "").strip()
        if v_name:
            val_map[v_name] = v.text.strip() if v.text else ""

    if val_map:
        raw_fields = val_map.get("List Box (11)", "")
        fields = [f.strip(' "\'') for f in re.split(r'[,;\n]+', raw_fields) if f.strip(' "\'')]

        rep_numeric = _parse_bool(val_map.get("Check Box (84)"), default=False)
        rep_string = _parse_bool(val_map.get("Check Box (117)"), default=False)
        trim_ws = _parse_bool(val_map.get("Check Box (15)"), default=True)
        remove_tabs = _parse_bool(val_map.get("Check Box (109)"), default=False)
        remove_all_ws = _parse_bool(val_map.get("Check Box (122)"), default=False)
        remove_letters = _parse_bool(val_map.get("Check Box (53)"), default=False)
        remove_numbers = _parse_bool(val_map.get("Check Box (58)"), default=False)
        remove_punct = _parse_bool(val_map.get("Check Box (70)"), default=False)
        modify_case = _parse_bool(val_map.get("Check Box (77)"), default=False)
        case_mode = str(val_map.get("Drop Down (81)", "none")).lower() if modify_case else "none"

        return "clean", {
            "columns": fields,
            "replace_nulls_numeric": rep_numeric,
            "replace_nulls_string": rep_string,
            "trim_whitespace": trim_ws,
            "remove_tabs_linebreaks": remove_tabs,
            "remove_all_ws": remove_all_ws,
            "remove_letters": remove_letters,
            "remove_numbers": remove_numbers,
            "remove_punctuation": remove_punct,
            "case_mode": case_mode
        }

    # 2. Standard Cleanse plugin XML
    fields = []
    fields_elem = config.find("Fields")
    if fields_elem is not None:
        for f in fields_elem.findall("Field"):
            f_name = f.attrib.get("field", "").strip() or f.attrib.get("name", "").strip()
            if f_name and _parse_bool(f.attrib.get("selected"), default=True):
                fields.append(f_name)

    return "clean", {
        "columns": fields,
        "trim_whitespace": _parse_bool(_get_text(config, "Whitespace"), default=True),
        "remove_letters": _parse_bool(_get_text(config, "Letters"), default=False),
        "remove_numbers": _parse_bool(_get_text(config, "Numbers"), default=False),
        "remove_punctuation": _parse_bool(_get_text(config, "Punctuation"), default=False),
        "replace_nulls_numeric": _parse_bool(_get_text(config, "ReplaceNullsNumeric"), default=False),
        "replace_nulls_string": _parse_bool(_get_text(config, "ReplaceNullsString"), default=False)
    }


def map_select_records(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    ranges_val = ""
    for v in config.findall("Value"):
        if v.attrib.get("name", "").lower() == "ranges":
            ranges_val = v.text.strip() if v.text else ""
            break
    if not ranges_val:
        ranges_elem = config.find("Ranges")
        if ranges_elem is not None and ranges_elem.text:
            ranges_val = ranges_elem.text.strip()

    return "sample", {
        "sample_type": "records_range",
        "ranges": ranges_val
    }


def map_running_total(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    rt_fields = []
    rt_elem = config.find("RunningTotalFields")
    if rt_elem is not None:
        for f in rt_elem.findall("Field"):
            fn = f.attrib.get("field", "").strip()
            if fn:
                rt_fields.append(fn)

    gb_fields = []
    gb_elem = config.find("GroupByFields")
    if gb_elem is not None:
        for f in gb_elem.findall("Field"):
            fn = f.attrib.get("field", "").strip()
            if fn:
                gb_fields.append(fn)

    return "running_total", {
        "running_total_fields": rt_fields,
        "group_by_fields": gb_fields
    }


def map_dynamic_rename(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    rename_mode = _get_text(config, "RenameMode", "FirstRow")
    fields = []
    fields_elem = config.find("Fields")
    if fields_elem is not None:
        for f in fields_elem.findall("Field"):
            fn = f.attrib.get("name", "").strip()
            if fn and fn != "*Unknown":
                fields.append(fn)

    return "dynamic_rename", {
        "rename_mode": rename_mode.lower(),
        "fields": fields
    }


def map_regex(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    field = _get_text(config, "Field", "")
    pattern = _get_text(config, "RegExExpression", "")
    method = _get_text(config, "Method", "Match")
    replace_expr = _get_text(config, "ReplaceExpression", "")

    return "regex", {
        "field": field,
        "pattern": pattern,
        "method": method.lower(),
        "replace_expression": replace_expr
    }


def map_auto_field(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    fields = []
    f_elem = config.find("Fields")
    if f_elem is not None:
        for f in f_elem.findall("Field"):
            f_name = f.attrib.get("field", "").strip()
            if f_name and _parse_bool(f.attrib.get("selected"), default=True):
                fields.append(f_name)

    return "auto_field", {
        "fields": fields
    }


def map_browse(config: ET.Element, tool_id: str, warnings: List[ConversionWarning]) -> Tuple[str, Dict[str, Any]]:
    return "browse", {}


# ---------------------------------------------------------------------------
# Registry of Alteryx Plugin Translators
# ---------------------------------------------------------------------------

ALTERYX_TOOL_MAPPERS = {
    # File Input & Output
    "alteryxbasepluginsgui.dbfileinput.dbfileinput": map_db_file_input,
    "alteryxbasepluginsgui.dbfileoutput.dbfileoutput": map_db_file_output,
    "alteryxbasepluginsgui.textinput.textinput": map_text_input,
    "alteryxbasepluginsgui.browsev2.browsev2": map_browse,

    # Preparation Tools
    "alteryxbasepluginsgui.alteryxselect.alteryxselect": map_select,
    "alteryxbasepluginsgui.filter.filter": map_filter,
    "alteryxbasepluginsgui.formula.formula": map_formula,
    "alteryxbasepluginsgui.multirowformula.multirowformula": map_multi_row_formula,
    "alteryxbasepluginsgui.multifieldformula.multifieldformula": map_multi_field_formula,
    "alteryxbasepluginsgui.sort.sort": map_sort,
    "alteryxbasepluginsgui.unique.unique": map_unique,
    "alteryxbasepluginsgui.sample.sample": map_sample,
    "alteryxbasepluginsgui.recordid.recordid": map_record_id,
    "alteryxbasepluginsgui.autofield.autofield": map_auto_field,
    "alteryxbasepluginsgui.cleanse.cleanse": map_clean,
    "cleanse": map_clean,
    "macro.cleanse": map_clean,
    "datacleanse": map_clean,
    "selectrecords": map_select_records,
    "macro.selectrecords": map_select_records,
    "alteryxbasepluginsgui.runningtotal.runningtotal": map_running_total,
    "runningtotal": map_running_total,
    "alteryxbasepluginsgui.dynamicrename.dynamicrename": map_dynamic_rename,
    "dynamicrename": map_dynamic_rename,
    "alteryxbasepluginsgui.regex.regex": map_regex,
    "regex": map_regex,

    # Join Tools
    "alteryxbasepluginsgui.join.join": map_join,
    "alteryxbasepluginsgui.joinmultiple.joinmultiple": map_join_multiple,
    "alteryxbasepluginsgui.union.union": map_union,
    "alteryxbasepluginsgui.findreplace.findreplace": map_find_replace,
    "alteryxbasepluginsgui.appendfields.appendfields": map_append_fields,

    # Transform Tools
    "alteryxbasepluginsgui.summarize.summarize": map_summarize,
    "alteryxspatialpluginsgui.summarize.summarize": map_summarize,
    "alteryxbasepluginsgui.transpose.transpose": map_transpose,
    "alteryxbasepluginsgui.crosstab.crosstab": map_crosstab,

    # Parse Tools
    "alteryxbasepluginsgui.texttocolumns.texttocolumns": map_text_to_columns,
    "alteryxbasepluginsgui.datetime.datetime": map_date_time,
}


def resolve_tool_mapper(plugin_str: str) -> Optional[Any]:
    """Finds a matching mapper by normalized plugin identifier."""
    if not plugin_str:
        return None
    key = plugin_str.strip().lower()
    if key in ALTERYX_TOOL_MAPPERS:
        return ALTERYX_TOOL_MAPPERS[key]
    
    # Check by short name (e.g. "DbFileInput", "Filter", "Formula")
    short_key = key.split(".")[-1]
    if short_key in ALTERYX_TOOL_MAPPERS:
        return ALTERYX_TOOL_MAPPERS[short_key]
    for p_key, mapper in ALTERYX_TOOL_MAPPERS.items():
        if p_key.split(".")[-1] == short_key:
            return mapper

    return None
