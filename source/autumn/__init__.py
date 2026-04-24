from importlib.metadata import PackageNotFoundError, version as __version

try:
    __version__ = __version('autumn-framework')

except PackageNotFoundError:
    __version__ = '0.1.0'


from .core.app import Autumn
from .core.request.request import Request
from .core.dependencies.decorators import (
    leaf,
    service
)
from .core.serialization import (
    Public,
    Private,
    serializable
)

__all__ = (
    'Autumn', 
    'Request',

    # Dependency Injection
    'leaf',
    'service',

    # Serialization
    'Public',
    'Private',
    'serializable',
)
