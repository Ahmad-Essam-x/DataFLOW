"""
Alteryx Formula AST to SQL Scalar Expression Transpiler.
Converts Alteryx formula expressions into dialect-specific SQL expressions.
"""
import ast
import re
from typing import Dict, Any, List, Optional, Tuple

from backend.engine.formula import parse_alteryx_conditionals
from backend.engine.sql_compiler.dialects import SQLDialect, get_dialect


class SQLFormulaTranspileError(Exception):
    pass


class SQLASTTranspiler:
    """Translates a Python AST expression tree into dialect-compliant SQL."""

    def __init__(self, dialect: SQLDialect, var_map: Dict[str, str], available_columns: Optional[List[str]] = None):
        self.dialect = dialect
        self.var_map = var_map  # var_name -> orig_column_name
        self.available_columns = set(available_columns or [])

    def transpile(self, node: ast.AST) -> str:
        method = f"_transpile_{node.__class__.__name__}"
        transpiler = getattr(self, method, None)
        if transpiler is None:
            raise SQLFormulaTranspileError(f"Unsupported formula syntax element: {node.__class__.__name__}")
        return transpiler(node)

    def _transpile_Expression(self, node: ast.Expression) -> str:
        return self.transpile(node.body)

    def _transpile_Constant(self, node: ast.Constant) -> str:
        return self.dialect.quote_literal(node.value)

    # Legacy python AST nodes (<= 3.7)
    def _transpile_Num(self, node: ast.Num) -> str:
        return str(node.n)

    def _transpile_Str(self, node: ast.Str) -> str:
        return self.dialect.quote_literal(node.s)

    def _transpile_NameConstant(self, node: ast.NameConstant) -> str:
        return self.dialect.quote_literal(node.value)

    def _transpile_Name(self, node: ast.Name) -> str:
        name = node.id
        # Check if mapped from bracketed syntax [Column Name]
        if name in self.var_map:
            return self.dialect.quote_identifier(self.var_map[name])

        # Check standard constants
        if name in ("True", "true", "TRUE"):
            return self.dialect.quote_literal(True)
        if name in ("False", "false", "FALSE"):
            return self.dialect.quote_literal(False)
        if name in ("None", "null", "NULL"):
            return "NULL"

        # Check if matches an unbracketed available column
        if self.available_columns and name in self.available_columns:
            return self.dialect.quote_identifier(name)

        # Fallback to quoting as column identifier
        return self.dialect.quote_identifier(name)

    def _transpile_UnaryOp(self, node: ast.UnaryOp) -> str:
        operand = self.transpile(node.operand)
        if isinstance(node.op, ast.Not):
            return f"(NOT {operand})"
        elif isinstance(node.op, ast.USub):
            return f"(-{operand})"
        elif isinstance(node.op, ast.UAdd):
            return f"(+{operand})"
        raise SQLFormulaTranspileError(f"Unsupported unary operator: {node.op.__class__.__name__}")

    def _transpile_BinOp(self, node: ast.BinOp) -> str:
        left = self.transpile(node.left)
        right = self.transpile(node.right)
        op = node.op

        if isinstance(op, ast.Add):
            return f"({left} + {right})"
        elif isinstance(op, ast.Sub):
            return f"({left} - {right})"
        elif isinstance(op, ast.Mult):
            return f"({left} * {right})"
        elif isinstance(op, ast.Div):
            return f"({left} / {right})"
        elif isinstance(op, ast.Mod):
            return f"({left} % {right})"
        elif isinstance(op, ast.Pow):
            return f"POWER({left}, {right})"
        raise SQLFormulaTranspileError(f"Unsupported binary operator: {op.__class__.__name__}")

    def _transpile_BoolOp(self, node: ast.BoolOp) -> str:
        op_str = " AND " if isinstance(node.op, ast.And) else " OR "
        sub_exprs = [self.transpile(v) for v in node.values]
        return f"({op_str.join(sub_exprs)})"

    def _transpile_Compare(self, node: ast.Compare) -> str:
        left = self.transpile(node.left)
        comparisons = []

        for op, comp in zip(node.ops, node.comparators):
            right = self.transpile(comp)
            # Null comparisons in SQL
            if right == "NULL":
                if isinstance(op, ast.Eq):
                    comparisons.append(f"({left} IS NULL)")
                elif isinstance(op, ast.NotEq):
                    comparisons.append(f"({left} IS NOT NULL)")
                else:
                    comparisons.append(f"({left} IS NULL)")
            elif left == "NULL":
                if isinstance(op, ast.Eq):
                    comparisons.append(f"({right} IS NULL)")
                elif isinstance(op, ast.NotEq):
                    comparisons.append(f"({right} IS NOT NULL)")
                else:
                    comparisons.append(f"({right} IS NULL)")
            else:
                if isinstance(op, ast.Eq):
                    comparisons.append(f"({left} = {right})")
                elif isinstance(op, ast.NotEq):
                    comparisons.append(f"({left} != {right})")
                elif isinstance(op, ast.Lt):
                    comparisons.append(f"({left} < {right})")
                elif isinstance(op, ast.LtE):
                    comparisons.append(f"({left} <= {right})")
                elif isinstance(op, ast.Gt):
                    comparisons.append(f"({left} > {right})")
                elif isinstance(op, ast.GtE):
                    comparisons.append(f"({left} >= {right})")
                elif isinstance(op, ast.In):
                    comparisons.append(f"({left} IN {right})")
                elif isinstance(op, ast.NotIn):
                    comparisons.append(f"({left} NOT IN {right})")
                else:
                    raise SQLFormulaTranspileError(f"Unsupported comparison: {op.__class__.__name__}")
            left = right

        if len(comparisons) == 1:
            return comparisons[0]
        return f"({' AND '.join(comparisons)})"

    def _transpile_List(self, node: ast.List) -> str:
        items = [self.transpile(el) for el in node.elts]
        return f"({', '.join(items)})"

    def _transpile_Tuple(self, node: ast.Tuple) -> str:
        items = [self.transpile(el) for el in node.elts]
        return f"({', '.join(items)})"

    def _transpile_IfExp(self, node: ast.IfExp) -> str:
        test_sql = self.transpile(node.test)
        body_sql = self.transpile(node.body)
        orelse_sql = self.transpile(node.orelse)
        return f"CASE WHEN {test_sql} THEN {body_sql} ELSE {orelse_sql} END"

    def _unroll_iif_branches(self, node: ast.Call) -> List[Tuple[str, str]]:
        """Collects nested (condition, result) pairs for a clean CASE WHEN."""
        branches = []
        curr = node
        else_expr = "NULL"

        while True:
            if isinstance(curr, ast.Call) and isinstance(curr.func, ast.Name) and curr.func.id.upper() in ("IIF", "IF"):
                if len(curr.args) < 2:
                    break
                cond_sql = self.transpile(curr.args[0])
                then_sql = self.transpile(curr.args[1])
                branches.append((cond_sql, then_sql))
                if len(curr.args) >= 3:
                    curr = curr.args[2]
                else:
                    else_expr = "NULL"
                    break
            else:
                else_expr = self.transpile(curr)
                break

        return branches, else_expr

    def _transpile_Call(self, node: ast.Call) -> str:
        if not isinstance(node.func, ast.Name):
            raise SQLFormulaTranspileError("Dynamic function dispatch not supported in SQL transpilation.")

        fn_name = node.func.id.upper()
        args = node.args

        # 1. Conditionals: IIF / IF
        if fn_name in ("IIF", "IF"):
            branches, else_expr = self._unroll_iif_branches(node)
            when_clauses = [f"WHEN {c} THEN {t}" for c, t in branches]
            return f"CASE {' '.join(when_clauses)} ELSE {else_expr} END"

        # 2. Nulls and Checks
        if fn_name == "ISNULL":
            arg = self.transpile(args[0])
            return f"({arg} IS NULL)"
        if fn_name == "NOTNULL":
            arg = self.transpile(args[0])
            return f"({arg} IS NOT NULL)"
        if fn_name == "NULL":
            return "NULL"
        if fn_name == "ISEMPTY":
            arg = self.transpile(args[0])
            return f"({arg} IS NULL OR TRIM(CAST({arg} AS VARCHAR)) = '')"
        if fn_name in ("IFNULL", "COALESCE"):
            transpiled_args = [self.transpile(a) for a in args]
            return f"COALESCE({', '.join(transpiled_args)})"
        if fn_name == "NOTEMPTY":
            arg = self.transpile(args[0])
            return f"({arg} IS NOT NULL AND TRIM(CAST({arg} AS VARCHAR)) != '')"

        # 3. Conversions
        if fn_name == "TONUMBER":
            arg = self.transpile(args[0])
            target_type = "NUMERIC"
            if self.dialect.name == "sqlite":
                return f"CAST({arg} AS REAL)"
            if self.dialect.supports_try_cast:
                return f"TRY_CAST({arg} AS {target_type})"
            return f"CAST({arg} AS {target_type})"

        if fn_name == "TOSTRING":
            arg = self.transpile(args[0])
            sql_type = "TEXT" if self.dialect.name in ("sqlite", "postgres") else "VARCHAR"
            return f"CAST({arg} AS {sql_type})"

        # 4. String functions
        if fn_name in ("CONTAINS",):
            target = self.transpile(args[0])
            sub = self.transpile(args[1])
            # Case-insensitive like or position
            if self.dialect.supports_ilike:
                return f"({target} ILIKE '%' || {sub} || '%')"
            return f"(LOWER({target}) LIKE '%' || LOWER({sub}) || '%')"

        if fn_name in ("STARTSWITH", "STARTS_WITH"):
            target = self.transpile(args[0])
            sub = self.transpile(args[1])
            if self.dialect.supports_ilike:
                return f"({target} ILIKE {sub} || '%')"
            return f"(LOWER({target}) LIKE LOWER({sub}) || '%')"

        if fn_name in ("ENDSWITH", "ENDS_WITH"):
            target = self.transpile(args[0])
            sub = self.transpile(args[1])
            if self.dialect.supports_ilike:
                return f"({target} ILIKE '%' || {sub})"
            return f"(LOWER({target}) LIKE '%' || LOWER({sub}))"

        if fn_name in ("UPPER", "UPPERCASE"):
            return f"UPPER({self.transpile(args[0])})"

        if fn_name in ("LOWER", "LOWERCASE"):
            return f"LOWER({self.transpile(args[0])})"

        if fn_name == "TRIM":
            return f"TRIM({self.transpile(args[0])})"

        if fn_name in ("LEN", "LENGTH"):
            return f"LENGTH({self.transpile(args[0])})"

        if fn_name == "LEFT":
            target = self.transpile(args[0])
            n = self.transpile(args[1])
            if self.dialect.name == "sqlite":
                return f"SUBSTR({target}, 1, {n})"
            return f"LEFT({target}, {n})"

        if fn_name == "RIGHT":
            target = self.transpile(args[0])
            n = self.transpile(args[1])
            if self.dialect.name == "sqlite":
                return f"SUBSTR({target}, -({n}))"
            return f"RIGHT({target}, {n})"

        if fn_name in ("SUBSTRING", "SUBSTR"):
            target = self.transpile(args[0])
            start = self.transpile(args[1])
            length = self.transpile(args[2]) if len(args) > 2 else None
            if length:
                return f"SUBSTR({target}, {start}, {length})"
            return f"SUBSTR({target}, {start})"

        if fn_name == "REPLACE":
            target = self.transpile(args[0])
            src = self.transpile(args[1])
            dst = self.transpile(args[2])
            return f"REPLACE({target}, {src}, {dst})"

        if fn_name == "CONCAT":
            parts = [self.transpile(a) for a in args]
            return self.dialect.concat_expr(parts)

        # 5. Math functions
        if fn_name == "ROUND":
            target = self.transpile(args[0])
            decimals = self.transpile(args[1]) if len(args) > 1 else "0"
            return f"ROUND({target}, {decimals})"

        if fn_name == "ABS":
            return f"ABS({self.transpile(args[0])})"

        if fn_name in ("CEIL", "CEILING"):
            if self.dialect.name == "sqlite":
                arg = self.transpile(args[0])
                return f"(CASE WHEN {arg} = CAST({arg} AS INT) THEN CAST({arg} AS INT) WHEN {arg} > 0 THEN CAST({arg} AS INT) + 1 ELSE CAST({arg} AS INT) END)"
            return f"CEIL({self.transpile(args[0])})"

        if fn_name == "FLOOR":
            if self.dialect.name == "sqlite":
                arg = self.transpile(args[0])
                return f"(CASE WHEN {arg} = CAST({arg} AS INT) THEN CAST({arg} AS INT) WHEN {arg} > 0 THEN CAST({arg} AS INT) ELSE CAST({arg} AS INT) - 1 END)"
            return f"FLOOR({self.transpile(args[0])})"

        if fn_name in ("MIN", "MAX"):
            fn_sql = "MIN" if fn_name == "MIN" else "MAX"
            if len(args) == 1:
                return f"{fn_sql}({self.transpile(args[0])})"
            # Scalar comparison between multiple values
            transpiled_args = [self.transpile(a) for a in args]
            if self.dialect.name == "sqlite":
                return f"{fn_sql}({', '.join(transpiled_args)})"
            scale_fn = "LEAST" if fn_name == "MIN" else "GREATEST"
            return f"{scale_fn}({', '.join(transpiled_args)})"

        if fn_name == "BETWEEN":
            target = self.transpile(args[0])
            low = self.transpile(args[1])
            high = self.transpile(args[2])
            return f"({target} BETWEEN {low} AND {high})"

        # 6. DateTime functions
        if fn_name in ("DATETIMENOW", "NOW"):
            return self.dialect.current_timestamp_expr()

        if fn_name in ("DATETIMETODAY", "TODAY"):
            return self.dialect.current_date_expr()

        if fn_name == "DATETIMEYEAR":
            arg = self.transpile(args[0])
            if self.dialect.name == "sqlite":
                return f"CAST(STRFTIME('%Y', {arg}) AS INT)"
            return f"EXTRACT(YEAR FROM {arg})"

        if fn_name == "DATETIMEMONTH":
            arg = self.transpile(args[0])
            if self.dialect.name == "sqlite":
                return f"CAST(STRFTIME('%m', {arg}) AS INT)"
            return f"EXTRACT(MONTH FROM {arg})"

        if fn_name == "DATETIMEDAY":
            arg = self.transpile(args[0])
            if self.dialect.name == "sqlite":
                return f"CAST(STRFTIME('%d', {arg}) AS INT)"
            return f"EXTRACT(DAY FROM {arg})"

        # Fallback to standard function call
        transpiled_args = [self.transpile(a) for a in args]
        return f"{fn_name}({', '.join(transpiled_args)})"


def transpile_expression(
    expr: str,
    dialect: Optional[SQLDialect] = None,
    available_columns: Optional[List[str]] = None
) -> str:
    """
    Public entrypoint: Transpiles an Alteryx formula string to dialect-compliant SQL.
    Example:
        transpile_expression("IF [Score] >= 90 THEN 'A' ELSE 'B' ENDIF")
        -> "CASE WHEN \"Score\" >= 90 THEN 'A' ELSE 'B' END"
    """
    if not expr or not expr.strip():
        return "NULL"

    d = dialect or get_dialect("ansi")

    # 1. Transform Alteryx conditional IF...THEN...ELSEIF...ELSE...ENDIF to IIF(...)
    preprocessed = parse_alteryx_conditionals(expr.strip())

    # 2. Extract and map bracketed column names [Column Name]
    var_map: Dict[str, str] = {}
    col_counter = 0

    def replace_bracket(m: re.Match) -> str:
        nonlocal col_counter
        col_name = m.group(1).strip()
        var_name = f"_af_col_{col_counter}_"
        col_counter += 1
        var_map[var_name] = col_name
        return var_name

    sanitized = re.sub(r"\[(.*?)\]", replace_bracket, preprocessed)

    # 3. Handle symbol-based operators (&&, ||, !) outside quoted strings
    parts = re.split(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')', sanitized)
    for i in range(0, len(parts), 2):
        chunk = parts[i]
        chunk = re.sub(r'&&', ' and ', chunk)
        chunk = re.sub(r'\|\|', ' or ', chunk)
        chunk = re.sub(r'(?<![!=<>])!(?!=)', ' not ', chunk)
        chunk = re.sub(r'\bAND\b', ' and ', chunk, flags=re.IGNORECASE)
        chunk = re.sub(r'\bOR\b', ' or ', chunk, flags=re.IGNORECASE)
        chunk = re.sub(r'\bNOT\b', ' not ', chunk, flags=re.IGNORECASE)
        parts[i] = chunk
    sanitized = "".join(parts).strip()

    # 4. Parse into Python AST
    try:
        parsed_ast = ast.parse(sanitized, mode="eval")
    except SyntaxError as se:
        raise SQLFormulaTranspileError(f"Syntax error in formula '{expr}': {se.msg}")

    # 5. Transpile AST to SQL
    transpiler = SQLASTTranspiler(d, var_map, available_columns=available_columns)
    return transpiler.transpile(parsed_ast)
