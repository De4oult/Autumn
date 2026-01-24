from autumn.core.response.response import JSONResponse

from functools import wraps
from typing import get_type_hints
from pydantic import BaseModel

def json_response(func):
    hints = get_type_hints(func)
    returns = hints.get('return')

    response_model = returns if isinstance(returns, type) and issubclass(returns, BaseModel) else None

    @wraps(func)
    async def wrapped(*args, **kwargs):
        result = await func(*args, **kwargs)

        if isinstance(result, BaseModel):
            return JSONResponse(result.model_dump(mode = 'json'))
        
        return result
    

    wrapped.__json_response__ = True
    wrapped.__response_model__ = response_model
    return wrapped