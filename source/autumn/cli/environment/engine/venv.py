from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import subprocess
import venv

@dataclass(frozen = True)
class PythonVersion:
    major: int
    minor: int

    @classmethod
    def parse_major_minor(cls, string: str) -> 'PythonVersion':
        parts = string.strip().split('.')
        
        if len(parts) < 2:
            raise ValueError('Python version must be major.minor, e.g. 3.12')
        
        return cls(major = int(parts[0]), minor = int(parts[1]))

class VenvManager:
    def __init__(self, venv_directory: Path) -> None:
        self.venv_directory = venv_directory

    def ensure(self) -> None:
        if self.python_exe().exists():
            return
        
        self.venv_directory.mkdir(parents = True, exist_ok = True)

        builder = venv.EnvBuilder(with_pip = True, clear = False, upgrade_deps = False)
        builder.create(str(self.venv_directory))

    def remove(self) -> None:
        if self.venv_directory.exists():
            for path in sorted(self.venv_directory.rglob('*'), reverse = True):
                if path.is_file():
                    try:
                        path.unlink()

                    except OSError:
                        pass
                else:
                    try:
                        path.rmdir()
                    except OSError:
                        pass

            try:
                self.venv_directory.rmdir()

            except OSError:
                pass

    def python_exe(self) -> Path:
        return self.venv_directory / 'Scripts' / 'python.exe'

    def pip_exe(self) -> Path:
        return self.venv_directory / 'Scripts' / 'pip.exe'

    def assert_python_version(self, expected: PythonVersion) -> None:
        python = self.python_exe()

        if not python.exists():
            raise RuntimeError('Venv python not found. Ensure venv is created first.')

        out = subprocess.check_output([str(python), '-c', 'import sys; print(f\'{sys.version_info[0]}.{sys.version_info[1]}\')'])
        actual = PythonVersion.parse_major_minor(out.decode().strip())

        if (actual.major, actual.minor) != (expected.major, expected.minor):
            raise RuntimeError(f'Python version mismatch: expected {expected.major}.{expected.minor}, got {actual.major}.{actual.minor}.')
