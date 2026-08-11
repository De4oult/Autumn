import unittest
from pathlib import Path

from autumn.core.app import Autumn
from tests.support import asgi_request, reset_framework_state, run_async


class ExplicitDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_boolean_discovery_is_rejected(self) -> None:
        with self.assertRaisesRegex(TypeError, 'explicit module names'):
            Autumn(discover = True)

        with self.assertRaisesRegex(TypeError, 'explicit module names'):
            Autumn(discover = False)

    def test_only_explicit_modules_are_discovered(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'fixtures' / 'discovery_project'
        app = Autumn(root_path = root, discover = ('controllers.hello',))

        response = run_async(asgi_request(app, path = '/hello'))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['message'], 'Hello from discovery')
