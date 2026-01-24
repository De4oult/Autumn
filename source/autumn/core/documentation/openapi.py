import ast
import inspect
from typing import Any, Dict, Optional, Type

from autumn.core.response.response import JSONResponse
from pydantic import BaseModel

PYTYPE_TO_SCHEMA = {
    int:   {'type': 'integer'},
    str:   {'type': 'string'},
    float: {'type': 'number'},
    bool:  {'type': 'boolean'},
}

TYPENAME_TO_SCHEMA = {
    'int':  {'type': 'integer'},
    'str':  {'type': 'string'},
    'float':{'type': 'number'},
    'bool': {'type': 'boolean'},
    'uuid': {'type': 'string', 'format': 'uuid'},
}

class OpenAPIGenerator:
    def __init__(self, *, title: str = 'Autumn API', version: str = '0.1.0'):
        self.title = title
        self.version = version

    def generate(self, app) -> dict:
        paths: Dict[str, Any] = {}

        tags = []
        seen = set()

        for route in app.router.get_routes():
            # пока документируем только контроллерные хэндлеры
            if not (isinstance(route.handler, tuple) and len(route.handler) == 2 and isinstance(route.handler[1], str)):
                continue

            controller_cls, method_name = route.handler
            method_obj = getattr(controller_cls, method_name)

            openapi_path = route.openapi_path
            http_method = route.method.lower()

            op = self.build_operation(
                route=route,
                controller_cls=controller_cls,
                method_name=method_name,
                method_obj=method_obj,
            )

            paths.setdefault(openapi_path, {})
            paths[openapi_path][http_method] = op
            
            tag = getattr(controller_cls, "__tag__", None) or controller_cls.__name__.removesuffix("Controller")

            if tag not in seen:
                seen.add(tag)
                desc = getattr(controller_cls, "__description__", None)
                tags.append({"name": tag, **({"description": desc} if desc else {})})

        info = {
            'title' : getattr(app, 'name', None) or self.title,
            'version' : getattr(app, 'version', None) or self.version,
            'description' : getattr(app, 'description', None) or 'Modern web-application powered by Autumn Framework'
        }

        return {
            'openapi': '3.0.3',
            'info': info,
            'paths': paths,
            'tags' : tags
        }

    # --------- customization hooks ---------

    def get_tags(self, controller_cls: type) -> list[str]:
        return [getattr(controller_cls, "__tag__", None) or controller_cls.__name__.removesuffix("Controller")]

    def get_operation_id(self, controller_cls: type, method_name: str, http_method: str, path: str) -> str:
        return f'{controller_cls.__name__}.{method_name}:{http_method}:{path}'

    # --------- operation builder ---------
    def _get_attr_chain(self, obj, name, default=None):
        if hasattr(obj, name):
            return getattr(obj, name)
        # попробовать unwrap
        cur = obj
        while hasattr(cur, "__wrapped__"):
            cur = cur.__wrapped__
            if hasattr(cur, name):
                return getattr(cur, name)
        return default

    def build_operation(self, *, route, controller_cls: type, method_name: str, method_obj: Any) -> dict:
        # params
        parameters = []
        parameters.extend(self._build_path_parameters(route))
        parameters.extend(self._build_query_parameters(method_obj))

        # request body
        request_body = self._build_request_body(method_obj)
        ctrl_tag = getattr(controller_cls, "__tag__", None) or controller_cls.__name__.removesuffix("Controller")

        method_summary = self._get_attr_chain(method_obj, "__summary__", None)
        method_desc    = self._get_attr_chain(method_obj, "__description__", None)

        method_tags = self._get_attr_chain(method_obj, "__tags__", []) or []
        op_tags = [ctrl_tag, *method_tags] if method_tags else [ctrl_tag]
        # responses

        responses = self._build_responses(route, controller_cls, method_name, method_obj)

        op = {
            'operationId': self.get_operation_id(controller_cls, method_name, route.method.lower(), route.openapi_path),
            'parameters': parameters,
            'responses': responses,
            "summary": method_summary or method_name,
            "description": method_desc or None,
            "tags": op_tags,
        }
        if request_body is not None:
            op['requestBody'] = request_body

        if method_desc:
            op["description"] = method_desc

        if op["description"] is None:
            op.pop("description")

        return op

    # --------- parameters ---------

    def _build_path_parameters(self, route) -> list[dict]:
        params = []
        for name, typ_name in zip(route.parameters, route.parameters_types_names):
            schema = TYPENAME_TO_SCHEMA.get(typ_name, {'type': 'string'})
            params.append({
                'name': name,
                'in': 'path',
                'required': True,
                'schema': schema,
            })
        return params

    def _build_query_parameters(self, method_obj: Any) -> list[dict]:
        query_meta = getattr(method_obj, '__query_parameters__', [])
        params = []
        for q in query_meta:
            name = q.get('name')
            py_type = q.get('type', str)
            required = bool(q.get('required', False))
            default = q.get('default', None)

            schema = PYTYPE_TO_SCHEMA.get(py_type, {'type': 'string'})
            if default is not None:
                schema = dict(schema)
                schema['default'] = default

            params.append({
                'name': name,
                'in': 'query',
                'required': required,
                'schema': schema,
            })
        return params

    # --------- request body ---------

    def _build_request_body(self, method_obj: Any) -> Optional[dict]:
        body_model = self._get_attr_chain(method_obj, '__body_schema__', None)
        if body_model is None:
            return None

        if inspect.isclass(body_model) and issubclass(body_model, BaseModel):
            return {
                'required': True,
                'content': {
                    'application/json': {
                        'schema': body_model.model_json_schema()
                    }
                },
            }

        # если ты поддержишь не только Pydantic — расширишь тут
        return None

    # --------- responses ---------

    def _build_responses(self, route, controller_cls: type, method_name: str, method_obj: Any) -> dict:
        responses: Dict[str, Any] = {}

        is_json_response = bool(self._get_attr_chain(method_obj, "__json_response__", False))
        response_model = self._get_attr_chain(method_obj, "__response_model__", None)
        ret = inspect.signature(method_obj).return_annotation

        responses['200'] = {'description': 'OK'}

        # инфраструктурные ошибки
        if getattr(method_obj, '__query_parameters__', []):
            responses.setdefault('400', {'description': 'Bad Request'})
        if self._get_attr_chain(method_obj, '__body_schema__', None) is not None:
            responses.setdefault('422', {'description': 'Validation Error'})

        # 500 всегда как fallback (сервисы/непредвиденное)
        responses.setdefault('500', {'description': 'Internal Server Error'})

        # статический анализ raise HTTPException в методе контроллера
        for code in self._extract_http_exception_statuses(method_obj):
            responses.setdefault(str(code), {'description': f'HTTP {code}'})

        # если хочешь: автосхема ответа для @json_response
        if is_json_response:
            if response_model and inspect.isclass(response_model) and issubclass(response_model, BaseModel):
                schema = response_model.model_json_schema()
            else:
                schema = self._infer_json_response_schema(method_obj)

            if schema is not None:
                responses["200"] = {
                    "description": "OK",
                    "content": {"application/json": {"schema": schema}},
                }
                return responses

        if ret is not inspect._empty and ret is JSONResponse:
            responses["200"] = {
                "description": "OK",
                "content": {"application/json": {"schema": {"type":"object"}}},
            }

        return responses

    def _infer_json_response_schema(self, method_obj: Any) -> Optional[dict]:
        '''
        Минимально:
        - если есть return annotation = BaseModel subclass -> берём schema
        - иначе None (без магии)
        '''
        try:
            sig = inspect.signature(method_obj)
            ret = sig.return_annotation
        except Exception:
            return None

        if ret is inspect._empty:
            return None

        if inspect.isclass(ret) and issubclass(ret, BaseModel):
            return ret.model_json_schema()

        return None

    # --------- AST analysis for raise HTTPException ---------

    def _extract_http_exception_statuses(self, method_obj: Any) -> set[int]:
        try:
            target = self._unwrap(method_obj) 
            src = inspect.getsource(target)
        except Exception:
            return set()

        try:
            tree = ast.parse(src)
        except SyntaxError:
            return set()

        statuses: set[int] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and node.exc is not None:
                code = self._try_parse_http_exception_status(node.exc)
                if code is not None:
                    statuses.add(code)

        return statuses

    def _try_parse_http_exception_status(self, exc_node: ast.AST) -> Optional[int]:
        '''
        Поддерживаем:
        - raise HTTPException(404, ...)
        - raise HTTPException(status_code=403, ...)
        - raise autumn.core.response.exception.HTTPException(...)
        '''
        if not isinstance(exc_node, ast.Call):
            return None

        # имя вызываемого: HTTPException или что-то. Мы проверим просто суффикс имени.
        fn = exc_node.func
        fn_name = None
        if isinstance(fn, ast.Name):
            fn_name = fn.id
        elif isinstance(fn, ast.Attribute):
            fn_name = fn.attr

        if fn_name != 'HTTPException':
            return None

        # 1) статус как первый positional arg
        if exc_node.args:
            first = exc_node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, int):
                return int(first.value)

        # 2) статус как keyword status_code=
        for kw in exc_node.keywords:
            if kw.arg == 'status_code':
                v = kw.value
                if isinstance(v, ast.Constant) and isinstance(v.value, int):
                    return int(v.value)

        return None

    def _unwrap(self, callable_obj):
        while hasattr(callable_obj, "__wrapped__"):
            callable_obj = callable_obj.__wrapped__
        return callable_obj
