from __future__ import annotations

from autumn.cli.environment.engine.models import EnvironmentConfig
from pathlib import Path
from typing import List, Optional

import json

class EnvironmentRepository:
    def __init__(self, environments_directory: Path) -> None:
        self.environments_directory = environments_directory

    def list_names(self) -> List[str]:
        if not self.environments_directory.exists():
            return []
        
        return sorted([p.stem for p in self.environments_directory.glob('*.json') if not p.name.endswith('.lock.json')])

    def exists(self, env_name: str) -> bool:
        return (self.environments_directory / f'{env_name}.json').exists()

    def read(self, env_path: Path) -> EnvironmentConfig:
        data = json.loads(env_path.read_text(encoding = 'utf-8'))
        return EnvironmentConfig.model_validate(data)

    def write(self, env_path: Path, config: EnvironmentConfig) -> None:
        env_path.parent.mkdir(parents = True, exist_ok = True)
        env_path.write_text(
            config.model_dump_json(indent = 4, exclude_none = True),
            encoding = 'utf-8'
        )

    def delete(self, env_path: Path) -> None:
        if env_path.exists():
            env_path.unlink()


class ActiveEnvironmentRepository:
    def __init__(self, active_env_file: Path) -> None:
        self.active_env_file = active_env_file

    def get(self) -> Optional[str]:
        if not self.active_env_file.exists():
            return None
        
        name = self.active_env_file.read_text(encoding = 'utf-8').strip()

        return name or None

    def set(self, env_name: str) -> None:
        self.active_env_file.parent.mkdir(parents = True, exist_ok = True)
        self.active_env_file.write_text(env_name, encoding = 'utf-8')
