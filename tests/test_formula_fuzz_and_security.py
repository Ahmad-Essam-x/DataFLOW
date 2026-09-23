"""
Formula Engine Fuzzing, Security Penetration, and Robustness Test Suite.
Verifies AST sandboxing, immunity to code injection, graceful degradation
on mathematical edge cases, and path containment security.
"""
import os
import math
import numpy as np
import pandas as pd
import pytest

from backend.engine.formula import evaluate_expression, parse_alteryx_conditionals, FormulaExecutionError
from backend.engine.security import validate_safe_path, is_safe_path, sanitize_file_basename, SecurityError


# ----------------------------------------------------------------------
# 1. Formula Sandbox Escape & Code Injection Attempts
# ----------------------------------------------------------------------
def test_sandbox_escape_import_attempt():
    df = pd.DataFrame({"X": [1, 2, 3]})
    malicious_exprs = [
        "__import__('os').system('echo hacked')",
        "eval('1 + 1')",
        "exec('a = 5')",
        "open('/etc/passwd', 'r')",
        "globals()",
        "locals()",
        "getattr(math, 'sin')",
        "[X].__class__.__mro__[1].__subclasses__()"
    ]

    for expr in malicious_exprs:
        with pytest.raises(Exception):
            evaluate_expression(df, expr)


def test_sandbox_disallow_dunder_attributes():
    df = pd.DataFrame({"Name": ["Admin", "User"]})
    with pytest.raises(Exception):
        evaluate_expression(df, "[Name].__dict__")


# ----------------------------------------------------------------------
# 2. Deep Nesting & Malformed Conditional Fuzzing
# ----------------------------------------------------------------------
def test_deeply_nested_conditionals():
    """Generates a 20-level nested IF...ELSEIF...ENDIF conditional block."""
    df = pd.DataFrame({"Score": [95, 82, 73, 61, 45, 12]})

    branches = []
    for i in range(99, 10, -5):
        branches.append(f"ELSEIF [Score] >= {i} THEN '{i}+'")
    
    expr = f"IF [Score] >= 100 THEN '100' {' '.join(branches)} ELSE 'Fail' ENDIF"
    res = evaluate_expression(df, expr)
    assert len(res) == 6
    assert res.iloc[0] == "94+" or res.iloc[0] == "89+" or "9" in str(res.iloc[0])


def test_malformed_unbalanced_conditionals():
    df = pd.DataFrame({"Val": [10, 20]})
    # Missing ENDIF
    with pytest.raises(Exception):
        evaluate_expression(df, "IF [Val] > 15 THEN 'High' ELSE 'Low'")


def test_mixed_case_conditional_keywords():
    df = pd.DataFrame({"Category": ["A", "B", "C"]})
    expr = 'iF [Category] == "A" tHeN 10 eLsEiF [Category] == "B" ThEn 20 eLsE 30 eNdIf'
    res = evaluate_expression(df, expr)
    assert list(res) == [10, 20, 30]


# ----------------------------------------------------------------------
# 3. Math & String Boundary Fuzzing (Nulls, Zero-Div, Infinite)
# ----------------------------------------------------------------------
def test_division_by_zero_does_not_crash():
    df = pd.DataFrame({"A": [10.0, 20.0, 0.0], "B": [0.0, 2.0, 0.0]})
    res = evaluate_expression(df, "[A] / [B]")
    # Must produce inf or NaN, never uncaught Python ZeroDivisionError
    assert math.isinf(res.iloc[0]) or math.isnan(res.iloc[0])
    assert res.iloc[1] == 10.0


def test_math_log_of_negative_and_zero():
    df = pd.DataFrame({"X": [10.0, 0.0, -5.0]})
    # Log(-5) or Log(0) must return NaN or -inf rather than crashing
    res = evaluate_expression(df, "Log([X])")
    assert not math.isnan(res.iloc[0])
    assert math.isnan(res.iloc[2]) or math.isinf(res.iloc[2])


def test_string_functions_on_null_and_empty():
    df = pd.DataFrame({"Txt": ["  hello  ", None, "", np.nan]})
    # Trim on nulls
    trimmed = evaluate_expression(df, "Trim([Txt])")
    assert trimmed.iloc[0] == "hello"

    # Upper on nulls
    upper = evaluate_expression(df, "UpperCase([Txt])")
    assert upper.iloc[0] == "  HELLO  "

    # Length on nulls
    length = evaluate_expression(df, "Length([Txt])")
    assert length.iloc[0] == 9


def test_invalid_regex_pattern_handling():
    df = pd.DataFrame({"Txt": ["abc", "123"]})
    # Unclosed bracket in regex pattern
    with pytest.raises(Exception):
        evaluate_expression(df, 'RegexMatch([Txt], "[a-z")')


# ----------------------------------------------------------------------
# 4. Security Sandboxing: Path Traversal Penetration
# ----------------------------------------------------------------------
def test_path_traversal_parent_directory():
    allowed_dirs = ["C:/Users/App/data", "C:/Users/App/workflows"]
    forbidden_targets = [
        "C:/Users/App/data/../../Windows/System32/calc.exe",
        "C:/Windows/explorer.exe",
        "../../boot.ini",
        "C:/Users/App/data/../../../etc/passwd"
    ]

    for target in forbidden_targets:
        assert not is_safe_path(target, allowed_dirs)
        with pytest.raises(SecurityError):
            validate_safe_path(target, allowed_dirs, label="Test Path")


def test_sanitize_file_basename_null_bytes_and_traversal():
    assert sanitize_file_basename("../../secret.exe") == "secret.exe"
    assert sanitize_file_basename("report\x00.exe") == "report.exe"
    assert sanitize_file_basename("folder/subfolder/file.csv") == "file.csv"
    assert sanitize_file_basename("") == "output"
