from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type, get_type_hints
import inspect

from autumn.core.dependencies.registry import SERVICE_CLASSES, DEPENDENCY_FUNCTIONS
from autumn.core.dependencies.scope import Scope


def _doc_parts(obj: Any) -> tuple[Optional[str], Optional[str]]:
    doc = inspect.getdoc(obj) or ""
    if not doc.strip():
        return None, None
    lines = doc.splitlines()
    summary = (lines[0].strip() if lines else None) or None
    body = "\n".join(lines[1:]).strip() or None
    return summary, body


def _safe_type_str(t: Any) -> str:
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
    # In your Container.register_dependency_function the key is func return type
    try:
        hints = get_type_hints(func)
        return hints.get("return")
    except Exception:
        return None


class DependenciesDocumentationGenerator:
    def generate(self, app: Any) -> dict:
        # leaf map: return_type -> func
        leaf_by_key: Dict[Any, Callable[..., Any]] = {}
        for f in DEPENDENCY_FUNCTIONS:
            k = _provider_key_for_leaf(f)
            if k is not None:
                leaf_by_key[k] = f

        services_out = []
        leaf_out = []

        # --- leaf docs ---
        for f in DEPENDENCY_FUNCTIONS:
            ret = _provider_key_for_leaf(f)
            scope = getattr(f, "__autumn_scope__", Scope.APP)
            s, body = _doc_parts(f)

            leaf_out.append({
                "kind": "leaf",
                "name": getattr(f, "__name__", "leaf"),
                "qualname": getattr(f, "__qualname__", None),
                "module": getattr(f, "__module__", None),
                "scope": str(scope),
                "provides": _safe_type_str(ret) if ret is not None else None,
                "signature": _signature_str(f),
                "doc": {"summary": s, "body": body},
                "dependencies": [_safe_type_str(d) for d in _callable_deps(f, skip_self=False)],
            })

        # --- service docs ---
        for cls in SERVICE_CLASSES:
            scope = getattr(cls, "__autumn_scope__", Scope.APP)
            s, body = _doc_parts(cls)

            init = cls.__init__
            init_s, init_body = _doc_parts(init)

            methods = []
            for m in _iter_public_methods(cls):
                ms, mbody = _doc_parts(m)
                # dependencies of method itself (если хочешь документировать это тоже)
                mdeps = _callable_deps(m, skip_self=True)

                methods.append({
                    "name": m.__name__,
                    "qualname": m.__qualname__,
                    "signature": _signature_str(m),
                    "doc": {"summary": ms, "body": mbody},
                    "dependencies": [_safe_type_str(d) for d in mdeps],
                })

            services_out.append({
                "kind": "service",
                "name": cls.__name__,
                "qualname": cls.__qualname__,
                "module": cls.__module__,
                "scope": str(scope),
                "doc": {"summary": s, "body": body},
                "init": {
                    "signature": _signature_str(init),
                    "doc": {"summary": init_s, "body": init_body},
                    "dependencies": [_safe_type_str(d) for d in _callable_deps(init, skip_self=True)],
                },
                "methods": methods,
            })

        # --- dependency graph (services + leaf) ---
        def edges_for_type(t: Any, visited: set[Any], stack: set[Any]) -> dict:
            """
            Возвращает узел с deps. Без падений, с детектом циклов.
            """
            label = _safe_type_str(t)
            if t in stack:
                return {"type": label, "cycle": True, "deps": []}
            if t in visited:
                return {"type": label, "ref": True}

            visited.add(t)
            stack.add(t)

            # node can be service class (provider_meta class) or leaf return type
            deps: List[Any] = []

            if inspect.isclass(t) and t in SERVICE_CLASSES:
                deps = _callable_deps(t.__init__, skip_self=True)
            elif t in leaf_by_key:
                deps = _callable_deps(leaf_by_key[t], skip_self=False)
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
                "description": getattr(app, "description", None),
            },
            "services": services_out,
            "leaf": leaf_out,
            "graph": roots,
        }
