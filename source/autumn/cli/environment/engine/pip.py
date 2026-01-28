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
from typing import List, Sequence, Optional, Iterable
from pathlib import Path

import subprocess
import hashlib
import orjson

class RequirementsBuilder:
    def build(self, config: EnvironmentConfig, groups: Sequence[str]) -> List[str]:
        requirements: List[str] = []

        for group in groups:
            items = config.dependencies.get(group, {})

            for name, spec in items.items():
                requirements.append(self.__to_pip_requirement(name, spec))

        return sorted(requirements)

    def __to_pip_requirement(self, name: str, spec: DependencySpec) -> str:
        if isinstance(spec, str):
            s = spec.strip()
            if s == '' or s == '*':
                return name
            
            return f'{name}{s}'.replace(' ', '')


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
            extras = f'[{",".join(spec.extras)}]' if spec.extras else ''

            if spec.editable:
                return f'-e {spec.path}{extras}'

            return f'{spec.path}{extras}'


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

        command = [
            str(self.python_exe),
            '-m',
            'pip',
            'install',
            '--cache-dir',
            str(self.cache_directory)
        ]
        
        if upgrade:
            command.append('--upgrade')

        command += ['--index-url', indexes.index_url]

        for extra_index in indexes.extra_index_urls:
            command += ['--extra-index-url', extra_index]

        for host in indexes.trusted_hosts:
            command += ['--trusted-host', host]

        command += requirements

        subprocess.check_call(command)

    def install_from_file(
        self,
        requirements_file: Path,
        indexes: PipIndexes | None = None,
        *,
        require_hashes: bool = False,
        no_deps: bool = False,
        no_index: bool = False,
        find_links: Optional[Iterable[Path]] = None,
    ) -> None:
        self.cache_directory.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.python_exe), "-m", "pip", "install",
            "--cache-dir", str(self.cache_directory),
            "-r", str(requirements_file),
        ]

        if no_deps:
            cmd.append("--no-deps")

        if no_index:
            cmd.append("--no-index")

        if find_links:
            for p in find_links:
                cmd += ["--find-links", str(p)]

        if require_hashes:
            cmd.append("--require-hashes")

        # indexes используются только если no_index=False
        if not no_index and indexes is not None:
            cmd += ["--index-url", indexes.index_url]
            for extra_index in indexes.extra_index_urls:
                cmd += ["--extra-index-url", extra_index]
            for host in indexes.trusted_hosts:
                cmd += ["--trusted-host", host]

        subprocess.check_call(cmd)

    def freeze(self) -> List[str]:
        out = subprocess.check_output([str(self.python_exe), '-m', 'pip', 'freeze'])

        return [line.strip() for line in out.decode('utf-8').splitlines() if line.strip()]

    def download_no_deps(
        self,
        requirement: str,
        destination_directory: Path,
        indexes: PipIndexes,
    ) -> List[Path]:
        destination_directory.mkdir(parents=True, exist_ok=True)

        cmd = [
            str(self.python_exe),
            '-m', 'pip',
            'download',
            '--no-deps',
            '--dest', str(destination_directory),
            '--index-url', indexes.index_url,
        ]

        for extra_index in indexes.extra_index_urls:
            cmd += ['--extra-index-url', extra_index]

        for host in indexes.trusted_hosts:
            cmd += ['--trusted-host', host]

        cmd.append(requirement)

        subprocess.check_call(cmd)

        return [path for path in destination_directory.iterdir() if path.is_file()]

    def sha256_file(self, path: Path) -> str:
        hash = hashlib.sha256()
        
        with path.open('rb') as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b''):
                hash.update(chunk)

        return hash.hexdigest()
    
    def inspect_direct_urls(self) -> dict:
        script = 'import importlib.metadata as md, json; print(json.dumps({(n := (d.metadata.get(\'Name\') or d.metadata.get(\'Summary\') or \'\').strip().lower().replace(\'_\', \'-\')): {\'name\': n, \'version\': d.version, \'direct_url\': (json.loads(p.read_text(encoding=\'utf-8\')) if (p := d.locate_file(\'direct_url.json\')) and p.exists() else None)} for d in md.distributions() if (d.metadata.get(\'Name\') or d.metadata.get(\'Summary\') or \'\').strip()}))'

        out = subprocess.check_output([str(self.python_exe), '-c', script])

        return orjson.loads(out.decode('utf-8'))