"""
Tests for Template Library API routes.
"""
import json
import os
import pytest
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


class TestListTemplates:
    """GET /api/templates"""

    def test_returns_200(self, client):
        res = client.get("/api/templates")
        assert res.status_code == 200

    def test_returns_templates_key(self, client):
        data = json.loads(client.get("/api/templates").data)
        assert "templates" in data

    def test_templates_is_list(self, client):
        data = json.loads(client.get("/api/templates").data)
        assert isinstance(data["templates"], list)

    def test_curated_templates_present(self, client):
        data = json.loads(client.get("/api/templates").data)
        tpl_names = [t["name"] for t in data["templates"]]
        assert len(tpl_names) > 0, "Expected at least one curated template"

    def test_template_has_required_fields(self, client):
        data = json.loads(client.get("/api/templates").data)
        required = {"id", "file", "name", "description", "category", "tags",
                    "difficulty", "node_count", "nodes_preview", "is_user"}
        for tpl in data["templates"]:
            for field in required:
                assert field in tpl, f"Template missing field: {field}"

    def test_template_is_user_false_for_curated(self, client):
        data = json.loads(client.get("/api/templates").data)
        curated = [t for t in data["templates"] if not t["is_user"]]
        assert len(curated) > 0
        for t in curated:
            assert t["is_user"] is False


class TestGetTemplate:
    """GET /api/templates/<filename>"""

    def _get_first_template_file(self, client):
        data = json.loads(client.get("/api/templates").data)
        templates = data.get("templates", [])
        if not templates:
            pytest.skip("No templates available")
        return templates[0]["file"]

    def test_load_curated_template_200(self, client):
        fname = self._get_first_template_file(client)
        res = client.get(f"/api/templates/{fname}")
        assert res.status_code == 200

    def test_load_curated_template_has_nodes(self, client):
        fname = self._get_first_template_file(client)
        data = json.loads(client.get(f"/api/templates/{fname}").data)
        assert "nodes" in data
        assert len(data["nodes"]) > 0

    def test_load_nonexistent_template_404(self, client):
        res = client.get("/api/templates/definitely_does_not_exist_xyz.json")
        assert res.status_code == 404

    def test_path_traversal_blocked(self, client):
        res = client.get("/api/templates/../../../etc/passwd")
        assert res.status_code in (400, 403, 404)


class TestSaveTemplate:
    """POST /api/templates/save"""

    def _make_workflow(self):
        return {
            "nodes": [
                {"id": "n1", "type": "input_data", "name": "Test Input",
                 "x": 100, "y": 100, "config": {}}
            ],
            "connections": [],
            "containers": [],
            "comments": []
        }

    def test_save_valid_template_201(self, client):
        payload = {
            "name": "Test Template for Unit Tests",
            "description": "A template created by pytest",
            "category": "general",
            "tags": ["test"],
            "workflow": self._make_workflow()
        }
        res = client.post("/api/templates/save",
                          data=json.dumps(payload),
                          content_type="application/json")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["success"] is True
        assert "file" in data

        # Clean up
        from backend.app import WORKFLOW_TEMPLATES_USER_DIR
        dest = os.path.join(WORKFLOW_TEMPLATES_USER_DIR, data["file"])
        if os.path.exists(dest):
            os.remove(dest)

    def test_save_missing_name_400(self, client):
        payload = {"name": "", "workflow": self._make_workflow()}
        res = client.post("/api/templates/save",
                          data=json.dumps(payload),
                          content_type="application/json")
        assert res.status_code == 400

    def test_save_empty_workflow_400(self, client):
        payload = {"name": "Empty WF", "workflow": {"nodes": []}}
        res = client.post("/api/templates/save",
                          data=json.dumps(payload),
                          content_type="application/json")
        assert res.status_code == 400


class TestDeleteTemplate:
    """DELETE /api/templates/<filename>"""

    def test_delete_nonexistent_404(self, client):
        res = client.delete("/api/templates/no_such_file_xyz.json")
        assert res.status_code == 404

    def test_delete_curated_not_in_user_dir_404(self, client):
        # Curated templates live in templates/ not templates/user/ — delete should 404
        data = json.loads(client.get("/api/templates").data)
        curated = [t for t in data["templates"] if not t["is_user"]]
        if not curated:
            pytest.skip("No curated templates")
        res = client.delete(f"/api/templates/{curated[0]['file']}")
        assert res.status_code == 404
