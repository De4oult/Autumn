from autumn.core.request.request import Request
from autumn.core.response.response import Response

from dataclasses import dataclass
from typing import Callable, Awaitable, List, Literal, Optional, Sequence

import inspect
import re

HTTPMethod = Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
RouteFilter = Optional[str | Sequence[str]]
MethodFilter = Optional[str | Sequence[str]]
MiddlewareFunc = Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]
AfterMiddlewareFunc = Callable[[Request, Response], Awaitable[Response] | Response | None]


@dataclass(frozen = True)
class MiddlewareEntry:
    func: MiddlewareFunc | AfterMiddlewareFunc
    path: tuple[str, ...]
    method: tuple[str, ...]
    patterns: tuple[re.Pattern[str], ...]


@dataclass(frozen = True)
class MiddlewarePlan:
    before: tuple[MiddlewareEntry, ...]
    after: tuple[MiddlewareEntry, ...]

    @property
    def is_empty(self) -> bool:
        return not self.before and not self.after

    async def execute(
        self,
        invoke: Callable[[Request], Awaitable[Response]],
        request: Request
    ) -> Response:
        async def run_before(index: int, current_request: Request) -> Response:
            if index == len(self.before):
                return await invoke(current_request)

            entry = self.before[index]

            async def next_call(next_request: Request) -> Response:
                return await run_before(index + 1, next_request)

            return await entry.func(current_request, next_call)

        response = await run_before(0, request)

        for entry in self.after:
            result = entry.func(request, response)

            if inspect.isawaitable(result):
                result = await result

            if result is not None:
                response = result

        return response


class MiddlewareManager:
    def __init__(self):
        self.before_middlewares: List[MiddlewareEntry] = []
        self.after_middlewares: List[MiddlewareEntry] = []
        self.__selection_cache: dict[tuple[str, str], MiddlewarePlan] = {}

    def __register(
        self,
        collection: List[MiddlewareEntry],
        func: MiddlewareFunc | AfterMiddlewareFunc,
        path: RouteFilter,
        method: MethodFilter
    ):
        paths = self.__normalize_filter_values(path)
        methods = tuple(value.upper() for value in self.__normalize_filter_values(method))

        collection.append(
            MiddlewareEntry(
                func     = func,
                path     = paths,
                method   = methods,
                patterns = tuple(self.__path_to_regex(value) for value in paths)
            )
        )
        
        self.__selection_cache.clear()

        return func

    def before(self, func: Optional[MiddlewareFunc] = None, *, path: RouteFilter = None, method: MethodFilter = None):
        if func is not None and callable(func):
            return self.__register(self.before_middlewares, func, path, method)

        def decorator(inner_func: MiddlewareFunc):
            return self.__register(self.before_middlewares, inner_func, path, method)

        return decorator
    
    def after(self, func: Optional[AfterMiddlewareFunc] = None, *, path: RouteFilter = None, method: MethodFilter = None):
        if func is not None and callable(func):
            return self.__register(self.after_middlewares, func, path, method)

        def decorator(inner_func: AfterMiddlewareFunc):
            return self.__register(self.after_middlewares, inner_func, path, method)
        
        return decorator

    @staticmethod
    def __normalize_filter_values(value: str | Sequence[str] | None) -> tuple[str, ...]:
        if value is None:
            return ()

        if isinstance(value, str):
            return (value,)

        return tuple(str(item) for item in value)
    
    @staticmethod
    def __path_to_regex(path: str) -> re.Pattern[str]:
        return re.compile('^' + re.sub(r'{[^}]+}', r'[^/]+', path.rstrip('/')) + '$')
    
    @staticmethod
    def __match(path: str, method: str, entry: MiddlewareEntry) -> bool:
        if entry.patterns and not any(pattern.match(path.rstrip('/')) for pattern in entry.patterns):
            return False
            
        if entry.method and method.upper() not in entry.method:
            return False
        
        return True

    def compile(self, path: str, method: str) -> MiddlewarePlan:
        key = (path, method.upper())

        if key in self.__selection_cache:
            return self.__selection_cache[key]

        before = tuple(
            entry
            for entry in self.before_middlewares
            if self.__match(path, method, entry)
        )
        after = tuple(
            entry
            for entry in self.after_middlewares
            if self.__match(path, method, entry)
        )

        plan = MiddlewarePlan(before = before, after = after)
        self.__selection_cache[key] = plan
        return plan

    def wrap(
        self,
        invoke: Callable[[Request], Awaitable[Response]], 
        path: str, 
        method: str
    ) -> Callable[[Request], Awaitable[Response]]:
        plan = self.compile(path, method)

        if plan.is_empty:
            return invoke

        async def wrapped(request: Request) -> Response:
            return await plan.execute(invoke, request)

        return wrapped
