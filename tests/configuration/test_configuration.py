import os
import unittest

from tests.support import reset_framework_state

from autumn.configuration import Configuration, source, Maple
from autumn.core.configuration.builtin import (
    ApplicationConfiguration,
    CORSConfiguration,
    WebsocketConfiguration
)
from autumn.core.configuration.configuration import get_registered_configs


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
        self.assertIn(WebsocketConfiguration, configs)

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
