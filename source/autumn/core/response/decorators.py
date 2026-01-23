from autumn.core.response.response import JSONResponse

from functools import wraps
from pydantic import BaseModel

def json_response(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)

        if isinstance(result, BaseModel):
            return JSONResponse(result.model_dump(mode = 'json'))
        
        return result
    return wrapper