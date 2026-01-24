from __future__ import annotations

from autumn.cli.environment.engine.models import (
    DependencySpec,
    EnvironmentConfig,
    GitDependency,
    PathDependency,
    UrlDependency,
    VersionDependency
)

from dataclasses import dataclass
from pathlib import Path
from typing import List, Sequence

import subprocess

class RequirementsBuilder:
    def build(self, config: EnvironmentConfig, groups: Sequence[str]) -> List[str]:
        requirements: List[str] = []

        for group in groups:
            items = config.dependencies.get(group, {})

            for name, spec in items.items():
                requirements.append(self.__to_pip_requirement(name, spec))

        return requirements

    def __to_pip_requirement(self, name: str, spec: DependencySpec) -> str:
        if isinstance(spec, str):
            return f'{name}{spec}'.replace(' ', '')

        if isinstance(spec, VersionDependency):
            extras = f'[{','.join(spec.extras)}]' if spec.extras else ''
            return f'{name}{extras}{spec.version}'.replace(' ', '')

        if isinstance(spec, GitDependency):
            extras = f'[{','.join(spec.extras)}]' if spec.extras else ''
            ref = f'@{spec.ref}' if spec.ref else ''
            subdir = f'#subdirectory={spec.subdirectory}' if spec.subdirectory else ''

            return f'{name}{extras} @ git+{spec.url}{ref}{subdir}'

        if isinstance(spec, UrlDependency):
            return f'{name} @ {spec.url}'

        if isinstance(spec, PathDependency):
            extras = f'[{','.join(spec.extras)}]' if spec.extras else ''
            editable = '-e ' if spec.editable else ''
            
            if spec.editable:
                return f'-e {spec.path}'
            
            return f'{editable}{spec.path}'

        raise TypeError(f'Unsupported dependency spec for {name}: {spec!r}')


@dataclass(frozen = True)
class PipIndexes:
    index_url: str
    extra_index_urls: List[str]
    trusted_hosts: List[str]

class PipClient:
    def __init__(self, python_exe: Path, cache_directory: Path) -> None:
        self.python_exe = python_exe
        self.cache_directory = cache_directory

    def install(
        self,
        requirements: List[str],
        indexes: PipIndexes,
        *,
        upgrade: bool = False,
    ) -> None:
        self.cache_directory.mkdir(parents = True, exist_ok = True)

        cmd = [
            str(self.python_exe),
            '-m',
            'pip',
            'install',
            '--cache-dir',
            str(self.cache_dir)
        ]
        if upgrade:
            cmd.append('--upgrade')

        cmd += ['--index-url', indexes.index_url]

        for extra_index in indexes.extra_index_urls:
            cmd += ['--extra-index-url', extra_index]

        for host in indexes.trusted_hosts:
            cmd += ['--trusted-host', host]

        cmd += requirements

        subprocess.check_call(cmd)