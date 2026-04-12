from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, get_origin, get_type_hints
import inspect
import re

from autumn.core.configuration.configuration import get_registered_configs
from autumn.core.dependencies.registry import SERVICE_CLASSES, DEPENDENCY_FUNCTIONS
from autumn.core.dependencies.scope import Scope


def _doc_parts(obj: Any) -> tuple[Optional[str], Optional[str]]:
    doc = inspect.getdoc(obj) or ""
    if not doc.strip():
        return None, None
    lines = doc.splitlines()
    summary = (lines[0].strip() if lines else None) or None
    body = "\n".join(lines[1:]).strip() or None

    if summary == "Initialize self.  See help(type(self)) for accurate signature." and body is None:
        return None, None

    return summary, body


def _safe_type_str(t: Any) -> str:
    origin = get_origin(t)

    if origin is list:
        args = getattr(t, "__args__", ())
        inner = _safe_type_str(args[0]) if args else "Any"
        return f"list[{inner}]"

    if origin is dict:
        args = getattr(t, "__args__", ())
        key = _safe_type_str(args[0]) if len(args) > 0 else "Any"
        value = _safe_type_str(args[1]) if len(args) > 1 else "Any"
        return f"dict[{key}, {value}]"

    if origin is not None:
        args = getattr(t, "__args__", ())
        rendered = ", ".join(_safe_type_str(arg) for arg in args) or "Any"
        origin_name = getattr(origin, "__name__", None) or str(origin)
        return f"{origin_name}[{rendered}]"

    try:
        return getattr(t, "__name__", None) or str(t)
    except Exception:
        return "Any"


def _signature_str(fn: Callable[..., Any]) -> str:
    try:
        return str(inspect.signature(fn))
    except Exception:
        return "(...)"


def _iter_public_methods(cls: Type[Any]) -> List[Callable[..., Any]]:
    out = []
    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        out.append(member)
    return out


def _callable_deps(fn: Callable[..., Any], *, skip_self: bool) -> List[Any]:
    """
    Dependency list according to your DI rules:
    - only parameters that have type hints
    - optionally skip self
    """
    try:
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)
    except Exception:
        return []

    deps: List[Any] = []
    for name, p in sig.parameters.items():
        if skip_self and name == "self":
            continue
        if name not in hints:
            continue
        deps.append(hints[name])
    return deps


def _provider_key_for_leaf(func: Callable[..., Any]) -> Optional[Any]:
    try:
        hints = get_type_hints(func)
        return hints.get("return")
    except Exception:
        return None


def _scope_value(scope: Any) -> str:
    if isinstance(scope, Scope):
        return scope.value

    return str(scope)


def _lifecycle_for_scope(scope: Any) -> str:
    normalized = _scope_value(scope)

    if normalized == Scope.APP.value:
        return "singleton"

    if normalized in (Scope.REQUEST.value, Scope.WEBSOCKET.value):
        return "scoped"

    if normalized == Scope.TRANSIENT.value:
        return "transient"

    return normalized


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _doc_id(kind: str, *, name: str, module: Optional[str], qualname: Optional[str], provides: Optional[str] = None) -> str:
    base = ".".join(part for part in (module, qualname or name, provides) if part)
    return f"{kind}-{_slugify(base or name)}"


def _dependency_ref(dependency: Any, providers: Dict[Any, dict]) -> str | dict:
    meta = providers.get(dependency)

    if meta is None:
        return _safe_type_str(dependency)

    return {
        "name": meta["name"],
        "type": meta["kind"],
        "qualname": meta.get("qualname"),
        "scope": meta.get("scope"),
        "lifecycle": meta.get("lifecycle"),
        "provides": meta.get("provides"),
    }


class DependenciesDocumentationGenerator:
    def generate(self, app: Any) -> dict:
        leaf_by_key: Dict[Any, Callable[..., Any]] = {}

        for f in DEPENDENCY_FUNCTIONS:
            k = _provider_key_for_leaf(f)

            if k is not None:
                leaf_by_key[k] = f

        config_classes = list(get_registered_configs())
        providers: Dict[Any, dict] = {}
        services_out: List[dict] = []
        leaf_out: List[dict] = []
        configurations_out: List[dict] = []

        for cls in SERVICE_CLASSES:
            scope = getattr(cls, "__autumn_scope__", Scope.APP)
            scope_value = _scope_value(scope)
            provides = _safe_type_str(cls)
            service_id = _doc_id(
                "service",
                name = cls.__name__,
                module = getattr(cls, "__module__", None),
                qualname = getattr(cls, "__qualname__", None),
            )

            providers[cls] = {
                "id": service_id,
                "kind": "service",
                "name": cls.__name__,
                "qualname": getattr(cls, "__qualname__", None),
                "module": getattr(cls, "__module__", None),
                "scope": scope_value,
                "lifecycle": _lifecycle_for_scope(scope),
                "provides": provides,
            }

        for config_class in config_classes:
            scope_value = Scope.APP.value
            provides = _safe_type_str(config_class)
            leaf_id = _doc_id(
                "configuration",
                name = config_class.__name__,
                module = getattr(config_class, "__module__", None),
                qualname = getattr(config_class, "__qualname__", None),
                provides = provides,
            )

            providers[config_class] = {
                "id": leaf_id,
                "kind": "configuration",
                "name": config_class.__name__,
                "qualname": getattr(config_class, "__qualname__", None),
                "module": getattr(config_class, "__module__", None),
                "scope": scope_value,
                "lifecycle": _lifecycle_for_scope(scope_value),
                "provides": provides,
            }

        for f in DEPENDENCY_FUNCTIONS:
            ret = _provider_key_for_leaf(f)
            scope = getattr(f, "__autumn_scope__", Scope.APP)
            scope_value = _scope_value(scope)
            provides = _safe_type_str(ret) if ret is not None else None
            leaf_id = _doc_id(
                "leaf",
                name = getattr(f, "__name__", "leaf"),
                module = getattr(f, "__module__", None),
                qualname = getattr(f, "__qualname__", None),
                provides = provides,
            )

            if ret is not None:
                providers[ret] = {
                    "id": leaf_id,
                    "kind": "leaf",
                    "name": getattr(f, "__name__", "leaf"),
                    "qualname": getattr(f, "__qualname__", None),
                    "module": getattr(f, "__module__", None),
                    "scope": scope_value,
                    "lifecycle": _lifecycle_for_scope(scope),
                    "provides": provides,
                }

        for f in DEPENDENCY_FUNCTIONS:
            ret = _provider_key_for_leaf(f)
            scope = getattr(f, "__autumn_scope__", Scope.APP)
            s, body = _doc_parts(f)
            provides = _safe_type_str(ret) if ret is not None else None
            leaf_id = _doc_id(
                "leaf",
                name = getattr(f, "__name__", "leaf"),
                module = getattr(f, "__module__", None),
                qualname = getattr(f, "__qualname__", None),
                provides = provides,
            )

            leaf_out.append({
                "id": leaf_id,
                "kind": "leaf",
                "name": getattr(f, "__name__", "leaf"),
                "qualname": getattr(f, "__qualname__", None),
                "module": getattr(f, "__module__", None),
                "scope": _scope_value(scope),
                "lifecycle": _lifecycle_for_scope(scope),
                "provides": provides,
                "signature": _signature_str(f),
                "doc": {"summary": s, "body": body},
                "dependencies": [
                    _dependency_ref(d, providers)
                    for d in _callable_deps(f, skip_self = False)
                ],
            })

        for config_class in config_classes:
            s, body = _doc_parts(config_class)

            configurations_out.append({
                "id": _doc_id(
                    "configuration",
                    name = config_class.__name__,
                    module = getattr(config_class, "__module__", None),
                    qualname = getattr(config_class, "__qualname__", None),
                    provides = _safe_type_str(config_class),
                ),
                "kind": "configuration",
                "name": config_class.__name__,
                "qualname": getattr(config_class, "__qualname__", None),
                "module": getattr(config_class, "__module__", None),
                "scope": Scope.APP.value,
                "lifecycle": _lifecycle_for_scope(Scope.APP),
                "provides": _safe_type_str(config_class),
                "signature": f"() -> {_safe_type_str(config_class)}",
                "doc": {"summary": s, "body": body},
                "dependencies": [],
            })

        for cls in SERVICE_CLASSES:
            scope = getattr(cls, "__autumn_scope__", Scope.APP)
            s, body = _doc_parts(cls)

            init = cls.__init__
            init_s, init_body = _doc_parts(init)

            methods = []
            for m in _iter_public_methods(cls):
                ms, mbody = _doc_parts(m)
                mdeps = _callable_deps(m, skip_self=True)
                signature = inspect.signature(m)
                returns = signature.return_annotation

                methods.append({
                    "name": m.__name__,
                    "qualname": m.__qualname__,
                    "signature": _signature_str(m),
                    "returnType": None if returns is inspect._empty else _safe_type_str(returns),
                    "doc": {"summary": ms, "body": mbody},
                    "dependencies": [_dependency_ref(d, providers) for d in mdeps],
                })

            services_out.append({
                "id": _doc_id(
                    "service",
                    name = cls.__name__,
                    module = getattr(cls, "__module__", None),
                    qualname = getattr(cls, "__qualname__", None),
                ),
                "kind": "service",
                "name": cls.__name__,
                "qualname": cls.__qualname__,
                "module": cls.__module__,
                "scope": _scope_value(scope),
                "lifecycle": _lifecycle_for_scope(scope),
                "provides": _safe_type_str(cls),
                "doc": {"summary": s, "body": body},
                "init": {
                    "signature": _signature_str(init),
                    "doc": {"summary": init_s, "body": init_body},
                    "dependencies": [
                        _dependency_ref(d, providers)
                        for d in _callable_deps(init, skip_self = True)
                    ],
                },
                "methods": methods,
            })

        def edges_for_type(t: Any, visited: set[Any], stack: set[Any]) -> dict:
            label = _safe_type_str(t)

            if t in stack:
                return {"type": label, "cycle": True, "deps": []}

            if t in visited:
                return {"type": label, "ref": True}

            visited.add(t)
            stack.add(t)

            deps: List[Any] = []

            if inspect.isclass(t) and t in SERVICE_CLASSES:
                deps = _callable_deps(t.__init__, skip_self = True)
            elif t in leaf_by_key:
                deps = _callable_deps(leaf_by_key[t], skip_self = False)
            else:
                deps = []

            node = {
                "type": label,
                "deps": [edges_for_type(x, visited, stack) for x in deps],
            }

            stack.remove(t)
            return node

        roots = []
        for cls in SERVICE_CLASSES:
            roots.append(edges_for_type(cls, visited=set(), stack=set()))

        return {
            "app": {
                "name": getattr(app, "name", None),
                "version": getattr(app, "version", None),
                "description": getattr(app, "description", None) or "Services documentation",
            },
            "services": services_out,
            "leaf": leaf_out,
            "configurations": configurations_out,
            "graph": roots,
        }
