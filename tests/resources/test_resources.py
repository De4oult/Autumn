import importlib.util
import unittest
from pathlib import Path

from tests.support import reset_framework_state

from autumn.resources import Resources, ResourceType


FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
RESOURCE_ROOT = FIXTURES / 'resources'


class ResourcesTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_resources_are_singletons_per_root(self) -> None:
        first = Resources(RESOURCE_ROOT)
        second = Resources(Path(RESOURCE_ROOT))

        self.assertIs(first, second)

    def test_resources_read_text_json_and_cache_data(self) -> None:
        resources = Resources(RESOURCE_ROOT)
        first = resources.read('settings.json', ResourceType.DATA)
        second = resources.read('settings.json', ResourceType.DATA)

        self.assertEqual(resources.read('hello.txt').strip(), 'Hello Autumn')
        self.assertEqual(first, {'enabled': True})
        self.assertIs(first, second)

    def test_resources_read_bytes(self) -> None:
        resources = Resources(RESOURCE_ROOT)

        self.assertEqual(resources.read('hello.txt', ResourceType.BYTES).strip(), b'Hello Autumn')

    @unittest.skipIf(importlib.util.find_spec('yaml') is None, 'PyYAML is not installed')
    def test_resources_read_yaml_data(self) -> None:
        resources = Resources(RESOURCE_ROOT)

        self.assertEqual(resources.read('ru.yaml', ResourceType.DATA), {'hello': {'message': 'Привет'}})

    def test_resources_reject_path_escape(self) -> None:
        resources = Resources(RESOURCE_ROOT)

        with self.assertRaises(PermissionError):
            resources.resolve('../outside-root.txt', must_exist = False)

    def test_resources_build_rooted_response(self) -> None:
        response = Resources(RESOURCE_ROOT).response('hello.txt')

        self.assertEqual(response.body.strip(), b'Hello Autumn')

    def test_resources_find_data_file_by_stem(self) -> None:
        self.assertEqual(Resources(RESOURCE_ROOT).find('settings'), RESOURCE_ROOT / 'settings.json')
