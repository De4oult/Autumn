from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen = True, slots = True)
class FileSystem:
    def ensure_dir(self, path: Path) -> None:
        path.mkdir(
            parents  = True, 
            exist_ok = True
        )

    def exists(self, path: Path) -> bool:
        return path.exists()

    def write_text_if_missing(self, path: Path, text: str, encoding: str = 'utf-8') -> bool:
        if path.exists():
            return False
        
        self.ensure_dir(path.parent)
        path.write_text(text, encoding = encoding)
        
        return True

    def write_text(self, path: Path, text: str, encoding: str = 'utf-8') -> None:
        self.ensure_dir(path.parent)
        path.write_text(text, encoding = encoding)