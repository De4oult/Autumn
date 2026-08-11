import unittest

from autumn.core.routing.router import Router


class RouteScalingTests(unittest.TestCase):
    def test_dynamic_prefix_index_selects_one_candidate_among_many_routes(self) -> None:
        router = Router()

        for index in range(1000):
            router.add_route('GET', f'/shared/{index}/{{id:int}}', lambda: None)

        calls = {'count': 0}
        for route in router.routes:
            original_match = route.match

            def tracked_match(method: str, path: str, match = original_match):
                calls['count'] += 1
                return match(method, path)

            route.match = tracked_match
        result = router.match('GET', '/shared/999/42')

        self.assertIsNotNone(result)
        self.assertEqual(result.parameters, {'id': 42})
        self.assertEqual(calls['count'], 1)
