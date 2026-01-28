# autumn/core/configuration/configuration.py
from __future__ import annotations

from typing import Any, Dict, List, Type, Set, get_origin, get_args, Annotated

from autumn.core.configuration.alias import Alias
from autumn.core.configuration.source import ConfigurationSource, SourceChain
from autumn.core.configuration.errors import AutumnConfigValueMissing, AutumnConfigCastError, AutumnConfigError
from autumn.core.configuration.casting import cast_value, MISSING
from autumn.core.configuration.maple import AliasMeta

CONFIG_REGISTRY: Set[Type['Configuration']] = set()
INTERNAL_FIELDS = {
    '__config_sources__',
    '__fields__',
    '__field_types__',
    '__aliases__'
}


def _split_annotated(annotation: Any) -> tuple[Any, list[Any]]:
    origin = get_origin(annotation)
    if origin is Annotated:
        args = list(get_args(annotation))
        return args[0], args[1:]
    return annotation, []


class ConfigurationMeta(type):
    def __new__(meta_cls, name, bases, namespace):
        cls = super().__new__(meta_cls, name, bases, namespace)

        inherited_sources: List[ConfigurationSource] = []
        for b in reversed(cls.__mro__[1:]):
            inherited_sources.extend(getattr(b, "__config_sources__", []))
        cls.__config_sources__ = list(inherited_sources)

        fields: Dict[str, Any] = {}
        field_types: Dict[str, Any] = {}
        field_aliases: Dict[str, Alias] = {}

        for b in reversed(cls.__mro__):
            annotations = getattr(b, "__annotations__", {}) or {}

            for field_name, annotation in annotations.items():
                if field_name in INTERNAL_FIELDS or field_name.startswith("_"):
                    continue

                fields[field_name] = annotation

                real_type, meta = _split_annotated(annotation)
                field_types[field_name] = real_type

                # Maple(...) => Annotated[T, AliasMeta(path)]
                for m in meta:
                    if isinstance(m, AliasMeta):
                        field_aliases[field_name] = Alias(path=m.path)
                    elif isinstance(m, Alias):
                        field_aliases[field_name] = m  # если кто-то положил Alias прямо в metadata

                # (опционально) старый стиль: field = Alias("x.y")
                maybe_value = getattr(b, "__dict__", {}).get(field_name, None)
                if isinstance(maybe_value, Alias):
                    field_aliases[field_name] = maybe_value

        cls.__fields__ = fields
        cls.__field_types__ = field_types
        cls.__aliases__ = field_aliases

        if name != "Configuration":
            CONFIG_REGISTRY.add(cls)

        return cls

class Configuration(metaclass=ConfigurationMeta):
    __config_sources__: List[ConfigurationSource] = []
    __fields__: Dict[str, Any] = {}
    __field_types__: Dict[str, Any] = {}
    __aliases__: Dict[str, Alias] = {}

    def __init__(self, **values: Any):
        for key, value in values.items():
            setattr(self, key, value)

    @classmethod
    @classmethod
    def build(cls) -> "Configuration":
        chain = SourceChain(
            name=f"{cls.__name__}.chain",
            sources=list(cls.__config_sources__),
        )

        values: Dict[str, Any] = {}

        for field_name, field_type in cls.__field_types__.items():
            has_default = hasattr(cls, field_name)
            default_value = getattr(cls, field_name) if has_default else MISSING

            if field_name in cls.__aliases__:
                alias = cls.__aliases__[field_name]
                raw = chain.get(alias.path)

                if raw is MISSING:
                    if has_default:
                        values[field_name] = default_value
                        continue

                    raise AutumnConfigValueMissing(
                        f"[{cls.__name__}.{field_name}] missing value for path '{alias.path}' "
                        f"from sources: {[s.name for s in chain.sources]}"
                    )

                try:
                    values[field_name] = cast_value(raw, field_type)
                except AutumnConfigCastError as error:
                    raise AutumnConfigError(
                        f"[{cls.__name__}.{field_name}] cannot cast path '{alias.path}' "
                        f"value={raw!r} to {field_type!r}"
                    ) from error

                continue

            if has_default:
                values[field_name] = default_value
                continue

            raise AutumnConfigValueMissing(
                f"[{cls.__name__}.{field_name}] has no Alias and no default value"
            )

        return cls(**values)


def get_registered_configs() -> List[Type[Configuration]]:
    return list(CONFIG_REGISTRY)
