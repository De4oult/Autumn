from typing import List, Optional

from autumn.core.configuration.configuration import Configuration
from autumn.core.configuration.maple import Maple


class CORSConfiguration(Configuration):
    enabled: bool = True

    allowed_origins: List[str] = ['']
    allowed_methods: List[str] = ['']
    allowed_headers: List[str] = ['']

    allow_credentials: bool = False
    expose_headers: List[str] = []
    max_age: int = 600

class ApplicationConfiguration(Configuration):
    name: Optional[str]

    host: str = '127.0.0.1'
    port: int = 8000

    url: Optional[str] = None
    
    workers: int = 1
    log_level: str = 'info'

class WebsocketConfiguration(Configuration):
    enabled: bool = True

    ping_interval: int = 20
    ping_timeout: int = 20

    max_message_size: int = 1048576