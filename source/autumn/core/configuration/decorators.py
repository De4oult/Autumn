from autumn.core.configuration.source import YamlFileSource, JsonFileSource, EnvironmentSource
from autumn.core.configuration.errors import AutumnConfigSourceError
from autumn.core.configuration.configuration import Configuration

from pathlib import Path
from typing import Type


def yaml(path: str):
    filepath: Path = Path(path)

    if not filepath.suffix:
        yaml_path = filepath.with_suffix('.yaml')
        yml_path = filepath.with_suffix('.yml')

        if yaml_path.exists():
            filepath = yaml_path

        elif yml_path.exists():
            filepath = yml_path

        else:
            raise AutumnConfigSourceError(
                f'File not found: {filepath}'
            )

    def decorator(cls: Type[Configuration]):
        cls.__config_sources__.append(
            YamlFileSource(
                name     = f'yaml:{filepath.stem}', 
                filepath = filepath
            )
        )
        return cls
    
    return decorator

def json(path: str):
    filepath: Path = Path(path)

    if not filepath.suffix:
        json_path = filepath.with_suffix('.json')

        if json_path.exists():
            filepath = json_path

        else:
            raise AutumnConfigSourceError(
                f'File not found: {filepath}'
            )

    def decorator(cls: Type[Configuration]):
        cls.__config_sources__.append(
            JsonFileSource(
                name     = f'json:{filepath.stem}', 
                filepath = filepath
            )
        )
        return cls
    
    return decorator

def env(prefix: str = ''):
    def decorator(cls: Type[Configuration]):
        cls.__config_sources__.append(
            EnvironmentSource(
                prefix = prefix
            )
        )
        return cls
    
    return decorator