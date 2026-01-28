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
    _line_re = re.compile(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$')

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

        loaded, parse_warnings = self.__parse(used)
        warnings.extend(parse_warnings)

        for key, value in loaded.items():
            if key not in os.environ:
                os.environ[key] = value

        return DotenvResult(
            used_file = used, 
            loaded = loaded, 
            warnings = warnings
        )

    def __strip_inline_comment(self, value: str) -> str:
        # срезаем комментарий только если не внутри кавычек
        in_s = False
        in_d = False
        out = []
        for ch in value:
            if ch == "'" and not in_d:
                in_s = not in_s
            elif ch == '"' and not in_s:
                in_d = not in_d
            if ch == '#' and not in_s and not in_d:
                break
            out.append(ch)
        return "".join(out).rstrip()

    def __parse(self, path: Path) -> tuple[Dict[str, str], List[str]]:
        out: Dict[str, str] = {}
        warnings: List[str] = []

        for idx, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            line = raw.strip()
            if not line or line.startswith('#'):
                continue

            match = self._line_re.match(raw)
            if not match:
                warnings.append(f'{path.name}:{idx}: cannot parse line: {raw!r}')
                continue

            key = match.group(1)
            value = match.group(2).strip()
            value = self.__strip_inline_comment(value).strip()

            if (value.startswith("'") and value.endswith("'")) or (value.startswith('"') and value.endswith('"')):
                value = value[1:-1]

            out[key] = value

        return out, warnings
