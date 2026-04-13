from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type, Tuple, get_origin, get_type_hints
import inspect
import re

from autumn.core.configuration.configuration import get_registered_configs
from autumn.core.dependencies.registry import SERVICE_CLASSES, DEPENDENCY_FUNCTIONS
from autumn.core.dependencies.scope import Scope


def _docstring_parts(object: Any) -> Tuple[Optional[str], Optional[str]]:
    docstring = inspect.getdoc(object) or ''

    if not docstring.strip():
        return None, None
    
    lines = docstring.splitlines()
    summary = (lines[0].strip() if lines else None) or None
    body = '\n'.join(lines[1:]).strip() or None

    if summary == 'Initialize self.  See help(type(self)) for accurate signature.' and body is None:
        return None, None

    return summary, body


def _safe_type_str(t: Any) -> str:
    origin = get_origin(t)

    if origin is list:
        arguments = getattr(t, '__args__', ())
        inner = _safe_type_str(arguments[0]) if arguments else 'Any'

        return f'list[{inner}]'

    if origin is dict:
        arguments = getattr(t, '__args__', ())

        key = _safe_type_str(arguments[0]) if len(arguments) > 0 else 'Any'
        value = _safe_type_str(arguments[1]) if len(arguments) > 1 else 'Any'

        return f'dict[{key}, {value}]'

    if origin is not None:
        arguments = getattr(t, '__args__', ())

        rendered = ', '.join(_safe_type_str(arg) for arg in arguments) or 'Any'
        origin_name = getattr(origin, '__name__', None) or str(origin)

        return f'{origin_name}[{rendered}]'

    try:
        return getattr(t, '__name__', None) or str(t)
    
    except Exception:
        return 'Any'


def _signature_string(fn: Callable[..., Any]) -> str:
    try:
        return str(inspect.signature(fn))
    
    except Exception:
        return '(...)'


def _iter_public_methods(cls: Type[Any]) -> List[Callable[..., Any]]:
    out = []

    for name, member in inspect.getmembers(cls, predicate=inspect.isfunction):
        if name.startswith('_'):
            continue

        out.append(member)

    return out


def _callable_deps(fn: Callable[..., Any], *, skip_self: bool) -> List[Any]:
    '''
    Dependency list according to your DI rules:
    - only parameters that have type hints
    - optionally skip self
    '''
    try:
        signature = inspect.signature(fn)
        hints = get_type_hints(fn)

    except Exception:
        return []

    dependencies: List[Any] = []

    for name, _ in signature.parameters.items():
        if skip_self and name == 'self':
            continue

        if name not in hints:
            continue

        dependencies.append(hints[name])

    return dependencies


def _provider_key_for_leaf(func: Callable[..., Any]) -> Optional[Any]:
    try:
        hints = get_type_hints(func)

        return hints.get('return')
    
    except Exception:
        return None


def _scope_value(scope: Any) -> str:
    if isinstance(scope, Scope):
        return scope.value

    return str(scope)


def _lifecycle_for_scope(scope: Any) -> str:
    normalized = _scope_value(scope)

    if normalized == Scope.APP.value:
        return 'singleton'

    if normalized in (Scope.REQUEST.value, Scope.WEBSOCKET.value):
        return 'scoped'

    if normalized == Scope.TRANSIENT.value:
        return 'transient'

    return normalized


def _slugify(value: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')

def _documentation_id(kind: str, *, name: str, module: Optional[str], qualname: Optional[str], provides: Optional[str] = None) -> str:
    base = '.'.join(part for part in (module, qualname or name, provides) if part)

    return f'{kind}-{_slugify(base or name)}'


def _dependency_ref(dependency: Any, providers: Dict[Any, dict]) -> str | dict:
    meta = providers.get(dependency)

    if meta is None:
        return _safe_type_str(dependency)

    return {
        'name'      : meta['name'],
        'type'      : meta['kind'],
        'qualname'  : meta.get('qualname'),
        'scope'     : meta.get('scope'),
        'lifecycle' : meta.get('lifecycle'),
        'provides'  : meta.get('provides')
    }


def _serialize_default(value: Any) -> Any:
    if value is inspect._empty:
        return None

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return repr(value)


def _configuration_fields(config_class: Type[Any]) -> List[dict]:
    fields: List[dict] = []
    aliases = getattr(config_class, '__aliases__', {}) or {}
    field_types = getattr(config_class, '__field_types__', {}) or {}

    for field_name, field_type in field_types.items():
        alias = aliases.get(field_name)
        has_default = hasattr(config_class, field_name)
        default_value = getattr(config_class, field_name) if has_default else inspect._empty

        fields.append({
            'name'     : field_name,
            'type'     : _safe_type_str(field_type),
            'path'     : getattr(alias, 'path', None),
            'required' : not has_default,
            'default'  : _serialize_default(default_value)
        })

    return fields


class DependenciesDocumentationGenerator:
    def generate(self, app: Any) -> dict:
        leaf_by_key: Dict[Any, Callable[..., Any]] = {}

        for function in DEPENDENCY_FUNCTIONS:
            key = _provider_key_for_leaf(function)

            if key is not None:
                leaf_by_key[key] = function

        config_classes = list(get_registered_configs())
        providers: Dict[Any, dict] = {}
        services_out: List[dict] = []
        leaf_out: List[dict] = []
        configurations_out: List[dict] = []

        for cls in SERVICE_CLASSES:
            scope = getattr(cls, '__autumn_scope__', Scope.APP)

            scope_value = _scope_value(scope)
            provides = _safe_type_str(cls)

            service_id = _documentation_id(
                'service',
                name     = cls.__name__,
                module   = getattr(cls, '__module__', None),
                qualname = getattr(cls, '__qualname__', None)
            )

            providers[cls] = {
                'id'        : service_id,
                'kind'      : 'service',
                'name'      : cls.__name__,
                'qualname'  : getattr(cls, '__qualname__', None),
                'module'    : getattr(cls, '__module__', None),
                'scope'     : scope_value,
                'lifecycle' : _lifecycle_for_scope(scope),
                'provides'  : provides
            }

        for config_class in config_classes:
            scope_value = Scope.APP.value
            provides = _safe_type_str(config_class)

            leaf_id = _documentation_id(
                'configuration',
                name     = config_class.__name__,
                module   = getattr(config_class, '__module__', None),
                qualname = getattr(config_class, '__qualname__', None),
                provides = provides
            )

            providers[config_class] = {
                'id'        : leaf_id,
                'kind'      : 'configuration',
                'name'      : config_class.__name__,
                'qualname'  : getattr(config_class, '__qualname__', None),
                'module'    : getattr(config_class, '__module__', None),
                'scope'     : scope_value,
                'lifecycle' : _lifecycle_for_scope(scope_value),
                'provides'  : provides
            }

        for function in DEPENDENCY_FUNCTIONS:
            ret = _provider_key_for_leaf(function)

            scope = getattr(function, '__autumn_scope__', Scope.APP)

            scope_value = _scope_value(scope)
            provides = _safe_type_str(ret) if ret is not None else None

            leaf_id = _documentation_id(
                'leaf',
                name     = getattr(function, '__name__', 'leaf'),
                module   = getattr(function, '__module__', None),
                qualname = getattr(function, '__qualname__', None),
                provides = provides
            )

            if ret is not None:
                providers[ret] = {
                    'id'        : leaf_id,
                    'kind'      : 'leaf',
                    'name'      : getattr(function, '__name__', 'leaf'),
                    'qualname'  : getattr(function, '__qualname__', None),
                    'module'    : getattr(function, '__module__', None),
                    'scope'     : scope_value,
                    'lifecycle' : _lifecycle_for_scope(scope),
                    'provides'  : provides
                }

        for function in DEPENDENCY_FUNCTIONS:
            ret = _provider_key_for_leaf(function)

            scope = getattr(function, '__autumn_scope__', Scope.APP)

            summary, body = _docstring_parts(function)
            provides = _safe_type_str(ret) if ret is not None else None

            leaf_id = _documentation_id(
                'leaf',
                name     = getattr(function, '__name__', 'leaf'),
                module   = getattr(function, '__module__', None),
                qualname = getattr(function, '__qualname__', None),
                provides = provides
            )

            leaf_out.append({
                'id'        : leaf_id,
                'kind'      : 'leaf',
                'name'      : getattr(function, '__name__', 'leaf'),
                'qualname'  : getattr(function, '__qualname__', None),
                'module'    : getattr(function, '__module__', None),
                'scope'     : _scope_value(scope),
                'lifecycle' : _lifecycle_for_scope(scope),
                'provides'  : provides,
                'signature' : _signature_string(function),
                'doc'       : {
                    'summary' : summary, 
                    'body'    : body
                },
                'dependencies': [
                    _dependency_ref(dependency, providers)
                    for dependency in _callable_deps(function, skip_self = False)
                ]
            })

        for config_class in config_classes:
            summary, body = _docstring_parts(config_class)

            configurations_out.append({
                'id': _documentation_id(
                    'configuration',
                    name     = config_class.__name__,
                    module   = getattr(config_class, '__module__', None),
                    qualname = getattr(config_class, '__qualname__', None),
                    provides = _safe_type_str(config_class)
                ),
                'kind'      : 'configuration',
                'name'      : config_class.__name__,
                'qualname'  : getattr(config_class, '__qualname__', None),
                'module'    : getattr(config_class, '__module__', None),
                'scope'     : Scope.APP.value,
                'lifecycle' : _lifecycle_for_scope(Scope.APP),
                'provides'  : _safe_type_str(config_class),
                'signature' : f'() -> {_safe_type_str(config_class)}',
                'doc'       : {
                    'summary' : summary, 
                    'body'    : body
                },
                'dependencies' : [],
                'fields'       : _configuration_fields(config_class)
            })

        for cls in SERVICE_CLASSES:
            scope = getattr(cls, '__autumn_scope__', Scope.APP)
            summary, body = _docstring_parts(cls)

            init = cls.__init__
            init_summary, init_body = _docstring_parts(init)

            methods = []

            for method in _iter_public_methods(cls):
                method_summary, method_body = _docstring_parts(method)

                method_dependencies = _callable_deps(method, skip_self=True)
                signature = inspect.signature(method)
                returns = signature.return_annotation

                methods.append({
                    'name'       : method.__name__,
                    'qualname'   : method.__qualname__,
                    'signature'  : _signature_string(method),
                    'returnType' : None if returns is inspect._empty else _safe_type_str(returns),
                    'doc'        : {
                        'summary' : method_summary, 
                        'body'    : method_body
                    },
                    'dependencies' : [
                        _dependency_ref(dependency, providers) 
                        for dependency in method_dependencies
                    ]
                })

            services_out.append({
                'id' : _documentation_id(
                    'service',
                    name     = cls.__name__,
                    module   = getattr(cls, '__module__', None),
                    qualname = getattr(cls, '__qualname__', None)
                ),
                'kind'      : 'service',
                'name'      : cls.__name__,
                'qualname'  : cls.__qualname__,
                'module'    : cls.__module__,
                'scope'     : _scope_value(scope),
                'lifecycle' : _lifecycle_for_scope(scope),
                'provides'  : _safe_type_str(cls),
                'doc'       : {
                    'summary' : summary, 
                    'body'    : body
                },
                'init': {
                    'signature' : _signature_string(init),
                    'doc'       : {
                        'summary' : init_summary,
                        'body'    : init_body
                    },
                    'dependencies': [
                        _dependency_ref(dependency, providers)
                        for dependency in _callable_deps(init, skip_self = True)
                    ]
                },
                'methods': methods
            })

        def edges_for_type(_type: Any, visited: set[Any], stack: set[Any]) -> dict:
            label = _safe_type_str(_type)

            if _type in stack:
                return {
                    'type'  : label, 
                    'cycle' : True, 
                    'deps'  : []
                }

            if _type in visited:
                return {
                    'type' : label, 
                    'ref'  : True
                }

            visited.add(_type)
            stack.add(_type)

            dependencies: List[Any] = []

            if inspect.isclass(_type) and _type in SERVICE_CLASSES:
                dependencies = _callable_deps(_type.__init__, skip_self = True)

            elif _type in leaf_by_key:
                dependencies = _callable_deps(leaf_by_key[_type], skip_self = False)

            else:
                dependencies = []

            node = {
                'type' : label,
                'deps' : [
                    edges_for_type(dependency, visited, stack) 
                    for dependency in dependencies
                ]
            }

            stack.remove(_type)

            return node

        roots = []

        for cls in SERVICE_CLASSES:
            roots.append(edges_for_type(
                cls, 
                visited = set(), 
                stack   = set()
            ))

        return {
            'app' : {
                'name'        : getattr(app, 'name', None),
                'version'     : getattr(app, 'version', None),
                'description' : getattr(app, 'description', None) or 'Services documentation',
            },
            'services'      : services_out,
            'leaf'          : leaf_out,
            'configurations': configurations_out,
            'graph'         : roots
        }
