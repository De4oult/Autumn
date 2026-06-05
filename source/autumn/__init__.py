from importlib.metadata import PackageNotFoundError, version as __version

try:
    __version__ = __version('autumn-framework')

except PackageNotFoundError:
    __version__ = '0.1.0'


from .core.app import Autumn
from .core.environment import Environment, Theme, only
from .core.request.request import Request
from .core.dependencies.decorators import (
    leaf,
    service
)
from .core.lifecycle.decorators import (
    middleware,
    shutdown,
    startup
)
from .core.serialization import (
    Public,
    Private,
    serializable
)

__all__ = (
    'Autumn', 
    'Environment',
    'Theme',
    'only',
    'Request',

    # Dependency Injection
    'leaf',
    'service',

    # Lifecycle
    'middleware',
    'shutdown',
    'startup',

    # Serialization
    'Public',
    'Private',
    'serializable',
)
