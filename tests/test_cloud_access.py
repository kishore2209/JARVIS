import os
import sys
import unittest
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['JARVIS_WEB_PASSWORD'] = 'test-only-password-not-for-production'
from fastapi.testclient import TestClient
assets = tempfile.TemporaryDirectory()
Path(assets.name, 'index.html').write_text('<html>JARVIS test</html>')
os.environ['JARVIS_FRONTEND_DIR'] = assets.name
from cloud_app import app

class CloudAccessTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.auth = ('jarvis', os.environ['JARVIS_WEB_PASSWORD'])
    def test_health_public(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
    def test_private_routes_require_login(self):
        for path in ('/', '/docs', '/api/v1/memory', '/api/v1/diagnostics'):
            self.assertEqual(self.client.get(path).status_code, 401)
    def test_bad_password(self):
        self.assertEqual(self.client.get('/', auth=('jarvis', 'wrong')).status_code, 401)
    def test_owner_can_open_interface(self):
        self.assertEqual(self.client.get('/', auth=self.auth).status_code, 200)
    def test_cross_origin_writes_blocked(self):
        result = self.client.post('/api/v1/chat', auth=self.auth, headers={'Origin':'https://evil.example'}, json={'text':'hello'})
        self.assertEqual(result.status_code, 403)
    def test_invalid_auth(self):
        self.assertEqual(self.client.get('/', headers={'Authorization':'Basic invalid'}).status_code, 401)

if __name__ == '__main__': unittest.main()
