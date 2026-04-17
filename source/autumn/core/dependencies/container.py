from __future__ import annotations

from autumn.core.exception.exception import DependencyInjectionError, DependencyProviderError
from autumn.core.introspection import get_declared_body_parameter
from autumn.core.dependencies.scope import Scope
from autumn.core.response.exception import HTTPException

# Built-in Providers
from autumn.core.websocket.websocket import WebSocket
from autumn.core.request.request import Request

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type, TypeVar, get_type_hints
from pydantic import TypeAdapter, ValidationError

import inspect

T = TypeVar('T')

@dataclass
class Provider:
    kind: str
    target: Any
    scope: Scope

@dataclass
class ExecutionContext:
    cache: Dict[Type[Any], Any] = field(default_factory = dict)
    values: Dict[Type[Any], Any] = field(default_factory = dict)


@dataclass(frozen = True)
class DependencyParameter:
    name: str
    dependency_type: Any


@dataclass(frozen = True)
class CallMetadata:
    parameters: tuple[tuple[str, inspect.Parameter], ...]
    dependency_parameters: tuple[DependencyParameter, ...]
    dependency_map: Dict[str, Any]
    has_var_kwargs: bool
    body_parameter: Any


@dataclass(frozen = True)
class InjectMetadata:
    dependency_parameters: tuple[DependencyParameter, ...]

class BuiltinProvider:
    def __init__(self, key: Type[Any], scope: Scope):
        self.key = key
        self.scope = scope

    async def resolve(self, context: ExecutionContext):
        if self.key not in context.values:
            raise DependencyInjectionError(
                f'{self.key.__name__} is not available in this scope'
            )
        
        return context.values[self.key]

class Container:
    def __init__(self) -> None:
        self.__providers: Dict[Type[Any], Provider] = {}
        self.__app_cache: Dict[Type[Any], Any] = {}
        
        self.__call_metadata_cache: Dict[tuple[Any, bool], CallMetadata] = {}
        self.__inject_metadata_cache: Dict[tuple[Any, bool], InjectMetadata] = {}
        self.__type_adapter_cache: Dict[Any, TypeAdapter] = {}

        self.__providers[Request] = Provider(
            kind   = 'builtin',
            target = BuiltinProvider(Request, Scope.REQUEST),
            scope  = Scope.REQUEST
        )

        self.__providers[WebSocket] = Provider(
            kind   = 'builtin',
            target = BuiltinProvider(WebSocket, Scope.WEBSOCKET),
            scope  = Scope.WEBSOCKET
        )

    @staticmethod
    def __callable_cache_key(callable: Callable[..., Any]) -> Any:
        return getattr(callable, '__func__', callable)

    def __invalidate_callable_caches(self) -> None:
        self.__call_metadata_cache.clear()
        self.__inject_metadata_cache.clear()

    def __get_call_metadata(self, func: Callable[..., Any], *, skip_self: bool = False) -> CallMetadata:
        cache_key = (self.__callable_cache_key(func), skip_self)

        if cache_key in self.__call_metadata_cache:
            return self.__call_metadata_cache[cache_key]

        signature = inspect.signature(func)
        hints = get_type_hints(func)
        body_parameter = get_declared_body_parameter(
            func,
            provided_kwargs = {},
            skip_self = skip_self,
            can_resolve_dependency = self.__can_resolve_dependency,
            signature = signature,
            hints = hints
        )

        parameters: list[tuple[str, inspect.Parameter]] = []
        dependency_parameters: list[DependencyParameter] = []
        has_var_kwargs = False

        for name, parameter in signature.parameters.items():
            if skip_self and name == 'self':
                continue

            if parameter.kind == inspect.Parameter.VAR_KEYWORD:
                has_var_kwargs = True
                continue

            if parameter.kind == inspect.Parameter.VAR_POSITIONAL:
                continue

            parameters.append((name, parameter))

            if body_parameter is not None and name == body_parameter.name:
                continue

            if name in hints:
                dependency_parameters.append(
                    DependencyParameter(
                        name = name,
                        dependency_type = hints[name]
                    )
                )

        metadata = CallMetadata(
            parameters = tuple(parameters),
            dependency_parameters = tuple(dependency_parameters),
            dependency_map = {
                dependency.name: dependency.dependency_type
                for dependency in dependency_parameters
            },
            has_var_kwargs = has_var_kwargs,
            body_parameter = body_parameter
        )

        self.__call_metadata_cache[cache_key] = metadata
        return metadata

    def __get_inject_metadata(self, callable: Callable[..., Any], *, skip_self: bool = False) -> InjectMetadata:
        cache_key = (self.__callable_cache_key(callable), skip_self)

        if cache_key in self.__inject_metadata_cache:
            return self.__inject_metadata_cache[cache_key]

        signature = inspect.signature(callable)
        hints = get_type_hints(callable)
        dependencies: list[DependencyParameter] = []

        for name, parameter in signature.parameters.items():
            if skip_self and name == 'self':
                continue

            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if name not in hints:
                continue

            dependencies.append(
                DependencyParameter(
                    name = name,
                    dependency_type = hints[name]
                )
            )

        metadata = InjectMetadata(
            dependency_parameters = tuple(dependencies)
        )

        self.__inject_metadata_cache[cache_key] = metadata
        return metadata

    def __get_type_adapter(self, annotation: Any) -> TypeAdapter:
        try:
            if annotation in self.__type_adapter_cache:
                return self.__type_adapter_cache[annotation]

            adapter = TypeAdapter(annotation)

            self.__type_adapter_cache[annotation] = adapter

            return adapter

        except TypeError:
            return TypeAdapter(annotation)

    # Registration
    def register_dependency_function(self, func: Callable[..., Any]):
        hints = get_type_hints(func)
        returns = hints.get('return')

        if returns is None:
            raise DependencyInjectionError(f'@leaf function must have return type annotation: {func.__name__}')
        
        scope = getattr(func, '__autumn_scope__', Scope.APP)

        self.register(returns, Provider(kind = 'func', target = func, scope = scope))

    def register(self, key: Type[Any], provider: Provider) -> Type[Any]:
        self.__providers[key] = provider
        
        self.__invalidate_callable_caches()

    def register_value(self, key: Type[Any], instance: Any, *, scope: Scope = Scope.APP) -> None:
        self.__providers[key] = Provider(
            kind   = 'value', 
            target = instance, 
            scope  = scope
        )

        self.__invalidate_callable_caches()

    def __get_provider(self, key: type) -> Provider:
        if key in self.__providers:
            return self.__providers[key]
        
        provider_meta = getattr(key, '__autumn_provider__', None)

        if provider_meta and provider_meta[0] == 'class':
            scope = getattr(key, '__autumn_scope__', Scope.APP)
            provider = Provider(kind = 'class', target = key, scope = scope)
            
            self.__providers[key] = provider

            return provider

        raise DependencyProviderError(f'No provider for: {key}')

    def __can_resolve_dependency(self, key: Any) -> bool:
        try:
            self.__get_provider(key)

            return True

        except (DependencyProviderError, TypeError):
            return False

    async def __resolve_request_body(self, request: Request, parameter) -> Any:
        raw = await request.body()

        if not raw or raw.strip() == b'':
            if parameter.default is not inspect.Parameter.empty:
                return parameter.default

            raise HTTPException(
                status = 400,
                details = 'Request body is empty'
            )

        try:
            payload = await request.json()

        except Exception as error:
            raise HTTPException(
                status = 400,
                details = f'Invalid request body: {str(error)}'
            ) from error

        try:
            adapter = self.__get_type_adapter(parameter.annotation)

            return adapter.validate_python(payload)

        except ValidationError as error:
            raise HTTPException(
                status  = 422,
                details = str(error)
            ) from error

        except Exception as error:
            raise HTTPException(
                status  = 400,
                details = f'Invalid request body: {str(error)}'
            ) from error
    
    async def resolve(self, key: Type[Any], context: Optional[ExecutionContext] = None) -> Any:
        provider = self.__get_provider(key)

        if provider.kind == 'builtin':
            return await provider.target.resolve(context)

        if provider.scope == Scope.APP:
            if key in self.__app_cache:
                return self.__app_cache[key]
            
        elif provider.scope in (Scope.REQUEST, Scope.WEBSOCKET):
            if context is None:
                raise DependencyInjectionError(f'ExecutionContext is required to resolve request-scoped dependency: {key}')
            
            if key in context.cache:
                return context.cache[key]
            
        instance = await self.__build(provider, context)

        if provider.scope == Scope.APP:
            self.__app_cache[key] = instance

        elif provider.scope in (Scope.REQUEST, Scope.WEBSOCKET):
            context.cache[key] = instance

        return instance
    
    async def __build(self, provider: Provider, context: Optional[ExecutionContext] = None) -> Any:
        if provider.kind == 'builtin':
            return await provider.target.resolve(context)
        
        if provider.kind == 'value':
            return provider.target

        if provider.kind == 'func':
            func = provider.target

            kwargs = await self.__inject_kwargs(func, context)
            result = func(**kwargs)

            if inspect.isawaitable(result):
                result = await result

            return result
        
        if provider.kind == 'class':
            cls = provider.target

            init = cls.__init__
            kwargs = await self.__inject_kwargs(init, context, skip_self = True)

            return cls(**kwargs)
        
        raise DependencyInjectionError(f'Unknown provider kind: {provider.kind}')
    
    async def __inject_kwargs(self, callable: Callable[..., Any], context: Optional[ExecutionContext], skip_self: bool = False) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {}
        metadata = self.__get_inject_metadata(callable, skip_self = skip_self)

        for dependency in metadata.dependency_parameters:
            try:
                kwargs[dependency.name] = await self.resolve(dependency.dependency_type, context)

            except (DependencyInjectionError, DependencyProviderError) as error:
                raise DependencyInjectionError(
                    f'Cannot resolve parameter \'{dependency.name}\' ({dependency.dependency_type}) for {callable}'
                ) from error

        return kwargs

    async def resolve_call_kwargs(
        self,
        func: Callable[..., Any],
        *,
        context: Optional[ExecutionContext] = None,
        provided_kwargs: Optional[Dict[str, Any]] = None,
        skip_self: bool = False
    ) -> Dict[str, Any]:
        provided_kwargs = provided_kwargs or {}

        kwargs: Dict[str, Any] = {}
        metadata = self.__get_call_metadata(func, skip_self = skip_self)

        parsed_body = inspect.Parameter.empty
        
        for name, parameter in metadata.parameters:
            if name in provided_kwargs:
                kwargs[name] = provided_kwargs[name]
                continue

            if metadata.body_parameter is not None and name == metadata.body_parameter.name:
                request = provided_kwargs.get('request')

                if request is None and context is not None:
                    request = context.values.get(Request)

                if request is None:
                    raise DependencyInjectionError(f'Cannot resolve request body parameter \'{name}\' for {func} without Request')

                if parsed_body is inspect.Parameter.empty:
                    parsed_body = await self.__resolve_request_body(request, metadata.body_parameter)

                kwargs[name] = parsed_body
                
                continue

            if name in metadata.dependency_map:
                try:
                    kwargs[name] = await self.resolve(metadata.dependency_map[name], context)
                    continue

                except (DependencyInjectionError, DependencyProviderError) as error:
                    raise DependencyInjectionError(
                        f'Cannot resolve parameter \'{name}\' ({metadata.dependency_map[name]}) for {func}'
                    ) from error

            if parameter.default is inspect.Parameter.empty:
                raise DependencyInjectionError(f'Missing required argument \'{name}\' for {func}')

        if metadata.has_var_kwargs:
            for key, value in provided_kwargs.items():
                if key in kwargs:
                    continue

                if key in ('request', 'websocket'):
                    continue

                kwargs[key] = value

        return kwargs

    async def call(
        self,
        func: Callable[..., Any],
        *,
        context: Optional[ExecutionContext] = None,
        provided_kwargs: Optional[Dict[str, Any]] = None,
        skip_self: bool = False
    ) -> Any:
        kwargs = await self.resolve_call_kwargs(
            func,
            context = context,
            provided_kwargs = provided_kwargs,
            skip_self = skip_self
        )

        result = func(**kwargs)

        if inspect.isawaitable(result):
            result = await result

        return result
