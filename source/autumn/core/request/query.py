from typing import Any, Callable

class QueryBuilder:
    def __init__(self, cast_type: type):
        self.cast_type = cast_type

    def __call__(self, name: str, *, required: bool = False, default: Any = None):
        if required and default is not None:
            raise ValueError(f'Parameter \'{name}\' cannot be required and have default')

        def decorator(func: Callable):
            if not hasattr(func, '__query_parameters__'):
                func.__query_parameters__ = []

            func.__query_parameters__.append({
                'name'     : name,
                'type'     : self.cast_type,
                'required' : required,
                'default'  : default
            })

            return func

        return decorator