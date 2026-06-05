from autumn.core.response.response import HTMLResponse, JSONResponse, FileResponse
from autumn.core.documentation.openapi import OpenAPIGenerator
from autumn.core.response.exception import HTTPException

from pathlib import Path
import json

NO_CACHE_HEADERS = {
    'Cache-Control' : 'no-store, no-cache, must-revalidate, max-age=0',
    'Pragma'        : 'no-cache',
    'Expires'       : '0'
}

async def favicon_route():
    favicon_path: Path = Path(__file__).resolve().parents[2] / 'public' / 'autumn.svg'

    return FileResponse(favicon_path, content_type = 'image/svg+xml')

def dependencies_json_route(app):
    async def handler(request):
        if not app.is_webui_allowed():
            raise HTTPException(status = 404, details = f'Route {request.path} not found')

        from autumn.core.documentation.dependencies import DependenciesDocumentationGenerator
        
        return JSONResponse(
            DependenciesDocumentationGenerator().generate(app),
            status = 200,
            headers = NO_CACHE_HEADERS
        )
    
    return handler

def openapi_json_route(app):
    async def openapi_json(request):
        if not app.is_webui_allowed():
            raise HTTPException(status = 404, details = f'Route {request.path} not found')

        generator = OpenAPIGenerator(title = app.name, version = app.version)
        schema = generator.generate(app)
        return JSONResponse(schema, headers = NO_CACHE_HEADERS)
    
    return openapi_json

def _render_autumn_web_template(template: str, configuration) -> str:
    from autumn import __version__ as package_version

    default_theme = getattr(configuration.default_theme, 'value', configuration.default_theme)
    default_theme = str(default_theme or 'dark').strip().lower()

    if default_theme not in ('light', 'dark'):
        default_theme = 'dark'

    payload = {
        'leavesAnimationEnabled': bool(configuration.leaves_animation_enabled),
        'defaultTheme': default_theme,
        'packageVersion': package_version
    }

    initial_script = (
        '<script>'
        f'window.__AUTUMN_WEBUI_CONFIGURATION__={json.dumps(payload, separators = (",", ":"))};'
        '</script>'
    )

    return template.replace('</head>', f'{initial_script}</head>', 1)

def autumn_web_route(app):
    async def handler(request):
        if not app.is_webui_allowed():
            raise HTTPException(status = 404, details = f'Route {request.path} not found')

        template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'autumn.html'
        template = template_path.read_text(encoding = 'utf-8')

        return HTMLResponse(
            _render_autumn_web_template(template, app.webui_configuration),
            status = 200,
            headers = NO_CACHE_HEADERS
        )

    return handler
