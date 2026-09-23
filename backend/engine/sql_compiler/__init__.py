"""
Antigravity DataFlow SQL Compiler Package.
Provides visual workflow to SQL transpilation with multi-dialect support.
"""
from backend.engine.sql_compiler.dialects import (
    SQLDialect,
    SnowflakeDialect,
    PostgresDialect,
    DuckDBDialect,
    BigQueryDialect,
    SQLiteDialect,
    DIALECT_REGISTRY,
    get_dialect
)
from backend.engine.sql_compiler.formula_transpiler import (
    transpile_expression,
    SQLFormulaTranspileError
)
from backend.engine.sql_compiler.compiler import (
    SQLCompiler,
    compile_workflow_to_sql
)

__all__ = [
    "SQLDialect",
    "SnowflakeDialect",
    "PostgresDialect",
    "DuckDBDialect",
    "BigQueryDialect",
    "SQLiteDialect",
    "DIALECT_REGISTRY",
    "get_dialect",
    "transpile_expression",
    "SQLFormulaTranspileError",
    "SQLCompiler",
    "compile_workflow_to_sql"
]
