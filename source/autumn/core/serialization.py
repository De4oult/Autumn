from __future__ import annotations
from pydantic import BaseModel, TypeAdapter
from typing import Annotated, Any, TypeVar, get_args, get_origin
from dataclasses import dataclass

import operator
import textwrap
import inspect
import types
import ast

T = TypeVar('T')


@dataclass(frozen = True)
class _Visibility:
    public: bool


_PUBLIC = _Visibility(public = True)
_PRIVATE = _Visibility(public = False)

Public = Annotated[T, _PUBLIC]
Private = Annotated[T, _PRIVATE]


@dataclass(frozen = True)
class SerializableField:
    name: str
    annotation: Any
    public: bool
    has_default: bool = False
    default: Any = None

def _unwrap_annotated(annotation: Any) -> tuple[Any, _Visibility | None]:
    current = annotation
    visibility = None

    while get_origin(current) is Annotated:
        arguments = get_args(current)

        if not arguments:
            break

        current = arguments[0]

        for meta in arguments[1:]:
            if isinstance(meta, _Visibility):
                visibility = meta

    return current, visibility


def _build_annotation_context(cls: type) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    module = inspect.getmodule(cls)

    if module is not None:
        namespace.update(vars(module))

    namespace.update(vars(cls))
    namespace[cls.__name__] = cls

    return namespace


_SAFE_ANNOTATION_NAMES = {
    'None': type(None),
    'bool': bool,
    'bytes': bytes,
    'dict': dict,
    'float': float,
    'frozenset': frozenset,
    'int': int,
    'list': list,
    'object': object,
    'set': set,
    'str': str,
    'tuple': tuple,
    'Any': Any
}


def _resolve_annotation_node(node: ast.AST, namespace: dict[str, Any]) -> Any:
    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]

        if node.id in _SAFE_ANNOTATION_NAMES:
            return _SAFE_ANNOTATION_NAMES[node.id]

        raise ValueError(f'Unknown annotation name: {node.id}')

    if isinstance(node, ast.Attribute):
        if node.attr.startswith('_'):
            raise ValueError('Private attributes are not allowed in annotations')

        owner = _resolve_annotation_node(node.value, namespace)

        if isinstance(owner, types.ModuleType):
            try:
                return vars(owner)[node.attr]

            except KeyError as error:
                raise ValueError(f'Unknown annotation attribute: {node.attr}') from error

        if isinstance(owner, type):
            try:
                return inspect.getattr_static(owner, node.attr)

            except AttributeError as error:
                raise ValueError(f'Unknown annotation attribute: {node.attr}') from error

        raise ValueError('Annotation attributes are only allowed on modules and types')

    if isinstance(node, ast.Subscript):
        target = _resolve_annotation_node(node.value, namespace)

        try:
            argument = _resolve_annotation_node(node.slice, namespace)

        except (AttributeError, KeyError, TypeError, ValueError):
            argument = Any

        return target[argument]

    if isinstance(node, ast.Tuple):
        return tuple(_resolve_annotation_node(item, namespace) for item in node.elts)

    if isinstance(node, ast.List):
        return [_resolve_annotation_node(item, namespace) for item in node.elts]

    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (str, int, bool)):
            return node.value

        raise ValueError('Unsupported annotation constant')

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return operator.or_(
            _resolve_annotation_node(node.left, namespace),
            _resolve_annotation_node(node.right, namespace)
        )

    raise ValueError(f'Unsupported annotation expression: {type(node).__name__}')


def _resolve_annotation(annotation: Any, namespace: dict[str, Any]) -> Any:
    if not isinstance(annotation, str):
        return annotation

    expression = ast.parse(annotation, mode = 'eval')
    return _resolve_annotation_node(expression.body, namespace)


def _safe_get_annotations(target: Any, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    namespace = namespace or {}

    try:
        annotations = inspect.get_annotations(target, eval_str = False)

    except Exception:
        annotations = getattr(target, '__annotations__', {}) or {}

    resolved: dict[str, Any] = {}

    for name, annotation in annotations.items():
        try:
            resolved[name] = _resolve_annotation(annotation, namespace)

        except (AttributeError, KeyError, SyntaxError, TypeError, ValueError):
            resolved[name] = Any

    return resolved


def _collect_class_level_fields(cls: type) -> list[SerializableField]:
    fields: list[SerializableField] = []

    for base in reversed(cls.__mro__):
        if base is object:
            continue

        annotations = _safe_get_annotations(base, _build_annotation_context(base))

        for name, annotation in annotations.items():
            if name.startswith('_'):
                continue

            _, visibility = _unwrap_annotated(annotation)
            has_default = name in base.__dict__
            
            fields.append(
                SerializableField(
                    name       = name,
                    annotation = annotation,
                    public     = (
                        True
                        if visibility is None 
                        else visibility.public
                    ),
                    has_default = has_default,
                    default     = base.__dict__.get(name)
                )
            )

    return fields


def _collect_instance_fields_from_init(cls: type) -> list[SerializableField]:
    init = cls.__dict__.get('__init__')

    if init is None:
        return []

    try:
        source = textwrap.dedent(inspect.getsource(init))
        tree = ast.parse(source)

    except (OSError, TypeError, SyntaxError):
        return []

    function = next(
        (
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ),
        None
    )

    if function is None:
        return []

    found: list[tuple[int, str, Any]] = []
    namespace = _build_annotation_context(cls)

    for node in ast.walk(function):
        if not isinstance(node, ast.AnnAssign):
            continue

        target = node.target

        if not (
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == 'self'
        ):
            continue

        try:
            annotation = _resolve_annotation_node(node.annotation, namespace)

        except Exception:
            annotation = Any

        found.append((getattr(node, 'lineno', 0), target.attr, annotation))

    found.sort(key = lambda item: item[0])

    fields: list[SerializableField] = []

    for _, name, annotation in found:
        _, visibility = _unwrap_annotated(annotation)

        fields.append(
            SerializableField(
                name       = name,
                annotation = annotation,
                public     = (
                    True 
                    if visibility is None 
                    else visibility.public
                ),
            )
        )

    return fields


def _merge_fields(*field_groups: list[SerializableField]) -> list[SerializableField]:
    merged: dict[str, SerializableField] = {}

    for fields in field_groups:
        for field in fields:
            merged[field.name] = field

    return list(merged.values())


def get_serializable_fields(cls: type) -> list[SerializableField]:
    fields = getattr(cls, '__autumn_serializable_fields__', None)

    if fields is None:
        fields = _merge_fields(
            _collect_class_level_fields(cls),
            _collect_instance_fields_from_init(cls)
        )

        setattr(cls, '__autumn_serializable_fields__', fields)

    return fields


def _has_declared_init(cls: type) -> bool:
    init = cls.__dict__.get('__init__')
    return init is not None and init is not object.__init__


def _install_auto_init(cls: type, fields: list[SerializableField]) -> None:
    if _has_declared_init(cls):
        return

    def __init__(self, **kwargs: Any) -> None:
        unknown = set(kwargs) - {field.name for field in fields}

        if unknown:
            names = ', '.join(sorted(unknown))
            raise TypeError(f'Unexpected serializable field(s): {names}')

        for field in fields:
            if field.name in kwargs:
                value = kwargs[field.name]

            elif field.has_default:
                value = field.default

            else:
                raise TypeError(f'Missing required serializable field: {field.name}')

            setattr(self, field.name, value)

    __init__.__name__ = '__init__'
    __init__.__qualname__ = f'{cls.__qualname__}.__init__'
    __init__.__module__ = cls.__module__
    setattr(cls, '__init__', __init__)


def serializable(cls: type[T]) -> type[T]:
    fields = _merge_fields(
        _collect_class_level_fields(cls),
        _collect_instance_fields_from_init(cls)
    )

    setattr(cls, '__autumn_serializable__', True)
    setattr(
        cls,
        '__autumn_serializable_fields__',
        fields
    )
    _install_auto_init(cls, fields)

    return cls


def is_serializable_type(annotation: Any) -> bool:
    annotation, _ = _unwrap_annotated(annotation)

    return isinstance(annotation, type) and bool(getattr(annotation, '__autumn_serializable__', False))


def is_serializable_instance(value: Any) -> bool:
    return is_serializable_type(type(value))


def serialize_instance(value: Any) -> dict[str, Any]:
    field_map = {field.name: field for field in get_serializable_fields(type(value))}
    payload: dict[str, Any] = {}

    for name, field_value in getattr(value, '__dict__', {}).items():
        field = field_map.get(name)

        if field is not None:
            if field.public:
                payload[name] = field_value
                
            continue

        if not name.startswith('_'):
            payload[name] = field_value

    for field in get_serializable_fields(type(value)):
        if not field.public or field.name in payload or not hasattr(value, field.name):
            continue

        payload[field.name] = getattr(value, field.name)

    return payload


def json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode = 'json')

    if is_serializable_instance(value):
        return serialize_instance(value)

    raise TypeError


def value_supports_json_response(value: Any) -> bool:
    return isinstance(value, (dict, list, BaseModel)) or is_serializable_instance(value)


def annotation_supports_json_response(annotation: Any) -> bool:
    annotation, _ = _unwrap_annotated(annotation)

    if annotation is None or annotation is inspect._empty:
        return False

    if is_serializable_type(annotation):
        return True

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True

    origin = get_origin(annotation)

    if annotation in (dict, list):
        return True

    if origin in (dict, list):
        return True

    return False


def schema_for_annotation(annotation: Any) -> dict[str, Any] | None:
    annotation, _ = _unwrap_annotated(annotation)

    if annotation is None or annotation is inspect._empty:
        return None

    if is_serializable_type(annotation):
        properties: dict[str, Any] = {}
        required: list[str] = []

        for field in get_serializable_fields(annotation):
            if not field.public:
                continue

            field_schema = schema_for_annotation(field.annotation)

            if field_schema is None:
                field_schema = {}

            properties[field.name] = field_schema

            if not field.has_default:
                required.append(field.name)

        return {
            'type'       : 'object',
            'properties' : properties,
            'required'   : required
        }

    origin = get_origin(annotation)

    if annotation in (dict,) or origin is dict:
        args = get_args(annotation)
        value_type = args[1] if len(args) > 1 else Any
        value_schema = schema_for_annotation(value_type) or {}

        return {
            'type'                 : 'object',
            'additionalProperties' : value_schema
        }

    if annotation in (list,) or origin is list:
        args = get_args(annotation)
        item_type = args[0] if args else Any

        return {
            'type'  : 'array',
            'items' : schema_for_annotation(item_type) or {}
        }

    try:
        return TypeAdapter(annotation).json_schema()

    except Exception:
        return None
