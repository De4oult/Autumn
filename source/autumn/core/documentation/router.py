from autumn.core.response import HTMLResponse, JSONResponse
from autumn.core.documentation.openapi import OpenAPIGenerator

from pathlib import Path

def dependencies_json_route(app):
    async def handler(request):
        from autumn.core.documentation.dependencies import DependenciesDocumentationGenerator
        
        return JSONResponse(
            DependenciesDocumentationGenerator().generate(app),
            status = 200
        )
    
    return handler

def openapi_json_route(app):
    generator = OpenAPIGenerator(title = app.name, version = app.version)

    async def openapi_json(request):
        schema = generator.generate(app)
        return JSONResponse(schema)
    
    return openapi_json

async def dependencies_route(request):
    template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'documentation' / 'dependencies.html'

    return HTMLResponse(
        template_path.read_text(encoding = 'utf-8'), 
        status = 200
    )

async def documentation_route(request):
    template_path: Path = Path(__file__).resolve().parents[2] / 'templates' / 'documentation' / 'openapi.html'

    return HTMLResponse(
        template_path.read_text(encoding = 'utf-8'), 
        status = 200
    )
