import unittest

from tests.support import make_request, reset_framework_state, run_async

from autumn.core.dependencies.container import Container, ExecutionContext
from autumn.core.dependencies.decorators import leaf, service
from autumn.core.exception.exception import DependencyInjectionError
from autumn.core.request.request import Request
from autumn.core.response.exception import HTTPException

from pydantic import BaseModel


class UserSchema(BaseModel):
    name: str
    age: int


class ContainerTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_container_injects_request_body_from_annotation(self) -> None:
        container = Container()
        context = ExecutionContext()
        request = make_request(
            method = 'POST',
            path = '/users',
            body = b'{"name":"Autumn","age":2}'
        )
        context.values[Request] = request

        async def handler(request: Request, user: UserSchema):
            return user

        result = run_async(
            container.call(handler, context = context, provided_kwargs = {'request': request})
        )

        self.assertIsInstance(result, UserSchema)
        self.assertEqual(result.name, 'Autumn')

    def test_container_returns_422_for_invalid_body(self) -> None:
        container = Container()
        context = ExecutionContext()
        request = make_request(
            method = 'POST',
            path = '/users',
            body = b'{"name":"Broken"}'
        )
        context.values[Request] = request

        async def handler(request: Request, user: UserSchema):
            return user

        with self.assertRaises(HTTPException) as raised:
            run_async(
                container.call(handler, context = context, provided_kwargs = {'request': request})
            )

        self.assertEqual(raised.exception.status, 422)

    def test_container_resolves_registered_dependencies(self) -> None:
        @leaf
        async def provide_port() -> int:
            return 8000

        @service
        class ServerConfiguration:
            def __init__(self, port: int):
                self.port = port

        container = Container()
        container.register_dependency_function(provide_port)

        resolved = run_async(container.resolve(ServerConfiguration, ExecutionContext()))

        self.assertEqual(resolved.port, 8000)

    def test_container_raises_when_required_argument_missing(self) -> None:
        container = Container()

        async def handler(name: str):
            return name

        with self.assertRaises(DependencyInjectionError):
            run_async(container.call(handler))
