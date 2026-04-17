from autumn.core.request.request import Request
from autumn.core.response.response import Response

from dataclasses import dataclass
from typing import Callable, Awaitable, List, Literal, Optional

import re

HTTPMethod = Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
MiddlewareFunc = Callable[[Request, Callable[..., Awaitable[Response]]], Awaitable[Response]]


@dataclass(frozen = True)
class MiddlewareEntry:
    func: MiddlewareFunc
    path: Optional[str]
    method: Optional[str]
    pattern: Optional[re.Pattern[str]]


class MiddlewareManager:
    def __init__(self):
        self.before_middlewares: List[MiddlewareEntry] = []
        self.after_middlewares: List[MiddlewareEntry] = []
        self.__selection_cache: dict[tuple[str, str], tuple[list[MiddlewareEntry], list[MiddlewareEntry]]] = {}

    def __register(
        self,
        collection: List[MiddlewareEntry],
        func: MiddlewareFunc,
        path: Optional[str],
        method: Optional[str]
    ) -> MiddlewareFunc:
        collection.append(
            MiddlewareEntry(
                func = func,
                path = path,
                method = method,
                pattern = self.__path_to_regex(path) if path is not None else None
            )
        )
        
        self.__selection_cache.clear()

        return func

    def before(self, func: Optional[MiddlewareFunc] = None, *, path: Optional[str] = None, method: Optional[HTTPMethod] = None):
        if func is not None and callable(func):
            return self.__register(self.before_middlewares, func, path, method)

        def decorator(inner_func: MiddlewareFunc):
            return self.__register(self.before_middlewares, inner_func, path, method)

        return decorator
    
    def after(self, func: Optional[MiddlewareFunc] = None, *, path: Optional[str] = None, method: Optional[HTTPMethod] = None):
        if func is not None and callable(func):
            return self.__register(self.after_middlewares, func, path, method)

        def decorator(inner_func: MiddlewareFunc):
            return self.__register(self.after_middlewares, inner_func, path, method)
        
        return decorator
    
    @staticmethod
    def __path_to_regex(path: str) -> re.Pattern[str]:
        return re.compile('^' + re.sub(r'{[^}]+}', r'[^/]+', path.rstrip('/')) + '$')
    
    @staticmethod
    def __match(path: str, method: str, entry: MiddlewareEntry) -> bool:
        if entry.pattern is not None and not entry.pattern.match(path.rstrip('/')):
            return False
            
        if entry.method is not None and entry.method != method:
            return False
        
        return True

    def __select(self, path: str, method: str) -> tuple[list[MiddlewareEntry], list[MiddlewareEntry]]:
        key = (path, method)

        if key in self.__selection_cache:
            return self.__selection_cache[key]

        before = [
            entry
            for entry in self.before_middlewares
            if self.__match(path, method, entry)
        ]
        after = [
            entry
            for entry in self.after_middlewares
            if self.__match(path, method, entry)
        ]

        self.__selection_cache[key] = (before, after)
        return before, after

    def wrap(
        self,
        invoke: Callable[[Request], Awaitable[Response]], 
        path: str, 
        method: str
    ) -> Callable[[Request], Awaitable[Response]]:
        selected_before, selected_after = self.__select(path, method)

        if not selected_before and not selected_after:
            return invoke

        async def wrapped(request: Request) -> Response:
            call_next = invoke
            
            for entry in reversed(selected_before):
                call_next = self.__wrap_before_middleware(entry.func, call_next)

            response = await call_next(request)

            for entry in selected_after:
                async def call_next(_: Request) -> Response:
                    return response
            
                response = await entry.func(request, call_next)

            return response

        return wrapped
    
    def __wrap_before_middleware(self, middleware: MiddlewareFunc, next_call: Callable[[Request], Awaitable[Response]]) -> Callable[[Request], Awaitable[Response]]:
        async def wrapped(req: Request):
            return await middleware(req, next_call)
        
        return wrapped
