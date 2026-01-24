import ast
import inspect
from typing import Callable, Any, Dict, List, Optional, Type

from autumn.core.response.response import JSONResponse
from pydantic import BaseModel

PYTYPE_TO_SCHEMA = {
    int:   { 'type' : 'integer' },
    str:   { 'type' : 'string'  },
    float: { 'type' : 'number'  },
    bool:  { 'type' : 'boolean' }
}

TYPENAME_TO_SCHEMA = {
    'int'   : { 'type' : 'integer' },
    'str'   : { 'type' : 'string' },
    'float' : { 'type' : 'number' },
    'bool'  : { 'type' : 'boolean' },
    'uuid'  : { 'type' : 'string', 'format': 'uuid' }
}

class OpenAPIGenerator:
    def __init__(
        self, 
        *, 
        title: str = 'Autumn API', 
        version: str = '0.1.0'
    ):
        self.title = title
        self.version = version

    def generate(self, app) -> dict:
        paths: Dict[str, Any] = {}

        tags = []
        seen = set()

        for route in app.router.get_routes():
            if not (isinstance(route.handler, tuple) and len(route.handler) == 2 and isinstance(route.handler[1], str)):
                continue

            controller_class, method_name = route.handler
            method_object = getattr(controller_class, method_name)

            openapi_path = route.openapi_path
            http_method = route.method.lower()

            operation = self.build_operation(
                route            = route,
                controller_class = controller_class,
                method_name      = method_name,
                method_object    = method_object
            )

            paths.setdefault(openapi_path, {})
            paths[openapi_path][http_method] = operation
            
            tag = getattr(controller_class, '__tag__', None) or controller_class.__name__.removesuffix('Controller')

            if tag not in seen:
                seen.add(tag)
                description = getattr(controller_class, '__description__', None)

                tags.append({
                    'name': tag, 
                    **({ 'description': description } if description else {})
                })

        info = {
            'title'       : getattr(app, 'name', None) or self.title,
            'version'     : getattr(app, 'version', None) or self.version,
            'description' : getattr(app, 'description', None) or 'Modern web-application powered by Autumn Framework'
        }

        return {
            'openapi': '3.0.3',
            'info': info,
            'paths': paths,
            'tags' : tags
        }

    def get_tags(self, controller_class: Type[Any]) -> List[str]:
        return [getattr(controller_class, '__tag__', None) or controller_class.__name__.removesuffix('Controller')]

    def get_operation_id(self, controller_class: Type[Any], method_name: str, http_method: str, path: str) -> str:
        return f'{controller_class.__name__}.{method_name}:{http_method}:{path}'

    def __get_attribute_chain(self, object, name, default=None):
        if hasattr(object, name):
            return getattr(object, name)
        
        current = object

        while hasattr(current, '__wrapped__'):
            current = current.__wrapped__

            if hasattr(current, name):
                return getattr(current, name)
            
        return default

    def build_operation(self, *, route, controller_class: Type[Any], method_name: str, method_object: Any) -> dict:
        parameters = []
        parameters.extend(self.__build_path_parameters(route))
        parameters.extend(self.__build_query_parameters(method_object))

        request_body = self.__build_request_body(method_object)
        contoller_tag = getattr(controller_class, '__tag__', None) or controller_class.__name__.removesuffix('Controller')

        method_summary = self.__get_attribute_chain(method_object, '__summary__', None)
        method_description    = self.__get_attribute_chain(method_object, '__description__', None)
        method_tags = self.__get_attribute_chain(method_object, '__tags__', []) or []
        operation_tags = [contoller_tag, *method_tags] if method_tags else [contoller_tag]
        
        responses = self._build_responses(route, controller_class, method_name, method_object)

        operation = {
            'operationId' : self.get_operation_id(controller_class, method_name, route.method.lower(), route.openapi_path),
            'parameters'  : parameters,
            'responses'   : responses,
            'summary'     : method_summary or method_name,
            'description' : method_description or None,
            'tags'        : operation_tags
        }

        if request_body is not None:
            operation['requestBody'] = request_body

        if method_description:
            operation['description'] = method_description

        if operation['description'] is None:
            operation.pop('description')

        return operation

    def __build_path_parameters(self, route) -> list[dict]:
        parameters = []

        for name, typ_name in zip(route.parameters, route.parameters_types_names):
            schema = TYPENAME_TO_SCHEMA.get(typ_name, { 'type': 'string' })

            parameters.append({
                'name'     : name,
                'in'       : 'path',
                'required' : True,
                'schema'   : schema
            })

        return parameters

    def __build_query_parameters(self, method_object: Any) -> list[dict]:
        query_meta = getattr(method_object, '__query_parameters__', [])

        parameters = []

        for query in query_meta:
            name        = query.get('name')
            python_type = query.get('type', str)
            required    = bool(query.get('required', False))
            default     = query.get('default', None)

            schema = PYTYPE_TO_SCHEMA.get(python_type, { 'type': 'string' })

            if default is not None:
                schema = dict(schema)
                schema['default'] = default

            parameters.append({
                'name'     : name,
                'in'       : 'query',
                'required' : required,
                'schema'   : schema
            })

        return parameters

    def __build_request_body(self, method_object: Any) -> Optional[dict]:
        body_model = self.__get_attribute_chain(method_object, '__body_schema__', None)

        if body_model is None:
            return None

        if inspect.isclass(body_model) and issubclass(body_model, BaseModel):
            return {
                'required' : True,
                'content'  : {
                    'application/json' : {
                        'schema': body_model.model_json_schema()
                    }
                }
            }

        # add later special response classes

        return None

    def __build_responses(self, route, controller_class: Type[Any], method_name: str, method_object: Any) -> dict:
        responses: Dict[str, Any] = {}

        is_json_response = bool(self.__get_attribute_chain(method_object, '__json_response__', False))
        response_model = self.__get_attribute_chain(method_object, '__response_model__', None)
        returns = inspect.signature(method_object).return_annotation

        responses['200'] = { 'description': 'Success' }

        if getattr(method_object, '__query_parameters__', []):
            responses.setdefault('400', { 'description': 'Bad Request' })
            
        if self.__get_attribute_chain(method_object, '__body_schema__', None) is not None:
            responses.setdefault('422', { 'description': 'Validation Error' })

        responses.setdefault('500', { 'description': 'Internal Server Error' })

        for code in self.__extract_http_exception_statuses(method_object):
            responses.setdefault(str(code), { 'description': f'HTTP {code}' })

        if is_json_response:
            if response_model and inspect.isclass(response_model) and issubclass(response_model, BaseModel):
                schema = response_model.model_json_schema()

            else:
                schema = self.__infer_json_response_schema(method_object)

            if schema is not None:
                responses['200'] = {
                    'description' : 'OK',
                    'content'     : { 'application/json' : { 'schema': schema } },
                }

                return responses

        if returns is not inspect._empty and returns is JSONResponse:
            responses['200'] = {
                'description' : 'OK',
                'content'     : { 'application/json': { 'schema': { 'type' : 'object' } } },
            }

        return responses

    def __infer_json_response_schema(self, method_object: Any) -> Optional[dict]:
        try:
            signature = inspect.signature(method_object)
            returns = signature.return_annotation

        except Exception:
            return None

        if returns is inspect._empty:
            return None

        if inspect.isclass(returns) and issubclass(returns, BaseModel):
            return returns.model_json_schema()

        return None

    def __extract_http_exception_statuses(self, method_object: Any) -> set[int]:
        try:
            target = self.__unwrap(method_object) 
            source = inspect.getsource(target)

        except Exception:
            return set()

        try:
            tree = ast.parse(source)
            print(tree)

        except SyntaxError:
            return set()

        statuses: set[int] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                code = self.__try_parse_http_exception_status(node.exc)

                if code is not None:
                    statuses.add(code)

        return statuses

    def __try_parse_http_exception_status(self, exception_node: ast.AST) -> Optional[int]:
        if not isinstance(exception_node, ast.Call):
            return None

        func = exception_node.func
        func_name = None

        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name != 'HTTPException':
            return None

        if exception_node.args:
            first = exception_node.args[0]

            if isinstance(first, ast.Constant) and isinstance(first.value, int):
                return int(first.value)

        for keyword in exception_node.keywords:
            if keyword.arg == 'status_code':
                value = keyword.value

                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return int(value.value)

        return None

    def __unwrap(self, callable_object: Callable):
        while hasattr(callable_object, '__wrapped__'):
            callable_object = callable_object.__wrapped__

        return callable_object
