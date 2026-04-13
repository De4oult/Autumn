from importlib.metadata import PackageNotFoundError, version as __version

try:
    __version__ = __version('Autumn')

except PackageNotFoundError:
    __version__ = '0.1.0'


from .core.app import Autumn
from .core.request.request import Request
from .core.dependencies.decorators import (
    leaf,
    service
)

__all__ = (
    'Autumn', 
    'Request',

    # Dependency Injection
    leaf,
    service,
)
