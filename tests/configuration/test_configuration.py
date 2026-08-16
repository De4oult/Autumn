import os
import unittest

from tests.support import reset_framework_state

from autumn.configuration import Configuration, source, Maple, Theme
from autumn.core.configuration.builtin import (
    ApplicationConfiguration,
    CORSConfiguration,
    LocalizationConfiguration,
    WebUIConfiguration,
    WebsocketConfiguration
)
from autumn.core.configuration.configuration import get_registered_configs
from autumn.core.environment import Environment


class ConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def tearDown(self) -> None:
        for key in ('AUTUMN_FEATURE_ENABLED', 'AUTUMN_SERVER_PORT'):
            os.environ.pop(key, None)

    def test_builtin_configurations_are_registered_by_default(self) -> None:
        configs = get_registered_configs()

        self.assertIn(CORSConfiguration, configs)
        self.assertIn(ApplicationConfiguration, configs)
        self.assertIn(LocalizationConfiguration, configs)
        self.assertIn(WebsocketConfiguration, configs)
        self.assertIn(WebUIConfiguration, configs)

    def test_custom_cors_configuration_overrides_builtin_registration(self) -> None:
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']

        configs = get_registered_configs([CustomCORSConfiguration])

        self.assertIn(CustomCORSConfiguration, configs)
        self.assertNotIn(CORSConfiguration, configs)

    def test_environment_source_builds_configuration_values(self) -> None:
        os.environ['AUTUMN_FEATURE_ENABLED'] = 'true'
        os.environ['AUTUMN_SERVER_PORT'] = '9001'

        @source.env(prefix = 'AUTUMN_')
        class TestConfiguration(Configuration):
            feature_enabled: Maple['feature.enabled', bool]
            server_port: Maple['server.port', int]

        configuration = TestConfiguration.build()

        self.assertTrue(configuration.feature_enabled)
        self.assertEqual(configuration.server_port, 9001)

    def test_configuration_build_is_callable_from_class(self) -> None:
        class TestConfiguration(Configuration):
            enabled: bool = True

        configuration = TestConfiguration.build()

        self.assertIsInstance(configuration, TestConfiguration)
        self.assertTrue(configuration.enabled)

    def test_configuration_public_exports_support_wildcard_import(self) -> None:
        namespace: dict[str, object] = {}

        exec('from autumn.configuration import *', namespace)

        self.assertIn('Configuration', namespace)
        self.assertIn('source', namespace)
        self.assertIn('Maple', namespace)
        self.assertIn('Theme', namespace)
        self.assertIn('LocalizationConfiguration', namespace)
        self.assertIn('WebUIConfiguration', namespace)

    def test_configuration_casts_tuple_of_environments(self) -> None:
        class TestConfiguration(Configuration):
            allowed_on: Maple['allowed.on', tuple[Environment, ...]]

        TestConfiguration.__config_sources__ = [
            type(
                'InlineSource',
                (),
                {
                    'name': 'inline',
                    'get': lambda self, path: ['development', 'PRODUCTION']
                }
            )()
        ]

        configuration = TestConfiguration.build()

        self.assertEqual(
            configuration.allowed_on,
            (Environment.DEVELOPMENT, Environment.PRODUCTION)
        )

    def test_application_configuration_defaults_to_local_environment(self) -> None:
        configuration = ApplicationConfiguration.build()

        self.assertEqual(configuration.environment, Environment.LOCAL)

    def test_configuration_casts_theme_enum(self) -> None:
        class TestConfiguration(Configuration):
            default_theme: Maple['default.theme', Theme]

        TestConfiguration.__config_sources__ = [
            type(
                'InlineSource',
                (),
                {
                    'name': 'inline',
                    'get': lambda self, path: 'LIGHT'
                }
            )()
        ]

        configuration = TestConfiguration.build()

        self.assertEqual(configuration.default_theme, Theme.LIGHT)
