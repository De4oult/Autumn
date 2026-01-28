from autumn.core.configuration.casting import deep_get, MISSING
from autumn.core.configuration.errors import AutumnConfigSourceError

from dataclasses import dataclass
from typing import Any, Dict, Optional, List
import json
import os

class ConfigurationSource:
    name: str

    def get(self, path: str) -> Any:
        raise NotImplementedError

@dataclass(slots = True)
class DictionarySource(ConfigurationSource):
    name: str
    data: Dict[str, Any]

    def get(self, path: str) -> Any:
        return deep_get(self.data, path)

@dataclass(slots = True)
class JsonFileSource(ConfigurationSource):
    name: str
    filepath: str
    data: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        if self.data is not None:
            return self.data
        
        with open(self.filepath, 'r', encoding = 'utf-8') as file:
            return json.load(file)

    def get(self, path: str) -> Any:
        return deep_get(self.load(), path)

@dataclass(slots = True)
class YamlFileSource(ConfigurationSource):
    name: str
    filepath: str
    data: Optional[Dict[str, Any]] = None

    def load(self) -> Dict[str, Any]:
        if self.data is not None:
            return self.data
        
        try:
            import yaml

        except Exception as error:
            raise AutumnConfigSourceError(
                'PyYAML is required for @yaml(...)'
            ) from error

        with open(self.filepath, 'r', encoding = 'utf-8') as file:
            return yaml.safe_load(file) or {}

    def get(self, path: str) -> Any:
        return deep_get(self.load(), path)

@dataclass(slots = True)
class EnvironmentSource(ConfigurationSource):
    name: str = 'env'
    prefix: str = ''

    def get(self, path: str) -> Any:
        key = path.replace('.', '_').upper()

        if self.prefix:
            key = self.prefix + key
        
        if key not in os.environ:
            return MISSING
        
        return os.environ[key]

@dataclass(slots = True)
class SourceChain(ConfigurationSource):
    name: str
    sources: List[ConfigurationSource]

    def get(self, path: str) -> Any:
        for source in reversed(self.sources):
            value = source.get(path)

            if value is not MISSING:
                return value
            
        return MISSING