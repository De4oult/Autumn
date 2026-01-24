from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class EnvironmentType(str, Enum):
    LOCAL = 'local'
    DEVELOPMENT = 'development'
    STAGING = 'staging'
    PRODUCTION = 'production'


class PythonConfig(BaseModel):
    version: str = Field(..., description='Major.minor, e.g. 3.12')

class IndexesConfig(BaseModel):
    index_url: str = Field('https://pypi.org/simple')
    extra_index_urls: List[str] = Field(default_factory = list)
    trusted_hosts: List[str] = Field(default_factory = list)


class ApplicationConfig(BaseModel):
    name: str
    module: str = Field(..., description = 'ASGI app entrypoint, e.g. my_app.main:app')
    version: str = '0.1.0'


class ServerConfig(BaseModel):
    host: str = '127.0.0.1'
    port: int = 8000
    reload: bool = False
    workers: int = 1


# ---- Dependency specs ----
class VersionDependency(BaseModel):
    type: Literal['version'] = 'version'
    version: str = Field(..., description = 'PEP 440 spec, e.g. >=1,<2')
    extras: List[str] = Field(default_factory = list)

class GitDependency(BaseModel):
    type: Literal['git'] = 'git'
    url: str
    ref: Optional[str] = None
    subdirectory: Optional[str] = None
    extras: List[str] = Field(default_factory = list)

class UrlDependency(BaseModel):
    type: Literal['url'] = 'url'
    url: str
    hash: Optional[str] = Field(default = None, description = 'sha256:...')

class PathDependency(BaseModel):
    type: Literal['path'] = 'path'
    path: str
    editable: bool = False
    extras: List[str] = Field(default_factory = list)


DependencySpec = Union[str, VersionDependency, GitDependency, UrlDependency, PathDependency]
DependencyGroups = Dict[str, Dict[str, DependencySpec]]

class EnvironmentConfig(BaseModel):
    format_version: int = 1

    name: str
    type: EnvironmentType

    python: PythonConfig
    indexes: IndexesConfig = Field(default_factory = IndexesConfig)

    app: ApplicationConfig
    server: ServerConfig = Field(default_factory = ServerConfig)

    dependencies: DependencyGroups = Field(default_factory = lambda: { 'default': {}, 'dev': {} })
    plugins: Dict[str, Any] = Field(default_factory = dict)

    @field_validator('name')
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Environment name cannot be empty.')
        
        for character in value:
            if not (character.isalnum() or character in ('-', '_')):
                raise ValueError('Environment name must be [a-zA-Z0-9_-].')
            
        return value

    @field_validator('dependencies')
    @classmethod
    def ensure_default_groups(cls, value: DependencyGroups) -> DependencyGroups:
        value = dict(value or {})
        value.setdefault('default', {})
        value.setdefault('dev', {})
        
        return value
