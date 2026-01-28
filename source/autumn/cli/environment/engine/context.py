from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from autumn.cli.environment.engine.dotenv import DotenvLoader, DotenvResult
from autumn.cli.environment.engine.models import EnvironmentConfig
from autumn.cli.environment.engine.paths import AutumnPaths
from autumn.cli.environment.engine.repositories import ActiveEnvironmentRepository, EnvironmentRepository
from autumn.cli.environment.engine.venv import PythonVersion, VenvManager
from autumn.cli.environment.engine.pip import PipClient, PipIndexes, RequirementsBuilder

@dataclass
class EnvironmentContext:
    env_name: str
    config: EnvironmentConfig
    paths: AutumnPaths
    venv: VenvManager
    dotenv: DotenvResult

class EnvironmentContextLoader:
    def __init__(self, paths: AutumnPaths) -> None:
        self.paths = paths
        self.env_repo = EnvironmentRepository(paths.environments_directory)
        self.active_repo = ActiveEnvironmentRepository(paths.active_env_file)
        self.dotenv_loader = DotenvLoader()

    def resolve_env_name(self, explicit: Optional[str]) -> str:
        if explicit:
            return explicit
        
        active = self.active_repo.get()

        if active:
            return active
        
        if self.env_repo.exists('local'):
            return 'local'
        
        raise RuntimeError('No active environment. Create \'local\' or run: autumn use <env>')

    def load(self, env_name: str) -> EnvironmentContext:
        environment_path = self.paths.environment_json_path(env_name)

        if not environment_path.exists():
            raise RuntimeError(f'Environment config not found: {environment_path}')

        config = self.env_repo.read(environment_path)

        venv_manager = VenvManager(self.paths.venv_directory(env_name))
        venv_manager.ensure()
        venv_manager.assert_python_version(PythonVersion.parse_major_minor(config.python.version))

        dotenv = self.dotenv_loader.load_and_inject(
            env_file      = self.paths.dotenv_env_file(env_name),
            fallback_file = self.paths.dotenv_default_file(),
        )

        return EnvironmentContext(
            env_name = env_name,
            config   = config,
            paths    = self.paths,
            venv     = venv_manager,
            dotenv   = dotenv
        )

    def build_pip(self, context: EnvironmentContext) -> PipClient:
        return PipClient(
            python_exe      = context.venv.python_exe(),
            cache_directory = context.paths.cache_directory / 'pip',
        )

    def build_indexes(self, config: EnvironmentConfig) -> PipIndexes:
        return PipIndexes(
            index_url        = config.indexes.index_url,
            extra_index_urls = list(config.indexes.extra_index_urls),
            trusted_hosts    = list(config.indexes.trusted_hosts)
        )

    def build_requirements(self, config: EnvironmentConfig, groups: Sequence[str]) -> List[str]:
        return RequirementsBuilder().build(config, groups)
