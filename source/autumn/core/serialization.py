from __future__ import annotations
from pydantic import BaseModel, TypeAdapter
from typing import Annotated, Any, TypeVar, get_args, get_origin
from dataclasses import dataclass

import textwrap
import inspect
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


def _safe_get_annotations(target: Any, namespace: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return inspect.get_annotations(
            target,
            eval_str = True,
            globals  = namespace,
            locals   = namespace
        )

    except Exception:
        return getattr(target, '__annotations__', {}) or {}


def _collect_class_level_fields(cls: type) -> list[SerializableField]:
    fields: list[SerializableField] = []

    for base in reversed(cls.__mro__):
        if base is object:
            continue

        annotations = _safe_get_annotations(base, _build_annotation_context(base))

        for name, annotation in annotations.items():
            _, visibility = _unwrap_annotated(annotation)
            
            fields.append(
                SerializableField(
                    name       = name,
                    annotation = annotation,
                    public     = (
                        True
                        if visibility is None 
                        else visibility.public
                    )
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
            annotation = eval(
                compile(ast.Expression(node.annotation), '<autumn-serializable>', 'eval'),
                namespace,
                namespace
            )

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
                )
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


def serializable(cls: type[T]) -> type[T]:
    setattr(cls, '__autumn_serializable__', True)
    setattr(
        cls,
        '__autumn_serializable_fields__',
        _merge_fields(
            _collect_class_level_fields(cls),
            _collect_instance_fields_from_init(cls)
        )
    )

    return cls


def is_serializable_type(annotation: Any) -> bool:
    annotation, _ = _unwrap_annotated(annotation)

    return isinstance(annotation, type) and bool(getattr(annotation, '__autumn_serializable__', False))


def is_serializable_instance(value: Any) -> bool:
    return is_serializable_type(type(value))


def serialize_instance(value: Any) -> dict[str, Any]:
    field_map = {field.name: field for field in get_serializable_fields(type(value))}
    payload: dict[str, Any] = {}

    for name, field_value in vars(value).items():
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
