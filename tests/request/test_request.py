import unittest

from tests.support import make_receive, make_scope, reset_framework_state, run_async

from autumn.core.request.request import Request


class RequestTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_framework_state()

    def test_request_parses_query_and_headers(self) -> None:
        request = Request(
            make_scope(
                path = '/users',
                query_string = 'page=2&search=autumn',
                headers = {'x-test': 'ok'}
            ),
            make_receive()
        )

        self.assertEqual(request.query.page, '2')
        self.assertEqual(request.query.search, 'autumn')
        self.assertEqual(request.header('x-test'), 'ok')

    def test_body_is_cached_between_reads(self) -> None:
        receive = make_receive(chunks = [b'{"name":', b'"Autumn"}'])
        request = Request(make_scope(method = 'POST', path = '/users'), receive)

        first = run_async(request.body())
        second = run_async(request.body())

        self.assertEqual(first, b'{"name":"Autumn"}')
        self.assertEqual(second, first)
        self.assertEqual(receive.calls['count'], 2)

    def test_json_reads_request_payload(self) -> None:
        request = Request(
            make_scope(method = 'POST', path = '/users'),
            make_receive(body = b'{"name":"Autumn","age":2}')
        )

        payload = run_async(request.json())

        self.assertEqual(payload['name'], 'Autumn')
        self.assertEqual(payload['age'], 2)
