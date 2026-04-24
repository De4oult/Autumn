from autumn.core.websocket.websocket import WebSocket, WebSocketDisconnect
from autumn.core.configuration.builtin import ApplicationConfiguration, CORSConfiguration
from autumn.core.configuration.configuration import Configuration, get_registered_configs
from autumn.core.dependencies import registry as dependency_registry
from autumn.core.dependencies.container import Container, ExecutionContext
from autumn.core.serialization import value_supports_json_response
from autumn.core.middleware.manager import MiddlewareManager
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import JSONResponse, Response
from autumn.core.dependencies.scope import Scope
from autumn.core.request.request import Request
from autumn.core.routing.router import Router

from typing import Any, Callable, Optional
from pathlib import Path
from colorama import Fore
from enum import Enum

import importlib.util
import asyncio
import inspect
import types
import time
import sys

class Environment(str, Enum):
    LOCAL = 'local'
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'

class Autumn:
    def __init__(
        self,
        *,
        environment: Environment = Environment.DEVELOPMENT,
        discover: bool = True,
        root_path: Optional[str | Path] = None
    ):
        self.environment: Environment = environment
        caller_file = inspect.stack()[1].filename
        self.__entrypoint_path: Optional[Path] = Path(caller_file).resolve() if caller_file else None
        self.__root_path: Optional[Path] = Path(root_path).resolve() if root_path is not None else (
            self.__entrypoint_path.parent if self.__entrypoint_path is not None else None
        )
        self.__discover_enabled: bool = discover
        self.__discovery_completed: bool = False
        self.__discovery_package: str = f'_autumn_discovered_{id(self)}'

        self.router = Router()
        
        self.startup_hooks: list[Callable] = []
        self.shutdown_hooks: list[Callable] = []
        
        self.middleware = MiddlewareManager()
        self.container = Container()
        self.__application_configuration: Optional[ApplicationConfiguration] = None
        self.__cors_configuration: Optional[CORSConfiguration] = None
        self.__http_handler_cache: dict[tuple[type, str], Callable] = {}
        self.__websocket_handler_cache: dict[tuple[type, str], Callable] = {}
        self.__controllers: list[type] = []
        self.__route_functions: list[Callable] = []
        self.__dependency_functions: list[Callable] = []
        self.__configuration_classes: list[type[Configuration]] = []
        self.__service_classes: list[type] = []
        self.__middleware_entries: list[tuple[str, Callable, Optional[str], Optional[str]]] = []

        self.__providers_synced: bool = False

        self.__resolve_base_routes()

    @property
    def name(self) -> str:
        return self.__get_application_metadata('name')

    @property
    def version(self) -> str:
        return self.__get_application_metadata('version')

    @property
    def description(self) -> Optional[str]:
        return self.__get_application_metadata('description')

    @property
    def application_configuration(self) -> Optional[ApplicationConfiguration]:
        if not self.__providers_synced or self.__application_configuration is None:
            self.__sync_providers()

        return self.__application_configuration

    def __get_application_metadata(self, name: str):
        configuration = self.application_configuration

        if configuration is None:
            return getattr(ApplicationConfiguration, name, None)

        return getattr(configuration, name, None)

    @staticmethod
    def __append_unique(collection: list, item) -> bool:
        if item in collection:
            return False

        collection.append(item)
        return True

    @staticmethod
    def __normalize_route_path(path: str) -> str:
        value = str(path or '/').strip()

        if not value:
            return '/'

        if not value.startswith('/'):
            value = '/' + value

        return value

    @classmethod
    def __join_paths(cls, prefix: str, path: str) -> str:
        normalized_prefix = '' if prefix == '/' else cls.__normalize_route_path(prefix).rstrip('/')
        normalized_path = cls.__normalize_route_path(path)

        if not normalized_prefix:
            return normalized_path

        if normalized_path == '/':
            return normalized_prefix or '/'

        return normalized_prefix + normalized_path

    def __register_routes_for_controller(self, controller_class: type) -> None:
        prefix = getattr(controller_class, '__autumn_prefix__', '')

        for name, attribute in controller_class.__dict__.items():
            routes = getattr(attribute, '__routes__', None)

            if not routes:
                continue

            for route in routes:
                full_path = self.__join_paths(prefix, route.get('path', '/'))
                method = route.get('method', 'GET')

                if method == 'WS':
                    self.router.add_websocket_route(full_path, (controller_class, name))
                else:
                    self.router.add_route(method, full_path, (controller_class, name))

    def __register_routes_for_function(self, func: Callable) -> None:
        routes = getattr(func, '__routes__', None) or []

        for route in routes:
            path = self.__normalize_route_path(route.get('path', '/'))
            method = route.get('method', 'GET')

            if method == 'WS':
                self.router.add_websocket_route(path, func)
            else:
                self.router.add_route(method, path, func)

    @staticmethod
    def __is_discoverable_file(path: Path) -> bool:
        framework_path = Path(__file__).resolve().parents[2]
        ignored_parts = {
            '__pycache__',
            '.git',
            '.pytest_cache',
            '.mypy_cache',
            '.venv',
            'venv',
            'env',
            'node_modules',
            'dist',
            'build'
        }

        try:
            if path.is_relative_to(framework_path):
                return False

        except ValueError:
            pass

        return path.suffix == '.py' and not any(part in ignored_parts for part in path.parts)

    def __ensure_discovery_package(self, module_name: str, filepath: Path) -> None:
        parts = module_name.split('.')

        for index in range(1, len(parts)):
            package_name = '.'.join(parts[:index])

            if package_name in sys.modules:
                continue

            package = types.ModuleType(package_name)

            if index == 1 or self.__root_path is None:
                package_path = self.__root_path or filepath.parent

            else:
                package_path = self.__root_path.joinpath(*parts[1:index])

            package.__path__ = [str(package_path)]
            sys.modules[package_name] = package

    def __discover_modules(self) -> None:
        if self.__discovery_completed:
            return

        self.__discovery_completed = True

        if not self.__discover_enabled or self.__root_path is None:
            return

        root = self.__root_path

        if not root.exists() or not root.is_dir():
            return

        for filepath in sorted(root.rglob('*.py')):
            filepath = filepath.resolve()

            if filepath == self.__entrypoint_path:
                continue

            if not self.__is_discoverable_file(filepath):
                continue

            if self.__module_loaded_from_file(filepath):
                continue

            relative = filepath.relative_to(root).with_suffix('')
            module_parts = [
                part
                for part in relative.parts
                if part != '__init__'
            ]

            if not module_parts:
                continue

            module_name = '.'.join((self.__discovery_package, *module_parts))

            if module_name in sys.modules:
                continue

            self.__ensure_discovery_package(module_name, filepath)

            spec = importlib.util.spec_from_file_location(module_name, filepath)

            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

    @staticmethod
    def __module_loaded_from_file(filepath: Path) -> bool:
        for module in tuple(sys.modules.values()):
            module_name = getattr(module, '__name__', '')

            if module_name.startswith('_autumn_discovered_'):
                continue

            module_file = getattr(module, '__file__', None)

            if module_file is None:
                continue

            try:
                if Path(module_file).resolve() == filepath:
                    return True

            except (OSError, ValueError):
                continue

        return False

    def __sync_registered_definitions(self) -> None:
        self.__discover_modules()

        (
            controller_classes,
            route_functions,
            dependency_functions,
            service_classes,
            configuration_classes,
            startup_hooks,
            shutdown_hooks,
            middleware_entries
        ) = dependency_registry.registered_definitions()

        for definition in (
            *configuration_classes,
            *controller_classes,
            *route_functions,
            *dependency_functions,
            *service_classes
        ):
            self.__include(definition)

        for hook in startup_hooks:
            self.__append_unique(self.startup_hooks, hook)

        for hook in shutdown_hooks:
            self.__append_unique(self.shutdown_hooks, hook)

        for entry in middleware_entries:
            if not self.__append_unique(self.__middleware_entries, entry):
                continue

            kind, func, path, method = entry

            if kind == 'before':
                self.middleware.before(func, path = path, method = method)

            elif kind == 'after':
                self.middleware.after(func, path = path, method = method)

    def __include(self, *definitions) -> None:
        for definition in definitions:
            if definition is None:
                continue

            if isinstance(definition, (list, tuple, set, frozenset)):
                self.__include(*definition)
                continue

            if inspect.isclass(definition):
                if issubclass(definition, Configuration):
                    if self.__append_unique(self.__configuration_classes, definition):
                        self.__providers_synced = False

                    continue

                if getattr(definition, '__autumn_controller__', False):
                    if self.__append_unique(self.__controllers, definition):
                        self.__register_routes_for_controller(definition)

                    continue

                provider_meta = getattr(definition, '__autumn_provider__', None)

                if provider_meta and provider_meta[0] == 'class':
                    self.__append_unique(self.__service_classes, definition)

                    continue

            if callable(definition):
                routes = getattr(definition, '__routes__', None)

                if routes:
                    if self.__append_unique(self.__route_functions, definition):
                        self.__register_routes_for_function(definition)

                    continue

                provider_meta = getattr(definition, '__autumn_provider__', None)

                if provider_meta and provider_meta[0] == 'func':
                    if self.__append_unique(self.__dependency_functions, definition):
                        self.__providers_synced = False
                        
                    continue

    def get_registered_configs(self) -> list[type[Configuration]]:
        self.__sync_registered_definitions()
        return get_registered_configs(self.__configuration_classes)

    def get_registered_dependency_functions(self) -> list[Callable]:
        self.__sync_registered_definitions()
        return list(self.__dependency_functions)

    def get_registered_controller_classes(self) -> list[type]:
        self.__sync_registered_definitions()
        return list(self.__controllers)

    def get_registered_route_functions(self) -> list[Callable]:
        self.__sync_registered_definitions()
        return list(self.__route_functions)

    def get_registered_service_classes(self) -> list[type]:
        self.__sync_registered_definitions()
        return list(self.__service_classes)

    def __resolve_base_routes(self) -> None:
        from autumn.core.routing.base import favicon_route

        if self.environment != Environment.PRODUCTION:
            self.__enable_documentation()

        self.router.add_route('GET', '/favicon.ico', favicon_route)

    def __enable_documentation(self) -> None:
        from autumn.core.routing.base import (
            dependencies_json_route,
            openapi_json_route, 
            autumn_web_route
        )

        self.router.add_route('GET', '/documentation/dependencies.json', dependencies_json_route(self))
        self.router.add_route('GET', '/documentation/openapi.json', openapi_json_route(self))

        self.router.add_route('GET', '/autumn', autumn_web_route)
        
    def __sync_providers(self):
        if self.__providers_synced:
            return

        self.__sync_registered_definitions()

        self.__application_configuration = None
        self.__cors_configuration = None

        for func in self.__dependency_functions:
            self.container.register_dependency_function(func)

        for configuration_class in self.get_registered_configs():
            configuration = configuration_class.build()

            self.container.register_value(
                configuration_class, 
                configuration, 
                scope = Scope.APP
            )

            for base_class in configuration_class.__mro__[1:]:
                if getattr(base_class, '__autumn_builtin_config__', False):
                    self.container.register_value(
                        base_class,
                        configuration,
                        scope = Scope.APP
                    )

            if issubclass(configuration_class, ApplicationConfiguration):
                self.__application_configuration = configuration

            if issubclass(configuration_class, CORSConfiguration):
                self.__cors_configuration = configuration

        self.__providers_synced = True

    def __normalize_response(self, result, handler_callable) -> Response:
        if isinstance(result, Response):
            return result

        if getattr(handler_callable, '__json_response__', False) or value_supports_json_response(result):
            return JSONResponse(result)

        raise TypeError(f'Handler returned unsupported result type: {type(result).__name__}')

    @staticmethod
    def __copy_handler_metadata(source: Callable, target: Callable) -> Callable:
        for attribute in ('__query_parameters__', '__body_schema__', '__json_response__', '__response_model__'):
            if hasattr(source, attribute):
                setattr(target, attribute, getattr(source, attribute))

        return target

    @staticmethod
    def __resolve_query_kwargs(request: Request, query_meta: list[dict]) -> dict[str, object]:
        raw_query = request.query.__dict__ if hasattr(request.query, '__dict__') else request.query
        parsed: dict[str, object] = {}

        for parameter in query_meta:
            name     = parameter.get('name')
            cast     = parameter.get('type')
            required = parameter.get('required')
            default  = parameter.get('default')

            raw_value = raw_query.get(name)

            if raw_value is None:
                if required:
                    raise HTTPException(
                        status  = 400,
                        details = f'Missing query parameter: \'{name}\''
                    )

                if default is not None:
                    parsed[name] = default
                else:
                    parsed[name] = None

                continue

            try:
                parsed[name] = cast(raw_value)

            except Exception:
                raise HTTPException(
                    status = 400,
                    details = f'Invalid value for \'{name}\''
                )

        request.query = parsed
        return parsed

    @staticmethod
    def __get_controller_middleware_metadata(controller_class: type) -> dict[str, tuple[str, ...]]:
        cached = getattr(controller_class, '__autumn_controller_middlewares__', None)

        if cached is not None:
            return cached

        around: list[str] = []
        before: list[str] = []
        after: list[str] = []

        for name, attribute in controller_class.__dict__.items():
            metadata = getattr(attribute, '__controller_middleware__', None)

            if metadata is None:
                continue

            kind = metadata.get('kind', 'around')

            if kind == 'around':
                if not (inspect.isgeneratorfunction(attribute) or inspect.isasyncgenfunction(attribute)):
                    raise TypeError(
                        f'Controller middleware \'{controller_class.__name__}.{name}\' must yield exactly once'
                    )

                around.append(name)
                continue

            if kind == 'before':
                before.append(name)
                continue

            if kind == 'after':
                after.append(name)
                continue

            raise TypeError(f'Unknown controller middleware kind: {kind}')

        cached = {
            'around' : tuple(around),
            'before' : tuple(before),
            'after'  : tuple(after)
        }
        setattr(controller_class, '__autumn_controller_middlewares__', cached)

        return cached

    @staticmethod
    def __controller_call_kwargs(
        request: Request,
        path_parameters: dict[str, Any],
        *,
        response: Optional[Response] = None
    ) -> dict[str, Any]:
        kwargs = {
            **path_parameters,
            'request': request
        }

        if response is not None:
            kwargs['response'] = response

        return kwargs

    async def __run_controller_before_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> None:
        await self.container.call(
            getattr(controller, middleware_name),
            context = context,
            provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
        )

    async def __run_controller_after_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        response: Response,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> Response:
        result = await self.container.call(
            getattr(controller, middleware_name),
            context = context,
            provided_kwargs = self.__controller_call_kwargs(
                request,
                path_parameters,
                response = response
            )
        )

        if isinstance(result, Response):
            return result

        return response

    async def __enter_controller_middleware(
        self,
        controller: Any,
        middleware_name: str,
        *,
        request: Request,
        context: ExecutionContext,
        path_parameters: dict[str, Any]
    ) -> tuple[str, Any, str]:
        middleware_callable = getattr(controller, middleware_name)
        kwargs = await self.container.resolve_call_kwargs(
            middleware_callable,
            context = context,
            provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
        )
        generator = middleware_callable(**kwargs)

        if inspect.isasyncgen(generator):
            try:
                await anext(generator)

            except StopAsyncIteration as error:
                raise RuntimeError(
                    f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must yield exactly once'
                ) from error

            return ('async', generator, middleware_name)

        if inspect.isgenerator(generator):
            try:
                next(generator)

            except StopIteration as error:
                raise RuntimeError(
                    f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must yield exactly once'
                ) from error

            return ('sync', generator, middleware_name)

        raise TypeError(
            f'Controller middleware \'{type(controller).__name__}.{middleware_name}\' must be a generator'
        )

    @staticmethod
    async def __close_controller_middleware(state: tuple[str, Any, str]) -> None:
        mode, generator, _ = state

        if mode == 'async':
            await generator.aclose()
            return

        generator.close()

    async def __exit_controller_middleware(
        self,
        state: tuple[str, Any, str],
        response: Response,
        *,
        controller_name: str
    ) -> Response:
        mode, generator, middleware_name = state

        if mode == 'async':
            try:
                await generator.asend(response)

            except StopAsyncIteration:
                return response

            raise RuntimeError(
                f'Controller middleware \'{controller_name}.{middleware_name}\' must yield exactly once'
            )

        try:
            generator.send(response)

        except StopIteration as stop:
            if isinstance(stop.value, Response):
                return stop.value

            return response

        raise RuntimeError(
            f'Controller middleware \'{controller_name}.{middleware_name}\' must yield exactly once'
        )

    def __get_http_handler_callable(self, handler: tuple[type, str]) -> Callable:
        if handler in self.__http_handler_cache:
            return self.__http_handler_cache[handler]

        controller_class, method_name = handler
        original_method = getattr(controller_class, method_name)
        controller_middlewares = self.__get_controller_middleware_metadata(controller_class)

        async def endpoint(request: Request, **path_parameters):
            context = getattr(request, '_autumn_execution_context', None)

            controller = await self.container.resolve(controller_class, context)
            method = getattr(controller, method_name)
            active_middlewares: list[tuple[str, Any, str]] = []

            try:
                for middleware_name in controller_middlewares['around']:
                    active_middlewares.append(
                        await self.__enter_controller_middleware(
                            controller,
                            middleware_name,
                            request = request,
                            context = context,
                            path_parameters = path_parameters
                        )
                    )

                for middleware_name in controller_middlewares['before']:
                    await self.__run_controller_before_middleware(
                        controller,
                        middleware_name,
                        request = request,
                        context = context,
                        path_parameters = path_parameters
                    )

                response = await self.container.call(
                    method,
                    context = context,
                    provided_kwargs = self.__controller_call_kwargs(request, path_parameters)
                )

                for middleware_name in controller_middlewares['after']:
                    response = await self.__run_controller_after_middleware(
                        controller,
                        middleware_name,
                        request = request,
                        response = response,
                        context = context,
                        path_parameters = path_parameters
                    )

            except Exception:
                for state in reversed(active_middlewares):
                    await self.__close_controller_middleware(state)

                raise

            for state in reversed(active_middlewares):
                response = await self.__exit_controller_middleware(
                    state,
                    response,
                    controller_name = controller_class.__name__
                )

            return response

        cached = self.__copy_handler_metadata(original_method, endpoint)
        self.__http_handler_cache[handler] = cached

        return cached

    def __get_websocket_handler_callable(self, handler: tuple[type, str]) -> Callable:
        if handler in self.__websocket_handler_cache:
            return self.__websocket_handler_cache[handler]

        controller_class, method_name = handler

        async def endpoint(websocket: WebSocket, **path_parameters):
            context = getattr(websocket, '_autumn_execution_context', None)

            controller = await self.container.resolve(controller_class, context)
            method = getattr(controller, method_name)

            return await self.container.call(
                method,
                context = context,
                provided_kwargs = {
                    **path_parameters,
                    'websocket': websocket
                }
            )

        self.__websocket_handler_cache[handler] = endpoint
        return endpoint

    @staticmethod
    async def __send_response(send, response: Response) -> None:
        await send({
            'type'    : 'http.response.start',
            'status'  : response.status,
            'headers' : response.headers_as_list(),
        })

        if hasattr(response, 'body_iterate') and callable(getattr(response, 'body_iterate')):
            async for chunk in response.body_iterate():
                await send({
                    'type'      : 'http.response.body',
                    'body'      : chunk,
                    'more_body' : True
                })

            await send({
                'type'      : 'http.response.body',
                'body'      : b'',
                'more_body' : False
            })
            
            return

        await send({
            'type'      : 'http.response.body',
            'body'      : response.body_as_bytes(),
            'more_body' : False
        })

    @staticmethod
    def __normalize_header_values(values) -> list[str]:
        if values is None:
            return []

        return [
            str(value).strip()
            for value in values
            if str(value).strip()
        ]

    @staticmethod
    def __merge_vary(current: Optional[str], *values: str) -> Optional[str]:
        merged: list[str] = []

        for chunk in (current, *values):
            if not chunk:
                continue

            for item in str(chunk).split(','):
                normalized = item.strip()

                if normalized and normalized not in merged:
                    merged.append(normalized)

        if not merged:
            return None

        return ', '.join(merged)

    def __is_cors_preflight(self, request: Request) -> bool:
        if self.__cors_configuration is None or not self.__cors_configuration.enabled:
            return False

        return (
            request.method == 'OPTIONS'
            and bool(request.header('origin'))
            and bool(request.header('access-control-request-method'))
        )

    def __is_cors_origin_allowed(self, origin: str) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_origins = self.__normalize_header_values(configuration.allowed_origins)

        return '*' in allowed_origins or origin in allowed_origins

    def __is_cors_method_allowed(self, method: str) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_methods = [
            value.upper()
            for value in self.__normalize_header_values(configuration.allowed_methods)
        ]

        return '*' in allowed_methods or method.upper() in allowed_methods

    def __is_cors_headers_allowed(self, requested_headers: list[str]) -> bool:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return False

        allowed_headers = [
            value.lower()
            for value in self.__normalize_header_values(configuration.allowed_headers)
        ]

        if '*' in allowed_headers:
            return True

        return all(header.lower() in allowed_headers for header in requested_headers)

    def __build_cors_headers(self, request: Request, *, preflight: bool = False) -> dict[str, str]:
        configuration = self.__cors_configuration

        if configuration is None or not configuration.enabled:
            return {}

        origin = request.header('origin')

        if not origin or not self.__is_cors_origin_allowed(origin):
            if preflight and origin:
                raise HTTPException(
                    status = 403,
                    details = 'CORS origin is not allowed'
                )

            return {}

        allowed_origins = self.__normalize_header_values(configuration.allowed_origins)
        allow_any_origin = '*' in allowed_origins

        headers: dict[str, str] = {
            'Access-Control-Allow-Origin': (
                '*' 
                if allow_any_origin and not configuration.allow_credentials 
                else origin
            )
        }

        vary = None if headers['Access-Control-Allow-Origin'] == '*' else 'Origin'

        if configuration.allow_credentials:
            headers['Access-Control-Allow-Credentials'] = 'true'

        expose_headers = self.__normalize_header_values(configuration.expose_headers)

        if expose_headers and not preflight:
            headers['Access-Control-Expose-Headers'] = ', '.join(expose_headers)

        if preflight:
            requested_method = (request.header('access-control-request-method') or '').upper()

            if not requested_method or not self.__is_cors_method_allowed(requested_method):
                raise HTTPException(
                    status = 405,
                    details = 'CORS method is not allowed'
                )

            allowed_methods = [
                value.upper()
                for value in self.__normalize_header_values(configuration.allowed_methods)
            ]

            headers['Access-Control-Allow-Methods'] = ', '.join(
                [requested_method]
                if '*' in allowed_methods
                else allowed_methods
            )

            requested_headers_raw = request.header('access-control-request-headers') or ''
            requested_headers = [
                header.strip()
                for header in requested_headers_raw.split(',')
                if header.strip()
            ]

            if requested_headers and not self.__is_cors_headers_allowed(requested_headers):
                raise HTTPException(
                    status = 400,
                    details = 'CORS headers are not allowed'
                )

            allowed_headers = self.__normalize_header_values(configuration.allowed_headers)

            if requested_headers_raw:
                headers['Access-Control-Allow-Headers'] = (
                    requested_headers_raw
                    if '*' in [value.lower() for value in allowed_headers]
                    else ', '.join(allowed_headers)
                )

            elif allowed_headers:
                headers['Access-Control-Allow-Headers'] = ', '.join(allowed_headers)

            headers['Access-Control-Max-Age'] = str(configuration.max_age)
            vary = self.__merge_vary(vary, 'Access-Control-Request-Method', 'Access-Control-Request-Headers')

        if vary is not None:
            headers['Vary'] = vary

        return headers

    def __apply_response_headers(self, response: Response, headers: dict[str, str]) -> Response:
        if not headers:
            return response

        for key, value in headers.items():
            if key.lower() == 'vary':
                response.headers['Vary'] = self.__merge_vary(response.headers.get('Vary'), value) or value
                continue

            response.headers[key] = value

        return response

    async def __lifespan(self, scope, receive, send):
        if scope['type'] != 'lifespan':
            return
        
        while True:
            message = await receive()

            if message['type'] == 'lifespan.startup':
                try:
                    start = time.perf_counter()

                    self.__sync_providers()
                    await asyncio.gather(*(hook() for hook in self.startup_hooks))

                    duration = (time.perf_counter() - start) * 1000

                    print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + Fore.GREEN + f'Startup completed in {duration:.2f}ms' + Fore.RESET)

                    await send({ 'type' : 'lifespan.startup.complete' })
                
                except Exception as error:
                    await send({ 
                        'type' : 'lifespan.startup.failed', 
                        'message' : str(error) 
                    })
                    raise

            elif message['type'] == 'lifespan.shutdown':
                try:
                    start = time.perf_counter()

                    await asyncio.gather(*(hook() for hook in self.shutdown_hooks))

                    duration = (time.perf_counter() - start) * 1000

                    print(Fore.YELLOW + '[AUTUMN]' + Fore.RESET + ': ' + Fore.GREEN + f'Shutdown completed in {duration:.2f}ms' + Fore.RESET)

                    await send({ 'type' : 'lifespan.shutdown.complete' })
                    return
                
                except Exception as error:
                    await send({ 
                        'type' : 'lifespan.shutdown.failed', 
                        'message' : str(error) 
                    })
                    raise


    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            await self.__lifespan(scope, receive, send)
            return

        self.__sync_providers()
		
        if scope['type'] == 'websocket':
            websocket: WebSocket = WebSocket(scope, receive, send)
            websocket.app = self

            match = self.router.match_websocket(scope['path'])

            try:
                if match is None:
                    await websocket.close(code = 1000)
                    return
                
                handler = match.handler
                parameters = match.parameters

                context = ExecutionContext()
                context.values[WebSocket] = websocket
                websocket._autumn_execution_context = context

                if isinstance(handler, tuple) and (len(handler) == 2) and isinstance(handler[1], str):
                    handler_callable = self.__get_websocket_handler_callable(handler)

                else:
                    handler_callable = handler

                await self.container.call(
                    handler_callable,
                    context         = context,
                    provided_kwargs = { 
                        **parameters,
                        'websocket': websocket 
                    }
                )
            
            except WebSocketDisconnect:
                return
            
            except Exception as error:
                print(error)
                try:
                    await websocket.close(code = 1011)

                except Exception:
                    pass
                
                return

            return

        if scope['type'] != 'http':
            raise NotImplementedError(f'Unsupported scope type: {scope['type']}')

        assert scope['type'] == 'http'

        request = Request(scope, receive)
        request.app = self

        if self.__is_cors_preflight(request):
            try:
                response = Response(
                    body = '',
                    status = 204,
                    headers = self.__build_cors_headers(request, preflight = True)
                )

            except HTTPException as error:
                response = error.to_response(request)

            except Exception as error:
                print(error)
                response = HTTPException(
                    status = 500,
                    details = str(error)
                ).to_response(request)

            await self.__send_response(send, response)
            return

        match = self.router.match(scope['method'], scope['path'])

        try:
            if match is None:
                raise HTTPException(
                    status = 404, 
                    details = f'Route {scope.get('path')} not found'
                )
        
            handler = match.handler
            parameters = match.parameters

            context = ExecutionContext()
            context.values[Request] = request
            request._autumn_execution_context = context

            if isinstance(handler, tuple) and (len(handler) == 2) and isinstance(handler[1], str):
                handler_callable = self.__get_http_handler_callable(handler)

            else:
                handler_callable = handler

            provided_kwargs = {
                **parameters,
                'request': request
            }

            query_meta = getattr(handler_callable, '__query_parameters__', [])

            if query_meta:
                provided_kwargs.update(self.__resolve_query_kwargs(request, query_meta))

            async def invoke(current_request: Request) -> Response:
                current_kwargs = provided_kwargs

                if current_request is not request:
                    current_kwargs = {
                        **provided_kwargs,
                        'request': current_request
                    }

                return self.__normalize_response(
                    await self.container.call(
                        handler_callable,
                        context = context,
                        provided_kwargs = current_kwargs
                    ),
                    handler_callable
                )

            response = self.__normalize_response(
                await self.middleware.wrap(
                    invoke,
                    match.route.path_template,
                    scope['method']
                )(request),
                handler_callable
            )

        except HTTPException as error:
            response = error.to_response(request)

        except Exception as error:
            print(error)
            response = HTTPException(
                status = 500, 
                details = str(error)
            ).to_response(request)

        response = self.__apply_response_headers(
            response,
            self.__build_cors_headers(request)
        )
        
        await self.__send_response(send, response)
