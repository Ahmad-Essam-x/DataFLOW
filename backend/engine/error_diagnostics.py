"""
State-of-the-Art Workflow Error Diagnostics Engine.
Translates Python, Pandas, and DAG exceptions into clear, actionable,
plain-English diagnostic objects with smart suggestions and column recommendations.
"""
import re
import difflib
from typing import Dict, Any, List, Optional


class ErrorDiagnostic:
    def __init__(
        self,
        node_id: Optional[str] = None,
        node_name: Optional[str] = None,
        node_type: Optional[str] = None,
        error_code: str = "GENERAL_ERROR",
        title: str = "Execution Error",
        message: str = "",
        details: str = "",
        suggestion: str = "",
        available_columns: Optional[List[str]] = None,
        missing_columns: Optional[List[str]] = None,
        action_type: str = "open_config"
    ):
        self.node_id = node_id
        self.node_name = node_name
        self.node_type = node_type
        self.error_code = error_code
        self.title = title
        self.message = message
        self.details = details
        self.suggestion = suggestion
        self.available_columns = available_columns or []
        self.missing_columns = missing_columns or []
        self.action_type = action_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_name": self.node_name,
            "node_type": self.node_type,
            "error_code": self.error_code,
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "suggestion": self.suggestion,
            "available_columns": self.available_columns,
            "missing_columns": self.missing_columns,
            "action_type": self.action_type
        }


def diagnose_error(
    error: Exception,
    node: Optional[Dict[str, Any]] = None,
    incoming_columns: Optional[List[str]] = None,
    workflow: Optional[Dict[str, Any]] = None
) -> ErrorDiagnostic:
    """
    Analyzes an error and context to return an actionable ErrorDiagnostic.
    """
    err_str = str(error)
    node_id = node.get("id") if node else None
    node_name = node.get("name") if node else (node.get("type") if node else "Unknown Tool")
    node_type = node.get("type") if node else "unknown"
    avail_cols = incoming_columns or []

    # 1. Circular Dependency (Cycle in DAG)
    if "circular dependency" in err_str.lower() or "cycle" in err_str.lower():
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="CIRCULAR_DEPENDENCY",
            title="Circular Dependency Detected (Loop)",
            message="Your workflow contains a loop where tool outputs feed back into upstream tools.",
            details=err_str,
            suggestion="DataFlow pipelines must flow forward in a Directed Acyclic Graph (DAG). Remove the connection that loops backwards.",
            action_type="inspect_canvas"
        )

    # 2. Missing Input Connection
    if "no input connected" in err_str.lower() or "not connected" in err_str.lower():
        if node_type == "join":
            missing_port = "Left ('L')" if "left input" in err_str.lower() else "Right ('R')"
            return ErrorDiagnostic(
                node_id=node_id,
                node_name=node_name,
                node_type=node_type,
                error_code="MISSING_CONNECTION",
                title=f"Join Missing {missing_port} Input",
                message=f"The Join tool '{node_name}' requires both Left (L) and Right (R) inputs to match records.",
                details=err_str,
                suggestion=f"Connect a data source into the {missing_port} port of the Join tool on the canvas.",
                action_type="open_config"
            )
        if node_type == "append_fields":
            missing_port = "Target ('T')" if "'t'" in err_str.lower() or "target" in err_str.lower() else "Source ('S')"
            return ErrorDiagnostic(
                node_id=node_id,
                node_name=node_name,
                node_type=node_type,
                error_code="MISSING_CONNECTION",
                title=f"Append Fields Missing {missing_port} Input",
                message=f"The Append Fields tool '{node_name}' requires both Target (T) and Source (S) inputs to perform Cartesian append.",
                details=err_str,
                suggestion=f"Connect your primary dataset to Target ('T') and your secondary dataset to Source ('S').",
                action_type="open_config"
            )
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="MISSING_CONNECTION",
            title=f"Tool '{node_name}' Needs An Input",
            message=f"This tool requires incoming data to operate, but no active connection was found.",
            details=err_str,
            suggestion="Drag a wire from an upstream tool's output port into this tool's input port.",
            action_type="open_config"
        )

    # 3. Formula / Expression Column Not Found (UndefinedVariableError / KeyError / NameError)
    var_match = re.search(r"name ['\"]?(.*?)['\"]? is not defined", err_str) or \
                re.search(r"KeyError:\s*['\"]?(.*?)['\"]?", err_str) or \
                re.search(r"Column ['\"]?(.*?)['\"]? not found", err_str)

    if var_match or "is not defined" in err_str:
        col_name = var_match.group(1).strip() if var_match else "unknown"
        # If it has sanitization artifacts e.g. __col_0__
        if "__col_" in col_name and node and "config" in node:
            expr = str(node.get("config", {}).get("formulas", ""))
            bracketed = re.findall(r"\[(.*?)\]", expr)
            if bracketed:
                col_name = bracketed[0]

        # Fuzzy match closest column
        suggestions = difflib.get_close_matches(col_name, avail_cols, n=3, cutoff=0.3)
        sugg_text = ""
        if suggestions:
            sugg_text = f"Did you mean {', '.join([repr(s) for s in suggestions])}? "
        elif avail_cols:
            sugg_text = f"Available incoming columns are: {', '.join(avail_cols[:8])}{'...' if len(avail_cols) > 8 else ''}."

        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="COLUMN_NOT_FOUND",
            title=f"Column [{col_name}] Not Found",
            message=f"Tool '{node_name}' tried to reference column [{col_name}], which does not exist in the incoming dataset.",
            details=err_str,
            suggestion=f"{sugg_text} Check upstream tools to ensure this column is included, or select it from the column pills in the configuration panel.",
            available_columns=avail_cols,
            missing_columns=[col_name],
            action_type="open_config"
        )

    # 4. Join Key Errors
    if node_type == "join" and ("join keys" in err_str.lower() or "key" in err_str.lower()):
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="JOIN_KEY_MISCONFIGURED",
            title="Join Key Configuration Error",
            message=f"The Join tool '{node_name}' could not match records between Left and Right inputs.",
            details=err_str,
            suggestion="Open the Join tool configuration and select at least one matching key pair (e.g. Left: CustomerID = Right: CustomerID). You can also click 'Auto-Match Keys'.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 5. File Not Found (Input Data)
    if "file not found" in err_str.lower() or "no such file" in err_str.lower():
        file_path = node.get("config", {}).get("file_path", "") if node else ""
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="FILE_NOT_FOUND",
            title="Input Data File Missing",
            message=f"Could not locate data file '{file_path}'.",
            details=err_str,
            suggestion="Verify the file path, upload a new CSV or Excel file via the configuration panel, or pick one of the pre-loaded sample datasets.",
            action_type="open_config"
        )

    # 6. Type Mismatch (e.g. string arithmetic or conversion errors)
    if "unsupported operand type" in err_str.lower() or "could not convert" in err_str.lower() or "can only concatenate" in err_str.lower():
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="TYPE_MISMATCH",
            title="Data Type Conflict in Calculation",
            message=f"Tool '{node_name}' failed because columns have incompatible data types for this calculation.",
            details=err_str,
            suggestion="Ensure numerical fields (Price, Quantity, Sales) are not formatted as text strings. Use a 'Select' tool upstream to cast them to Float or Integer.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 7. Division by Zero
    if "division by zero" in err_str.lower() or "zero division" in err_str.lower():
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="DIVISION_BY_ZERO",
            title="Division by Zero Detected",
            message=f"Formula in '{node_name}' attempted to divide by a zero denominator value.",
            details=err_str,
            suggestion="Use an IF conditional in your formula e.g.: IF([Denominator] != 0, [Numerator] / [Denominator], 0).",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 8. Empty / Missing Configuration
    if "no file specified" in err_str.lower() or "empty" in err_str.lower():
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="INCOMPLETE_CONFIG",
            title=f"Incomplete Configuration for '{node_name}'",
            message=f"The tool settings are incomplete or empty.",
            details=err_str,
            suggestion="Click on this tool on the canvas to open the Configuration panel and specify its parameters.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 9. Cartesian Join Limit (Append Fields)
    if "exceeding the limit of 16 records" in err_str.lower() or ("append fields" in err_str.lower() and "16 records" in err_str.lower()):
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="CARTESIAN_SAFETY_LIMIT",
            title="Append Fields Exceeded 16 Record Limit",
            message=f"The Source (S) input has more than 16 records. A Cartesian product could generate an excessively large number of rows.",
            details=err_str,
            suggestion="Open the Append Fields tool configuration and change 'Cartesian Mode' to 'Allow All Appends' if this cross join is intentional, or use a Filter / Sample tool to reduce source records.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 10. Text To Columns Extra Characters / Split Error
    if "extra characters" in err_str.lower() and "text to columns" in err_str.lower():
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="TEXT_SPLIT_OVERFLOW",
            title="Text To Columns: Extra Characters Detected",
            message=f"A record contained more delimited parts than the configured number of columns.",
            details=err_str,
            suggestion="In Text To Columns configuration, either increase 'Number of Columns' or change 'Extra Characters' handling to 'Leave in Last Column' or 'Drop with Warning'.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # 11. Date / Time Parsing Error
    if "datetime" in err_str.lower() and ("could not parse" in err_str.lower() or "format" in err_str.lower()):
        return ErrorDiagnostic(
            node_id=node_id,
            node_name=node_name,
            node_type=node_type,
            error_code="DATETIME_PARSE_ERROR",
            title="DateTime Format Mismatch",
            message=f"DateTime conversion failed to match the incoming string format.",
            details=err_str,
            suggestion="Verify the date format in the DateTime configuration panel. Choose the matching preset (e.g. 'yyyy-MM-dd') or specify a Custom Format string.",
            available_columns=avail_cols,
            action_type="open_config"
        )

    # General Fallback
    return ErrorDiagnostic(
        node_id=node_id,
        node_name=node_name,
        node_type=node_type,
        error_code="EXECUTION_FAILED",
        title=f"Error in Tool '{node_name}'",
        message=err_str,
        details=err_str,
        suggestion="Review this tool's configuration settings and upstream inputs.",
        available_columns=avail_cols,
        action_type="open_config"
    )
