import json
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point settings file at a temp location before importing app
import backend.app as app_module
_orig_settings_file = app_module.USER_SETTINGS_FILE

class TestUserSettingsAPI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix='.json', delete=False)
        self.tmp.close()
        # Make sure the file doesn't exist (simulates fresh state)
        os.remove(self.tmp.name)
        app_module.USER_SETTINGS_FILE = self.tmp.name
        app_module.app.testing = True
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module.USER_SETTINGS_FILE = _orig_settings_file
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_get_settings_empty(self):
        """GET /api/user-settings returns {} when no file exists."""
        res = self.client.get('/api/user-settings')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {})

    def test_post_and_get_settings(self):
        """POST saves settings; GET returns them."""
        payload = {'theme': 'light', 'wire_probes_enabled': True, 'execution_timeout': 120}
        res = self.client.post('/api/user-settings',
                               data=json.dumps(payload),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json(), {'status': 'ok'})

        res2 = self.client.get('/api/user-settings')
        self.assertEqual(res2.status_code, 200)
        data = res2.get_json()
        self.assertEqual(data['theme'], 'light')
        self.assertEqual(data['execution_timeout'], 120)

    def test_post_invalid_json_returns_400(self):
        """POST with invalid JSON body returns 400."""
        res = self.client.post('/api/user-settings',
                               data='not json',
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_post_non_object_returns_400(self):
        """POST with a JSON array (non-object) returns 400."""
        res = self.client.post('/api/user-settings',
                               data=json.dumps([1, 2, 3]),
                               content_type='application/json')
        self.assertEqual(res.status_code, 400)

    def test_settings_persisted_to_file(self):
        """POST actually writes data to user_settings.json file."""
        payload = {'theme': 'high-contrast', 'grid_snap': 8}
        self.client.post('/api/user-settings',
                         data=json.dumps(payload),
                         content_type='application/json')
        with open(self.tmp.name, 'r') as f:
            on_disk = json.load(f)
        self.assertEqual(on_disk['theme'], 'high-contrast')
        self.assertEqual(on_disk['grid_snap'], 8)


if __name__ == '__main__':
    unittest.main()
