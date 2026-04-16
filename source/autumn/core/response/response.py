from typing import Union, Any, Optional, Dict, List, Tuple, AsyncIterator
from pydantic import BaseModel
from pathlib import Path
from orjson import dumps
from asyncio import to_thread

import mimetypes

class Response:
    def __init__(
        self,
        body: Union[str, bytes],
        status: int = 200,
        content_type: str = 'text/plain; charset=utf-8',
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        self.body: Union[str, bytes] = body
        self.status: int = status
        self.content_type: str = content_type
        self.headers: Dict[str, str] = headers or {}

    @property
    def text(self) -> str:
        if isinstance(self.body, bytes):
            return self.body.decode('utf-8', errors = 'ignore')

        return self.body

    def body_as_bytes(self) -> bytes:
        if isinstance(self.body, str):
            return self.body.encode('utf-8')

        return self.body

    def headers_as_list(self) -> List[Tuple[bytes, bytes]]:
        encoded_headers: List[Tuple[bytes, bytes]] = [
            (b'content-type', self.content_type.encode('utf-8')),
            (b'autumn', b'Hello :)')
        ]

        for key, value in self.headers.items():
            encoded_headers.append((key.encode('utf-8'), value.encode('utf-8')))

        return encoded_headers


class JSONResponse(Response):
    def __init__(
        self, 
        body: dict, 
        status: int = 200, 
        headers: Optional[Dict[str, str]] = None
    ):
        serialized = self.serialize(body)

        super().__init__(
            body         = dumps(serialized),
            status       = status,
            content_type = 'application/json',
            headers      = headers or {}
        )
    
    def serialize(self, object: Any) -> Any:
        if isinstance(object, BaseModel):
            return object.model_dump(mode = 'json')
        
        elif isinstance(object, list):
            return [self.serialize(item) for item in object]
        
        elif isinstance(object, dict):
            return {
                key : self.serialize(value)
                for key, value in object.items()
            }
        
        return object


class HTMLResponse(Response):
    def __init__(
        self, 
        body: str, 
        status: int = 200, 
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            body         = body,
            status       = status,
            content_type = 'text/html; charset=utf-8',
            headers      = headers or {}
        )


class XMLResponse(Response):
    def __init__(
        self, 
        body: str, 
        status: int = 200, 
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            body         = body,
            status       = status,
            content_type = 'application/xml',
            headers      = headers or {}
        )


class RedirectResponse(Response):
    def __init__(
        self, 
        location: str, 
        status: int = 302,
        headers: Optional[Dict[str, str]] = None
    ):
        headers: Dict[str, str] = headers or {}
        
        super().__init__(
            body         = '',
            status       = status,
            content_type = 'text/plain; charset=utf-8',
            headers      = { 
                **headers,
                'Location' : location
            }
        )
        

class FileResponse(Response):
    def __init__(
        self, 
        path: Union[str, Path], 
        filename: Optional[str] = None,
        status: int = 200, 
        content_type: Optional[str] = None,
        download: bool = False,
        headers: Optional[Dict[str, str]] = None
    ):
        path: Path = Path(path)

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f'File not found: {path}')

        body = path.read_bytes()

        if content_type is None:
            guessed, _ = mimetypes.guess_type(path.name)
            content_type = guessed or 'application/octet-stream'

        filename = filename or path.name
        disposition = 'attachment' if download else 'inline'

        headers: Dict[str, str] = headers or {}

        super().__init__(
            body         = body,
            status       = status,
            content_type = content_type,
            headers      = {
                **headers,
                'Content-Disposition' : f'{disposition}; filename="{filename}"',
                'Content-Length'      : str(len(body))
            }
        )

class StreamFileResponse(Response):
    def __init__(
        self,
        path: Union[str, Path],
        filename: Optional[str] = None,
        status: int = 200,
        content_type: Optional[str] = None,
        download: bool = False,
        chunk_size: int = 64 * 1024,
        headers: Optional[Dict[str, str]] = None
    ):
        self.path = Path(path)

        if not self.path.exists() or not self.path.is_file():
            raise FileNotFoundError(f'File not found: {self.path}')

        self.chunk_size = int(chunk_size)

        if self.chunk_size <= 0:
            raise ValueError('chunk_size must be > 0')

        if content_type is None:
            guessed, _ = mimetypes.guess_type(self.path.name)
            content_type = guessed or 'application/octet-stream'

        filename = filename or self.path.name
        disposition = 'attachment' if download else 'inline'

        filesize = self.path.stat().st_size

        headers: Dict[str, str] = headers or {}

        super().__init__(
            body         = b'',
            status       = status,
            content_type = content_type,
            headers      = {
                **headers,
                'Content-Disposition' : f'{disposition}; filename="{filename}"',
                'Content-Length'      : str(filesize)
            }
        )

    async def body_iterate(self) -> AsyncIterator[bytes]:
        with self.path.open('rb') as file: # ЖЫВЕ БЕЛАРУСЬ
            while True:
                chunk = await to_thread(file.read, self.chunk_size)

                if not chunk:
                    break

                yield chunk
