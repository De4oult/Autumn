from typing import Any, Optional
from types import SimpleNamespace
from urllib.parse import parse_qs
from orjson import loads
from autumn.core.response.exception import HTTPException

_UNSET = object()


class Request:
    def __init__(
        self,
        scope: dict,
        receive: Any,
        *,
        max_body_bytes: Optional[int] = 1024 * 1024
    ):
        if max_body_bytes is not None and max_body_bytes < 0:
            raise ValueError('max_body_bytes must be greater than or equal to 0, or None')

        self.app = None
        
        self.scope = scope
        self.receive = receive
        self.max_body_bytes = max_body_bytes

        self.method = scope.get('method')
        self.path = scope.get('path')
        
        self.headers = self.__parse_headers(scope.get('headers', []))

        self._query_raw: Optional[dict[str, Any]] = None
        self._query_value: Any = _UNSET

        self.__body: Optional[bytes] = None
        self.__json: Any = _UNSET
    
    def __parse_headers(self, raw_headers):
        return { 
            key.decode().lower(): value.decode()
            for key, value in raw_headers
        }
    
    def __parse_query(self) -> dict:
        raw = self.scope.get('query_string', b'').decode('utf-8')
        parsed = parse_qs(raw)

        return {
            key : value[0] 
            if value else None
            for key, value in parsed.items()
        }

    @property
    def query(self):
        if self._query_value is _UNSET:
            if self._query_raw is None:
                self._query_raw = self.__parse_query()

            self._query_value = SimpleNamespace(**self._query_raw)

        return self._query_value

    @query.setter
    def query(self, value: Any) -> None:
        if isinstance(value, dict):
            self._query_raw = value
            self._query_value = SimpleNamespace(**value)
            
            return

        self._query_value = value

        if hasattr(value, '__dict__'):
            self._query_raw = dict(value.__dict__)
        else:
            self._query_raw = None

    async def body(self) -> bytes:
        if self.__body is None:
            content_length = self.header('content-length')

            if content_length is not None and self.max_body_bytes is not None:
                try:
                    declared_size = int(content_length)

                except ValueError:
                    declared_size = None

                if declared_size is not None and declared_size > self.max_body_bytes:
                    raise HTTPException(
                        status = 413,
                        details = f'Request body exceeds the {self.max_body_bytes} byte limit'
                    )

            body = bytearray()

            more_body = True
            
            while more_body:
                message = await self.receive()

                chunk = message.get('body', b'')

                if chunk:
                    body.extend(chunk)

                    if self.max_body_bytes is not None and len(body) > self.max_body_bytes:
                        raise HTTPException(
                            status = 413,
                            details = f'Request body exceeds the {self.max_body_bytes} byte limit'
                        )
                
                more_body = message.get('more_body', False)
            
            self.__body = bytes(body)
        
        return self.__body

    async def json(self) -> dict:
        if self.__json is _UNSET:
            self.__json = self.parse_json_bytes(await self.body())

        return self.__json

    def parse_json_bytes(self, body: bytes):
        if self.__json is _UNSET:
            self.__json = loads(body)

        return self.__json

    def header(self, name: str) -> Optional[str]:
        return self.headers.get(name.lower())
