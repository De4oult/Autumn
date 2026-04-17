from autumn.core.dependencies.scope import Scope

from typing import Callable, Optional

def REST(prefix: str = ''):
    def wrapper(__class):
        if not hasattr(__class, '__autumn_provider__'):
            setattr(__class, '__autumn_provider__', ('class', __class))

        if not hasattr(__class, '__autumn_scope__'):
            setattr(__class, '__autumn_scope__', Scope.REQUEST)

        if not hasattr(__class, '__tag__'):
            setattr(__class, '__tag__', __class.__name__.removesuffix("Controller"))
        
        setattr(__class, '__autumn_controller__', True)
        setattr(__class, '__autumn_prefix__', prefix)

        return __class
    
    return wrapper

def route(method: str, path: str = '/') -> Callable:
    def decorator(func):
        if not hasattr(func, '__routes__'):
            func.__routes__ = []
        
        func.__routes__.append({
            'method' : method.upper(),
            'path'   : path
        })

        return func
    
    return decorator

def _method_decorator(method: str, arg: Optional[Callable | str] = None) -> Callable:
    if callable(arg):
        return route(method, '/')(arg)

    path = '/' if arg is None else str(arg)
    return route(method, path)

def get(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('GET', arg)

def post(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('POST', arg)

def put(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('PUT', arg)

def patch(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('PATCH', arg)

def delete(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('DELETE', arg)

def websocket(arg: Optional[Callable | str] = None) -> Callable:
    return _method_decorator('WS', arg)


def _controller_middleware(kind: str):
    def decorator(func: Callable) -> Callable:
        setattr(func, '__controller_middleware__', {
            'kind': kind
        })
        return func

    return decorator


class _ControllerMiddlewareDecorator:
    def __call__(self, func: Optional[Callable] = None) -> Callable:
        decorator = _controller_middleware('around')

        if func is not None and callable(func):
            return decorator(func)

        return decorator

    def before(self, func: Optional[Callable] = None) -> Callable:
        decorator = _controller_middleware('before')

        if func is not None and callable(func):
            return decorator(func)

        return decorator

    def after(self, func: Optional[Callable] = None) -> Callable:
        decorator = _controller_middleware('after')

        if func is not None and callable(func):
            return decorator(func)

        return decorator


middleware = _ControllerMiddlewareDecorator()
