from __future__ import annotations

from autumn.core.exception.exception import DependencyInjectionError, DependencyProviderError
from autumn.core.dependencies.scope import Scope

# Built-in Providers
from autumn.core.websocket.websocket import WebSocket
from autumn.core.request.request import Request

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Type, TypeVar, get_type_hints

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

    def register_value(self, key: Type[Any], instance: Any, *, scope: Scope = Scope.APP) -> None:
        self.__providers[key] = Provider(
            kind   = 'value', 
            target = instance, 
            scope  = scope
        )

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
        signature = inspect.signature(callable)
        hints = get_type_hints(callable)

        kwargs: Dict[str, Any] = {}

        for name, parameter in signature.parameters.items():
            if skip_self and name == 'self':
                continue

            if name not in hints:
                continue

            dependency_type = hints[name]

            try:
                kwargs[name] = await self.resolve(dependency_type, context)

            except (DependencyInjectionError, DependencyProviderError) as error:
                raise DependencyInjectionError(
                    f'Cannot resolve parameter \'{name}\' ({dependency_type}) for {callable}'
                ) from error

        return kwargs
    
    async def call(
        self,
        func: Callable[..., Any],
        *,
        context: Optional[ExecutionContext] = None,
        provided_kwargs: Optional[Dict[str, Any]] = None,
        skip_self: bool = False
    ) -> Any:
        provided_kwargs = provided_kwargs or {}

        signature = inspect.signature(func)
        hints = get_type_hints(func)

        kwargs: Dict[str, Any] = {}

        has_var_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )

        for name, parameter in signature.parameters.items():
            if skip_self and name == 'self':
                continue

            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            if name in provided_kwargs:
                kwargs[name] = provided_kwargs[name]
                continue

            if name in hints:
                dependency_type = hints[name]

                try:
                    kwargs[name] = await self.resolve(dependency_type, context)
                    continue

                except (DependencyInjectionError, DependencyProviderError) as error:
                    raise DependencyInjectionError(
                        f'Cannot resolve parameter \'{name}\' ({dependency_type}) for {func}'
                    ) from error

            if parameter.default is inspect.Parameter.empty:
                raise DependencyInjectionError(f'Missing required argument \'{name}\' for {func}')

        if has_var_kwargs:
            for key, value in provided_kwargs.items():
                if key in kwargs:
                    continue

                if key in ('request', 'websocket'):
                    continue

                kwargs[key] = value

        result = func(**kwargs)

        if inspect.isawaitable(result):
            result = await result

        return result