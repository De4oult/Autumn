from autumn.core.websocket.websocket import WebSocket, WebSocketDisconnect
from autumn.core.configuration.builtin import CORSConfiguration
from autumn.core.dependencies.container import Container, ExecutionContext
from autumn.core.configuration.configuration import get_registered_configs
from autumn.core.introspection import value_contains_pydantic_model
from autumn.core.middleware.manager import MiddlewareManager
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import JSONResponse, Response
from autumn.core.dependencies.scope import Scope
from autumn.core.request.request import Request
from autumn.core.routing.router import router

from typing import Callable, Optional
from types import SimpleNamespace
from colorama import Fore
from enum import Enum

import asyncio
import time

class Environment(str, Enum):
    LOCAL = 'local'
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'

class Autumn:
    def __init__(self, *, name: str = 'Autumn API', version: str = 'v0.1.0', description: Optional[str] = None, environment: Environment = Environment.DEVELOPMENT):
        self.name: str = name
        self.version: str = version
        self.description: Optional[str] = description
        self.environment: Environment = environment

        self.router = router
        
        self.startup_hooks: list[Callable] = []
        self.shutdown_hooks: list[Callable] = []
        
        self.middleware = MiddlewareManager()
        self.container = Container()
        self.__cors_configuration: Optional[CORSConfiguration] = None

        self.__providers_synced: bool = False

        self.__resolve_base_routes()

    def __resolve_base_routes(self) -> None:
        from autumn.core.routing.base import favicon_route

        if self.environment != Environment.PRODUCTION:
            self.__enable_documentation()

        self.router.add_route('GET', '/favicon.ico', favicon_route)

    def __enable_documentation(self) -> None:
        from autumn.core.routing.base import (
            favicon_route,
            dependencies_json_route,
            openapi_json_route, 
            autumn_web_route
        )

        self.router.add_route('GET', '/favicon.ico', favicon_route)

        self.router.add_route('GET', '/documentation/dependencies.json', dependencies_json_route(self))
        self.router.add_route('GET', '/documentation/openapi.json', openapi_json_route(self))

        self.router.add_route('GET', '/autumn', autumn_web_route)
        
    def __sync_providers(self):
        if self.__providers_synced:
            return
        
        from autumn.core.dependencies.registry import DEPENDENCY_FUNCTIONS

        for func in DEPENDENCY_FUNCTIONS:
            self.container.register_dependency_function(func)

        for configuration_class in get_registered_configs():
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

            if issubclass(configuration_class, CORSConfiguration):
                self.__cors_configuration = configuration

        self.__providers_synced = True

    def __normalize_response(self, result, handler_callable) -> Response:
        if isinstance(result, Response):
            return result

        if getattr(handler_callable, '__json_response__', False) or value_contains_pydantic_model(result):
            return JSONResponse(result)

        raise TypeError(f'Handler returned unsupported result type: {type(result).__name__}')

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

    def startup(self, func: Callable) -> Callable:
        self.startup_hooks.append(func)
        
        return func

    def shutdown(self, func: Callable) -> Callable:
        self.shutdown_hooks.append(func)
        
        return func

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

            match = self.router.match_websocket(scope['path'])

            try:
                if match is None:
                    await websocket.close(code = 1000)
                    return
                
                handler, parameters = match

                context = ExecutionContext()
                context.values[WebSocket] = websocket

                if isinstance(handler, tuple) and (len(handler) == 2) and isinstance(handler[1], str):
                    controller_class, method_name = handler

                    async def endpoint(websocket: WebSocket, **path_parameters):
                        controller = await self.container.resolve(controller_class, context)
                        method = getattr(controller, method_name)

                        return await self.container.call(
                            method,
                            context         = context,
                            provided_kwargs = {
                                **path_parameters,
                                'websocket': websocket
                            }
                        )

                    handler_callable = endpoint

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
                'body'      : response.body.encode('utf-8') if isinstance(response.body, str) else response.body,
                'more_body' : False
            })
            return

        match = self.router.match(scope['method'], scope['path'])

        try:
            if match is None:
                raise HTTPException(
                    status = 404, 
                    details = f'Route {scope.get('path')} not found'
                )
        
            handler, parameters = match

            context = ExecutionContext()
            context.values[Request] = request

            if isinstance(handler, tuple) and (len(handler) == 2) and isinstance(handler[1], str):
                controller_class, method_name = handler

                async def endpoint(request: Request, **path_parameters):
                    controller = await self.container.resolve(controller_class, context)
                    method = getattr(controller, method_name)

                    return await self.container.call(
                        method,
                        context         = context,
                        provided_kwargs = {
                            **path_parameters,
                            'request': request
                        }
                    )
                
                original_method = getattr(controller_class, method_name)

                for attribute in ('__query_parameters__', '__body_schema__', '__json_response__', '__response_model__'):
                    if hasattr(original_method, attribute):
                        setattr(endpoint, attribute, getattr(original_method, attribute))
                    
                handler_callable = endpoint

            else:
                handler_callable = handler


            async def invoke(request: Request) -> Response:
                return await self.container.call(
                    handler_callable,
                    context         = context,
                    provided_kwargs = {
                        **parameters,
                        'request': request
                    }
                )
            
            wrapped_handler = await self.middleware.wrap(
                invoke, 
                scope['path'], 
                scope['method']
            )

            query_meta = getattr(handler_callable, '__query_parameters__', [])

            if query_meta:
                raw_query = request.query.__dict__ if hasattr(request.query, '__dict__') else request.query
                parsed = {}

                for parameter in query_meta:
                    name = parameter.get('name')
                    cast = parameter.get('type')
                    required = parameter.get('required')
                    default = parameter.get('default')

                    raw_value = raw_query.get(name)

                    if raw_value is None:
                        if required:
                            raise HTTPException(
                                status = 400, 
                                details = f'Missing query parameter: \'{name}\''
                            )
                        
                        elif default is not None:
                            parsed[name] = default
                        
                        else:
                            parsed[name] = None

                    else:
                        try:
                            parsed[name] = cast(raw_value)

                        except Exception:
                            raise HTTPException(
                                status = 400, 
                                details = f'Invalid value for \'{name}\''
                            )

                request.query = SimpleNamespace(**parsed)

            response = self.__normalize_response(
                await wrapped_handler(request),
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
            'body'      : response.body.encode('utf-8') if isinstance(response.body, str) else response.body,
            'more_body' : False
        })
