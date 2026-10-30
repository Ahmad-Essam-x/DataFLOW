"""
Sandboxed execution of generated/user pandas code (Schema Fit).

Layers, from the inside out:
1. validate_code(): ALLOWLIST static check. Only a fixed set of syntax nodes, names and attribute names is
   accepted; everything else is rejected. (A denylist cannot be made sound against the pandas/numpy surface,
   which exposes file, network and process access through hundreds of members.)
2. The code never sees real modules: `re` and `datetime` are tiny namespaces holding only safe functions, and
   `pd` / `np` are the real libraries restricted by layer 1 to an explicit set of members.
3. run_pandas_code(): the code runs in a separate spawned process with a scrubbed environment, a hard memory cap
   (Windows job object), a wall-clock timeout, and a result handed back as Feather bytes - never unpickled.
"""
import ast
import datetime as _datetime
import multiprocessing
import os
import re as _re
import sys
import tempfile
import types
from typing import Optional, Tuple

import numpy as np
import pandas as pd

DEFAULT_TIMEOUT_SECONDS = 30.0
MEMORY_LIMIT_BYTES = 2 * 1024 ** 3  # per sandbox process

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate,
    "float": float, "int": int, "isinstance": isinstance, "len": len, "list": list, "max": max,
    "min": min, "range": range, "round": round, "set": set, "str": str, "sum": sum,
    "tuple": tuple, "zip": zip, "sorted": sorted, "True": True, "False": False, "None": None,
}

# ----------------------------------------------------------------------------- layer 1: allowlists
_ALLOWED_NODES = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.If, ast.For, ast.Pass,
    ast.Name, ast.Load, ast.Store, ast.Constant, ast.Attribute, ast.Subscript, ast.Slice,
    ast.Call, ast.keyword, ast.List, ast.Tuple, ast.Dict, ast.Set,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.Invert, ast.USub, ast.UAdd, ast.Not, ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
    ast.Lambda, ast.arguments, ast.arg, ast.JoinedStr, ast.FormattedValue, ast.Starred,
)

# Plain names the code may read. Loop/lambda/comprehension variables are added dynamically.
_BASE_NAMES = frozenset({"df", "pd", "np", "re", "datetime"} | set(SAFE_BUILTINS))
# Names the code must never rebind: everything except `df` (rebinding `re = pd` would make the per-name
# attribute rules below apply to the wrong object).
_RESERVED_NAMES = _BASE_NAMES - {"df"}

_RE_MEMBERS = frozenset({"sub", "search", "match", "fullmatch", "findall", "split", "escape", "compile",
                         "IGNORECASE", "I", "MULTILINE", "M"})
_DATETIME_MEMBERS = frozenset({"datetime", "date", "timedelta", "time"})

_PD_MEMBERS = frozenset({
    "to_datetime", "to_numeric", "to_timedelta", "isna", "isnull", "notna", "notnull", "NA", "NaT",
    "Series", "DataFrame", "concat", "cut", "qcut", "factorize", "get_dummies", "Timestamp", "Timedelta",
    "api",  # pd.api.types.is_*_dtype only; deeper members are checked below
})
_NP_MEMBERS = frozenset({
    "nan", "NaN", "inf", "pi", "where", "select", "isnan", "isinf", "isfinite", "abs", "round", "floor", "ceil",
    "sqrt", "log", "log10", "exp", "power", "minimum", "maximum", "clip", "sign", "mean", "median", "std",
    "var", "sum", "min", "max", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64",
    "float16", "float32", "float64", "bool_", "str_", "object_", "datetime64", "timedelta64", "array", "arange",
    "nan_to_num", "isin", "unique", "cumsum", "cumprod", "number", "integer", "floating",
})
_PD_API_TYPES = frozenset({
    "is_numeric_dtype", "is_string_dtype", "is_object_dtype", "is_bool_dtype", "is_datetime64_any_dtype",
    "is_integer_dtype", "is_float_dtype", "is_categorical_dtype",
})

# Methods/attributes of DataFrame, Series, .str, .dt, .cat and scalars. Deliberately excludes anything that
# dispatches by name string (agg, transform, pipe, eval, query), reads/writes files (to_*, read_*), or
# exposes plotting/styling (style, plot).
_FRAME_MEMBERS = frozenset({
    # frame / series basics
    "rename", "astype", "copy", "drop", "drop_duplicates", "dropna", "fillna", "replace", "reset_index",
    "set_index", "sort_values", "sort_index", "assign", "reindex", "insert", "pop", "head", "tail", "iloc", "loc",
    "at", "iat", "columns", "index", "values", "dtypes", "dtype", "shape", "empty", "size", "T",
    "isin", "isna", "isnull", "notna", "notnull", "between", "clip", "round", "abs", "where", "mask",
    "map", "apply", "applymap", "combine_first", "squeeze", "unique", "nunique", "value_counts", "tolist",
    "sum", "mean", "median", "min", "max", "std", "var", "count", "cumsum", "cumprod", "diff", "shift", "rank",
    "idxmax", "idxmin", "any", "all", "bfill", "ffill", "interpolate", "explode", "melt", "stack", "unstack",
    "to_list", "to_numpy", "to_dict", "to_frame", "to_series", "to_period", "to_timestamp", "to_pydatetime",
    "str", "dt", "cat", "append", "extend", "keys", "items", "get", "update", "lower", "upper", "strip",
    # .str
    "contains", "startswith", "endswith", "match", "fullmatch", "extract", "extractall", "findall", "split",
    "rsplit", "rstrip", "lstrip", "title", "capitalize", "swapcase", "len", "slice", "slice_replace", "zfill",
    "pad", "center", "ljust", "rjust", "cat", "join", "repeat", "normalize", "partition", "rpartition", "isdigit",
    "isalpha", "isalnum", "isnumeric", "isspace", "islower", "isupper", "get_dummies", "removeprefix",
    "removesuffix", "casefold",
    # .dt
    "year", "month", "day", "hour", "minute", "second", "weekday", "dayofweek", "day_of_week", "dayofyear",
    "quarter", "date", "time", "strftime", "floor", "ceil", "tz_localize", "tz_convert", "days", "seconds",
    "total_seconds", "isocalendar", "is_month_start", "is_month_end", "days_in_month", "month_name", "day_name",
    "microsecond", "nanosecond",
})
_FORMAT_NAMES = frozenset({"format", "format_map"})  # str.format traverses attributes via strings: never allowed

_FORBIDDEN_ANYWHERE = frozenset({
    "agg", "aggregate", "transform", "pipe", "eval", "query", "style", "plot", "hist", "boxplot", "dump", "dumps",
    "load", "loads", "save", "savez", "memmap", "open", "fromfile", "tofile", "compile", "exec", "system",
    "popen", "environ", "getenv", "ctypeslib", "f2py", "lib", "ma", "testing", "io", "compat", "util", "errors",
})


class SandboxError(Exception):
    """Raised when code is rejected by the static check or fails to run safely."""


class _Validator(ast.NodeVisitor):
    def __init__(self):
        self.scope_names = set(_BASE_NAMES)

    def generic_visit(self, node):
        if not isinstance(node, _ALLOWED_NODES):
            raise SandboxError(f"'{type(node).__name__}' is not allowed in transformation code.")
        super().generic_visit(node)

    def _bind(self, target):
        for n in ast.walk(target):
            if isinstance(n, ast.Name):
                if n.id in _RESERVED_NAMES:
                    raise SandboxError(f"'{n.id}' cannot be reassigned.")
                self.scope_names.add(n.id)

    def visit_Name(self, node):
        if node.id.startswith("_") or (isinstance(node.ctx, ast.Load) and node.id not in self.scope_names):
            raise SandboxError(f"Use of name '{node.id}' is not allowed.")
        if isinstance(node.ctx, ast.Store):
            if node.id in _RESERVED_NAMES:
                raise SandboxError(f"'{node.id}' cannot be reassigned.")
            self.scope_names.add(node.id)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value.startswith("__"):
            raise SandboxError("Strings starting with '__' are not allowed.")
        if isinstance(node.value, (bytes, complex)) or node.value is Ellipsis:
            raise SandboxError("This literal type is not allowed.")

    def visit_Assign(self, node):
        self.visit(node.value)
        for t in node.targets:
            self._bind(t)
            self.visit(t)

    def visit_AugAssign(self, node):
        self.visit(node.value)
        self.visit(node.target)

    def visit_For(self, node):
        self.visit(node.iter)
        self._bind(node.target)
        self.visit(node.target)
        for stmt in node.body + node.orelse:
            self.visit(stmt)

    def visit_comprehension(self, node):
        self.visit(node.iter)
        self._bind(node.target)
        self.visit(node.target)
        for cond in node.ifs:
            self.visit(cond)

    def _comp(self, node):
        for gen in node.generators:
            self.visit(gen)
        for field in ("elt", "key", "value"):
            if hasattr(node, field):
                self.visit(getattr(node, field))

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comp

    def visit_Lambda(self, node):
        a = node.args
        if a.vararg or a.kwarg or a.kwonlyargs or a.defaults or a.kw_defaults or a.posonlyargs:
            raise SandboxError("Only simple lambda arguments are allowed.")
        for arg in a.args:
            if arg.arg in _RESERVED_NAMES or arg.arg.startswith("_"):
                raise SandboxError(f"'{arg.arg}' cannot be used as a lambda argument.")
            self.scope_names.add(arg.arg)
        self.visit(node.body)

    def visit_JoinedStr(self, node):
        for v in node.values:
            self.visit(v)

    def visit_FormattedValue(self, node):
        if node.format_spec is not None:
            raise SandboxError("Format specifications are not allowed.")
        self.visit(node.value)

    def visit_Attribute(self, node):
        attr = node.attr
        # re.compile is the regex-pattern constructor (safe); the global ban on `compile` is aimed at the builtin.
        is_re_compile = attr == "compile" and isinstance(node.value, ast.Name) and node.value.id == "re"
        if attr.startswith("_") or (attr in _FORBIDDEN_ANYWHERE and not is_re_compile) or attr in _FORMAT_NAMES:
            raise SandboxError(f"Access to attribute '{attr}' is not allowed.")
        base = node.value
        if isinstance(base, ast.Name) and base.id == "pd":
            if attr not in _PD_MEMBERS:
                raise SandboxError(f"pd.{attr} is not allowed.")
        elif isinstance(base, ast.Name) and base.id == "np":
            if attr not in _NP_MEMBERS:
                raise SandboxError(f"np.{attr} is not allowed.")
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name) and base.value.id == "pd" and base.attr == "api":
            if attr != "types":  # only pd.api.types.<is_*_dtype> is reachable
                raise SandboxError("pd.api members must be accessed as pd.api.types.<is_*_dtype>.")
        elif (isinstance(base, ast.Attribute) and base.attr == "types" and isinstance(base.value, ast.Attribute)
              and base.value.attr == "api"):
            if attr not in _PD_API_TYPES:
                raise SandboxError(f"pd.api.types.{attr} is not allowed.")
        elif isinstance(base, ast.Name) and base.id == "re":
            if attr not in _RE_MEMBERS:
                raise SandboxError(f"re.{attr} is not allowed.")
        elif isinstance(base, ast.Name) and base.id == "datetime":
            if attr not in _DATETIME_MEMBERS:
                raise SandboxError(f"datetime.{attr} is not allowed.")
        elif attr not in _FRAME_MEMBERS:
            raise SandboxError(f"Access to attribute '{attr}' is not allowed.")
        self.visit(base)

    def visit_Call(self, node):
        func = node.func
        # apply/map/where-style methods must take a callable or value, never a method name string
        if isinstance(func, ast.Attribute) and func.attr in ("apply", "map", "applymap") and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                raise SandboxError(f"'{func.attr}' with a string argument is not allowed.")
        if isinstance(func, ast.Name) and func.id not in self.scope_names:
            raise SandboxError(f"Call to '{func.id}' is not allowed.")
        self.visit(func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            if kw.arg is None:
                raise SandboxError("**kwargs expansion is not allowed.")
            self.visit(kw.value)

    def visit_Starred(self, node):
        self.visit(node.value)


def validate_code(code: str) -> None:
    """Raises SandboxError unless `code` only uses the allowed pandas-transformation subset."""
    if len(code) > 20000:
        raise SandboxError("Transformation code is too long.")
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        raise SandboxError(f"Syntax error: {exc.msg} (line {exc.lineno})") from exc
    _Validator().visit(tree)


# ----------------------------------------------------------------------------- layer 2: namespaces
def _make_re():
    ns = types.SimpleNamespace(
        sub=_re.sub, search=_re.search, match=_re.match, fullmatch=_re.fullmatch, findall=_re.findall,
        split=_re.split, escape=_re.escape, IGNORECASE=_re.IGNORECASE, I=_re.I, MULTILINE=_re.MULTILINE,
        compile=_re.compile,
    )
    return ns


def _make_datetime():
    return types.SimpleNamespace(
        datetime=_datetime.datetime, date=_datetime.date, timedelta=_datetime.timedelta, time=_datetime.time,
    )


# ----------------------------------------------------------------------------- layer 3: child process
def _limit_memory_windows(limit_bytes: int) -> None:
    """Attach the current process to a job object that kills it if it exceeds limit_bytes (Windows only)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                        ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

        k32 = ctypes.windll.kernel32
        k32.CreateJobObjectW.restype = wintypes.HANDLE
        job = k32.CreateJobObjectW(None, None)
        info = EXTENDED()
        # JOB_OBJECT_LIMIT_PROCESS_MEMORY | KILL_ON_JOB_CLOSE | ACTIVE_PROCESS(1 = no child processes)
        info.BasicLimitInformation.LimitFlags = 0x100 | 0x2000 | 0x8
        info.BasicLimitInformation.ActiveProcessLimit = 1
        info.ProcessMemoryLimit = limit_bytes
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        k32.AssignProcessToJobObject(job, k32.GetCurrentProcess())
    except Exception:
        pass  # best effort; the wall-clock timeout still applies


def _child_main(in_path: str, out_path: str, code: str, mem_limit: int) -> None:
    """Runs in the spawned process: load df, exec validated code, write the resulting df (Feather) or an error."""
    import json
    # Scrub the environment: no tokens, proxies or user paths reachable from the generated code.
    keep = {"SYSTEMROOT", "TEMP", "TMP", "PATH"}
    for k in list(os.environ):
        if k.upper() not in keep:
            os.environ.pop(k, None)
    _limit_memory_windows(mem_limit)

    status = {"ok": False, "error": "unknown error"}
    try:
        with open(in_path, "rb") as fh:
            df = pd.read_feather(fh)
        env_globals = {"pd": pd, "np": np, "re": _make_re(), "datetime": _make_datetime(), "__builtins__": SAFE_BUILTINS}
        env_locals = {"df": df}
        exec(compile(code, "<schema_fit>", "exec"), env_globals, env_locals)
        out_df = env_locals.get("df")
        if not isinstance(out_df, pd.DataFrame):
            status = {"ok": False, "error": "Transformation code did not result in a valid Pandas DataFrame named `df`."}
        else:
            out_df = out_df.copy()
            out_df.columns = [str(c) for c in out_df.columns]
            out_df.reset_index(drop=True).to_feather(out_path)
            status = {"ok": True, "error": None}
    except BaseException as exc:  # noqa: BLE001 - report everything to the parent
        status = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    with open(out_path + ".status", "w", encoding="utf-8") as fh:
        json.dump(status, fh)


def run_pandas_code(df_input: pd.DataFrame, code: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Tuple[pd.DataFrame, Optional[str]]:
    """Validates then runs `code` against a copy of df_input in an isolated child process.

    Returns (result_df, None) on success, or (df_input, error_message) on any failure.
    """
    import json
    try:
        validate_code(code)
    except SandboxError as exc:
        return df_input, str(exc)

    ctx = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix="dataflow_sandbox_") as tmp:
        in_path = os.path.join(tmp, "in.feather")
        out_path = os.path.join(tmp, "out.feather")
        try:
            src = df_input.copy()
            src.columns = [str(c) for c in src.columns]
            src.reset_index(drop=True).to_feather(in_path)
        except Exception as exc:  # noqa: BLE001
            return df_input, f"Could not prepare data for the sandbox: {exc}"

        proc = ctx.Process(target=_child_main, args=(in_path, out_path, code, MEMORY_LIMIT_BYTES), daemon=True)
        proc.start()
        proc.join(timeout)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
            return df_input, f"Transformation code exceeded the {timeout:g}s time limit and was stopped."

        status_path = out_path + ".status"
        if not os.path.exists(status_path):
            return df_input, "Transformation process ended unexpectedly (it may have exceeded the memory limit)."
        try:
            with open(status_path, "r", encoding="utf-8") as fh:
                status = json.load(fh)
            if not status.get("ok"):
                return df_input, status.get("error") or "Transformation failed."
            return pd.read_feather(out_path), None
        except Exception as exc:  # noqa: BLE001
            return df_input, f"Could not read transformation result: {exc}"
