from autumn.core.response import HTMLResponse
from pathlib import Path

class HTTPException(Exception):    
    def __init__(self, status_code: int = 500, title: str | None = None, details: str = None):
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

        self.status_code = status_code
        self.title = title if title else titles.get(status_code, 'Something')
        self.details = details or ''
        
        self.response = self.__render_response()

    def __render_response(self) -> HTMLResponse:
        template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'error.html'
        error_template = template_path.read_text(encoding = 'utf-8')

        html = error_template.format(
            status_code = self.status_code,
            title = self.title,
            details = self.details
        )

        return HTMLResponse(html, status = self.status_code)