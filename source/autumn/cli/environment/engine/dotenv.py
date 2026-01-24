from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import os
import re

@dataclass
class DotenvResult:
    used_file: Optional[Path]
    loaded: Dict[str, str]
    warnings: List[str]

class DotenvLoader:
    _line_re = re.compile(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$')

    def load_and_inject(self, env_file: Path, fallback_file: Path) -> DotenvResult:
        warnings: List[str] = []
        used: Optional[Path] = None

        if env_file.exists():
            used = env_file

        elif fallback_file.exists():
            used = fallback_file
            warnings.append(f'{env_file.name} not found; using {fallback_file.name}.')

        else:
            warnings.append(f'No dotenv file found: {env_file.name} and {fallback_file.name} are missing.')
            
            return DotenvResult(
                used_file = None, 
                loaded = {}, 
                warnings = warnings
            )

        loaded = self.__parse(used)

        for key, value in loaded.items():
            if key not in os.environ:
                os.environ[key] = value

        return DotenvResult(
            used_file = used, 
            loaded = loaded, 
            warnings = warnings
        )

    def __parse(self, path: Path) -> Dict[str, str]:
        out: Dict[str, str] = {}

        for raw in path.read_text(encoding = 'utf-8').splitlines():
            line = raw.strip()

            if not line or line.startswith('#'):
                continue
            
            match = self._line_re.match(raw)

            if not match:
                continue

            key = match.group(1)
            value = match.group(2).strip()

            if (value.startswith('\'') and value.endswith('\'')) or (value.startswith('\'') and value.endswith('\'')):
                value = value[1:-1]

            out[key] = value
            
        return out
