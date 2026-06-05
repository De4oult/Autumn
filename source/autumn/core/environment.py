from enum import Enum

class Environment(str, Enum):
    LOCAL = 'local'
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'

class Theme(str, Enum):
    LIGHT = 'light'
    DARK = 'dark'
