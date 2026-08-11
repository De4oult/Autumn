import unittest

from autumn.core.app import Autumn
from autumn.core.environment import Environment
from autumn.core.routing.decorators import REST, get
from tests.support import asgi_request, reset_framework_state, run_async


class ErrorDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_production_does_not_disclose_unhandled_exception_details(self) -> None:
        app = Autumn(environment = Environment.PRODUCTION)

        @REST()
        class FailureController:
            @get('/failure')
            async def failure(self):
                raise RuntimeError('database password is secret')

        response = run_async(asgi_request(app, path = '/failure'))

        self.assertEqual(response.status, 500)
        self.assertEqual(response.json()['details'], 'Internal Server Error')
        self.assertNotIn('secret', response.text)
