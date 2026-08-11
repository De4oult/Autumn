from __future__ import annotations

import unittest

from autumn.response import InvalidHeaderError, Response
from autumn.core.serialization import Private, Public, serializable, serialize_instance


class HeaderValidationTests(unittest.TestCase):
    def test_response_rejects_invalid_header_name(self) -> None:
        response = Response('ok', headers = {'Bad Header': 'value'})

        with self.assertRaises(InvalidHeaderError):
            response.headers_as_list()

    def test_response_rejects_response_splitting_characters(self) -> None:
        response = Response('ok', headers = {'X-Value': 'safe\r\nX-Injected: yes'})

        with self.assertRaises(InvalidHeaderError):
            response.headers_as_list()

    def test_response_preserves_valid_ascii_header_names(self) -> None:
        response = Response('ok', headers = {'X-Trace': 'enabled'})

        headers = dict(response.headers_as_list())

        self.assertEqual(headers[b'X-Trace'], b'enabled')


class AnnotationAllowlistTests(unittest.TestCase):
    def test_annotation_calls_are_not_executed_and_private_wrapper_is_preserved(self) -> None:
        calls: list[str] = []

        def malicious():
            calls.append('executed')
            return str

        @serializable
        class Account:
            name: Public[str]
            secret: Private[malicious()]

            def __init__(self) -> None:
                self.name = 'Autumn'
                self.secret = 'hidden'

        payload = serialize_instance(Account())

        self.assertEqual(calls, [])
        self.assertEqual(payload, {'name': 'Autumn'})

    def test_allowlist_resolves_nested_generics_and_union(self) -> None:
        @serializable
        class Payload:
            values: Public[list[str] | None]

            def __init__(self) -> None:
                self.values = ['safe']

        self.assertEqual(serialize_instance(Payload()), {'values': ['safe']})

    def test_instance_annotation_call_is_not_executed(self) -> None:
        calls: list[str] = []

        def malicious():
            calls.append('executed')
            return str

        @serializable
        class Account:
            def __init__(self) -> None:
                self.secret: Private[malicious()] = 'hidden'

        self.assertEqual(serialize_instance(Account()), {})
        self.assertEqual(calls, [])
