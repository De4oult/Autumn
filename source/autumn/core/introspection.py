from __future__ import annotations

from autumn.core.response.response import Response

from dataclasses import dataclass
from pydantic import BaseModel
from typing import Annotated, Any, Callable, Optional, get_args, get_origin

import inspect


@dataclass(frozen = True)
class BodyParameter:
    name: str
    annotation: Any
    required: bool
    default: Any = inspect.Parameter.empty


def unwrap_annotated(annotation: Any) -> Any:
    current = annotation

    while get_origin(current) is Annotated:
        args = get_args(current)

        if not args:
            break

        current = args[0]

    return current


def annotation_contains_pydantic_model(annotation: Any) -> bool:
    annotation = unwrap_annotated(annotation)

    if annotation is None or annotation is inspect._empty:
        return False

    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True

    origin = get_origin(annotation)

    if origin is None:
        return False

    return any(
        argument is not type(None) and annotation_contains_pydantic_model(argument)
        for argument in get_args(annotation)
    )


def annotation_is_response(annotation: Any) -> bool:
    annotation = unwrap_annotated(annotation)

    return isinstance(annotation, type) and issubclass(annotation, Response)


def value_contains_pydantic_model(value: Any) -> bool:
    if isinstance(value, BaseModel):
        return True

    if isinstance(value, dict):
        return any(value_contains_pydantic_model(item) for item in value.values())

    if isinstance(value, (list, tuple, set, frozenset)):
        return any(value_contains_pydantic_model(item) for item in value)

    return False


def get_declared_body_parameter(
    callable: Callable[..., Any],
    *,
    provided_kwargs: Optional[dict[str, Any]] = None,
    skip_self: bool = False,
    can_resolve_dependency: Optional[Callable[[Any], bool]] = None
) -> Optional[BodyParameter]:
    provided_kwargs = provided_kwargs or {}

    signature = inspect.signature(callable)
    hints = inspect.get_annotations(callable, eval_str = True)

    explicit_schema = getattr(callable, '__body_schema__', None)
    explicit_candidates: list[BodyParameter] = []
    implicit_candidates: list[BodyParameter] = []

    for name, parameter in signature.parameters.items():
        if skip_self and name == 'self':
            continue

        if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue

        if name in provided_kwargs:
            continue

        annotation = hints.get(name, inspect._empty)

        if explicit_schema is not None:
            if name == 'body' or annotation == explicit_schema:
                explicit_candidates.append(
                    BodyParameter(
                        name       = name,
                        annotation = explicit_schema,
                        required   = parameter.default is inspect.Parameter.empty,
                        default    = parameter.default
                    )
                )
                continue

        if annotation is inspect._empty:
            continue

        if can_resolve_dependency is not None and can_resolve_dependency(annotation):
            continue

        if annotation_contains_pydantic_model(annotation):
            implicit_candidates.append(
                BodyParameter(
                    name = name,
                    annotation = annotation,
                    required = parameter.default is inspect.Parameter.empty,
                    default = parameter.default
                )
            )

    if len(explicit_candidates) > 1:
        raise RuntimeError(f'Only one request body parameter is supported for {callable}')

    if explicit_candidates:
        return explicit_candidates[0]

    if len(implicit_candidates) > 1:
        raise RuntimeError(f'Only one request body parameter is supported for {callable}')

    if implicit_candidates:
        return implicit_candidates[0]

    return None
