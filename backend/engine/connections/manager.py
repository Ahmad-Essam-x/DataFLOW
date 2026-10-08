"""
Connection Manager — named database connections with OS-keyring credential storage.

Connection metadata (everything except the password) is stored in connections.json.
Passwords are stored in the OS keyring (Windows Credential Manager on Windows).
Falls back to in-memory-only secret storage when keyring is unavailable.

Connection JSON schema:
{
    "id":          "uuid",
    "name":        "My Postgres",
    "type":        "postgresql" | "snowflake" | "duckdb" | "sqlite",
    "host":        "db.example.com",   # not used for duckdb/sqlite
    "port":        5432,
    "database":    "mydb",             # file path for duckdb/sqlite
    "username":    "alice",
    "account":     "...",              # Snowflake account identifier
    "schema_name": "public",           # Snowflake schema
    "options":     {},
    "created_at":  "ISO8601",
    "updated_at":  "ISO8601"
}
"""
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from .driver_base import BaseDriver

KEYRING_SERVICE = "antigravity_dataflow"
SUPPORTED_TYPES = frozenset({"postgresql", "snowflake", "duckdb", "sqlite"})


class ConnectionManager:
    """
    CRUD interface for named database connections.
    Passwords never written to disk.
    """

    def __init__(self, config_dir: str):
        self._config_dir = config_dir
        self._connections_file = os.path.join(config_dir, "connections.json")
        os.makedirs(config_dir, exist_ok=True)
        self._in_memory_secrets: Dict[str, str] = {}  # fallback when keyring unavailable

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_all(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self._connections_file):
            return {}
        try:
            with open(self._connections_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_all(self, connections: Dict[str, Dict[str, Any]]) -> None:
        with open(self._connections_file, "w", encoding="utf-8") as f:
            json.dump(connections, f, indent=2)

    def _store_secret(self, conn_id: str, password: str) -> None:
        if HAS_KEYRING:
            keyring.set_password(KEYRING_SERVICE, conn_id, password)
        else:
            self._in_memory_secrets[conn_id] = password

    def _get_secret(self, conn_id: str) -> Optional[str]:
        if HAS_KEYRING:
            return keyring.get_password(KEYRING_SERVICE, conn_id)
        return self._in_memory_secrets.get(conn_id)

    def _delete_secret(self, conn_id: str) -> None:
        if HAS_KEYRING:
            try:
                keyring.delete_password(KEYRING_SERVICE, conn_id)
            except Exception:
                pass
        self._in_memory_secrets.pop(conn_id, None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_connections(self) -> List[Dict[str, Any]]:
        """Returns all connections without passwords."""
        return list(self._load_all().values())

    def get_connection(self, conn_id: str) -> Optional[Dict[str, Any]]:
        """Returns connection metadata without password. None if not found."""
        return self._load_all().get(conn_id)

    def save_connection(self, conn: Dict[str, Any], password: Optional[str] = None) -> str:
        """
        Create or update a connection. Assigns a UUID if conn has no 'id'.
        Password is stored in keyring/memory, never persisted to disk.
        Returns the connection id.
        """
        conn_type = conn.get("type", "").lower()
        if conn_type not in SUPPORTED_TYPES:
            raise ValueError(
                f"Unsupported connection type: '{conn_type}'. "
                f"Supported: {sorted(SUPPORTED_TYPES)}"
            )

        now = datetime.now(timezone.utc).isoformat()
        all_conns = self._load_all()

        if not conn.get("id"):
            conn["id"] = str(uuid.uuid4())
            conn["created_at"] = now

        conn["updated_at"] = now
        # Strip any accidentally-included password field before persisting
        conn_to_save = {k: v for k, v in conn.items() if k not in ("password", "secret")}
        all_conns[conn["id"]] = conn_to_save
        self._save_all(all_conns)

        if password:
            self._store_secret(conn["id"], password)

        return conn["id"]

    def delete_connection(self, conn_id: str) -> None:
        """Remove connection metadata and its stored credential."""
        all_conns = self._load_all()
        all_conns.pop(conn_id, None)
        self._save_all(all_conns)
        self._delete_secret(conn_id)

    def get_driver(self, conn_id: str) -> BaseDriver:
        """Factory — returns the appropriate driver with credentials injected."""
        conn = self.get_connection(conn_id)
        if not conn:
            raise ValueError(f"Connection '{conn_id}' not found.")

        password = self._get_secret(conn_id)
        conn_type = conn.get("type", "").lower()

        if conn_type == "duckdb":
            from .drivers.duckdb_driver import DuckDBDriver
            return DuckDBDriver(file_path=conn.get("database") or ":memory:")

        if conn_type == "sqlite":
            from .drivers.sqlite_driver import SQLiteDriver
            return SQLiteDriver(file_path=conn.get("database") or ":memory:")

        if conn_type in ("postgresql", "snowflake"):
            from .drivers.sqlalchemy_driver import SQLAlchemyDriver
            return SQLAlchemyDriver(conn=conn, password=password)

        raise ValueError(f"No driver registered for connection type '{conn_type}'.")

    def test_connection(self, conn_id: str) -> Dict[str, Any]:
        """Tests connectivity. Returns {"success": bool, "error": str | None}."""
        try:
            driver = self.get_driver(conn_id)
            ok = driver.test()
            return {"success": ok, "error": None}
        except Exception as exc:
            return {"success": False, "error": str(exc)}
