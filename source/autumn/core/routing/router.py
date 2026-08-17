from typing import Callable, Optional, List, Type, Any, Dict
from dataclasses import dataclass
from uuid import UUID

import re

_type_map = {
    'int'   : int,
    'str'   : str,
    'float' : float,
    'uuid'  : UUID,
    'path'  : str
}

_regex_map = {
    'int'   : r'\d+',
    'str'   : r'[^/]+',
    'float' : r'[0-9]*\.[0-9]+',
    'uuid'  : r'[0-9a-fA-F-]{36}',
    'path'  : r'.+'
}

class Route:
    def __init__(self, method: str, path_template: str, handler: Callable) -> None:
        self.method = method.upper()
        self.path_template = path_template
        self.handler = handler
        self.execution_plan = None
        self.is_static = '{' not in self.path_template and '}' not in self.path_template
        
        parameter_offset = self.path_template.find('{')
        literal_prefix = (
            self.path_template[:parameter_offset].rstrip('/')
            if parameter_offset >= 0
            else self.path_template.rstrip('/')
        )

        self.dynamic_prefix = literal_prefix or None

        self.static_path = Router.normalize_static_path(self.path_template) if self.is_static else None
        
        (
            self.pattern, 
            self.parameters, 
            self.parameters_types,
            self.parameters_types_names,
            self.openapi_path    
        ) = self.__compile_path(self.path_template)

    def __compile_path(self, path_template: str):
        parts = path_template.strip('/').split('/')
        pattern = ''
        
        parameters: List[str] = []
        parameters_types: List[Type[Any]] = []
        parameters_types_names: List[str] = []
        openapi_parts: List[str] = []

        for (index, part) in enumerate(parts):
            is_last: int = index == len(parts) - 1

            if part.startswith('{') and part.endswith('}'):
                __name_type = part[1:-1].split(':')
                __name = __name_type[0]
                __type = __name_type[1] if len(__name_type) > 1 else 'str'

                if __type == 'path' and not is_last:
                    raise ValueError('{path:path} parameter must be the last path segment')

                parameters.append(__name)
                parameter_type = _type_map.get(__type, str)
                parameters_types.append(parameter_type)
                parameters_types_names.append(__type)

                regex_part = _regex_map.get(__type, r'[^/]+')
                pattern += f'/(?P<{__name}>{regex_part})'

                openapi_parts.append(f'{{{__name}}}')
                
            else:
                pattern += f'/{part}'
                openapi_parts.append(part)

        regex = re.compile(f'^{pattern}/?$')
        openapi_path = '/' + '/'.join(openapi_parts) if openapi_parts else '/'

        return regex, parameters, parameters_types, parameters_types_names, openapi_path
    
    def match(self, method: str, path: str) -> Optional[tuple[Callable, dict[str, Any]]]:
        if self.method != method.upper():
            return None
        
        match = self.pattern.match(path)

        if not match:
            return None
        
        raw_parameters = match.groupdict()
        casted: Dict[str, Any] = {}

        for name, cast in zip(self.parameters, self.parameters_types):
            try:
                casted[name] = cast(raw_parameters[name])
        
            except Exception:
                return None

        return self.handler, casted


@dataclass(frozen = True)
class RouteMatch:
    route: Route
    handler: Callable
    parameters: Dict[str, Any]
        
class Router:
    def __init__(self):
        self.routes: list[Route] = []
        self.dynamic_routes_by_method: dict[str, list[Route]] = {}
        self.dynamic_routes_by_method_prefix: dict[str, dict[str, list[Route]]] = {}
        self.dynamic_fallback_routes_by_method: dict[str, list[Route]] = {}
        self.static_routes_by_method: dict[str, dict[str, Route]] = {}

    @staticmethod
    def normalize_static_path(path: str) -> str:
        value = str(path or '/')

        if value == '/':
            return '/'

        return value.rstrip('/') or '/'

    def reset(self) -> None:
        self.routes.clear()
        self.dynamic_routes_by_method.clear()
        self.dynamic_routes_by_method_prefix.clear()
        self.dynamic_fallback_routes_by_method.clear()
        self.static_routes_by_method.clear()
        
    def add_route(self, method: str, path: str, handler: Callable) -> None:
        route = Route(method, path, handler)

        self.routes.append(route)

        if route.is_static:
            self.static_routes_by_method.setdefault(route.method, {})[route.static_path] = route
            return

        self.dynamic_routes_by_method.setdefault(route.method, []).append(route)

        if route.dynamic_prefix is None:
            self.dynamic_fallback_routes_by_method.setdefault(route.method, []).append(route)

        else:
            self.dynamic_routes_by_method_prefix.setdefault(route.method, {}).setdefault(
                route.dynamic_prefix,
                []
            ).append(route)

    def add_websocket_route(self, path: str, handler: Callable) -> None:
        self.add_route('WS', path, handler)

    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        method_key = method.upper()
        static_path = self.normalize_static_path(path)
        static_route = self.static_routes_by_method.get(method_key, {}).get(static_path)

        if static_route is not None:
            return RouteMatch(
                route      = static_route,
                handler    = static_route.handler,
                parameters = {}
            )

        prefix_routes = self.dynamic_routes_by_method_prefix.get(method_key, {})
        fallback = self.dynamic_fallback_routes_by_method.get(method_key, ())
        normalized_path = path.rstrip('/') or '/'
        probe = normalized_path

        while True:
            separator = probe.rfind('/')

            if separator <= 0:
                break

            probe = probe[:separator]
            candidates = prefix_routes.get(probe, ())

            for route in candidates:
                result = route.match(method_key, path)

                if result is not None:
                    _, parameters = result

                    return RouteMatch(
                        route      = route,
                        handler    = route.handler,
                        parameters = parameters
                    )

        for route in fallback:
            result = route.match(method_key, path)

            if result is not None:
                _, parameters = result

                return RouteMatch(
                    route      = route,
                    handler    = route.handler,
                    parameters = parameters
                )
            
        return None

    def allowed_methods(self, path: str) -> tuple[str, ...]:
        allowed: set[str] = set()

        for route in self.routes:
            if route.method == 'WS':
                continue

            if route.match(route.method, path) is not None:
                allowed.add(route.method)

        return tuple(sorted(allowed))
    
    def match_websocket(self, path: str) -> Optional[RouteMatch]:
        return self.match('WS', path)
    
    def get_routes(self) -> List[Route]:
        return list(self.routes)
