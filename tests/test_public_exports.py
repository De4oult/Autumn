import unittest


class PublicExportTests(unittest.TestCase):
    def test_public_modules_support_wildcard_imports(self) -> None:
        expected_exports = {
            'autumn': {
                'Autumn',
                'Environment',
                'Theme',
                'only',
                'Request',
                'leaf',
                'middleware',
                'service',
                'shutdown',
                'startup',
                'Public',
                'Private',
                'serializable'
            },
            'autumn.configuration': {'Configuration', 'source', 'Maple', 'Theme', 'WebUIConfiguration'},
            'autumn.controller': {'REST', 'get', 'post', 'put', 'patch', 'delete'},
            'autumn.documentation': {'tag', 'summary', 'description'},
            'autumn.lifecycle': {'middleware', 'shutdown', 'startup'},
            'autumn.request': {'Request', 'query'},
            'autumn.response': {'Response', 'JSONResponse', 'HTTPException'},
            'autumn.serialization': {'Public', 'Private', 'serializable'},
            'autumn.websocket': {'websocket', 'WebSocketDisconnect'},
        }

        for module, names in expected_exports.items():
            with self.subTest(module = module):
                namespace: dict[str, object] = {}

                exec(f'from {module} import *', namespace)

                for name in names:
                    self.assertIn(name, namespace)
