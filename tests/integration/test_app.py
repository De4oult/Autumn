import unittest

from tests.support import asgi_request, reset_framework_state, run_async

from autumn.core.app import Autumn
from autumn.core.configuration.builtin import CORSConfiguration
from autumn.core.request.request import Request
from autumn.core.response.exception import HTTPException
from autumn.core.routing.decorators import REST, get, post
from autumn.core.documentation.openapi import OpenAPIGenerator

from pydantic import BaseModel


class UserSchema(BaseModel):
    name: str
    age: int


class AppIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_app_injects_body_and_serializes_pydantic_response(self) -> None:
        app = Autumn()

        @REST(prefix = '/users')
        class UserController:
            @post('/')
            async def create(self, request: Request, user: UserSchema) -> UserSchema:
                return user

        response = run_async(
            asgi_request(
                app,
                method = 'POST',
                path = '/users',
                headers = {'content-type': 'application/json', 'accept': 'application/json'},
                body = b'{"name":"Autumn","age":2}'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.assertEqual(response.json()['name'], 'Autumn')

    def test_app_errors_follow_accept_header(self) -> None:
        app = Autumn()

        @REST(prefix = '/errors')
        class ErrorController:
            @get('/teapot')
            async def teapot(self):
                raise HTTPException(status = 418, details = 'short and stout')

        json_response = run_async(
            asgi_request(
                app,
                path = '/errors/teapot',
                headers = {'accept': 'application/json'}
            )
        )
        html_response = run_async(
            asgi_request(
                app,
                path = '/errors/teapot',
                headers = {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'}
            )
        )

        self.assertEqual(json_response.status, 418)
        self.assertEqual(json_response.headers['content-type'], 'application/json')
        self.assertEqual(json_response.json()['details'], 'short and stout')

        self.assertEqual(html_response.status, 418)
        self.assertTrue(html_response.headers['content-type'].startswith('text/html'))
        self.assertIn('short and stout', html_response.text)

    def test_default_cors_rejects_unknown_origin_preflight(self) -> None:
        app = Autumn()

        @REST(prefix = '/users')
        class UserController:
            @post('/test')
            async def create(self, request: Request, user: UserSchema) -> UserSchema:
                return user

        response = run_async(
            asgi_request(
                app,
                method = 'OPTIONS',
                path = '/users/test',
                headers = {
                    'origin'                         : 'https://example.com',
                    'access-control-request-method' : 'POST',
                    'access-control-request-headers': 'authorization'
                }
            )
        )

        self.assertEqual(response.status, 403)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.assertEqual(response.json()['status'], 403)

    def test_custom_cors_configuration_allows_preflight(self) -> None:
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']
            allowed_methods = ['POST']
            allowed_headers = ['authorization']
            allow_credentials = True
            max_age = 123

        app = Autumn()

        @REST(prefix = '/users')
        class UserController:
            @post('/test')
            async def create(self, request: Request, user: UserSchema) -> UserSchema:
                return user

        response = run_async(
            asgi_request(
                app,
                method = 'OPTIONS',
                path = '/users/test',
                headers = {
                    'origin'                         : 'https://example.com',
                    'access-control-request-method' : 'POST',
                    'access-control-request-headers': 'authorization'
                }
            )
        )

        self.assertEqual(response.status, 204)
        self.assertEqual(response.headers['Access-Control-Allow-Origin'], 'https://example.com')
        self.assertEqual(response.headers['Access-Control-Allow-Methods'], 'POST')
        self.assertEqual(response.headers['Access-Control-Allow-Headers'], 'authorization')
        self.assertEqual(response.headers['Access-Control-Max-Age'], '123')
        self.assertEqual(response.headers['Access-Control-Allow-Credentials'], 'true')

    def test_openapi_uses_signature_for_body_and_response_schemas(self) -> None:
        app = Autumn()

        @REST(prefix = '/users')
        class UserController:
            @post('/test')
            async def create(self, request: Request, user: UserSchema) -> UserSchema:
                return user

        schema = OpenAPIGenerator().generate(app)
        operation = schema['paths']['/users/test']['post']

        request_schema = operation['requestBody']['content']['application/json']['schema']
        response_schema = operation['responses']['200']['content']['application/json']['schema']

        self.assertEqual(request_schema['properties']['name']['type'], 'string')
        self.assertEqual(response_schema['properties']['age']['type'], 'integer')
