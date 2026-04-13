import unittest

from tests.support import reset_framework_state

from autumn.core.routing.router import Route


class RoutePathParameterTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_route_matches_integer_parameter(self) -> None:
        route = Route('GET', '/users/{id:int}', lambda: None)

        _, params = route.match('GET', '/users/123')

        self.assertEqual(params['id'], 123)

    def test_route_rejects_invalid_integer_parameter(self) -> None:
        route = Route('GET', '/users/{id:int}', lambda: None)

        result = route.match('GET', '/users/abc')

        self.assertIsNone(result)

    def test_path_parameter_must_be_last_segment(self) -> None:
        with self.assertRaises(ValueError):
            Route('GET', '/files/{file:path}/tail', lambda: None)
