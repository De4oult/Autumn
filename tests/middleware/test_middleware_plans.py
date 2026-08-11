import unittest

from autumn.core.middleware.manager import MiddlewareManager


class MiddlewarePlanTests(unittest.TestCase):
    def test_compile_reuses_plan_for_route_and_method(self) -> None:
        manager = MiddlewareManager()

        first = manager.compile('/users/{id:int}', 'GET')
        second = manager.compile('/users/{id:int}', 'GET')

        self.assertIs(first, second)
        self.assertTrue(first.is_empty)

    def test_registration_invalidates_compiled_plans(self) -> None:
        manager = MiddlewareManager()
        first = manager.compile('/users', 'GET')

        async def middleware(request, call):
            return await call(request)

        manager.before(middleware, path = '/users', method = 'GET')
        second = manager.compile('/users', 'GET')

        self.assertIsNot(first, second)
        self.assertFalse(second.is_empty)
