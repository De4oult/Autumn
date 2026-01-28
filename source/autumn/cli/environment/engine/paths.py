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
        return self.autumn_directory / 'environments'

    @property
    def venvs_directory(self) -> Path:
        return self.autumn_directory / 'venvs'

    @property
    def cache_directory(self) -> Path:
        return self.autumn_directory / 'cache'

    @property
    def schemas_directory(self) -> Path:
        return self.autumn_directory / 'schemas'

    @property
    def active_env_file(self) -> Path:
        return self.autumn_directory / 'active_env'

    def environment_json_path(self, environment_name: str) -> Path:
        return self.environments_directory / f'{environment_name}.json'

    def lock_json_path(self, environment_name: str) -> Path:
        return self.environments_directory / f'{environment_name}.lock.json'

    def venv_directory(self, environment_name: str) -> Path:
        return self.venvs_directory / environment_name

    def dotenv_env_file(self, environment_name: str) -> Path:
        return self.project_root / f'.env.{environment_name}'

    def dotenv_default_file(self) -> Path:
        return self.project_root / '.env'
    
    @property
    def artifacts_directory(self) -> Path:
        return self.cache_directory / 'artifacts'

    def artifacts_package_directory(self, name: str, version: str) -> Path:
        return self.artifacts_directory / name / version
    
    def to_relative(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.project_root))
        
        except ValueError:
            raise RuntimeError(
                f"Lock contains non-project artifact path: {path}"
            )

    @property
    def lock_venvs_directory(self) -> Path:
        return self.cache_directory / "lock-venvs"

    def lock_venv_directory(self, env_name: str, group: str) -> Path:
        return self.lock_venvs_directory / env_name / group
    
    def frozen_artifacts_directory(self, env_name: str) -> Path:
        return self.cache_directory / "frozen-artifacts" / env_name
