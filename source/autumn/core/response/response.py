from typing import Union, Any
from pydantic import BaseModel
from orjson import dumps

class Response:
	def __init__(
		self,
		body: Union[str, bytes],
		status: int = 200,
		content_type: str = 'text/plain',
		headers: dict[str, str] = {},
	) -> None:
		self.body = body if isinstance(body, str) else body.decode('utf-8')
		self.status = status
		self.content_type = content_type
		self.headers = headers

	def headers_as_list(self) -> list[tuple[bytes]]:
		encoded_headers = [(b'content-type', self.content_type.encode('utf-8'))]

		for key, value in self.headers.items():
			encoded_headers.append((key.encode('utf-8'), value.encode('utf-8')))

		return encoded_headers


def _serialize(object: Any) -> Any:
	if isinstance(object, BaseModel):
		return object.model_dump(mode = 'json')
	
	elif isinstance(object, list):
		return [_serialize(item) for item in object]
	
	elif isinstance(object, dict):
		return {
			key : _serialize(value)
			for key, value in object.items()
		}
	
	return object

class JSONResponse(Response):
	def __init__(self, body: dict, status: int = 200, headers: dict[str, str] = {}):
		serialized = _serialize(body)

		super().__init__(
			body = dumps(serialized).decode(),
			status = status,
			content_type = 'application/json',
			headers = headers
		)


class HTMLResponse(Response):
	def __init__(self, body: dict, status: int = 200, headers: dict[str, str] = {}):
		super().__init__(
			body = body,
			status = status,
			content_type = 'text/html',
			headers = headers
		)


class XMLResponse(Response):
	def __init__(self, body: str, status: int = 200, headers: dict[str, str] = {}):
		super().__init__(
			body = body,
			status = status,
			content_type = 'application/xml',
			headers = headers
		)


class RedirectResponse(Response):
    def __init__(self, location: str, status: int = 302):
        headers = { 'Location' : location }
		
        super().__init__(
            body = '',
			status = status,
			content_type = 'text/plain',
			headers = headers
		)