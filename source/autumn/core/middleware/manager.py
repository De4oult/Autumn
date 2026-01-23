from autumn.core.request.request import Request
from autumn.core.response.response import Response

from typing import Callable, Awaitable, List, Literal, Optional, Tuple

import re

HTTPMethod = Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
MiddlewareFunc = Callable[[Request, Callable[..., Awaitable[Response]]], Awaitable[Response]]

class MiddlewareManager:
    def __init__(self):
        self.before_middlewares: List[Tuple[MiddlewareFunc, Optional[str], Optional[str]]] = []
        self.after_middlewares: List[Tuple[MiddlewareFunc, Optional[str], Optional[str]]] = []

    def before(self, func: Optional[MiddlewareFunc] = None, *, path: Optional[str] = None, method: Optional[HTTPMethod] = None):
        if func is not None and callable(func):
            self.before_middlewares.append((func, path, method))

            return func

        def decorator(inner_func: MiddlewareFunc):
            self.before_middlewares.append((inner_func, path, method))

            return inner_func

        return decorator
    
    def after(self, func: Optional[MiddlewareFunc] = None, *, path: Optional[str] = None, method: Optional[HTTPMethod] = None):
        if func is not None and callable(func):
            self.after_middlewares.append((func, path, method))
            
            return func

        def decorator(inner_func: MiddlewareFunc):
            self.after_middlewares.append((inner_func, path, method))
            
            return inner_func
        
        return decorator
    
    @staticmethod
    def __path_to_regex(path: str) -> str:
        return '^' + re.sub(r'{[^}]+}', r'[^/]+', path.rstrip('/')) + '$'
    
    def __match(self, request: Request, path: Optional[str], method: Optional[str]) -> bool:
        if path is not None:
            pattern = self.__path_to_regex(path)

            if not re.match(pattern, request.path.rstrip('/')):
                return False
            
        if method is not None and method != request.method:
            return False
        
        return True

    async def wrap(self, handler: Callable[..., Awaitable[Response]], path: str, method: str) -> Callable[[Request], Awaitable[Response]]:
        async def wrapped(*args, **kwargs):
            request = kwargs.pop('request', None)

            if (not request) and args and isinstance(args[0], Request):
                request = args[0]

            if request is None:
                raise RuntimeError('Request not found in middleware context')

            async def final_handler(__request: Request):
                if args and isinstance(args[0], Request):
                    return await handler(*args, **kwargs)
                else:
                    return await handler(*args, request = __request, **kwargs)

            # before
            call_next = final_handler
            
            for middleware_function, middleware_path, middleware_method in reversed(self.before_middlewares):
                if self.__match(request, middleware_path, middleware_method):
                    call_next = self.__wrap_before_middleware(middleware_function, call_next)

            response = await call_next(request)

            # after
            for middleware_function, middleware_path, middleware_method in self.after_middlewares:
                if self.__match(request, middleware_path, middleware_method):
                    async def call_next(_: Request) -> Response:
                        return await self.__return_response(response)
                
                    response = await middleware_function(request, call_next)

            return response

        return wrapped
    
    async def __return_response(self, response: Response) -> Response:
        return response

    def __wrap_before_middleware(self, middleware: MiddlewareFunc, next_call: Callable[[Request], Awaitable[Response]]) -> Callable[[Request], Awaitable[Response]]:
        async def wrapped(req: Request):
            return await middleware(req, next_call)
        
        return wrapped