"""
Unit tests for the /api/file-schema endpoint and design-time schema inspection.
"""
import io
import os
import pytest
from backend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_file_schema_missing_file_param(client):
    """Calling /api/file-schema without 'file' query parameter should return 400."""
    res = client.get("/api/file-schema")
    assert res.status_code == 400
    data = res.get_json()
    assert data["success"] is False
    assert "required" in data["error"].lower()


def test_file_schema_nonexistent_file(client):
    """Calling /api/file-schema with a nonexistent file should return 404."""
    res = client.get("/api/file-schema?file=nonexistent_dataset_99999.csv")
    assert res.status_code == 404
    data = res.get_json()
    assert data["success"] is False
    assert "not found" in data["error"].lower()


def test_file_schema_path_traversal_forbidden(client):
    """Path traversal outside allowed workspace should return 403 or 404."""
    res = client.get("/api/file-schema?file=../../../../Windows/System32/drivers/etc/hosts")
    assert res.status_code in [403, 404]
    data = res.get_json()
    assert data["success"] is False


def test_file_schema_csv(client):
    """Inspect schema for a bundled CSV dataset."""
    res = client.get("/api/file-schema?file=sales_orders.csv")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "OrderID" in data["columns"]
    assert "CustomerID" in data["columns"]
    assert "CustomerName" in data["columns"]
    assert "Discount" in data["columns"]
    assert len(data["column_meta"]) == len(data["columns"])

    # Check column metadata shape
    order_id_meta = next(m for m in data["column_meta"] if m["name"] == "OrderID")
    assert "type" in order_id_meta
    assert "alteryx_type" in order_id_meta


def test_file_schema_excel(client):
    """Inspect schema for a bundled Excel dataset."""
    res = client.get("/api/file-schema?file=warehouse_inventory.xlsx")
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True
    assert "SKU" in data["columns"]
    assert "CompositeBatchCode" in data["columns"]
    assert "QtyOnHand" in data["columns"]
    assert len(data["column_meta"]) == len(data["columns"])


def test_upload_file_returns_column_meta(client):
    """Uploaded files should return column_meta in addition to columns."""
    csv_content = b"ProdID,ProdName,Price\n101,Widget,19.99\n102,Gadget,45.50\n"
    data = {
        'file': (io.BytesIO(csv_content), 'test_products.csv')
    }
    res = client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert res.status_code == 200
    res_data = res.get_json()
    assert res_data["success"] is True
    assert res_data["columns"] == ["ProdID", "ProdName", "Price"]
    assert "column_meta" in res_data
    assert len(res_data["column_meta"]) == 3
    col_names = [m["name"] for m in res_data["column_meta"]]
    assert col_names == ["ProdID", "ProdName", "Price"]
