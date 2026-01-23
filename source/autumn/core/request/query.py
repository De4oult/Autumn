from typing import Any
from uuid import UUID

class query:
    @staticmethod
    def _wrap(name: str, cast_type: type, required: bool, default: Any = None):
        def decorator(func):
            if required and default is not None:
                raise ValueError(f'Parameter \'{name}\' cannot be required and have default')

            if not hasattr(func, '__query_parameters__'):
                func.__query_parameters__ = []

            func.__query_parameters__.append({
                'name'     : name,
                'type'     : cast_type,
                'required' : required,
                'default'  : default
            })

            return func
        return decorator
    
    @staticmethod
    def string(name: str, required: bool = False, default: str = None):
        return query._wrap(name, str, required, default)
    
    @staticmethod
    def integer(name: str, required: bool = False, default: int = None):
        return query._wrap(name, int, required, default)
    
    @staticmethod
    def float(name: str, required: bool = False, default: float = None):
        return query._wrap(name, float, required, default)
    
    @staticmethod
    def uuid(name: str, required: bool = False, default: UUID = None):
        return query._wrap(name, UUID, required, default)