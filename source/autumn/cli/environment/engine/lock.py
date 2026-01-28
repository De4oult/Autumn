from __future__ import annotations

import re
from typing import Dict, List, Sequence, Tuple

from autumn.cli.environment.engine.models import EnvironmentConfig, LockFile, LockGroup, LockedRequirement, Artifact
from autumn.cli.environment.engine.pip import PipClient, RequirementsBuilder, PipIndexes
from autumn.cli.environment.engine.paths import AutumnPaths
from autumn.cli.environment.engine.venv import VenvManager, PythonVersion


_FREEZE_PIN_RE = re.compile(r'^([A-Za-z0-9_.-]+)==(.+)$')


def _normalize_name(name: str) -> str:
    return name.strip().lower().replace('_', '-')

def _normalize_requested(req: str) -> str:
    return re.sub(r'\s+', '', req.strip())

def _parse_freeze_line(line: str) -> LockedRequirement:
    raw = line.strip()

    if raw.startswith('-e '):
        return LockedRequirement(
            name     = _infer_name_from_direct(raw) or raw, 
            version  = 'editable', 
            raw      = raw, 
            editable = True
        )

    match = _FREEZE_PIN_RE.match(raw)

    if match:
        return LockedRequirement(
            name     = _normalize_name(match.group(1)), 
            version  = match.group(2), 
            raw      = raw, 
            editable = False
        )

    if '@' in raw and '://' in raw:
        parts = raw.split('@', 1)
        name  = _normalize_name(parts[0].strip())
    
        return LockedRequirement(
            name     = name or raw, 
            version  = 'direct', 
            raw      = raw, 
            editable = False
        )

    return LockedRequirement(
        name     = _infer_name_from_direct(raw) or raw, 
        version  = 'direct', 
        raw      = raw, 
        editable = False
    )


def _infer_name_from_direct(raw: str) -> str | None:
    match = re.search(r'(?:#|&|\?)egg=([^&]+)', raw)
    
    if match:
        return _normalize_name(match.group(1))
    
    return None

IGNORE = {"pip", "setuptools", "wheel"}

class LockBuilder:
    def __init__(self, requirements_builder: RequirementsBuilder) -> None:
        self.requirements_builder = requirements_builder

    def build_group_lock(
        self,
        config: EnvironmentConfig,
        group: str,
        indexes: PipIndexes,
        paths: AutumnPaths, 
        env_name: str, 
        python_version: str
    ) -> LockGroup:
        temp_venv = VenvManager(paths.lock_venv_directory(env_name, group))
        temp_venv.remove()
        temp_venv.ensure()
        temp_venv.assert_python_version(PythonVersion.parse_major_minor(python_version))

        pip = PipClient(
            python_exe=temp_venv.python_exe(),
            cache_directory=paths.cache_directory / "pip-lock"
        )

        requested = self.requirements_builder.build(config, [group])
        requested_norm = sorted({ _normalize_requested(r) for r in requested if r })

        pip.install(
            requested, 
            indexes = indexes, 
            upgrade = False
        )

        freeze_lines = pip.freeze()
        resolved = [_parse_freeze_line(line) for line in freeze_lines]
        resolved = [r for r in resolved if r.name not in IGNORE]

        resolved.sort(key = lambda package: (package.name, package.version, package.raw or ''))

        direct = pip.inspect_direct_urls()

        for item in resolved:
            __direct = (
                direct.get(item.name)
                or direct.get(item.name.replace('-', '_'))
                or {}
            )
            direct_url = __direct.get("direct_url")

            if direct_url:
                url = direct_url.get("url")
                vcs = direct_url.get("vcs_info")
                dir_info = direct_url.get("dir_info")
                archive = direct_url.get("archive_info")

                if vcs and vcs.get("vcs") == "git":
                    item.source.type = "git"
                    item.source.url = url
                    item.source.ref = vcs.get("requested_revision")
                    item.source.commit_id = vcs.get("commit_id")

                elif dir_info is not None:
                    item.source.type = "path"
                    item.source.path = url

                elif archive is not None:
                    item.source.type = "url"
                    item.source.url = url

                else:
                    item.source.type = "url"
                    item.source.url = url

            else:
                item.source.type = "pypi"

            if item.source.type == "pypi":
                dest = paths.artifacts_package_directory(item.name, item.version) 
                if not dest.exists() or not any(dest.iterdir()):
                    files = pip.download_no_deps(f"{item.name}=={item.version}", dest, indexes=indexes)
                else:
                    files = [p for p in dest.iterdir() if p.is_file()]

                item.artifacts = []
                for f in files:
                    sha = pip.sha256_file(f)
                    item.artifacts.append(Artifact(
                        filename = f.name,
                        sha256   = sha,
                        size     = f.stat().st_size,
                        local_path = paths.to_relative(f),
                    ))

            # Для url: если это прямая ссылка на файл — попробуем скачать через pip download
            if item.source.type == "url" and item.source.url:
                dest = paths.artifacts_package_directory(item.name, item.version) 
                if not dest.exists() or not any(dest.iterdir()):
                    files = pip.download_no_deps(item.raw or f"{item.name} @ {item.source.url}", dest, indexes=indexes)
                else:
                    files = [p for p in dest.iterdir() if p.is_file()]

                item.artifacts = []
                for f in files:
                    sha = pip.sha256_file(f)
                    item.artifacts.append(Artifact(
                        filename = f.name,
                        sha256   = sha,
                        size     = f.stat().st_size,
                        local_path = paths.to_relative(f),
                        url = item.source.url
                    ))

        return LockGroup(
            requested = requested_norm, 
            resolved  = resolved
        )

    def merge_groups(
        self,
        base: LockFile,
        updates: Dict[str, LockGroup],
    ) -> LockFile:
        groups = dict(base.groups or {})
        groups.update(updates)
        
        base.groups = groups

        return base

    def _is_hashable_locked(item: LockedRequirement) -> bool:
        if item.editable:
            return False
        
        if item.source.type in ('git', 'path'):
            return False
        
        if item.source.type == 'url':
            return len(item.artifacts) > 0
        
        if item.source.type == 'pypi':
            return len(item.artifacts) > 0
        
        return False
