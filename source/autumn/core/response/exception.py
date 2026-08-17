from autumn.core.response.response import HTMLResponse, JSONResponse, Response
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional


def _parse_accept_header(value: Optional[str]) -> list[tuple[str, float, int, int]]:
    if not value:
        return []

    parsed: list[tuple[str, float, int, int]] = []

    for index, chunk in enumerate(value.split(',')):
        part = chunk.strip()

        if not part:
            continue

        media_type, *parameters = [item.strip() for item in part.split(';')]
        quality = 1.0

        for parameter in parameters:
            if not parameter.startswith('q='):
                continue

            try:
                quality = float(parameter[2:])

            except ValueError:
                quality = 0.0

        specificity = 0

        if media_type == '*/*':
            specificity = 0

        elif media_type.endswith('/*'):
            specificity = 1

        else:
            specificity = 2

        parsed.append((media_type.lower(), quality, specificity, index))

    return parsed

class HTTPException(Exception):    
    def __init__(
        self,
        status: int = 500,
        title: str | None = None,
        code: str | None = None,
        details: str = None,
        headers: Optional[dict[str, str]] = None,
        *,
        request_id: str | None = None,
        fields: Optional[list[dict[str, Any]]] = None,
        meta: Optional[dict[str, Any]] = None,
        body: Optional[dict[str, Any]] = None
    ):
        self.status = status
        self.code = code or title or self.__default_code(status)
        self.title = self.code
        self.details = details or ''
        self.headers = headers or {}
        self.request_id = request_id
        self.fields = fields or []
        self.meta = meta or {}
        self.body = body
        self.timestamp = datetime.now(timezone.utc).isoformat()
        
        self.response = self.to_response()

    @staticmethod
    def __default_code(status: int) -> str:
        try:
            return HTTPStatus(status).phrase.upper().replace(' ', '_').replace('-', '_')

        except ValueError:
            return 'ERROR'

    def __headers(self, request: Optional[Any] = None) -> dict[str, str]:
        headers = dict(self.headers)
        request_id = self.request_id or getattr(request, 'request_id', None)

        if request_id is not None:
            headers.setdefault('X-Request-ID', str(request_id))

        return headers

    def __body(self, request: Optional[Any] = None) -> dict[str, Any]:
        if self.body is not None:
            payload = dict(self.body)
        else:
            payload = {
                'code'      : self.code,
                'details'   : self.details,
                'timestamp' : self.timestamp
            }

            if self.fields:
                payload['fields'] = self.fields

        request_id = self.request_id or getattr(request, 'request_id', None)

        if request_id is not None:
            payload.setdefault('request_id', str(request_id))

        if self.meta:
            payload.setdefault('meta', self.meta)

        return payload

    def __render_html_response(self, request: Optional[Any] = None) -> HTMLResponse:
        template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'error.html'
        error_template = template_path.read_text(encoding = 'utf-8')

        html = error_template.format(
            status = self.status,
            title = self.title,
            details = self.details
        )

        return HTMLResponse(
            html, 
            status = self.status, 
            headers = self.__headers(request)
        )

    def __render_json_response(self, request: Optional[Any] = None) -> JSONResponse:
        return JSONResponse(
            self.__body(request),
            status = self.status,
            headers = self.__headers(request)
        )

    def prefers_html(self, request: Optional[Any] = None) -> bool:
        if request is None or not hasattr(request, 'header'):
            return False

        accepted = _parse_accept_header(request.header('accept'))

        if not accepted:
            return False

        best_html: Optional[tuple[float, int, int]] = None
        best_json: Optional[tuple[float, int, int]] = None

        for media_type, quality, specificity, index in accepted:
            if quality <= 0:
                continue

            candidate = (quality, specificity, -index)

            if media_type in ('text/html', 'application/xhtml+xml'):
                if best_html is None or candidate > best_html:
                    best_html = candidate

            if media_type == 'application/json':
                if best_json is None or candidate > best_json:
                    best_json = candidate

        if best_html is None:
            return False

        if best_json is None:
            return True

        return best_html > best_json

    def to_response(self, request: Optional[Any] = None) -> Response:
        if self.prefers_html(request):
            return self.__render_html_response(request)

        return self.__render_json_response(request)
