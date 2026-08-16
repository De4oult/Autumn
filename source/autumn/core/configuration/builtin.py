from typing import Any, Callable, Union, List, Tuple, Optional

from autumn.core.configuration.configuration import Configuration
from autumn.core.environment import Environment, Theme
from autumn.core.resources import Resources

class CORSConfiguration(Configuration):
    __autumn_builtin_config__ = True

    enabled: bool = True

    allowed_origins: Union[List[str], Tuple[str, ...]] = ()
    allowed_methods: Union[List[str], Tuple[str, ...]] = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS')
    allowed_headers: Union[List[str], Tuple[str, ...]] = ()

    allow_credentials: bool = False
    expose_headers: Union[List[str], Tuple[str, ...]] = ()
    max_age: int = 600

class ApplicationConfiguration(Configuration):
    __autumn_builtin_config__ = True

    name: str = 'Autumn API'
    version: str = 'v0.1.0'
    description: Optional[str] = None
    environment: Environment = Environment.LOCAL

    host: str = '127.0.0.1'
    port: int = 8000

    url: Optional[str] = None
    
    workers: int = 1
    log_level: str = 'info'

    # One mebibyte by default. Set to None to explicitly allow unbounded bodies.
    max_request_body_bytes: Optional[int] = 1024 * 1024

class SecurityConfiguration(Configuration):
    __autumn_builtin_config__ = True

    schemes: Tuple[Any, ...] = ()
    fallback_authenticated: bool = False

class LocalizationConfiguration(Configuration):
    __autumn_builtin_config__ = True

    supported_locales: Tuple[str, ...] = ('en',)
    default_locale: str = 'en'
    source_header: str = 'Accept-Language'
    locales: Resources = Resources('resources/locales')
    plural_rules: dict[str, Callable[[int | float], str]] = {}

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
    allowed_on: Tuple[Environment, ...] = (Environment.LOCAL, Environment.DEVELOPMENT)
