from typing import Callable, Optional, Sequence

from autumn.core.dependencies.registry import (
    register_middleware,
    register_shutdown_hook,
    register_startup_hook
)

RouteFilter = Optional[str | Sequence[str]]
MethodFilter = Optional[str | Sequence[str]]


def _is_controller_method(func: Callable) -> bool:
    qualname = getattr(func, '__qualname__', '')
    parts = qualname.split('.')

    return len(parts) >= 2 and parts[-2] != '<locals>'


def _controller_middleware(kind: str, func: Callable) -> Callable:
    setattr(func, '__controller_middleware__', {
        'kind': kind
    })

    return func


def startup(func: Callable) -> Callable:
    return register_startup_hook(func)


def shutdown(func: Callable) -> Callable:
    return register_shutdown_hook(func)


class _MiddlewareDecorator:
    @staticmethod
    def __register(
        *,
        controller_kind: str,
        lifecycle_kind: str,
        func: Callable,
        path: RouteFilter,
        method: MethodFilter
    ) -> Callable:
        if _is_controller_method(func):
            return _controller_middleware(controller_kind, func)

        return register_middleware(lifecycle_kind, func, path = path, method = method)

    def __call__(
        self,
        func: Optional[Callable] = None,
        *,
        path: RouteFilter = None,
        method: MethodFilter = None
    ):
        if func is not None and callable(func):
            return self.__register(
                controller_kind = 'around',
                lifecycle_kind  = 'before',
                func            = func,
                path            = path,
                method          = method
            )

        def decorator(inner_func: Callable) -> Callable:
            return self.__register(
                controller_kind = 'around',
                lifecycle_kind  = 'before',
                func            = inner_func,
                path            = path,
                method          = method
            )

        return decorator

    def before(
        self,
        func: Optional[Callable] = None,
        *,
        path: RouteFilter = None,
        method: MethodFilter = None
    ):
        if func is not None and callable(func):
            return self.__register(
                controller_kind = 'before',
                lifecycle_kind  = 'before',
                func            = func,
                path            = path,
                method          = method
            )

        def decorator(inner_func: Callable) -> Callable:
            return self.__register(
                controller_kind = 'before',
                lifecycle_kind  = 'before',
                func            = inner_func,
                path            = path,
                method          = method
            )

        return decorator

    def after(
        self,
        func: Optional[Callable] = None,
        *,
        path: RouteFilter = None,
        method: MethodFilter = None
    ):
        if func is not None and callable(func):
            return self.__register(
                controller_kind = 'after',
                lifecycle_kind  = 'after',
                func            = func,
                path            = path,
                method          = method
            )

        def decorator(inner_func: Callable) -> Callable:
            return self.__register(
                controller_kind = 'after',
                lifecycle_kind  = 'after',
                func            = inner_func,
                path            = path,
                method          = method
            )

        return decorator


middleware = _MiddlewareDecorator()
