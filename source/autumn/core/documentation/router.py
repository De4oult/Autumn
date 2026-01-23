from __future__ import annotations

from autumn.core.response import HTMLResponse, JSONResponse  # поправь импорты под свои классы
from autumn.core.documentation.openapi import OpenAPIGenerator   # где у тебя лежит класс

SWAGGER_HTML = """
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8" />
    <title>Autumn Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    </head>
    <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        window.onload = () => {
        SwaggerUIBundle({
            url: '/development/openapi.json',
            dom_id: '#swagger-ui'
        });
        };
    </script>
    </body>
    </html>
""".strip()

def make_openapi_handler(app):
    generator = OpenAPIGenerator(title="Autumn API", version="0.1.0")

    async def openapi_json(request):
        schema = generator.generate(app)
        return JSONResponse(schema)  # если твой JSONResponse сам делает json.dumps
    return openapi_json

async def docs_handler(request):
    return HTMLResponse(SWAGGER_HTML)
