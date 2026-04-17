import unittest

from tests.support import asgi_request, reset_framework_state, run_async

from autumn.core.app import Autumn
from autumn.core.configuration.builtin import ApplicationConfiguration, CORSConfiguration
from autumn.core.configuration.configuration import Configuration
from autumn.core.documentation.dependencies import DependenciesDocumentationGenerator
from autumn.core.request.request import Request
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import JSONResponse, Response
from autumn.core.routing.decorators import get, post
from autumn.core.documentation.openapi import OpenAPIGenerator
from autumn.controller import middleware
from autumn.serialization import Private, Public, serializable
from autumn.request import query

from pydantic import BaseModel


class UserSchema(BaseModel):
    name: str
    age: int


@serializable
class SerializableUser:
    def __init__(self, name: str, age: int, password: str) -> None:
        self.id: Public[int] = 1
        self.name: Public[str] = name
        self.age: Public[int] = age
        self.password_hash: Private[str] = f'hash:{password}'


class AppIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_app_injects_body_and_serializes_pydantic_response(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
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

    def test_route_decorator_defaults_to_root_path(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
        class UserController:
            @get
            async def index(self) -> UserSchema:
                return UserSchema(name = 'Autumn', age = 2)

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['name'], 'Autumn')

    def test_app_serializes_plain_dict_response_automatically(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
        class UserController:
            @get('/')
            async def index(self) -> JSONResponse:
                return {
                    'id'   : 1,
                    'name' : 'Bertram Gilfoyle'
                }

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.assertEqual(response.json()['name'], 'Bertram Gilfoyle')

    def test_app_serializes_decorated_object_response_automatically(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
        class UserController:
            @get('/profile')
            async def profile(self) -> SerializableUser:
                return SerializableUser(name = 'Anton', age = 18, password = 'qwerty123!')

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users/profile'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['content-type'], 'application/json')
        self.assertEqual(response.json()['name'], 'Anton')
        self.assertEqual(response.json()['age'], 18)
        self.assertNotIn('password_hash', response.json())

    def test_query_decorator_injects_kwarg_and_updates_request_query(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
        class UserController:
            @get('/')
            @query.int('page', default = 10)
            async def search(self, request: Request, page: int) -> JSONResponse:
                return JSONResponse({
                    'page': page,
                    'request_page': request.query.page
                })

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users',
                query_string = 'page=5'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['page'], 5)
        self.assertEqual(response.json()['request_page'], 5)

        default_response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(default_response.status, 200)
        self.assertEqual(default_response.json()['page'], 10)
        self.assertEqual(default_response.json()['request_page'], 10)

    def test_app_errors_follow_accept_header(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/errors')
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

        @app.rest(prefix = '/users')
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
        app = Autumn()

        @app.config
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']
            allowed_methods = ['POST']
            allowed_headers = ['authorization']
            allow_credentials = True
            max_age = 123

        @app.rest(prefix = '/users')
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

        @app.rest(prefix = '/users')
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

    def test_openapi_uses_public_fields_for_serializable_response_schema(self) -> None:
        app = Autumn()

        @app.rest(prefix = '/users')
        class UserController:
            @get('/profile')
            async def profile(self) -> SerializableUser:
                return SerializableUser(name = 'Anton', age = 18, password = 'qwerty123!')

        schema = OpenAPIGenerator().generate(app)
        response_schema = schema['paths']['/users/profile']['get']['responses']['200']['content']['application/json']['schema']

        self.assertEqual(response_schema['properties']['id']['type'], 'integer')
        self.assertEqual(response_schema['properties']['name']['type'], 'string')
        self.assertEqual(response_schema['properties']['age']['type'], 'integer')
        self.assertNotIn('password_hash', response_schema['properties'])

    def test_application_metadata_is_backed_by_application_configuration(self) -> None:
        app = Autumn()

        @app.config
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            name = 'Autumn Test App'
            version = '1.2.3'
            description = 'Application metadata from configuration'

        self.assertEqual(app.name, 'Autumn Test App')
        self.assertEqual(app.version, '1.2.3')
        self.assertEqual(app.description, 'Application metadata from configuration')

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/documentation/openapi.json'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['info']['title'], 'Autumn Test App')
        self.assertEqual(response.json()['info']['version'], '1.2.3')
        self.assertEqual(response.json()['info']['description'], 'Application metadata from configuration')

    def test_app_scoped_root_decorators_register_runtime_objects(self) -> None:
        app = Autumn()

        @app.leaf
        async def provide_name() -> str:
            return 'Autumn'

        @app.service
        class GreetingService:
            def __init__(self, name: str):
                self.name = name

            def value(self) -> str:
                return self.name

        @app.rest(prefix = '/users')
        class UserController:
            def __init__(self, greetings: GreetingService):
                self.greetings = greetings

            @get
            async def index(self) -> UserSchema:
                return UserSchema(name = self.greetings.value(), age = 2)

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['name'], 'Autumn')

    def test_dependency_docs_hide_builtin_configurations(self) -> None:
        app = Autumn()

        @app.config
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']

        @app.config
        class ProjectConfiguration(Configuration):
            feature_enabled: bool = True

        docs = DependenciesDocumentationGenerator().generate(app)
        configuration_names = {item['name'] for item in docs['configurations']}

        self.assertIn('ProjectConfiguration', configuration_names)
        self.assertIn('CustomCORSConfiguration', configuration_names)
        self.assertNotIn('CORSConfiguration', configuration_names)
        self.assertNotIn('ApplicationConfiguration', configuration_names)
        self.assertNotIn('WebsocketConfiguration', configuration_names)

    def test_app_scoped_config_decorator_registers_configuration(self) -> None:
        app = Autumn()

        @app.config
        class ProjectConfiguration(Configuration):
            feature_enabled: bool = True

        configuration_names = {
            configuration.__name__
            for configuration in app.get_registered_configs()
        }

        self.assertIn('ProjectConfiguration', configuration_names)

    def test_controller_middlewares_run_only_for_own_controller(self) -> None:
        app = Autumn()
        events: list[str] = []

        @app.rest(prefix = '/users')
        class UserController:
            @middleware
            def controller_lifecycle(self, request: Request):
                events.append(f'around-before:{request.path}')
                response = yield
                response.headers['X-Controller-Around'] = 'enabled'
                events.append(f'around-after:{response.status}')

            @middleware.before
            def mark_request(self, request: Request) -> None:
                request.headers['x-controller-before'] = 'enabled'
                events.append('before')

            @middleware.after
            def mark_response(self, response: Response) -> None:
                response.headers['X-Controller-After'] = 'enabled'
                events.append(f'after:{response.status}')

            @get('/')
            async def index(self, request: Request) -> JSONResponse:
                events.append(f'handler:{request.headers["x-controller-before"]}')
                return JSONResponse({'ok': True})

        @app.rest(prefix = '/health')
        class HealthController:
            @get('/')
            async def index(self) -> dict:
                events.append('health-handler')
                return {'ok': True}

        users_response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(users_response.status, 200)
        self.assertEqual(users_response.headers['X-Controller-Around'], 'enabled')
        self.assertEqual(users_response.headers['X-Controller-After'], 'enabled')
        self.assertEqual(
            events,
            [
                'around-before:/users',
                'before',
                'handler:enabled',
                'after:200',
                'around-after:200'
            ]
        )

        events.clear()

        health_response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/health'
            )
        )

        self.assertEqual(health_response.status, 200)
        self.assertNotIn('X-Controller-Around', health_response.headers)
        self.assertNotIn('X-Controller-After', health_response.headers)
        self.assertEqual(events, ['health-handler'])
