from autumn.core.routing.router import router
from autumn.core.dependencies.scope import Scope

from typing import Callable

def REST(prefix: str = ''):
    def wrapper(__class):
        if not hasattr(__class, '__autumn_provider__'):
            setattr(__class, '__autumn_provider__', ('class', __class))

        if not hasattr(__class, '__autumn_scope__'):
            setattr(__class, '__autumn_scope__', Scope.REQUEST)

        if not hasattr(__class, '__tag__'):
            setattr(__class, '__tag__', __class.__name__.removesuffix("Controller"))

        for name, attribute in __class.__dict__.items():
            if hasattr(attribute, '__routes__'):
                for route in attribute.__routes__:
                    full_path = prefix.rstrip('/') + route.get('path')

                    router.add_route(route.get('method'), full_path, (__class, name))

        return __class
    
    return wrapper

def route(method: str, path: str):
    def decorator(func):
        if not hasattr(func, '__routes__'):
            func.__routes__ = []
        
        func.__routes__.append({
            'method' : method.upper(),
            'path'   : path
        })

        return func
    
    return decorator

def get(path: str) -> Callable:
    return route('GET', path)

def post(path: str) -> Callable:
    return route('POST', path)

def put(path: str) -> Callable:
    return route('PUT', path)

def patch(path: str) -> Callable:
    return route('PATCH', path)

def delete(path: str) -> Callable:
    return route('DELETE', path)