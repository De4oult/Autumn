import unittest
import contextlib
import io

from autumn.core.app import Autumn
from autumn.core.configuration.builtin import ApplicationConfiguration
from autumn.core.environment import Environment
from autumn.core.response.exception import HTTPException
from autumn.core.routing.decorators import REST, get
from tests.support import asgi_request, reset_framework_state, run_async


class ErrorDisclosureTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_production_does_not_disclose_unhandled_exception_details(self) -> None:
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()

        @REST()
        class FailureController:
            @get('/failure')
            async def failure(self):
                raise RuntimeError('database password is secret')

        response = run_async(asgi_request(app, path = '/failure'))

        self.assertEqual(response.status, 500)
        self.assertEqual(response.json()['details'], 'Internal Server Error')
        self.assertNotIn('secret', response.text)

    def test_unhandled_exception_prints_traceback_to_console(self) -> None:
        app = Autumn()

        @REST()
        class FailureController:
            @get('/failure')
            async def failure(self):
                raise RuntimeError('broken branch')

        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            response = run_async(asgi_request(app, path = '/failure'))

        self.assertEqual(response.status, 500)
        self.assertIn('Traceback (most recent call last)', output.getvalue())
        self.assertIn('RuntimeError: broken branch', output.getvalue())

    def test_http_exception_does_not_print_traceback_to_console(self) -> None:
        app = Autumn()

        @REST()
        class FailureController:
            @get('/failure')
            async def failure(self):
                raise HTTPException(status = 400, code = 'DOMAIN_ERROR', details = 'Expected failure')

        output = io.StringIO()

        with contextlib.redirect_stderr(output):
            response = run_async(asgi_request(app, path = '/failure'))

        self.assertEqual(response.status, 400)
        self.assertEqual(response.json()['code'], 'DOMAIN_ERROR')
        self.assertEqual(output.getvalue(), '')
