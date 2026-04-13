from autumn.core.response.response import HTMLResponse, JSONResponse, Response
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
    def __init__(self, status: int = 500, title: str | None = None, details: str = None):
        titles: dict[int, str] = {
            # 200 : 'You\'re still here, and the leaves are whispering yes',
            # 201 : 'Something new was born in this silence',
            # 204 : 'Just silence, and nothing more.',

            # 301 : 'I\'m gone forever, but you\'ll find me there',
            # 302 : 'The path has changed, but the autumn is the same',

            400 : 'The leaf fell off before the wind realized',
            401 : 'The smell of a campfire, but the door is still locked',
            403 : 'The path is blocked, but you knew it in advance',
            404 : 'There is no house or trace through the fog',
            408 : 'The answer did not come with the last light',
            418 : 'I\'m Autumn, not Spring',
            429 : 'Autumn is not in a hurry, and you don\'t have to',

            500 : 'The forest did not respond — even the echo was silent',
            502 : 'The winds brought fragments of other people\'s words',
            503 : 'The house is closed until spring',
            504 : 'The expectation disappeared into the damp air'
        }

        self.status = status
        self.title = title if title else titles.get(self.status, 'Something')
        self.details = details or ''
        
        self.response = self.to_response()

    def __render_html_response(self) -> HTMLResponse:
        template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'error.html'
        error_template = template_path.read_text(encoding = 'utf-8')

        html = error_template.format(
            status = self.status,
            title = self.title,
            details = self.details
        )

        return HTMLResponse(html, status = self.status)

    def __render_json_response(self) -> JSONResponse:
        return JSONResponse({
            'status'  : self.status,
            'title'   : self.title,
            'details' : self.details
        }, status = self.status)

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
            return self.__render_html_response()

        return self.__render_json_response()
