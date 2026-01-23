from __future__ import annotations

from autumn.core.exception.exception import DependencyInjectionError, DependencyProviderError
from autumn.core.dependencies.scope import Scope

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
class RequestContext:
    cache: Dict[Type[Any], Any] = field(default_factory = dict)

class Container:
    def __init__(self) -> None:
        self.__providers: Dict[Type[Any], Provider] = {}
        self.__app_cache: Dict[Type[Any], Any] = {}

    # Registration
    def register_dependency_function(self, func: Callable[..., Any]):
        hints = get_type_hints(func)
        returns = hints.get('return')

        if returns is None:
            raise DependencyInjectionError(f'@dependency function must have return type annotation: {func.__name__}')
        
        scope = getattr(func, '__autumn_scope__', Scope.APP)

        self.register(returns, Provider(kind = 'func', target = func, scope = scope))

    def register(self, key: Type[Any], provider: Provider) -> Type[Any]:
        self.__providers[key] = provider

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
    
    async def resolve(self, key: Type[Any], context: Optional[RequestContext] = None) -> Any:
        provider = self.__get_provider(key)

        if provider.scope == Scope.APP:
            if key in self.__app_cache:
                return self.__app_cache[key]
            
        elif provider.scope == Scope.REQUEST:
            if context is None:
                raise DependencyInjectionError(f'RequestContext is required to resolve request-scoped dependency: {key}')
            
            if key in context.cache:
                return context.cache[key]
            
        instance = await self.__build(provider, context)

        if provider.scope == Scope.APP:
            self.__app_cache[key] = instance

        elif provider.scope == Scope.REQUEST:
            context.cache[key] = instance

        return instance
    
    async def __build(self, provider: Provider, context: Optional[RequestContext] = None) -> Any:
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
    
    async def __inject_kwargs(self, callable: Callable[..., Any], context: Optional[RequestContext], skip_self: bool = False) -> Dict[str, Any]:
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