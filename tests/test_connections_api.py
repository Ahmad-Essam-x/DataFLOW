import os
import sqlite3
import tempfile
import unittest
from backend.app import app
import backend.extensions as ext
from backend.engine.nodes.io import InputDataNode


class TestConnectionsAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db_path = os.path.join(cls.temp_dir, "test_analytics.db")

        # Create a sample SQLite database with a table and records
        conn = sqlite3.connect(cls.test_db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price REAL)")
        cur.executemany("INSERT INTO products (name, price) VALUES (?, ?)", [
            ("Laptop Pro", 1299.99),
            ("Wireless Mouse", 29.50),
            ("Mechanical Keyboard", 89.00),
            ("USB-C Monitor", 349.00),
        ])
        conn.commit()
        conn.close()

    def test_01_draft_connection_test(self):
        """Test draft connection testing before saving."""
        res = self.client.post("/api/connections/test", json={
            "name": "Draft SQLite",
            "type": "sqlite",
            "database": self.test_db_path
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertGreaterEqual(data.get("table_count", 0), 1)

    def test_02_draft_connection_invalid_type(self):
        """Test error handling on invalid connection type."""
        res = self.client.post("/api/connections/test", json={
            "name": "Bad Connection",
            "type": "unsupported_db",
            "database": "some_file.db"
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data.get("success"))

    def test_03_create_and_list_connections(self):
        """Test creating, listing, and getting connections."""
        create_res = self.client.post("/api/connections", json={
            "name": "Inventory SQLite DB",
            "type": "sqlite",
            "database": self.test_db_path
        })
        self.assertEqual(create_res.status_code, 201)
        created = create_res.get_json()["connection"]
        conn_id = created["id"]
        self.assertTrue(conn_id)

        # List connections
        list_res = self.client.get("/api/connections")
        self.assertEqual(list_res.status_code, 200)
        conns = list_res.get_json().get("connections", [])
        self.assertTrue(any(c["id"] == conn_id for c in conns))

        # Test saved connection
        test_res = self.client.post(f"/api/connections/{conn_id}/test")
        self.assertEqual(test_res.status_code, 200)
        self.assertTrue(test_res.get_json().get("success"))

        # List tables in connection
        tables_res = self.client.get(f"/api/connections/{conn_id}/tables")
        self.assertEqual(tables_res.status_code, 200)
        tables = tables_res.get_json().get("tables", [])
        self.assertIn("products", tables)

        # Preview table query
        preview_res = self.client.post(f"/api/connections/{conn_id}/preview", json={
            "table": "products",
            "limit": 10
        })
        self.assertEqual(preview_res.status_code, 200)
        prev_data = preview_res.get_json()
        self.assertTrue(prev_data.get("success"))
        self.assertEqual(prev_data.get("row_count"), 4)
        self.assertIn("Laptop Pro", [r["name"] for r in prev_data.get("rows", [])])

        # Preview custom SQL query
        sql_res = self.client.post(f"/api/connections/{conn_id}/preview", json={
            "sql": "SELECT name, price FROM products WHERE price > 100",
            "limit": 10
        })
        self.assertEqual(sql_res.status_code, 200)
        sql_data = sql_res.get_json()
        self.assertEqual(sql_data.get("row_count"), 2)

        # Test InputDataNode execution with this connection
        node = InputDataNode(node_id="n1", config={
            "source_type": "database",
            "connection_id": conn_id,
            "table": "products"
        })
        out = node.execute(inputs={}, context={})
        df = out.get("O")
        self.assertIsNotNone(df)
        self.assertEqual(len(df), 4)
        self.assertIn("price", df.columns)

        # Delete connection
        del_res = self.client.delete(f"/api/connections/{conn_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json().get("success"))


if __name__ == "__main__":
    unittest.main()
