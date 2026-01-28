from autumn.core.configuration.errors import AutumnConfigCastError

from typing import Any, get_args, get_origin, Union
from uuid import UUID

MISSING = object()

def deep_get(data: Any, path: str) -> Any:
    current = data

    for part in path.split('.'):
        if current is None:
            return MISSING

        if isinstance(current, list):
            if not part.isdigit():
                return MISSING

            index = int(part)

            if index < 0 or index >= len(current):
                return MISSING
            
            current = current[index]
            continue

        if isinstance(current, dict):
            if part not in current:
                return MISSING

            current = current[part]
            continue

        return MISSING

    return current

def cast_value(raw: Any, target_type: Any) -> Any:
    origin = get_origin(target_type)
    arguments = get_args(target_type)

    if origin is Union and len(arguments) == 2 and type(None) in arguments:
        inner = (
            arguments[0] 
            if arguments[1] is type(None) 
            else arguments[1]
        )

        if raw is None:
            return None
        
        return cast_value(raw, inner)

    if origin is list:
        (inner, ) = arguments
        
        if raw is None:
            raise AutumnConfigCastError(f'Expected list, got None')
        
        if not isinstance(raw, list):
            raise AutumnConfigCastError(f'Expected list, got {type(raw).__name__}')
        
        return [cast_value(x, inner) for x in raw]

    if origin is dict:
        key_t, value_t = arguments

        if raw is None:
            raise AutumnConfigCastError(f'Expected dict, got None')
        
        if not isinstance(raw, dict):
            raise AutumnConfigCastError(f'Expected dict, got {type(raw).__name__}')
        
        return {
            cast_value(key, key_t) : cast_value(value, value_t) 
            for key, value in raw.items()
        }

    if target_type is UUID:
        if isinstance(raw, UUID):
            return raw

        if not isinstance(raw, str):
            raise AutumnConfigCastError(f'Expected UUID str, got {type(raw).__name__}')

        return UUID(raw)

    if target_type is bool:
        if isinstance(raw, bool):
            return raw

        if isinstance(raw, (int, float)):
            return bool(raw)

        if isinstance(raw, str):
            v = raw.strip().lower()

            if v in ('1', 'true', 'yes', 'y', 'on'):
                return True

            if v in ('0', 'false', 'no', 'n', 'off'):
                return False
            
        raise AutumnConfigCastError(f'Cannot cast {raw!r} to bool')

    if target_type in (int, float, str):
        try:
            return target_type(raw)
        
        except Exception as e:
            raise AutumnConfigCastError(f'Cannot cast {raw!r} to {target_type}') from e

    try:
        if isinstance(raw, target_type):
            return raw
        
    except Exception:
        pass

    if target_type is Any:
        return raw

    raise AutumnConfigCastError(f'Unsupported target type: {target_type!r}')
