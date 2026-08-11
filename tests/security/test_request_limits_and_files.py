import unittest
from pathlib import Path

from autumn.core.app import Autumn
from autumn.core.configuration.builtin import ApplicationConfiguration
from autumn.core.request.request import Request
from autumn.core.response.exception import HTTPException
from autumn.core.response.response import FileResponse
from autumn.core.routing.decorators import REST, post
from tests.support import asgi_request, make_receive, make_scope, reset_framework_state, run_async


class RequestBodyLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_request_rejects_chunked_body_as_soon_as_limit_is_exceeded(self) -> None:
        receive = make_receive(chunks = [b'abcd', b'efgh', b'ignored'])
        request = Request(make_scope(method = 'POST'), receive, max_body_bytes = 6)

        with self.assertRaises(HTTPException) as raised:
            run_async(request.body())

        self.assertEqual(raised.exception.status, 413)
        self.assertEqual(receive.calls['count'], 2)

    def test_request_uses_bytearray_and_returns_cached_bytes(self) -> None:
        receive = make_receive(chunks = [b'ab', b'cd'])
        request = Request(make_scope(method = 'POST'), receive, max_body_bytes = 4)

        first = run_async(request.body())
        second = run_async(request.body())

        self.assertEqual(first, b'abcd')
        self.assertIs(first, second)
        self.assertEqual(receive.calls['count'], 2)

    def test_content_length_over_limit_is_rejected_before_body_read(self) -> None:
        receive = make_receive(body = b'not-read')
        request = Request(
            make_scope(method = 'POST', headers = {'content-length': '100'}),
            receive,
            max_body_bytes = 10
        )

        with self.assertRaises(HTTPException) as raised:
            run_async(request.body())

        self.assertEqual(raised.exception.status, 413)
        self.assertEqual(receive.calls['count'], 0)

    def test_application_configuration_overrides_request_body_limit(self) -> None:
        app = Autumn()

        class SmallBodyApplicationConfiguration(ApplicationConfiguration):
            max_request_body_bytes = 4

        @REST()
        class UploadController:
            @post('/upload')
            async def upload(self, request: Request) -> dict:
                return {'size': len(await request.body())}

        response = run_async(
            asgi_request(app, method = 'POST', path = '/upload', body = b'12345')
        )

        self.assertEqual(response.status, 413)


class RootedFileResponseTests(unittest.TestCase):
    def test_from_root_serves_a_file_inside_root(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'fixtures' / 'file_root'

        response = FileResponse.from_root(root, 'hello.txt')

        self.assertEqual(response.body, b'hello\n')

    def test_from_root_rejects_path_traversal(self) -> None:
        root = Path(__file__).resolve().parents[1] / 'fixtures' / 'file_root'

        with self.assertRaises(PermissionError):
            FileResponse.from_root(root, '../outside-root.txt')
