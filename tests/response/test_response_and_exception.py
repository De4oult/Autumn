import unittest

from tests.support import reset_framework_state

from autumn.core.response.exception import HTTPException
from autumn.core.response.response import HTMLResponse, JSONResponse
from autumn.serialization import Private, Public, serializable

from pydantic import BaseModel


class UserModel(BaseModel):
    name: str
    age: int


@serializable
class SerializableUser:
    def __init__(self, name: str, age: int, password: str) -> None:
        self.id: Public[int] = 1
        self.name: Public[str] = name
        self.age: Public[int] = age
        self.password_hash: Private[str] = f'hash:{password}'


class RequestStub:
    def __init__(self, accept: str | None):
        self._accept = accept

    def header(self, name: str):
        if name.lower() == 'accept':
            return self._accept

        return None


class ResponseAndExceptionTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_json_response_serializes_pydantic_models(self) -> None:
        response = JSONResponse({
            'user'  : UserModel(name = 'Autumn', age = 2),
            'items' : [UserModel(name = 'Leaf', age = 1)]
        })

        self.assertIn('"name":"Autumn"', response.text)
        self.assertIn('"name":"Leaf"', response.text)
        self.assertEqual(response.content_type, 'application/json')

    def test_json_response_serializes_decorated_objects_without_private_fields(self) -> None:
        response = JSONResponse({
            'user': SerializableUser(name = 'Anton', age = 18, password = 'qwerty123!')
        })

        self.assertIn('"id":1', response.text)
        self.assertIn('"name":"Anton"', response.text)
        self.assertIn('"age":18', response.text)
        self.assertNotIn('password_hash', response.text)

    def test_http_exception_defaults_to_json_response(self) -> None:
        exception = HTTPException(status = 404, details = 'missing')

        response = exception.to_response()

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status, 404)
        self.assertIn('"details":"missing"', response.text)

    def test_http_exception_prefers_html_for_browser_accept(self) -> None:
        exception = HTTPException(status = 418, details = 'teapot')

        response = exception.to_response(
            RequestStub('text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8')
        )

        self.assertIsInstance(response, HTMLResponse)
        self.assertEqual(response.status, 418)
        self.assertIn('teapot', response.body)

    def test_http_exception_keeps_json_for_generic_accept(self) -> None:
        exception = HTTPException(status = 400, details = 'bad request')

        response = exception.to_response(RequestStub('*/*'))

        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status, 400)
        self.assertIn('"status":400', response.text)
