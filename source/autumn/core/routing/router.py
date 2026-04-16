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
        self.routes_by_method: dict[str, list[Route]] = {}

    def reset(self) -> None:
        self.routes.clear()
        self.routes_by_method.clear()
        
    def add_route(self, method: str, path: str, handler: Callable) -> None:
        route = Route(method, path, handler)

        self.routes.append(route)
        self.routes_by_method.setdefault(route.method, []).append(route)

    def add_websocket_route(self, path: str, handler: Callable) -> None:
        self.add_route('WS', path, handler)

    def match(self, method: str, path: str) -> Optional[RouteMatch]:
        method_key = method.upper()

        for route in self.routes_by_method.get(method_key, []):
            result = route.match(method_key, path)

            if result is not None:
                _, parameters = result

                return RouteMatch(
                    route      = route,
                    handler    = route.handler,
                    parameters = parameters
                )
            
        return None
    
    def match_websocket(self, path: str) -> Optional[RouteMatch]:
        return self.match('WS', path)
    
    def get_routes(self) -> List[Route]:
        return list(self.routes)
