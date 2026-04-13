from autumn.core.response import HTMLResponse, JSONResponse, FileResponse
from autumn.core.documentation.openapi import OpenAPIGenerator

from pathlib import Path

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
        from autumn.core.documentation.dependencies import DependenciesDocumentationGenerator
        
        return JSONResponse(
            DependenciesDocumentationGenerator().generate(app),
            status = 200,
            headers = NO_CACHE_HEADERS
        )
    
    return handler

def openapi_json_route(app):
    generator = OpenAPIGenerator(title = app.name, version = app.version)

    async def openapi_json(request):
        schema = generator.generate(app)
        return JSONResponse(schema, headers = NO_CACHE_HEADERS)
    
    return openapi_json

async def autumn_web_route(request):    
    template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'autumn.html'

    return HTMLResponse(
            template_path.read_text(encoding = 'utf-8'), 
            status = 200,
            headers = NO_CACHE_HEADERS
        )
