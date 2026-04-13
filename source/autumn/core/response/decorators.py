from typing import get_type_hints

def json_response(func):
    hints = get_type_hints(func)
    returns = hints.get('return')
    setattr(func, '__json_response__', True)
    setattr(func, '__response_model__', returns)
    return func
