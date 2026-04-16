from typing import Any, Optional
from types import SimpleNamespace
from urllib.parse import parse_qs
from orjson import loads

class Request:
    def __init__(self, scope: dict, receive: Any):
        self.app = None
        
        self.scope = scope
        self.receive = receive

        self.method = scope.get('method')
        self.path = scope.get('path')
        
        self.headers = self.__parse_headers(scope.get('headers', []))

        self._query_raw = self.__parse_query()
        self.query = SimpleNamespace(**self._query_raw)

        self.__body: Optional[bytes] = None
    
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

    async def body(self) -> bytes:
        if self.__body is None:
            chunks: list[bytes] = []

            more_body = True
            
            while more_body:
                message = await self.receive()

                chunks.append(message.get('body', b''))
                
                more_body = message.get('more_body', False)
            
            self.__body = b''.join(chunks)
        
        return self.__body

    async def json(self) -> dict:
        raw: bytes = await self.body()

        return loads(raw)

    def header(self, name: str) -> Optional[str]:
        return self.headers.get(name.lower())
