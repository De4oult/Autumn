from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import json
import sys
import types


def _ensure_test_environment() -> None:
    source_path = Path(__file__).resolve().parents[1] / 'source'

    if str(source_path) not in sys.path:
        sys.path.insert(0, str(source_path))

    if 'orjson' not in sys.modules:
        try:
            __import__('orjson')

        except ModuleNotFoundError:
            orjson_stub = types.ModuleType('orjson')
            orjson_stub.OPT_INDENT_2 = 2
            orjson_stub.dumps = lambda value, option = None: json.dumps(
                value,
                indent = 2 if option else None
            ).encode('utf-8')
            orjson_stub.loads = lambda value: json.loads(value)
            sys.modules['orjson'] = orjson_stub

    if 'colorama' not in sys.modules:
        try:
            __import__('colorama')

        except ModuleNotFoundError:
            colorama_stub = types.ModuleType('colorama')
            colorama_stub.Fore = types.SimpleNamespace(
                YELLOW = '',
                RESET = '',
                GREEN = ''
            )
            sys.modules['colorama'] = colorama_stub


_ensure_test_environment()

from autumn.core.configuration.configuration import reset_configuration_registry
from autumn.core.dependencies.registry import DEPENDENCY_FUNCTIONS, SERVICE_CLASSES
from autumn.core.request.request import Request
from autumn.core.routing.router import router

import asyncio


def reset_framework_state() -> None:
    router.reset()
    reset_configuration_registry()
    DEPENDENCY_FUNCTIONS.clear()
    SERVICE_CLASSES.clear()


def make_scope(
    *,
    method: str = 'GET',
    path: str = '/',
    headers: Optional[dict[str, str]] = None,
    query_string: str = ''
) -> dict[str, Any]:
    encoded_headers = [
        (key.lower().encode('utf-8'), value.encode('utf-8'))
        for key, value in (headers or {}).items()
    ]

    return {
        'type'         : 'http',
        'method'       : method,
        'path'         : path,
        'headers'      : encoded_headers,
        'query_string' : query_string.encode('utf-8')
    }


def make_request(
    *,
    method: str = 'GET',
    path: str = '/',
    headers: Optional[dict[str, str]] = None,
    body: bytes = b'',
    query_string: str = ''
) -> Request:
    return Request(
        make_scope(
            method       = method,
            path         = path,
            headers      = headers,
            query_string = query_string
        ),
        make_receive(body)
    )


def make_receive(body: bytes = b'', *, chunks: Optional[list[bytes]] = None):
    if chunks is None:
        payload_chunks = [body]
    else:
        payload_chunks = list(chunks)

    calls = {'count': 0}

    async def receive():
        calls['count'] += 1

        if payload_chunks:
            chunk = payload_chunks.pop(0)
            return {
                'type'      : 'http.request',
                'body'      : chunk,
                'more_body' : bool(payload_chunks)
            }

        return {
            'type'      : 'http.request',
            'body'      : b'',
            'more_body' : False
        }

    receive.calls = calls
    return receive


@dataclass
class ASGIResult:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode('utf-8', errors = 'ignore')

    def json(self) -> Any:
        return json.loads(self.text)


async def asgi_request(
    app,
    *,
    method: str = 'GET',
    path: str = '/',
    headers: Optional[dict[str, str]] = None,
    body: bytes = b'',
    query_string: str = ''
) -> ASGIResult:
    sent: list[dict[str, Any]] = []
    receive = make_receive(body)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await app(
        make_scope(
            method       = method,
            path         = path,
            headers      = headers,
            query_string = query_string
        ),
        receive,
        send
    )

    start = next(message for message in sent if message['type'] == 'http.response.start')
    response_body = b''.join(
        message.get('body', b'')
        for message in sent
        if message['type'] == 'http.response.body'
    )

    decoded_headers = {
        key.decode('utf-8') : value.decode('utf-8')
        for key, value in start['headers']
    }

    return ASGIResult(
        status  = start['status'],
        headers = decoded_headers,
        body    = response_body
    )


def run_async(coro):
    return asyncio.run(coro)
