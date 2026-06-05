from enum import Enum
from typing import Any

class Environment(str, Enum):
    LOCAL = 'local'
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'

class Theme(str, Enum):
    LIGHT = 'light'
    DARK = 'dark'


def _normalize_environment(value: Environment | str) -> Environment:
    if isinstance(value, Environment):
        return value

    return Environment(str(value))


def only(*environments: Environment | str):
    if not environments:
        raise ValueError('@only requires at least one environment')

    allowed_on = tuple(_normalize_environment(environment) for environment in environments)

    def decorator(obj: Any) -> Any:
        setattr(obj, '__autumn_only_environments__', allowed_on)
        return obj

    return decorator
