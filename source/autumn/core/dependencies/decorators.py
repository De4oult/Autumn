from typing import Callable, Optional, Type, TypeVar, Any

from autumn.core.dependencies.scope import Scope
from autumn.core.dependencies.registry import DEPENDENCY_FUNCTIONS, SERVICE_CLASSES

T = TypeVar('T')

def service(__cls: Optional[Type[T]] = None, *, scope: Scope = Scope.APP):
    def wrapper(cls: Type[T]) -> Type[T]:
        setattr(cls, '__autumn_provider__', ('class', cls))
        setattr(cls, '__autumn_scope__', scope)
        
        if cls not in SERVICE_CLASSES:
            SERVICE_CLASSES.append(cls)

        return cls
    
    return wrapper if __cls is None else wrapper(__cls)

def dependency(_func: Optional[Callable[..., Any]] = None, *, scope: Scope = Scope.APP):
    def wrapper(func: Callable[..., Any]) -> Callable[..., Any]:
        setattr(func, '__autumn_provider__', ('func', func))
        setattr(func, '__autumn_scope__', scope)

        if func not in DEPENDENCY_FUNCTIONS:
            DEPENDENCY_FUNCTIONS.append(func)

        return func
    
    return wrapper if _func is None else wrapper(_func)

