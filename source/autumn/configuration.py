from typing import Callable

from .core.configuration.configuration import Configuration
from .core.configuration.maple import Maple
from .core.configuration.builtin import (
    ApplicationConfiguration,
    CORSConfiguration,
    WebsocketConfiguration
)
from .core.configuration.decorators import (
    env, 
    json, 
    yaml
)

class __SourceNamespace:
    env:  Callable = staticmethod(env)
    json: Callable = staticmethod(json)
    yaml: Callable = staticmethod(yaml)

source = __SourceNamespace()

__all__ = (
    'Configuration',

    # Config source
    'source',

    # Config source keys
    'Maple',

    # Built-in configs
    'ApplicationConfiguration',
    'CORSConfiguration',
    'WebsocketConfiguration'
)
