from typing import Union, Any, Optional, Dict, List, Tuple, AsyncIterator
from pathlib import Path
from orjson import dumps
from asyncio import to_thread
from functools import lru_cache

from autumn.core.serialization import json_default

import mimetypes
import re

_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class InvalidHeaderError(ValueError):
    pass


@lru_cache(maxsize = 256)
def _encode_header_name(name: str) -> bytes:
    if not isinstance(name, str) or not _HEADER_NAME_PATTERN.fullmatch(name):
        raise InvalidHeaderError(f'Invalid HTTP header name: {name!r}')

    return name.encode('ascii')


def _encode_header(name: str, value: str) -> Tuple[bytes, bytes]:
    encoded_name = _encode_header_name(name)

    if not isinstance(value, str):
        raise InvalidHeaderError(f'HTTP header value for {name!r} must be a string')

    if '\r' in value or '\n' in value or '\0' in value:
        raise InvalidHeaderError(f'Invalid control character in HTTP header {name!r}')

    return encoded_name, value.encode('utf-8')


@lru_cache(maxsize = 64)
def _content_type_headers(content_type: str) -> tuple[Tuple[bytes, bytes], ...]:
    return (
        _encode_header('content-type', content_type),
        (b'autumn', b'Hello :)')
    )

class Response:
    def __init__(
        self,
        body: Union[str, bytes],
        status: int = 200,
        content_type: str = 'text/plain; charset=utf-8',
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        self.body = body
        self.status: int = status
        self.content_type = content_type
        self.headers: Dict[str, str] = headers or {}

    @property
    def body(self) -> Union[str, bytes]:
        return self.__body

    @body.setter
    def body(self, value: Union[str, bytes]) -> None:
        self.__body = value
        self.__body_bytes = value.encode('utf-8') if isinstance(value, str) else value

    @property
    def content_type(self) -> str:
        return self.__content_type

    @content_type.setter
    def content_type(self, value: str) -> None:
        self.__content_type = value
        self.__base_headers = _content_type_headers(value)

    @property
    def text(self) -> str:
        if isinstance(self.body, bytes):
            return self.body.decode('utf-8', errors = 'ignore')

        return self.body

    def body_as_bytes(self) -> bytes:
        return self.__body_bytes

    def headers_as_list(self) -> List[Tuple[bytes, bytes]]:
        encoded_headers: List[Tuple[bytes, bytes]] = list(self.__base_headers)

        for key, value in self.headers.items():
            encoded_headers.append(_encode_header(key, value))

        return encoded_headers


class JSONResponse(Response):
    def __init__(
        self, 
        body: Any, 
        status: int = 200, 
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(
            body         = dumps(body, default = json_default),
            status       = status,
            content_type = 'application/json',
            headers      = headers or {}
        )


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
    @classmethod
    def from_root(
        cls,
        root: Union[str, Path],
        path: Union[str, Path],
        **kwargs
    ) -> 'FileResponse':
        root_path = Path(root).resolve(strict = True)

        if not root_path.is_dir():
            raise NotADirectoryError(f'File root is not a directory: {root_path}')

        requested_path = Path(path)
        candidate = (
            requested_path
            if requested_path.is_absolute()
            else root_path / requested_path
        ).resolve(strict = True)

        if not candidate.is_relative_to(root_path):
            raise PermissionError(f'File path escapes the configured root: {path}')

        return cls(candidate, **kwargs)

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
