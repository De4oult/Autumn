from typing import Callable, Optional

from autumn.core.dependencies.registry import (
    register_middleware,
    register_shutdown_hook,
    register_startup_hook
)


def startup(func: Callable) -> Callable:
    return register_startup_hook(func)


def shutdown(func: Callable) -> Callable:
    return register_shutdown_hook(func)


def before(func: Optional[Callable] = None, *, path: Optional[str] = None, method: Optional[str] = None):
    if func is not None and callable(func):
        return register_middleware('before', func, path = path, method = method)

    def decorator(inner_func: Callable) -> Callable:
        return register_middleware('before', inner_func, path = path, method = method)

    return decorator


def after(func: Optional[Callable] = None, *, path: Optional[str] = None, method: Optional[str] = None):
    if func is not None and callable(func):
        return register_middleware('after', func, path = path, method = method)

    def decorator(inner_func: Callable) -> Callable:
        return register_middleware('after', inner_func, path = path, method = method)

    return decorator
