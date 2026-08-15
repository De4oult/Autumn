from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any

import json


class ResourceType(Enum):
    TEXT = 'text'
    BYTES = 'bytes'
    DATA = 'data'


class Resources:
    __instances: dict[Path, 'Resources'] = {}

    def __new__(cls, root: str | Path):
        key = Path(root).resolve(strict = False)

        if key not in cls.__instances:
            cls.__instances[key] = super().__new__(cls)

        return cls.__instances[key]

    def __init__(self, root: str | Path) -> None:
        if hasattr(self, 'root'):
            return

        self.root = Path(root).resolve(strict = False)
        self.__cache: dict[Path, Any] = {}

    def resolve(self, path: str | Path, *, must_exist: bool = True) -> Path:
        root = self.root.resolve(strict = False)
        requested = Path(path)
        candidate = (
            requested
            if requested.is_absolute()
            else root / requested
        ).resolve(strict = must_exist)

        if not candidate.is_relative_to(root):
            raise PermissionError(f'Resource path escapes root: {path}')

        return candidate

    def exists(self, path: str | Path) -> bool:
        try:
            return self.resolve(path).exists()

        except (FileNotFoundError, PermissionError):
            return False

    def read(
        self,
        path: str | Path,
        type: ResourceType = ResourceType.TEXT,
        *,
        encoding: str = 'utf-8'
    ) -> Any:
        if type == ResourceType.TEXT:
            return self.__read_text(path, encoding = encoding)

        if type == ResourceType.BYTES:
            return self.__read_bytes(path)

        if type == ResourceType.DATA:
            return self.__read_data(path)

        raise ValueError(f'Unsupported resource type: {type!r}')

    def __read_bytes(self, path: str | Path) -> bytes:
        resolved = self.resolve(path)
        return resolved.read_bytes()

    def __read_text(self, path: str | Path, *, encoding: str = 'utf-8') -> str:
        resolved = self.resolve(path)
        return resolved.read_text(encoding = encoding)

    def __read_data(self, path: str | Path) -> Any:
        resolved = self.resolve(path)

        if resolved in self.__cache:
            return self.__cache[resolved]

        suffix = resolved.suffix.lower()

        if suffix == '.json':
            data = json.loads(resolved.read_text(encoding = 'utf-8'))

        elif suffix in ('.yaml', '.yml'):
            try:
                import yaml

            except ModuleNotFoundError as error:
                raise RuntimeError('PyYAML is required to read YAML resources') from error

            data = yaml.safe_load(resolved.read_text(encoding = 'utf-8')) or {}

        else:
            raise ValueError(f'Unsupported resource format: {resolved.suffix}')

        self.__cache[resolved] = data
        return data

    def response(self, path: str | Path, **kwargs):
        from autumn.core.response.response import FileResponse

        return FileResponse.from_root(self.root, path, **kwargs)

    def stream(self, path: str | Path, **kwargs):
        from autumn.core.response.response import StreamFileResponse

        return StreamFileResponse(self.resolve(path), **kwargs)

    def find(self, stem: str) -> Path | None:
        for suffix in ('.json', '.yaml', '.yml'):
            try:
                candidate = self.resolve(f'{stem}{suffix}')

            except FileNotFoundError:
                continue

            if candidate.is_file():
                return candidate

        return None
