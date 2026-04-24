from __future__ import annotations

from typing import Callable, Any, Iterable, List, Optional, Type

DEPENDENCY_FUNCTIONS: List[Callable[..., Any]] = []
SERVICE_CLASSES: List[Type[Any]] = []
CONTROLLER_CLASSES: List[Type[Any]] = []
ROUTE_FUNCTIONS: List[Callable[..., Any]] = []
CONFIGURATION_CLASSES: List[Type[Any]] = []
STARTUP_HOOKS: List[Callable[..., Any]] = []
SHUTDOWN_HOOKS: List[Callable[..., Any]] = []
MIDDLEWARES: List[tuple[str, Callable[..., Any], Optional[str], Optional[str]]] = []


def append_unique(collection: list, item: Any) -> Any:
    if item not in collection:
        collection.append(item)

    return item


def register_dependency_function(func: Callable[..., Any]) -> Callable[..., Any]:
    return append_unique(DEPENDENCY_FUNCTIONS, func)


def register_service_class(cls: Type[Any]) -> Type[Any]:
    return append_unique(SERVICE_CLASSES, cls)


def register_controller_class(cls: Type[Any]) -> Type[Any]:
    return append_unique(CONTROLLER_CLASSES, cls)


def register_route_function(func: Callable[..., Any]) -> Callable[..., Any]:
    return append_unique(ROUTE_FUNCTIONS, func)


def register_configuration_class(cls: Type[Any]) -> Type[Any]:
    return append_unique(CONFIGURATION_CLASSES, cls)


def register_startup_hook(func: Callable[..., Any]) -> Callable[..., Any]:
    return append_unique(STARTUP_HOOKS, func)


def register_shutdown_hook(func: Callable[..., Any]) -> Callable[..., Any]:
    return append_unique(SHUTDOWN_HOOKS, func)


def register_middleware(
    kind: str,
    func: Callable[..., Any],
    *,
    path: Optional[str] = None,
    method: Optional[str] = None
) -> Callable[..., Any]:
    append_unique(MIDDLEWARES, (kind, func, path, method))

    return func


def registered_definitions() -> tuple[
    Iterable[Type[Any]],
    Iterable[Callable[..., Any]],
    Iterable[Callable[..., Any]],
    Iterable[Type[Any]],
    Iterable[Type[Any]],
    Iterable[Callable[..., Any]],
    Iterable[Callable[..., Any]],
    Iterable[tuple[str, Callable[..., Any], Optional[str], Optional[str]]]
]:
    return (
        list(CONTROLLER_CLASSES),
        list(ROUTE_FUNCTIONS),
        list(DEPENDENCY_FUNCTIONS),
        list(SERVICE_CLASSES),
        list(CONFIGURATION_CLASSES),
        list(STARTUP_HOOKS),
        list(SHUTDOWN_HOOKS),
        list(MIDDLEWARES)
    )


def reset_registry() -> None:
    DEPENDENCY_FUNCTIONS.clear()
    SERVICE_CLASSES.clear()
    CONTROLLER_CLASSES.clear()
    ROUTE_FUNCTIONS.clear()
    CONFIGURATION_CLASSES.clear()
    STARTUP_HOOKS.clear()
    SHUTDOWN_HOOKS.clear()
    MIDDLEWARES.clear()
