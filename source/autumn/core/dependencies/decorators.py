from typing import Callable, Optional, Type, TypeVar, Any

from autumn.core.dependencies.registry import register_dependency_function, register_service_class
from autumn.core.dependencies.scope import Scope

T = TypeVar('T')

def service(__cls: Optional[Type[T]] = None, *, scope: Scope = Scope.APP):
    def wrapper(cls: Type[T]) -> Type[T]:
        setattr(cls, '__autumn_provider__', ('class', cls))
        setattr(cls, '__autumn_scope__', scope)

        register_service_class(cls)

        return cls
    
    return wrapper if __cls is None else wrapper(__cls)

def leaf(_func: Optional[Callable[..., Any]] = None, *, scope: Scope = Scope.APP):
    def wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, '__autumn_provider__', ('func', func))
        setattr(func, '__autumn_scope__', scope)

        register_dependency_function(func)

        return func
    
    return wrapper if _func is None else wrapper(_func)
