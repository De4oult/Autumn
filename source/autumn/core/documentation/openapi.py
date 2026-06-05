import ast
import inspect
import textwrap
from autumn.core.introspection import (
    annotation_contains_pydantic_model,
    annotation_is_response,
    get_declared_body_parameter
)
from autumn.core.serialization import annotation_supports_json_response, schema_for_annotation
from typing import Callable, Any, Dict, List, Optional, Type
from uuid import UUID

from autumn.core.response.response import JSONResponse, Response


JSON_MEDIA_TYPE = 'application/json'

HTTP_EXCEPTION_SCHEMA = {
    'type'       : 'object',
    'properties' : {
        'status'  : { 'type' : 'integer' },
        'title'   : { 'type' : 'string' },
        'details' : { 'type' : 'string' }
    },
    'required' : ['status', 'title', 'details']
}

PYTYPE_TO_SCHEMA = {
    int:   { 'type' : 'integer' },
    str:   { 'type' : 'string'  },
    float: { 'type' : 'number'  },
    bool:  { 'type' : 'boolean' },
    UUID:  { 'type' : 'string', 'format': 'uuid' }
}

TYPENAME_TO_SCHEMA = {
    'int'   : { 'type' : 'integer' },
    'str'   : { 'type' : 'string' },
    'float' : { 'type' : 'number' },
    'bool'  : { 'type' : 'boolean' },
    'uuid'  : { 'type' : 'string', 'format': 'uuid' }
}

DEPRECATED_TAG_NAMES = {'deprecated', 'depricated', 'depr'}


def _normalize_tag_name(value: Any) -> str:
    tag = str(value).strip()

    if tag.lower() in DEPRECATED_TAG_NAMES:
        return 'Deprecated'

    return tag


def _docstring_parts(obj: Any) -> tuple[Optional[str], Optional[str]]:
    docstring = inspect.getdoc(obj) or ''

    if not docstring.strip():
        return None, None

    lines   = docstring.splitlines()
    summary = (lines[0].strip() if lines else None) or None
    body    = '\n'.join(lines[1:]).strip() or None

    return summary, body

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
        if hasattr(app, 'get_registered_controller_classes'):
            app.get_registered_controller_classes()

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
                _, doc_body = _docstring_parts(controller_class)
                description = getattr(controller_class, '__description__', None) or doc_body

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

        request_body  = self.__build_request_body(method_object)
        contoller_tag = getattr(controller_class, '__tag__', None) or controller_class.__name__.removesuffix('Controller')

        doc_summary, doc_description = _docstring_parts(method_object)

        method_summary     = self.__get_attribute_chain(method_object, '__summary__', None)
        method_description = self.__get_attribute_chain(method_object, '__description__', None)
        method_tags        = self.__get_attribute_chain(method_object, '__tags__', []) or []
        operation_tags     = []

        for tag in [contoller_tag, *method_tags] if method_tags else [contoller_tag]:
            normalized_tag = _normalize_tag_name(tag)

            if normalized_tag and normalized_tag not in operation_tags:
                operation_tags.append(normalized_tag)
        
        responses = self.__build_responses(route, controller_class, method_name, method_object)

        operation = {
            'operationId' : self.get_operation_id(controller_class, method_name, route.method.lower(), route.openapi_path),
            'parameters'  : parameters,
            'responses'   : responses,
            'summary'     : method_summary or doc_summary or method_name,
            'description' : method_description or doc_description or None,
            'tags'        : operation_tags
        }

        if any(str(tag).strip().lower() in DEPRECATED_TAG_NAMES for tag in operation_tags):
            operation['deprecated'] = True

        if request_body is not None:
            operation['requestBody'] = request_body

        if method_description:
            operation['description'] = method_description

        elif doc_description:
            operation['description'] = doc_description
            
        else:
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
        try:
            body_parameter = get_declared_body_parameter(method_object, skip_self = True)

        except RuntimeError:
            return None

        if body_parameter is None:
            return None

        schema = self.__schema_for_annotation(body_parameter.annotation)

        if schema is None:
            return None

        return {
            'required' : body_parameter.required,
            'content'  : {
                'application/json' : {
                    'schema': schema
                }
            }
        }

    def __build_responses(self, route, controller_class: Type[Any], method_name: str, method_object: Any) -> dict:
        responses: Dict[str, Any] = {}

        returns = inspect.signature(method_object).return_annotation
        is_json_response = bool(self.__get_attribute_chain(method_object, '__json_response__', False))
        auto_json_response = (
            returns is not inspect._empty
            and not annotation_is_response(returns)
            and (
                annotation_contains_pydantic_model(returns)
                or annotation_supports_json_response(returns)
            )
        )
        response_model = self.__get_attribute_chain(method_object, '__response_model__', None) or returns

        responses['200'] = { 'description': 'Success' }

        if getattr(method_object, '__query_parameters__', []):
            responses.setdefault('400', { 'description': 'Bad Request' })
            
        if self.__build_request_body(method_object) is not None:
            responses.setdefault('422', { 'description': 'Validation Error' })

        responses.setdefault('500', { 'description': 'Internal Server Error' })

        for code in self.__extract_http_exception_statuses(method_object):
            responses.setdefault(str(code), self.__json_response(f'HTTP {code}', HTTP_EXCEPTION_SCHEMA))

        if is_json_response or auto_json_response:
            schema = self.__schema_for_annotation(response_model) if response_model is not None else self.__infer_json_response_schema(method_object)

            if schema is not None:
                self.__merge_response(
                    responses,
                    '200',
                    self.__json_response('OK', schema)
                )

        if returns is not inspect._empty and returns is JSONResponse:
            self.__merge_response(
                responses,
                '200',
                self.__json_response('OK', { 'type' : 'object' })
            )

        return_responses = self.__extract_return_responses(method_object)

        if (
            return_responses
            and returns is not inspect._empty
            and annotation_is_response(returns)
            and '200' not in return_responses
            and responses.get('200') == { 'description': 'Success' }
        ):
            responses.pop('200')

        for code, response in return_responses.items():
            self.__merge_response(responses, code, response)

        return responses

    def __json_response(self, description: str, schema: Optional[dict] = None) -> dict:
        return self.__content_response(description, JSON_MEDIA_TYPE, schema)

    def __content_response(self, description: str, content_type: str, schema: Optional[dict] = None) -> dict:
        response = { 'description': description }

        if schema is not None:
            response['content'] = {
                content_type : {
                    'schema': schema
                }
            }

        return response

    def __merge_response(self, responses: Dict[str, Any], code: str, response: dict) -> None:
        current = responses.get(code)

        if current is None:
            responses[code] = response
            return

        current_schema = self.__response_schema(current)
        next_schema = self.__response_schema(response)

        if next_schema is None:
            if current_schema is None and 'content' not in current:
                responses[code] = response

            return

        if current_schema is None:
            responses[code] = response
            return

        if current_schema == next_schema:
            return

        variants = self.__schema_variants(current_schema)

        if next_schema not in variants:
            variants.append(next_schema)

        current['description'] = response.get('description', current.get('description', 'OK'))
        current['content'] = {
            JSON_MEDIA_TYPE : {
                'schema': { 'oneOf': variants }
            }
        }

    def __response_schema(self, response: dict) -> Optional[dict]:
        content = response.get('content')

        if not isinstance(content, dict):
            return None

        media = content.get(JSON_MEDIA_TYPE)

        if not isinstance(media, dict):
            return None

        schema = media.get('schema')

        return schema if isinstance(schema, dict) else None

    def __schema_variants(self, schema: dict) -> list[dict]:
        variants = schema.get('oneOf')

        if isinstance(variants, list):
            return [
                variant
                for variant in variants
                if isinstance(variant, dict)
            ]

        return [schema]

    def __infer_json_response_schema(self, method_object: Any) -> Optional[dict]:
        try:
            signature = inspect.signature(method_object)
            returns = signature.return_annotation

        except Exception:
            return None

        if returns is inspect._empty:
            return None

        return self.__schema_for_annotation(returns)

    def __schema_for_annotation(self, annotation: Any) -> Optional[dict]:
        if annotation is None or annotation is inspect._empty:
            return None

        schema = schema_for_annotation(annotation)

        if schema is not None:
            return schema

        return None

    def __extract_return_responses(self, method_object: Any) -> dict[str, dict]:
        tree = self.__parse_callable_source(method_object)

        if tree is None:
            return {}

        namespace = self.__callable_namespace(method_object)
        responses: dict[str, dict] = {}

        for node in ast.walk(tree):
            if not isinstance(node, ast.Return) or node.value is None:
                continue

            inferred = self.__infer_response_from_return(node.value, namespace)

            if inferred is None:
                continue

            code, response = inferred
            self.__merge_response(responses, code, response)

        return responses

    def __infer_response_from_return(self, node: ast.AST, namespace: dict[str, Any]) -> Optional[tuple[str, dict]]:
        if isinstance(node, ast.Call):
            func_name = self.__call_name(node.func)

            if func_name == 'JSONResponse':
                status = self.__extract_status_from_call(node, default = 200)
                body = node.args[0] if node.args else self.__keyword_value(node, 'body')
                schema = self.__schema_for_expression(body, namespace) if body is not None else { 'type' : 'object' }

                return str(status), self.__json_response(
                    'OK' if status < 400 else f'HTTP {status}',
                    schema or { 'type' : 'object' }
                )

            target = self.__resolve_name(func_name, namespace)

            if target is not None:
                response = self.__infer_response_class_return(target, node)

                if response is not None:
                    return response

                schema = self.__schema_for_annotation(target)

                if schema is not None:
                    return '200', self.__json_response('OK', schema)

        schema = self.__schema_for_expression(node, namespace)

        if schema is None:
            return None

        return '200', self.__json_response('OK', schema)

    def __infer_response_class_return(self, target: Any, node: ast.Call) -> Optional[tuple[str, dict]]:
        if not (isinstance(target, type) and issubclass(target, Response)):
            return None

        default_status = self.__response_class_default_status(target)
        status = self.__extract_status_from_call(node, default = default_status)
        content_type = self.__response_class_content_type(target)
        description = 'OK' if status < 400 else f'HTTP {status}'

        if content_type is None:
            return str(status), { 'description': description }

        return str(status), self.__content_response(
            description,
            content_type,
            self.__schema_for_content_type(content_type)
        )

    def __response_class_default_status(self, response_class: type[Response]) -> int:
        try:
            signature = inspect.signature(response_class.__init__)
            parameter = signature.parameters.get('status')

            if parameter is not None and isinstance(parameter.default, int):
                return int(parameter.default)

        except Exception:
            pass

        return 200

    def __response_class_content_type(self, response_class: type[Response]) -> Optional[str]:
        try:
            source = textwrap.dedent(inspect.getsource(response_class.__init__))
            tree = ast.parse(source)

        except Exception:
            return None

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            keyword = self.__keyword_value(node, 'content_type')

            if isinstance(keyword, ast.Constant) and isinstance(keyword.value, str):
                return keyword.value

        return None

    def __schema_for_content_type(self, content_type: str) -> dict:
        normalized = content_type.split(';', 1)[0].strip().lower()

        if normalized == JSON_MEDIA_TYPE or normalized.endswith('+json'):
            return { 'type' : 'object' }

        if normalized.startswith('text/') or normalized in ('application/xml', 'application/xhtml+xml'):
            return { 'type' : 'string' }

        return { 'type' : 'string', 'format' : 'binary' }

    def __schema_for_expression(self, node: Optional[ast.AST], namespace: dict[str, Any]) -> Optional[dict]:
        if node is None:
            return None

        if isinstance(node, ast.Constant):
            return self.__schema_for_constant(node.value)

        if isinstance(node, ast.Dict):
            return self.__schema_for_dict_expression(node, namespace)

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return self.__schema_for_sequence_expression(node, namespace)

        if isinstance(node, ast.Call):
            func_name = self.__call_name(node.func)
            target = self.__resolve_name(func_name, namespace)

            if target is not None:
                return self.__schema_for_annotation(target)

        return None

    def __schema_for_constant(self, value: Any) -> dict:
        if isinstance(value, bool):
            return { 'type' : 'boolean' }

        if isinstance(value, int):
            return { 'type' : 'integer' }

        if isinstance(value, float):
            return { 'type' : 'number' }

        if isinstance(value, str):
            return { 'type' : 'string' }

        if value is None:
            return { 'nullable' : True }

        return {}

    def __schema_for_dict_expression(self, node: ast.Dict, namespace: dict[str, Any]) -> dict:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue

            properties[key.value] = self.__schema_for_expression(value, namespace) or {}
            required.append(key.value)

        if not properties:
            return {
                'type'                 : 'object',
                'additionalProperties' : {}
            }

        return {
            'type'       : 'object',
            'properties' : properties,
            'required'   : required
        }

    def __schema_for_sequence_expression(self, node: ast.List | ast.Tuple | ast.Set, namespace: dict[str, Any]) -> dict:
        item_schemas = [
            schema
            for schema in (self.__schema_for_expression(item, namespace) for item in node.elts)
            if schema is not None
        ]

        if not item_schemas:
            return { 'type' : 'array', 'items' : {} }

        first = item_schemas[0]

        if all(schema == first for schema in item_schemas):
            return { 'type' : 'array', 'items' : first }

        return {
            'type'  : 'array',
            'items' : { 'oneOf': item_schemas }
        }

    def __extract_http_exception_statuses(self, method_object: Any) -> set[int]:
        tree = self.__parse_callable_source(method_object)

        if tree is None:
            return set()

        statuses: set[int] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                code = self.__try_parse_http_exception_status(node.exc)

                if code is not None:
                    statuses.add(code)

        return statuses

    def __parse_callable_source(self, method_object: Any) -> Optional[ast.AST]:
        try:
            target = self.__unwrap(method_object) 
            source = textwrap.dedent(inspect.getsource(target))

        except Exception:
            return None

        try:
            return ast.parse(source)

        except SyntaxError:
            return None

    def __try_parse_http_exception_status(self, exception_node: ast.AST) -> Optional[int]:
        if not isinstance(exception_node, ast.Call):
            return None

        func_name = self.__call_name(exception_node.func)

        if func_name != 'HTTPException':
            return None

        if exception_node.args:
            first = exception_node.args[0]

            if isinstance(first, ast.Constant) and isinstance(first.value, int):
                return int(first.value)

        for keyword in exception_node.keywords:
            if keyword.arg in ('status', 'status_code'):
                value = keyword.value

                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return int(value.value)

        return None

    def __extract_status_from_call(self, node: ast.Call, *, default: int) -> int:
        for keyword in node.keywords:
            if keyword.arg in ('status', 'status_code'):
                value = keyword.value

                if isinstance(value, ast.Constant) and isinstance(value.value, int):
                    return int(value.value)

        if len(node.args) > 1:
            value = node.args[1]

            if isinstance(value, ast.Constant) and isinstance(value.value, int):
                return int(value.value)

        return default

    def __keyword_value(self, node: ast.Call, name: str) -> Optional[ast.AST]:
        for keyword in node.keywords:
            if keyword.arg == name:
                return keyword.value

        return None

    def __call_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            return node.attr

        return None

    def __resolve_name(self, name: Optional[str], namespace: dict[str, Any]) -> Optional[Any]:
        if name is None:
            return None

        return namespace.get(name)

    def __callable_namespace(self, method_object: Any) -> dict[str, Any]:
        target = self.__unwrap(method_object)
        namespace: dict[str, Any] = {}
        module = inspect.getmodule(target)

        if module is not None:
            namespace.update(vars(module))

        namespace.update(getattr(target, '__globals__', {}) or {})

        try:
            closure = inspect.getclosurevars(target)
            namespace.update(closure.globals)
            namespace.update(closure.nonlocals)
            namespace.update(closure.builtins)

        except Exception:
            pass

        return namespace

    def __unwrap(self, callable_object: Callable):
        while hasattr(callable_object, '__wrapped__'):
            callable_object = callable_object.__wrapped__

        return callable_object
