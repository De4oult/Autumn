from enum import Enum

class Scope(str, Enum):
    APP     = 'app'
    REQUEST = 'request'
    TRANSIENT = 'transient'