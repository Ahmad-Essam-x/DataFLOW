"""
Connections Blueprint — REST API for named database connection CRUD.

Endpoints:
  GET    /api/connections              List all connections (no passwords)
  POST   /api/connections              Create a new connection
  PUT    /api/connections/<id>         Update an existing connection
  DELETE /api/connections/<id>         Delete connection + stored credential
  POST   /api/connections/<id>/test    Test connectivity
  GET    /api/connections/<id>/tables  List tables/views in the target DB
  POST   /api/connections/<id>/preview Run a SQL query; returns first 100 rows
"""
from flask import Blueprint, jsonify, request
import backend.extensions as ext

bp = Blueprint("connections", __name__)


def _mgr():
    if ext.connection_manager is None:
        from flask import abort
        abort(503, "Connection manager not initialized.")
    return ext.connection_manager


# ------------------------------------------------------------------
# List / Create
# ------------------------------------------------------------------

@bp.route("/api/connections", methods=["GET"])
def list_connections():
    conns = _mgr().list_connections()
    return jsonify({"success": True, "connections": conns})


@bp.route("/api/connections", methods=["POST"])
def create_connection():
    body = request.get_json(force=True) or {}
    conn = body.get("connection", body)
    password = body.get("password") or conn.pop("password", None)
    try:
        conn_id = _mgr().save_connection(conn, password=password)
        saved = _mgr().get_connection(conn_id)
        return jsonify({"success": True, "connection": saved}), 201
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


# ------------------------------------------------------------------
# Update / Delete
# ------------------------------------------------------------------

@bp.route("/api/connections/<conn_id>", methods=["PUT"])
def update_connection(conn_id: str):
    body = request.get_json(force=True) or {}
    conn = body.get("connection", body)
    password = body.get("password") or conn.pop("password", None)
    conn["id"] = conn_id
    try:
        _mgr().save_connection(conn, password=password)
        saved = _mgr().get_connection(conn_id)
        return jsonify({"success": True, "connection": saved})
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/connections/<conn_id>", methods=["DELETE"])
def delete_connection(conn_id: str):
    _mgr().delete_connection(conn_id)
    return jsonify({"success": True})


# ------------------------------------------------------------------
# Test / List tables / Preview
# ------------------------------------------------------------------

@bp.route("/api/connections/test", methods=["POST"])
def test_draft_connection():
    """Test connectivity for unsaved/draft connection parameters."""
    body = request.get_json(force=True) or {}
    conn = body.get("connection", body)
    password = body.get("password") or conn.get("password")
    result = _mgr().test_draft_connection(conn, password=password)
    status = 200 if result["success"] else 400
    return jsonify(result), status


@bp.route("/api/connections/<conn_id>/test", methods=["POST"])
def test_connection(conn_id: str):
    result = _mgr().test_connection(conn_id)
    status = 200 if result["success"] else 400
    return jsonify(result), status


@bp.route("/api/connections/<conn_id>/tables", methods=["GET"])
def list_tables(conn_id: str):
    try:
        driver = _mgr().get_driver(conn_id)
        tables = driver.list_tables()
        return jsonify({"success": True, "tables": tables})
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


@bp.route("/api/connections/<conn_id>/preview", methods=["POST"])
def preview_query(conn_id: str):
    body = request.get_json(force=True) or {}
    sql = (body.get("sql") or body.get("query") or "").strip()
    table = body.get("table", "").strip()
    limit = min(int(body.get("limit", 100)), 1000)

    if not sql and not table:
        return jsonify({"success": False, "error": "Provide 'sql' or 'table'."}), 400

    if not sql:
        sql = f'SELECT * FROM "{table}"'

    try:
        driver = _mgr().get_driver(conn_id)
        df = driver.read_query(sql, limit=limit)
        return jsonify({
            "success": True,
            "columns": list(df.columns),
            "rows": df.to_dict(orient="records"),
            "row_count": len(df),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500
