from typing import List, Optional

from autumn.core.configuration.configuration import Configuration
from autumn.core.environment import Environment, Theme

class CORSConfiguration(Configuration):
    __autumn_builtin_config__ = True

    enabled: bool = True

    allowed_origins: List[str] = []
    allowed_methods: List[str] = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']
    allowed_headers: List[str] = []

    allow_credentials: bool = False
    expose_headers: List[str] = []
    max_age: int = 600

class ApplicationConfiguration(Configuration):
    __autumn_builtin_config__ = True

    name: str = 'Autumn API'
    version: str = 'v0.1.0'
    description: Optional[str] = None

    host: str = '127.0.0.1'
    port: int = 8000

    url: Optional[str] = None
    
    workers: int = 1
    log_level: str = 'info'

class WebsocketConfiguration(Configuration):
    __autumn_builtin_config__ = True

    enabled: bool = True

    ping_interval: int = 20
    ping_timeout: int = 20

    max_message_size: int = 1048576

class WebUIConfiguration(Configuration):
    __autumn_builtin_config__ = True

    enabled: bool = True
    leaves_animation_enabled: bool = True
    default_theme: Theme = Theme.DARK
    allowed_on: tuple[Environment, ...] = (Environment.DEVELOPMENT,)
