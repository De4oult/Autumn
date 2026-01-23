from autumn.core.response.exception import HTTPException

from functools import wraps
from pydantic import BaseModel
from typing import get_origin, get_args, Type

def body(schema: Type):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = next((arg for arg in args if hasattr(arg, 'json') and callable(arg.json)), None)

            if request is None:
                raise HTTPException(500, details = 'Request object not found')
            
            try:
                raw = await request.body()

                if not raw or raw.strip() in (b'', b'null'):
                    raise HTTPException(400, details = 'Request body is empty')

                json_data = await request.json()
            
                origin = get_origin(schema)

                if origin is list:
                    inner_type = get_args(schema)[0]

                    if not issubclass(inner_type, BaseModel):
                        raise HTTPException(500, details = 'Invalid schema inside list')
                    
                    parsed_schema = [inner_type(**item) for item in json_data]

                else:
                    parsed_schema = schema(**json_data)

            except HTTPException:
                raise

            except Exception as error:
                raise HTTPException(400, details = f'Invalid request body: {str(error)}')
            
            if 'body' in kwargs:
                raise HTTPException(500, details = 'Parameter \'body\' already exists')

            return await func(*args, **kwargs, body = parsed_schema)
        
        return wrapper
    return decorator