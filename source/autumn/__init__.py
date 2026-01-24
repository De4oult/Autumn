from importlib.metadata import PackageNotFoundError, version as __version

try:
    __version__ = __version('Autumn')
except PackageNotFoundError:
    __version__ = '0.1.0'

from .core.app import Autumn
from .core.request import (
    Request, 
    query,
    body
)
from .core.response import (
    HTMLResponse, 
    JSONResponse, 
    RedirectResponse, 
    Response, 
    XMLResponse, 
    HTTPException,
    json_response
)
from .core.routing import (
    REST, 
    get, post, put, patch, delete
)

from .core.dependencies import (
    leaf,
    service
)

from .core.documentation import (
    summary,
    description,
    tag
)

__all__ = (
    'Autumn', 
    'Request',
    'query',
    body,
    'Response', 
    'JSONResponse', 
    'HTMLResponse', 
    'RedirectResponse', 
    'XMLResponse', 
    'HTTPException',
    json_response,
    REST, 
    get, post, put, patch, delete,

    leaf,
    service,

    summary,
    description,
    tag
)