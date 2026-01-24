from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen = True)
class AutumnPaths:
    project_root: Path

    @property
    def autumn_directory(self) -> Path:
        return self.project_root / '.autumn'

    @property
    def environments_directory(self) -> Path:
        return self.autumn_dir / 'environments'

    @property
    def venvs_directory(self) -> Path:
        return self.autumn_dir / 'venvs'

    @property
    def cache_directory(self) -> Path:
        return self.autumn_dir / 'cache'

    @property
    def schemas_directory(self) -> Path:
        return self.autumn_dir / 'schemas'

    @property
    def active_env_file(self) -> Path:
        return self.autumn_dir / 'active_env'

    def environment_json_path(self, environment_name: str) -> Path:
        return self.environments_dir / f'{environment_name}.json'

    def lock_json_path(self, environment_name: str) -> Path:
        return self.environments_dir / f'{environment_name}.lock.json'

    def venv_directory(self, environment_name: str) -> Path:
        return self.venvs_dir / environment_name

    def dotenv_env_file(self, environment_name: str) -> Path:
        return self.project_root / f'.env.{environment_name}'

    def dotenv_default_file(self) -> Path:
        return self.project_root / '.env'
