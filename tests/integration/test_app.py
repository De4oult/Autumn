import unittest
import contextlib
import io
from pathlib import Path

from tests.support import asgi_lifespan, asgi_request, reset_framework_state, run_async

from autumn.core.app import Autumn
from autumn.core.configuration.builtin import ApplicationConfiguration, CORSConfiguration, WebUIConfiguration
from autumn.core.configuration.configuration import Configuration
from autumn.core.environment import Environment, Theme
from autumn.core.environment import only
from autumn.core.exception.exception import DependencyInjectionError
from autumn.core.documentation.dependencies import DependenciesDocumentationGenerator
from autumn.core.request.request import Request
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import JSONResponse, Response
from autumn.core.routing.decorators import REST, get, post
from autumn.core.documentation.openapi import OpenAPIGenerator
from autumn import middleware
from autumn.serialization import Private, Public, serializable
from autumn.request import query
from autumn.core.dependencies.decorators import leaf, service
from autumn.core.lifecycle.decorators import shutdown, startup

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

    def test_route_decorator_defaults_to_root_path(self) -> None:
        app = Autumn()

        @REST(prefix = '/users')
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

        @REST(prefix = '/users')
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

        @REST(prefix = '/users')
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

        @REST(prefix = '/users')
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

    def test_app_adds_request_id_header_to_successful_responses(self) -> None:
        app = Autumn()

        @REST(prefix = '/trace')
        class TraceController:
            @get('/')
            async def index(self) -> dict:
                return {'ok': True}

        response = run_async(
            asgi_request(
                app,
                path = '/trace',
                headers = {'x-request-id': 'req-123'}
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['X-Request-ID'], 'req-123')

    def test_app_adds_request_id_and_meta_to_http_exception_response(self) -> None:
        app = Autumn()

        @REST(prefix = '/trace')
        class TraceController:
            @get('/failure')
            async def failure(self):
                raise HTTPException(
                    status = 409,
                    details = 'conflict',
                    meta = {'reason': 'duplicate'}
                )

        response = run_async(
            asgi_request(
                app,
                path = '/trace/failure',
                headers = {'x-request-id': 'req-456'}
            )
        )

        self.assertEqual(response.status, 409)
        self.assertEqual(response.headers['X-Request-ID'], 'req-456')
        self.assertEqual(response.json()['request_id'], 'req-456')
        self.assertEqual(response.json()['meta'], {'reason': 'duplicate'})

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
        app = Autumn()
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']
            allowed_methods = ['POST']
            allowed_headers = ['authorization']
            allow_credentials = True
            max_age = 123

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

    def test_openapi_uses_public_fields_for_serializable_response_schema(self) -> None:
        app = Autumn()

        @REST(prefix = '/users')
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

    def test_openapi_infers_responses_from_static_returns_and_http_exceptions(self) -> None:
        app = Autumn()

        class CreatedUser(BaseModel):
            id: int
            name: str

        @REST(prefix = '/users')
        class UserController:
            @post('/create')
            async def create(self):
                return JSONResponse({
                    'id'   : 1,
                    'user' : CreatedUser(id = 1, name = 'Autumn'),
                    'meta' : self
                }, status = 201)

            @get('/maybe')
            async def maybe(self):
                if False:
                    raise HTTPException(status = 404, details = 'missing')

                return CreatedUser(id = 1, name = 'Autumn')

        schema = OpenAPIGenerator().generate(app)
        created_response = schema['paths']['/users/create']['post']['responses']['201']['content']['application/json']['schema']
        maybe_responses = schema['paths']['/users/maybe']['get']['responses']

        self.assertEqual(created_response['properties']['id']['type'], 'integer')
        self.assertEqual(created_response['properties']['user']['properties']['name']['type'], 'string')
        self.assertEqual(created_response['properties']['meta'], {})
        self.assertEqual(maybe_responses['200']['content']['application/json']['schema']['properties']['id']['type'], 'integer')
        self.assertEqual(maybe_responses['404']['content']['application/json']['schema']['properties']['details']['type'], 'string')

    def test_openapi_infers_custom_response_subclasses(self) -> None:
        app = Autumn()

        class CustomResponse(Response):
            def __init__(self, message: str, status: int = 202):
                super().__init__(
                    body         = message,
                    status       = status,
                    content_type = 'text/custom-response; charset=utf-8'
                )

        @REST(prefix = '/custom')
        class CustomController:
            @get('/response')
            async def response(self) -> CustomResponse:
                return CustomResponse('accepted')

        schema = OpenAPIGenerator().generate(app)
        responses = schema['paths']['/custom/response']['get']['responses']
        response = responses['202']['content']['text/custom-response; charset=utf-8']

        self.assertNotIn('200', responses)
        self.assertEqual(response['schema']['type'], 'string')

    def test_application_metadata_is_backed_by_application_configuration(self) -> None:
        app = Autumn()
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

    def test_webui_configuration_controls_visibility_and_markup(self) -> None:
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/autumn'
            )
        )

        self.assertEqual(response.status, 404)

        class CustomWebUIConfiguration(WebUIConfiguration):
            allowed_on = (Environment.PRODUCTION,)
            default_theme = Theme.LIGHT
            leaves_animation_enabled = False

        configured_app = Autumn()
        configured_response = run_async(
            asgi_request(
                configured_app,
                method = 'GET',
                path = '/autumn'
            )
        )

        self.assertEqual(configured_response.status, 200)
        self.assertIn('"defaultTheme":"light"', configured_response.text)
        self.assertIn('"leavesAnimationEnabled":false', configured_response.text)
        self.assertIn('"packageVersion":', configured_response.text)

    def test_only_excludes_controllers_from_routes_and_documentation(self) -> None:
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()

        @only(Environment.DEVELOPMENT)
        @REST(prefix = '/debug')
        class DebugController:
            @get('/ping')
            async def ping(self) -> dict:
                return {'ok': True}

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/debug/ping'
            )
        )
        schema = OpenAPIGenerator().generate(app)

        self.assertEqual(response.status, 404)
        self.assertNotIn('/debug/ping', schema['paths'])

    def test_only_rejects_active_dependency_chain_that_requires_disabled_provider(self) -> None:
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()

        @only(Environment.DEVELOPMENT)
        @service
        class MockGateway:
            pass

        @service
        class CheckoutService:
            def __init__(self, gateway: MockGateway):
                self.gateway = gateway

        @REST(prefix = '/checkout')
        class CheckoutController:
            def __init__(self, checkout: CheckoutService):
                self.checkout = checkout

            @get('/status')
            async def status(self) -> dict:
                return {'ok': True}

        with self.assertRaises(DependencyInjectionError) as raised:
            run_async(
                asgi_request(
                    app,
                    method = 'GET',
                    path = '/checkout/status'
                )
            )

        self.assertIn('MockGateway is only allowed on development', str(raised.exception))

    def test_only_union_dependency_selects_provider_for_current_environment(self) -> None:
        @only(Environment.DEVELOPMENT)
        @service
        class MockGateway:
            def name(self) -> str:
                return 'mock'

        @only(Environment.PRODUCTION)
        @service
        class LiveGateway:
            def name(self) -> str:
                return 'live'

        @service
        class CheckoutService:
            def __init__(self, gateway: MockGateway | LiveGateway):
                self.gateway = gateway

            def gateway_name(self) -> str:
                return self.gateway.name()

        @REST(prefix = '/checkout')
        class CheckoutController:
            def __init__(self, checkout: CheckoutService):
                self.checkout = checkout

            @get('/gateway')
            async def gateway(self) -> dict:
                return {'gateway': self.checkout.gateway_name()}

        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        production_app = Autumn()
        production_response = run_async(
            asgi_request(
                production_app,
                method = 'GET',
                path = '/checkout/gateway'
            )
        )

        self.assertEqual(production_response.status, 200)
        self.assertEqual(production_response.json(), {'gateway': 'live'})

    def test_only_union_dependency_supports_leaf_providers(self) -> None:
        class MockGateway:
            def name(self) -> str:
                return 'mock'

        class LiveGateway:
            def name(self) -> str:
                return 'live'

        @only(Environment.DEVELOPMENT)
        @leaf
        async def mock_gateway() -> MockGateway:
            return MockGateway()

        @only(Environment.PRODUCTION)
        @leaf
        async def live_gateway() -> LiveGateway:
            return LiveGateway()

        @service
        class CheckoutService:
            def __init__(self, gateway: MockGateway | LiveGateway):
                self.gateway = gateway

            def gateway_name(self) -> str:
                return self.gateway.name()

        @REST(prefix = '/checkout')
        class CheckoutController:
            def __init__(self, checkout: CheckoutService):
                self.checkout = checkout

            @get('/gateway')
            async def gateway(self) -> dict:
                return {'gateway': self.checkout.gateway_name()}

        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()
        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/checkout/gateway'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {'gateway': 'live'})

    def test_only_union_dependency_rejects_overlapping_environments(self) -> None:
        app = Autumn()

        @only(Environment.DEVELOPMENT)
        @service
        class FirstGateway:
            pass

        @only(Environment.DEVELOPMENT, Environment.LOCAL)
        @service
        class SecondGateway:
            pass

        @service
        class CheckoutService:
            def __init__(self, gateway: FirstGateway | SecondGateway):
                self.gateway = gateway

        @REST(prefix = '/checkout')
        class CheckoutController:
            def __init__(self, checkout: CheckoutService):
                self.checkout = checkout

            @get('/status')
            async def status(self) -> dict:
                return {'ok': True}

        with self.assertRaises(DependencyInjectionError) as raised:
            run_async(
                asgi_request(
                    app,
                    method = 'GET',
                    path = '/checkout/status'
                )
            )

        self.assertIn('overlapping @only environments', str(raised.exception))
        self.assertIn('development', str(raised.exception))

    def test_only_union_dependency_rejects_missing_active_environment(self) -> None:
        class ProjectApplicationConfiguration(ApplicationConfiguration):
            environment = Environment.PRODUCTION

        app = Autumn()

        @only(Environment.DEVELOPMENT)
        @service
        class MockGateway:
            pass

        @only(Environment.LOCAL)
        @service
        class LocalGateway:
            pass

        @service
        class CheckoutService:
            def __init__(self, gateway: MockGateway | LocalGateway):
                self.gateway = gateway

        @REST(prefix = '/checkout')
        class CheckoutController:
            def __init__(self, checkout: CheckoutService):
                self.checkout = checkout

            @get('/status')
            async def status(self) -> dict:
                return {'ok': True}

        with self.assertRaises(DependencyInjectionError) as raised:
            run_async(
                asgi_request(
                    app,
                    method = 'GET',
                    path = '/checkout/status'
                )
            )

        self.assertIn('no union dependency is active for production', str(raised.exception))

    def test_only_warns_when_other_environment_dependency_graph_would_fail(self) -> None:
        app = Autumn()

        @only(Environment.LOCAL)
        @service
        class LocalGateway:
            pass

        @only(Environment.PRODUCTION)
        @service
        class ProductionCheckoutService:
            def __init__(self, gateway: LocalGateway):
                self.gateway = gateway

        @REST(prefix = '/health')
        class HealthController:
            @get('/')
            async def index(self) -> dict:
                return {'ok': True}

        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            response = run_async(
                asgi_request(
                    app,
                    method = 'GET',
                    path = '/health'
                )
            )

        self.assertEqual(response.status, 200)
        self.assertIn('@only dependency graph warning for production', output.getvalue())
        self.assertIn('ProductionCheckoutService.__init__ requires', output.getvalue())
        self.assertIn('LocalGateway', output.getvalue())

    def test_independent_decorators_register_runtime_objects(self) -> None:
        app = Autumn()

        @leaf
        async def provide_name() -> str:
            return 'Autumn'

        @service
        class GreetingService:
            def __init__(self, name: str):
                self.name = name

            def value(self) -> str:
                return self.name

        @REST(prefix = '/users')
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

    def test_independent_lifecycle_and_global_middlewares_register(self) -> None:
        app = Autumn()
        events: list[str] = []

        @startup
        async def on_startup() -> None:
            events.append('startup')

        @shutdown
        async def on_shutdown() -> None:
            events.append('shutdown')

        @middleware(path = ('/users', '/unused'), method = ['GET'])
        async def trace_request(request: Request, call):
            events.append('around-before')
            response = await call(request)
            events.append('around-after')
            return response

        @middleware.before(path = ['/users', '/unused'], method = ('GET',))
        async def mark_request(request: Request, call):
            request.headers['x-global-before'] = 'enabled'
            events.append('before')
            return await call(request)

        @middleware.after(path = ['/users', '/unused'], method = ('GET',))
        async def mark_response(request: Request, response: Response):
            response.headers['X-Global-After'] = 'enabled'
            events.append(f'after:{response.status}')
            return response

        @REST(prefix = '/users')
        class UserController:
            @get
            async def index(self, request: Request) -> dict:
                events.append(f'handler:{request.headers["x-global-before"]}')
                return {'ok': True}

        lifespan_messages = run_async(
            asgi_lifespan(
                app,
                'lifespan.startup',
                'lifespan.shutdown'
            )
        )
        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users'
            )
        )

        self.assertEqual(
            [message['type'] for message in lifespan_messages],
            ['lifespan.startup.complete', 'lifespan.shutdown.complete']
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['X-Global-After'], 'enabled')
        self.assertEqual(events, ['startup', 'shutdown', 'around-before', 'before', 'handler:enabled', 'around-after', 'after:200'])

    def test_dependency_docs_hide_builtin_configurations(self) -> None:
        app = Autumn()
        class CustomCORSConfiguration(CORSConfiguration):
            allowed_origins = ['https://example.com']
        class ProjectConfiguration(Configuration):
            feature_enabled: bool = True

        docs = DependenciesDocumentationGenerator().generate(app)
        configuration_names = {item['name'] for item in docs['configurations']}

        self.assertIn('ProjectConfiguration', configuration_names)
        self.assertIn('CustomCORSConfiguration', configuration_names)
        self.assertNotIn('CORSConfiguration', configuration_names)
        self.assertNotIn('ApplicationConfiguration', configuration_names)
        self.assertNotIn('WebsocketConfiguration', configuration_names)

    def test_independent_config_class_registers_configuration(self) -> None:
        app = Autumn()
        class ProjectConfiguration(Configuration):
            feature_enabled: bool = True

        configuration_names = {
            configuration.__name__
            for configuration in app.get_registered_configs()
        }

        self.assertIn('ProjectConfiguration', configuration_names)

    def test_app_discovers_independent_decorators_from_root_path(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'fixtures' / 'discovery_project'
        app = Autumn(
            root_path = root,
            discover = ('controllers.hello',)
        )

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/hello'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.json()['message'], 'Hello from discovery')

    def test_controller_middlewares_run_only_for_own_controller(self) -> None:
        app = Autumn()
        events: list[str] = []

        @REST(prefix = '/users')
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

        @REST(prefix = '/health')
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

    def test_controller_middleware_receives_normalized_response(self) -> None:
        app = Autumn()

        @serializable
        class User:
            def __init__(self, name: str) -> None:
                self.name: Public[str] = name

        @REST(prefix = '/users')
        class UserController:
            @middleware
            def trace(self):
                response = yield
                response.headers['X-Trace'] = '1'

            @get('/{name:str}')
            async def get_user(self, name: str) -> User:
                return User(name)

        response = run_async(
            asgi_request(
                app,
                method = 'GET',
                path = '/users/test'
            )
        )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers['X-Trace'], '1')
        self.assertEqual(response.json(), {'name': 'test'})

